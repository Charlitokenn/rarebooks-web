"""The customer site's side of trial end removal (specs 0007 and 0010): its removal status, the export job,
and the hold fields.

The control site reaches these through the signed endpoints in `remote.py`. `export_job` runs on the long
queue, and `lock_job` lets it past the read only lock by name, so it can open its own snapshot transaction on
a locked site. It writes nothing to the database, only files under its own folder (spec 0010 AC-5).
"""

import csv
import hashlib
import os
import shutil
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit

import frappe
import requests
from frappe.utils import get_datetime, get_url

from frappe_books.settings import company_name
from frappe_books.subscription import clock as subscription_clock
from frappe_books.subscription.clock import DOCTYPE, SubscriptionClock, utc_now
from frappe_books.subscription.control import ControlSiteUnreachable, parse_issued_at, post_signed
from frappe_books.subscription.state import set_removal_hold

MODULE = "Frappe Books"
# The subscription itself is the platform's record, not the customer's books.
EXCLUDED_DOCTYPES = frozenset({DOCTYPE})
PAGE_SIZE = 1000
FILE_FIELDS = (
	"name",
	"file_name",
	"file_url",
	"is_private",
	"attached_to_doctype",
	"attached_to_name",
	"attached_to_field",
)
ISOLATION_LEVELS = ("READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE")
# A byte order mark, so Excel opens the CSVs as UTF-8.
CSV_ENCODING = "utf-8-sig"

# Spec 0010 AC-4: the export job.
EXPORT_FOLDER = "books-removal"
# The job needs this much time left on its upload link to start, so a slow build can't outlive it.
MIN_LINK_LEFT = timedelta(hours=2)
# Below R2's single PUT limit; a bigger site needs the operator's help.
MAX_UPLOAD_BYTES = 5_000_000_000
# A bigger site briefly needs about twice its size free while its export is built and zipped.
DISK_HEADROOM = 2
# `export_ready` answered 503 (R2 couldn't be asked) or couldn't be reached: try again this many minutes later.
READY_RETRY_MINUTES = (1, 5, 15)
EXPORT_READY = "rarebooks_control.removal.export_ready"
STEP_FAILED = "rarebooks_control.removal.step_failed"
# Connect, then read: the read waits for R2 to take the whole body.
UPLOAD_TIMEOUT = (30, 60 * 60)
ERROR_CHARACTERS = 2000
# Files that are already compressed are stored in the zip as they are.
STORED_SUFFIXES = (".gz", ".zip", ".png", ".jpg", ".jpeg", ".pdf")
OK, SERVICE_UNAVAILABLE = 200, 503


class PendingWritesError(frappe.ValidationError):
	"""`build_export` opens its own snapshot transaction, which would commit the caller's writes."""


class DiskSpaceError(Exception):
	"""Not enough free disk to build this site's export."""


class ExportStepError(Exception):
	"""A failed `export` or `upload` step, reported to the control site with `step_failed`."""

	def __init__(self, step: str, text: str):
		super().__init__(text)
		self.step, self.text = step, text


def removal_status() -> dict:
	"""What the runner reports to the control site for this site. Reads the single fresh, never the cache."""
	# Through the module, so the tests' `managed_site()` patch reaches it.
	clock = SubscriptionClock(frappe.get_doc(DOCTYPE), subscription_clock.is_managed(), utc_now())
	status = clock.status()
	return {
		"site": frappe.local.site,
		"site_url": get_url(),
		"phase": status["phase"],
		"today": status["today"],
		"removal_on": status["removal_on"],
		"kind": clock.removal_kind,
		"paid_until": status["paid_until"],
		"exempt": bool(clock.facts.exempt),
		"payment_pending": status["payment_pending"],
		"language": frappe.get_system_settings("language") or None,
		"company_name": company_name(),
		"export_sent_on": _utc_iso(clock.facts.export_sent_on),
		"removal_hold_until": _utc_iso(clock.facts.removal_hold_until),
	}


def mark_export_sent(export_sent_on: str, removal_hold_until: str):
	"""Record that the export email went out and when the hold ends (AC-8). Takes ISO UTC timestamps."""
	set_removal_hold(_naive_utc(export_sent_on), _naive_utc(removal_hold_until))


def clear_removal():
	"""Empty both hold fields, as when the site paid before the drop (AC-11). Safe when already empty."""
	set_removal_hold(None, None)


