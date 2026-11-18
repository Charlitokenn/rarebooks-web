"""The removal runner behind `bench books-removal-run` (spec 0007): reads every hosted site on the bench,
reports them to the control site in signed calls, and carries out the signed instructions it gets back.

It runs on the hosting server from host cron, outside any site's web requests and jobs. Its secrets live in
`<bench>/config/books-runner.json`, which Frappe never loads, so no site can read them through `frappe.conf`.
"""

import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import frappe
import requests
from frappe.utils import get_bench_path, get_sites

from frappe_books.subscription.control import SIGNATURE_HEADER, is_valid_signature, issued_now, sign
from frappe_books.subscription.removal import (
	build_export,
	clear_removal,
	mark_export_sent,
	removal_status,
)

MODE_KEY = "books_removal_mode"
MODES = ("off", "dry_run", "live")
SECRETS_FILE = os.path.join("config", "books-runner.json")
WORK_FOLDER = "books-removal"
# The exports a run put off, sent with the next run's report (AC-12).
DEFERRED_FILE = "deferred.json"
METHOD_PREFIX = "rarebooks_control.removal."
SITES_PER_CALL = 200
EXPORTS_PER_RUN = 3
TIMEOUT_SECONDS = 60
MIN_SECRET_LENGTH = 32
# Error text sent to the control site, cut after the secrets are scrubbed.
ERROR_CHARACTERS = 2000
# A bigger site briefly needs about twice its size free while its export is built and zipped.
DISK_HEADROOM = 2
ACTION_ORDER = ("clear", "mark_sent", "export", "drop")
# Case names go into folder and R2 key paths, so only the control site's autoname shape is accepted.
CASE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")
UPLOAD_PART_BYTES = 64 * 1024 * 1024
STORED_SUFFIXES = (".gz", ".zip", ".png", ".jpg", ".jpeg", ".pdf")


class RunnerConfigError(Exception):
	"""The secrets file is missing, unsafe or incomplete. The run stops with exit code 1."""


class ControlRefused(Exception):
	"""The control site couldn't be reached, refused the call, or answered without a valid signature or echo."""


class DiskSpaceError(Exception):
	"""Not enough free disk to build this site's export."""


class StepError(Exception):
	"""A failed `export`, `upload` or `drop` step, reported to the control site with `step_failed`."""

	def __init__(self, step: str):
		super().__init__(step)
		self.step = step


@contextmanager
def failing_step(step: str) -> Iterator[None]:
	try:
		yield
	except Exception as error:
		raise StepError(step) from error


@dataclass
class RunnerConfig:
	bench_path: str
	runner_name: str
	runner_secret: bytes
	control_url: str
	export_storage: dict
	root_login: str | None = None
	root_password: str | None = None

	@property
	def work_path(self) -> str:
		return os.path.join(self.bench_path, WORK_FOLDER)

	def secrets(self) -> list[str]:
		"""Every value that must never reach a log line or the control site."""
		values = [self.runner_secret.decode(), self.root_password]
		values += [self.export_storage.get(key) for key in ("access_key_id", "secret_access_key")]
		return [value for value in values if value]


def run(bench_path: str | None = None, log: Callable[[str], None] = print) -> int:
	"""One hourly run. Returns the process exit code."""
	bench_path = bench_path or get_bench_path()
	mode = read_mode(bench_path)
	if mode == "off":
		log(_line("-", f"{MODE_KEY} is off, nothing to do"))
		return 0
	try:
		config = load_config(bench_path)
	except RunnerConfigError as error:
		log(_line("-", f"stopped: {error}"))
		return 1
	return Runner(config, mode, log).run()


def read_mode(bench_path: str) -> str:
	"""`books_removal_mode` from the bench's `common_site_config.json`. Missing or unknown reads as `off`."""
	path = os.path.join(bench_path, "sites", "common_site_config.json")
	try:
		with open(path) as handle:
			mode = json.load(handle).get(MODE_KEY)
	except (OSError, ValueError):
		return "off"
	return mode if mode in MODES else "off"


def load_config(bench_path: str) -> RunnerConfig:
	path = os.path.join(bench_path, SECRETS_FILE)
	try:
		info = os.stat(path)
	except FileNotFoundError:
		raise RunnerConfigError(f"{SECRETS_FILE} is missing") from None
	if info.st_mode & (stat.S_IRWXG | stat.S_IRWXO) or info.st_uid != os.getuid():
		raise RunnerConfigError(f"{SECRETS_FILE} must be owned by the bench user with mode 600")
	try:
		with open(path) as handle:
			values = json.load(handle)
	except ValueError:
		raise RunnerConfigError(f"{SECRETS_FILE} is not valid JSON") from None

	secret = values.get("runner_secret") or ""
	control_url = (values.get("control_url") or "").rstrip("/")
	storage = values.get("export_storage") or {}
	if not values.get("runner_name"):
		raise RunnerConfigError("runner_name is missing")
	if len(secret) < MIN_SECRET_LENGTH:
		raise RunnerConfigError(f"runner_secret must be at least {MIN_SECRET_LENGTH} characters")
	if not control_url.startswith("https://"):
		raise RunnerConfigError("control_url must start with https://")
	missing = [key for key in R2Storage.KEYS if not storage.get(key)]
	if missing:
		raise RunnerConfigError(f"export_storage is missing {', '.join(missing)}")
	return RunnerConfig(
		bench_path=bench_path,
		runner_name=values["runner_name"],
		runner_secret=secret.encode(),
		control_url=control_url,
		export_storage=storage,
		root_login=values.get("root_login"),
		root_password=values.get("root_password"),
	)


@contextmanager
def open_site(site: str) -> Iterator[None]:
	"""Connect to one site of this bench as Administrator, and always let it go again."""
	frappe.init(site=site, sites_path=os.path.join(get_bench_path(), "sites"))
	try:
		frappe.connect()
		yield
	finally:
		frappe.destroy()


def bench_sites() -> list[str]:
	return get_sites(os.path.join(get_bench_path(), "sites"))