def build_export(out_dir: str) -> dict:
	"""Write the AC-6 export layout into `out_dir`: readable CSVs, uploaded files, a database dump and a README.

	Every CSV is read in one REPEATABLE READ snapshot, so the files agree with each other. Writes nothing to the
	database. Refuses to start while the caller has uncommitted writes.
	"""
	if frappe.db.transaction_writes:
		raise PendingWritesError("Commit or roll back before building an export.")

	readable = os.path.join(out_dir, "readable")
	os.makedirs(readable, exist_ok=True)
	counts = {"doctypes": 0, "rows": 0, "files": 0, "bytes": 0}

	with _snapshot():
		for doctype in _export_doctypes():
			counts["rows"] += _write_doctype(doctype, readable)
			counts["doctypes"] += 1
		counts["rows"] += _write_file_index(readable)

	counts["files"] = _copy_files(os.path.join(out_dir, "files"))
	_write_database_backup(os.path.join(out_dir, "backup", "database.sql.gz"))
	_write_readme(os.path.join(out_dir, "README.txt"))
	counts["bytes"] = _folder_size(out_dir)
	return counts


def export_job(case: str, attempt_id: str, upload_url: str, expires_at: str):
	"""Build this site's export, zip it, PUT it to the presigned `upload_url`, then tell the control site
	(spec 0010 AC-4). Any failure is reported with `step_failed`, its text cleared of every secret and of the
	upload URL. The folder is deleted in every case."""
	folder = os.path.abspath(frappe.get_site_path(EXPORT_FOLDER, case))
	scrub = _scrubber(upload_url)
	try:
		size, digest = _build_and_upload(folder, attempt_id, upload_url, expires_at)
	except ExportStepError as error:
		_report_failure(case, error.step, scrub(error.text))
		return
	finally:
		shutil.rmtree(folder, ignore_errors=True)
	_report_ready(case, attempt_id, size, digest)


def _build_and_upload(folder: str, attempt_id: str, upload_url: str, expires_at: str) -> tuple[int, str]:
	expires = parse_issued_at(expires_at)
	if not expires or expires - utc_now() < MIN_LINK_LEFT:
		raise ExportStepError("export", "link_expiring")

	shutil.rmtree(folder, ignore_errors=True)
	archive = os.path.join(folder, f"{attempt_id}.zip")
	with _failing_step("export"):
		check_disk()
		build_export(os.path.join(folder, "export"))
		zip_folder(os.path.join(folder, "export"), archive)
		size, digest = file_digest(archive)
	if size > MAX_UPLOAD_BYTES:
		raise ExportStepError("upload", "too_large")
	with _failing_step("upload"):
		upload(archive, upload_url, size)
	return size, digest


def check_disk():
	"""Free disk must exceed twice the site's database plus its uploaded files."""
	database = frappe.db.sql(
		"select coalesce(sum(data_length + index_length), 0) from information_schema.tables "
		"where table_schema = %s",
		frappe.conf.db_name,
	)[0][0]
	files = sum(_folder_size(frappe.get_site_path(part, "files")) for part in ("public", "private"))
	needed = DISK_HEADROOM * (int(database) + files)
	free = shutil.disk_usage(frappe.get_site_path()).free
	if free <= needed:
		raise DiskSpaceError(f"needs {needed} bytes free, has {free}")


def zip_folder(folder: str, archive: str):
	"""ZIP64, so a large export still opens."""
	with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as bundle:
		for root, _dirs, files in os.walk(folder):
			for name in sorted(files):
				path = os.path.join(root, name)
				kind = zipfile.ZIP_STORED if name.lower().endswith(STORED_SUFFIXES) else zipfile.ZIP_DEFLATED
				bundle.write(path, os.path.relpath(path, folder), compress_type=kind)


def file_digest(path: str) -> tuple[int, str]:
	with open(path, "rb") as handle:
		digest = hashlib.file_digest(handle, "sha256").hexdigest()
	return os.path.getsize(path), digest


def upload(archive: str, upload_url: str, size: int):
	"""One streamed PUT to the presigned URL. No redirect is followed, so the body only ever goes to R2."""
	with open(archive, "rb") as handle:
		response = requests.put(
			upload_url,
			data=handle,
			headers={"Content-Length": str(size)},
			timeout=UPLOAD_TIMEOUT,
			allow_redirects=False,
		)
	if response.status_code != OK:
		raise RuntimeError(f"upload answered HTTP {response.status_code}")


def _report_ready(case: str, attempt_id: str, size: int, digest: str):
	"""`export_ready`, tried again 1, 5 and 15 minutes later while the control site answers 503 or can't be
	reached. A 409 means the control site waits for another attempt or none: stop, and delete nothing."""
	payload = {"case": case, "attempt_id": attempt_id, "bytes": size, "sha256": digest}
	for wait in (0, *READY_RETRY_MINUTES):
		if wait:
			time.sleep(wait * 60)
		try:
			status, _answer = post_signed(EXPORT_READY, payload)
		except ControlSiteUnreachable:
			continue
		if status == SERVICE_UNAVAILABLE:
			continue
		if status != OK:
			frappe.log_error(f"Books removal: export_ready for {case} answered {status}")
		return
	# The control site's 6 hour stuck export rule takes it from here (AC-3).
	frappe.log_error(f"Books removal: export_ready for {case} was never accepted")