@dataclass
class Runner:
	config: RunnerConfig
	mode: str
	log: Callable[[str], None]
	storage: R2Storage | None = None
	notes: dict[str, list[str]] = field(default_factory=dict)
	reported: dict[str, dict] = field(default_factory=dict)
	deferred: list[str] = field(default_factory=list)

	def __post_init__(self):
		self.storage = self.storage or make_storage(self.config.export_storage)

	def run(self) -> int:
		statuses = self.read_sites()
		try:
			instructions = self.report(statuses, read_deferred(self.config.work_path))
		except ControlRefused as error:
			# The deferred list stays on disk for the next report.
			self.log(_line("-", f"stopped, nothing done: {self.scrub(str(error))}"))
			return 1
		self.carry_out(instructions)
		write_deferred(self.config.work_path, self.deferred)
		self.write_summary()
		return 0

	def read_sites(self) -> list[dict]:
		"""Every site with a control URL: its removal status, or `error` when it can't be read."""
		statuses = []
		for site in bench_sites():
			try:
				with open_site(site):
					if not frappe.conf.get("books_control_url"):
						continue
					status = removal_status()
			except Exception as error:
				status = {"site": site, "error": self.scrub(_describe(error))[:ERROR_CHARACTERS]}
				self.note(site, "error reading the site")
			else:
				self.note(site, f"{status['phase']} removal_on={status['removal_on'] or '-'}")
			statuses.append(status)
			self.reported[site] = status
		return statuses

	def report(self, statuses: list[dict], deferred: list[str]) -> list[dict]:
		"""`report_sites` in chunks; one call even with no sites, so the control site knows the bench is alive.

		The exports the last run put off go with the first chunk, so the control site counts no attempt (AC-12).
		"""
		instructions = []
		for start in range(0, max(len(statuses), 1), SITES_PER_CALL):
			chunk = statuses[start : start + SITES_PER_CALL]
			payload = {"mode": self.mode, "sites": chunk, "deferred": deferred if start == 0 else []}
			answer = self.call("report_sites", payload)
			found = answer.get("instructions") or []
			if not isinstance(found, list):
				raise ControlRefused("report_sites answered without an instructions list")
			instructions += found
		return instructions

	def carry_out(self, instructions: list[dict]):
		"""`clear`, then `mark_sent`, then `export` (at most 3 a run), then `drop`."""
		valid = [item for item in instructions if self.is_valid_instruction(item)]
		exports = 0
		for action in ACTION_ORDER:
			for item in (item for item in valid if item["action"] == action):
				if action == "export":
					if exports >= EXPORTS_PER_RUN:
						self.deferred.append(item["case"])
						self.note(item["site"], f"export {item['case']} put off to the next run")
						continue
					exports += 1
				self.carry_out_one(item)

	def carry_out_one(self, item: dict):
		handler = getattr(self, f"do_{item['action']}", None)
		if not handler:
			self.note(item["site"], f"{item['action']} {item['case']} not handled by this runner")
			return
		try:
			handler(item)
		except Exception as error:
			cause = error.__cause__ if isinstance(error, StepError) else error
			text = self.scrub(_describe(cause))[:ERROR_CHARACTERS]
			self.note(item["site"], f"{item['action']} {item['case']} failed: {text}")
			if isinstance(error, StepError):
				self.report_failure(item, error.step, text)

	def report_failure(self, item: dict, step: str, text: str):
		"""`step_failed`, so the control site retries next run or fails the case (AC-12)."""
		try:
			self.call(
				"step_failed", {"case": item["case"], "site": item["site"], "step": step, "error": text}
			)
		except ControlRefused as error:
			self.note(item["site"], f"couldn't report the failure: {self.scrub(str(error))}")

	def is_valid_instruction(self, item) -> bool:
		"""Only a known action, for a site this run read itself, with a case name safe to put in a path."""
		site = item.get("site") if isinstance(item, dict) else None
		if isinstance(item, dict):
			case, action = item.get("case"), item.get("action")
			known_site = isinstance(site, str) and "error" not in self.reported.get(site, {"error": True})
			if action in ACTION_ORDER and known_site and isinstance(case, str) and CASE_NAME.match(case):
				return True
		self.log(
			_line(str(site or "-"), f"ignored an instruction: {self.scrub(json.dumps(item, default=str))}")
		)
		return False

	def do_clear(self, item: dict):
		"""Empty the hold fields of a site that paid before its drop (AC-11). A dry run never writes to a site."""
		if self.mode != "live":
			self.note(item["site"], f"clear {item['case']} skipped in dry_run")
			return
		with open_site(item["site"]):
			clear_removal()
			frappe.db.commit()
		self.note(item["site"], f"clear {item['case']} done")

	def do_mark_sent(self, item: dict):
		"""Write the hold fields on the site (AC-8). A dry run never writes to a site (AC-14)."""
		if self.mode != "live":
			self.note(item["site"], f"mark_sent {item['case']} skipped in dry_run")
			return
		with open_site(item["site"]):
			mark_export_sent(item["export_sent_on"], item["removal_hold_until"])
			frappe.db.commit()
		self.note(item["site"], f"mark_sent {item['case']} hold until {item['removal_hold_until']}")

	def do_export(self, item: dict):
		"""Build, zip and upload the export, then tell the control site where it is (AC-6, AC-7)."""
		site, case = item["site"], item["case"]
		folder = os.path.join(self.config.work_path, case)
		shutil.rmtree(folder, ignore_errors=True)
		try:
			export_dir = os.path.join(folder, "export")
			attempt = str(uuid4())
			archive = os.path.join(folder, f"{attempt}.zip")
			key = f"exports/{case}/{attempt}.zip"
			with failing_step("export"):
				with open_site(site):
					check_disk(self.config.bench_path)
					counts = build_export(export_dir)
				zip_folder(export_dir, archive)
				size, digest = file_digest(archive)
			with failing_step("upload"):
				self.storage.upload(archive, key)
			# A refused `export_ready` is no step failure: the control site times out the claim (AC-12).
			self.call(
				"export_ready",
				{"case": case, "site": site, "key": key, "bytes": size, "sha256": digest},
			)
		finally:
			shutil.rmtree(folder, ignore_errors=True)
		self.note(site, f"export {case} uploaded, {counts['rows']} rows, {size} bytes")

	def call(self, method: str, payload: dict) -> dict:
		"""A signed POST to the control site. Acts only on an answer signed with this bench's secret that
		echoes this request's `issued_at` (AC-15)."""
		issued_at = issued_now()
		body = json.dumps(
			{"bench": self.config.runner_name, "issued_at": issued_at, **payload}, default=str
		).encode()
		secret = self.config.runner_secret
		try:
			response = requests.post(
				f"{self.config.control_url}/api/method/{METHOD_PREFIX}{method}",
				data=body,
				headers={"Content-Type": "application/json", SIGNATURE_HEADER: sign(body, secret)},
				timeout=TIMEOUT_SECONDS,
			)
			response.raise_for_status()
		except requests.RequestException as error:
			raise ControlRefused(f"{method} failed: {type(error).__name__}") from None

		if not is_valid_signature(response.content, response.headers.get(SIGNATURE_HEADER), secret):
			raise ControlRefused(f"{method} answered without a valid signature")
		try:
			data = json.loads(response.content)
		except ValueError:
			raise ControlRefused(f"{method} answered with invalid JSON") from None
		message = data.get("message", data) if isinstance(data, dict) else None
		if not isinstance(message, dict) or message.get("issued_at") != issued_at:
			raise ControlRefused(f"{method} answer doesn't echo this request")
		return message

	def note(self, site: str, text: str):
		self.notes.setdefault(site, []).append(text)

	def write_summary(self):
		"""One line per site, which host cron appends to `<bench>/logs/books-removal.log`."""
		for site, texts in self.notes.items():
			self.log(_line(site, f"[{self.mode}] " + "; ".join(texts)))

	def scrub(self, text: str) -> str:
		for secret in self.config.secrets():
			text = text.replace(secret, "***")
		return text


class R2Storage:
	"""The private Cloudflare R2 bucket, through its S3 API, with the runner's write only token."""

	KEYS = ("endpoint_url", "bucket", "access_key_id", "secret_access_key")

	def __init__(self, conf: dict):
		self.conf = conf

	def upload(self, path: str, key: str):
		"""Multipart for anything over 64 MB; boto3 aborts the upload itself when a part fails."""
		import boto3
		from boto3.s3.transfer import TransferConfig

		client = boto3.client(
			"s3",
			endpoint_url=self.conf["endpoint_url"],
			aws_access_key_id=self.conf["access_key_id"],
			aws_secret_access_key=self.conf["secret_access_key"],
			region_name="auto",
		)
		transfer = TransferConfig(
			multipart_threshold=UPLOAD_PART_BYTES, multipart_chunksize=UPLOAD_PART_BYTES
		)
		client.upload_file(path, self.conf["bucket"], key, Config=transfer)


def make_storage(conf: dict) -> R2Storage:
	return R2Storage(conf)


def read_deferred(work_path: str) -> list[str]:
	"""The case names the last run put off. A missing or broken file reads as none."""
	try:
		with open(os.path.join(work_path, DEFERRED_FILE)) as handle:
			cases = json.load(handle)
	except (OSError, ValueError):
		return []
	return [case for case in cases if isinstance(case, str) and CASE_NAME.match(case)]


def write_deferred(work_path: str, cases: list[str]):
	os.makedirs(work_path, exist_ok=True)
	with open(os.path.join(work_path, DEFERRED_FILE), "w") as handle:
		json.dump(cases, handle)


def check_disk(bench_path: str):
	"""Free disk must exceed twice the site's database plus its uploaded files."""
	database = frappe.db.sql(
		"select coalesce(sum(data_length + index_length), 0) from information_schema.tables "
		"where table_schema = %s",
		frappe.conf.db_name,
	)[0][0]
	files = sum(_folder_size(frappe.get_site_path(part, "files")) for part in ("public", "private"))
	needed = DISK_HEADROOM * (int(database) + files)
	free = shutil.disk_usage(bench_path).free
	if free <= needed:
		raise DiskSpaceError(f"needs {needed} bytes free, has {free}")


def zip_folder(folder: str, archive: str):
	"""ZIP64, so a large export still opens. Files that are already compressed are stored as they are."""
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


def _folder_size(folder: str) -> int:
	return sum(
		os.path.getsize(os.path.join(root, name)) for root, _dirs, files in os.walk(folder) for name in files
	)


def _describe(error: Exception) -> str:
	return f"{type(error).__name__}: {error}"


def _line(site: str, text: str) -> str:
	return f"{datetime.now(UTC).isoformat(timespec='seconds')} {site} {text}"