def _report_failure(case: str, step: str, text: str):
	try:
		post_signed(STEP_FAILED, {"case": case, "step": step, "error": text[:ERROR_CHARACTERS]})
	except ControlSiteUnreachable:
		frappe.log_error(f"Books removal: step_failed for {case} couldn't be sent", text[:ERROR_CHARACTERS])


@contextmanager
def _failing_step(step: str) -> Iterator[None]:
	try:
		yield
	except Exception as error:
		raise ExportStepError(step, f"{type(error).__name__}: {error}") from error


def _scrubber(upload_url: str) -> Callable[[str], str]:
	"""Removes the site secret, the upload URL and its signed query from error text (AC-4, AC-13)."""
	values = [upload_url, urlsplit(upload_url).query if isinstance(upload_url, str) else None]
	values.append(frappe.conf.get("books_control_secret"))
	values = [value for value in values if isinstance(value, str) and value]

	def scrub(text: str) -> str:
		for value in values:
			text = text.replace(value, "***")
		return text

	return scrub


@contextmanager
def _snapshot():
	"""One consistent, read only REPEATABLE READ transaction, rolled back at the end.

	The level is set for the session, since MariaDB refuses a next transaction level while Frappe's implicit
	transaction is open, and the session's own level is put back afterwards.
	"""
	previous = _session_isolation_level()
	if previous not in ISOLATION_LEVELS:
		previous = "REPEATABLE READ"
	frappe.db.rollback()
	frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
	frappe.db.sql("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
	try:
		yield
	finally:
		frappe.db.rollback()
		frappe.db.sql(f"SET SESSION TRANSACTION ISOLATION LEVEL {previous}")


def _session_isolation_level() -> str:
	"""The session's isolation level, such as "REPEATABLE READ".

	MariaDB 11.1 renamed `tx_isolation` to `transaction_isolation` (keeping the old name as a deprecated alias),
	so ask for both names: a bench below 11.1 has only the old one, and a later release may drop it.
	"""
	rows = frappe.db.sql(
		"show session variables where variable_name in ('transaction_isolation', 'tx_isolation')"
	)
	return rows[0][1].replace("-", " ") if rows else ""


def _export_doctypes() -> list[str]:
	names = frappe.get_all(
		"DocType", filters={"module": MODULE, "is_virtual": 0}, pluck="name", order_by="name asc"
	)
	return [name for name in names if name not in EXCLUDED_DOCTYPES]


def _write_doctype(doctype: str, folder: str) -> int:
	meta = frappe.get_meta(doctype)
	hidden = password_fields(meta)
	path = os.path.join(folder, f"{doctype}.csv")
	if meta.issingle:
		return _write_single(doctype, hidden, path)

	# The table's own columns (child tables carry parent, parenttype, parentfield and idx), minus Password
	# fields and Frappe's internal `_` columns (tags, comments, assignments, likes).
	columns = [
		column
		for column in frappe.db.get_table_columns(doctype)
		if column not in hidden and not column.startswith("_")
	]
	select = ", ".join(f"`{column}`" for column in columns)
	with open(path, "w", encoding=CSV_ENCODING, newline="") as handle:
		writer = csv.writer(handle)
		writer.writerow(columns)
		return _write_pages(writer, doctype, select)


def password_fields(meta) -> set[str]:
	"""Fields no CSV may hold. Frappe keeps their values encrypted elsewhere, but the column is dropped too (AC-6)."""
	return {field.fieldname for field in meta.get("fields", {"fieldtype": "Password"})}


def _write_pages(writer, doctype: str, select: str) -> int:
	"""Keyset pages ordered by `name`, stable inside the snapshot."""
	count, last = 0, None
	while True:
		after = "where `name` > %(last)s" if last is not None else ""
		rows = frappe.db.sql(
			f"select {select} from `tab{doctype}` {after} order by `name` limit {PAGE_SIZE}",
			{"last": last},
			as_dict=True,
		)
		for row in rows:
			writer.writerow([_cell(value) for value in row.values()])
		count += len(rows)
		if len(rows) < PAGE_SIZE:
			return count
		last = rows[-1].name


def _write_single(doctype: str, hidden: set[str], path: str) -> int:
	rows = frappe.db.sql(
		"select `field`, `value` from `tabSingles` where `doctype` = %s order by `field`", doctype
	)
	rows = [(field, value) for field, value in rows if field not in hidden]
	with open(path, "w", encoding=CSV_ENCODING, newline="") as handle:
		writer = csv.writer(handle)
		writer.writerow(("field", "value"))
		writer.writerows((field, _cell(value)) for field, value in rows)
	return len(rows)


def _write_file_index(folder: str) -> int:
	"""`File.csv`, so each uploaded file can be matched to the record it is attached to."""
	select = ", ".join(f"`{field}`" for field in FILE_FIELDS)
	rows = frappe.db.sql(
		f"select {select} from `tabFile` where `is_folder` = 0 order by `name`", as_list=True
	)
	with open(os.path.join(folder, "File.csv"), "w", encoding=CSV_ENCODING, newline="") as handle:
		writer = csv.writer(handle)
		writer.writerow(FILE_FIELDS)
		writer.writerows([_cell(value) for value in row] for row in rows)
	return len(rows)


def _copy_files(target: str) -> int:
	"""Every uploaded file at its path under the site's public and private files folders."""
	count = 0
	for visibility in ("public", "private"):
		source = frappe.get_site_path(visibility, "files")
		destination = os.path.join(target, visibility)
		os.makedirs(destination, exist_ok=True)
		if os.path.isdir(source):
			shutil.copytree(source, destination, dirs_exist_ok=True)
			count += sum(len(files) for _root, _dirs, files in os.walk(destination))
	return count


def _write_database_backup(path: str):
	"""A fresh Frappe database dump. The site config Frappe copies beside it goes to a scratch folder, not the zip."""
	from frappe.utils.backups import new_backup

	scratch = tempfile.mkdtemp(prefix="books-export-")
	try:
		new_backup(
			ignore_files=True,
			# A full dump: ignore any partial backup includes or excludes in the site config.
			ignore_conf=True,
			# Never reuse a recent backup.
			force=True,
			backup_path_db=path,
			backup_path_conf=os.path.join(scratch, "site_config.json"),
			backup_path_files=os.path.join(scratch, "files.tar"),
			backup_path_private_files=os.path.join(scratch, "private-files.tar"),
		)
	finally:
		shutil.rmtree(scratch, ignore_errors=True)


def _write_readme(path: str):
	with open(path, "w", encoding="utf-8") as handle:
		handle.write(README.format(site=frappe.local.site, built_on=_utc_iso(utc_now())))


def _folder_size(folder: str) -> int:
	return sum(
		os.path.getsize(os.path.join(root, name)) for root, _dirs, files in os.walk(folder) for name in files
	)


def _cell(value):
	if value is None:
		return ""
	if isinstance(value, datetime):
		return value.isoformat(sep=" ")
	if isinstance(value, date):
		return value.isoformat()
	if isinstance(value, Decimal):
		return str(value)
	return value


def _utc_iso(value) -> str | None:
	"""A stored naive UTC Datetime as an ISO timestamp that says it is UTC."""
	return get_datetime(value).replace(tzinfo=UTC).isoformat() if value else None


def _naive_utc(value: str) -> datetime:
	"""An ISO timestamp from the control site as naive UTC. One without a time zone is taken as UTC."""
	parsed = datetime.fromisoformat(value)
	if parsed.tzinfo is not None:
		parsed = parsed.astimezone(UTC).replace(tzinfo=None)
	return parsed


README = """Your RareBooks data
===================

This is a full copy of the books kept on {site}, made on {built_on} (UTC).

What is in this zip
-------------------

readable/
    One CSV file per kind of record, for example "Books Sales Invoice.csv".
    Open them in Excel, LibreOffice or Google Sheets. The first row holds the
    field names. Rows of a table inside a record (such as an invoice's items)
    are in their own file, linked to their record by the "parent" column.
    Settings are listed as "field,value" rows.

readable/File.csv
    Every uploaded file, with the record it is attached to
    (attached_to_doctype and attached_to_name) and where it is in files/.

files/public/ and files/private/
    Every file uploaded to the site, at the same path it had there.

backup/database.sql.gz
    A Frappe database backup of the whole site.

How to restore it on your own Frappe bench
------------------------------------------

1. Set up a Frappe version 16 bench with the frappe_books app.
2. Create a site, then restore the backup with its files:

       bench --site <your-site> restore backup/database.sql.gz

3. Copy files/public/ into sites/<your-site>/public/files/ and files/private/
   into sites/<your-site>/private/files/.
4. Run: bench --site <your-site> migrate

Users keep their logins after a restore. Stored secrets (password fields, such
as an email account's password) can't be read on the new site, because the
key that protected them is not in this zip. Enter them again after you restore.

Other copies
------------

After the site is removed, the hosting provider may keep backups of the site
for a limited time under its own policy.
"""
