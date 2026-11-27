"""The control site's signed calls that import rows into this site (spec 0025).

The control site's Books Bulk Import grid sends rows keyed by the columns this site gives. The site owns the
column list, the import CSV, the dry run and the import, so its own controller rules still decide what saves.
Every call is a guest POST checked by `remote._verified()`, and every answer, an error included, is signed and
echoes the request's `issued_at`. None of these is in `ALLOWED_METHODS`: a locked site refuses every write call,
and `import_report` only reads.
"""

import csv
import hashlib
import io
import json
import os
import re
import uuid
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from werkzeug.wrappers import Response

from frappe_books.subscription import clock
from frappe_books.subscription.remote import BAD_REQUEST, CALLS_PER_MINUTE, SignedCall, _verified

NOT_FOUND, CONFLICT, TOO_LARGE, UNAVAILABLE = 404, 409, 413, 503
# A rows body over 2 MB is refused before anything is parsed (AC-12).
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000
ROW_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
# The control site's import name plus its attempt, and the Data Import named after it (AC-7, AC-16).
IMPORT_REF = re.compile(r"^BIMP-\d{5,}-\d+$")
DATA_IMPORT_NAME = re.compile(r"^CTRL-BIMP-\d{5,}-\d+$")
NAME_PREFIX = "CTRL-"
INSERT_NEW = "Insert New Records"
# Spec 0004 AC-12: an expense is always imported as a draft.
NEVER_SUBMITTED = {"Books Expense"}
FINISHED = ("Success", "Partial Success", "Error", "Timed Out")
LOGS_PER_PAGE = 500
MAX_CELL_LENGTH = 10000

# The types the Import Wizard offers, in its order: `getImportableSchemaNames` in `frontend/src/importer.ts`,
# as a user who may import everything sees it (AC-15).
IMPORTABLE = (
	"SalesInvoice",
	"PurchaseInvoice",
	"Payment",
	"Expense",
	"Party",
	"Item",
	"JournalEntry",
	"Tax",
	"Account",
	"Address",
	"NumberSeries",
)
# Offered only while Accounting Settings has inventory on.
STOCK_IMPORTABLE = ("StockMovement", "Shipment", "PurchaseReceipt", "Location")
INVENTORY_SETTINGS = "Books Accounting Settings"
# The wizard's template columns per type, written by `frontend/tests/import-templates.test.mjs`.
TEMPLATES_FILE = Path(__file__).with_name("import_templates.json")

SKIPPED_FIELDTYPES = {"Attach", "Attach Image", "Table", "Table MultiSelect"}
LAYOUT_FIELDTYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Button", "Fold"}
NUMBER_FIELDTYPES = {"Int", "Float", "Currency", "Percent"}
DATE_FIELDTYPES = {"Date", "Datetime"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def import_columns() -> Response:
	"""The types this site imports and each type's grid columns, in the wizard's order (AC-3). Read only."""
	call = _verified()
	if isinstance(call, Response):
		return call
	if clock.is_locked():
		return _site_locked(call)
	return call.answer({"types": [_public_type(doctype) for doctype in importable_doctypes()], **formats()})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def preview_import() -> Response:
	"""The dry run: Frappe's own import preview of the rows, which saves nothing (AC-5, AC-6).

	The CSV goes to a temporary file under the site's private folder, deleted before the call answers. No Data
	Import and no File row is written. Each warning names the grid rows and the column key it is about.
	"""
	call = _verified()
	if isinstance(call, Response):
		return call
	refused = _refused_write(call)
	if refused:
		return refused
	doctype, rows = call.body["import_type"], call.body["rows"]
	text, row_ids = build_import_csv(doctype, rows)
	return call.answer({"warnings": _preview_warnings(doctype, text, row_ids)})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def start_import() -> Response:
	"""Create the Data Import `CTRL-<import_ref>` from the rows and start it, once per ref (AC-7, AC-8).

	The same ref with the same rows answers the Data Import already there, and starts it only when it is Pending
	with no logs and no job queued. The same ref with different rows is a 409 `ref_conflict`.
	"""
	call = _verified()
	if isinstance(call, Response):
		return call
	refused = _refused_write(call)
	if refused:
		return refused
	body = call.body
	import_ref, submit = body.get("import_ref"), body.get("submit")
	if not (isinstance(import_ref, str) and IMPORT_REF.match(import_ref) and submit in (0, 1, True, False)):
		return call.answer({"status": "bad_request"}, BAD_REQUEST)

	doctype = body["import_type"]
	text, row_ids = build_import_csv(doctype, body["rows"])
	if not row_ids:
		return call.answer({"status": "bad_request"}, BAD_REQUEST)
	submit = _submits(doctype, submit)
	fingerprint = _fingerprint(doctype, submit, text)
	name = f"{NAME_PREFIX}{import_ref}"
	if frappe.db.exists("Data Import", name):
		return _answer_existing(call, name, fingerprint)
	if _scheduler_off():
		return call.answer({"status": "scheduler_inactive"}, UNAVAILABLE)

	try:
		with _as_administrator():
			_create_data_import(name, doctype, submit, text, row_ids, fingerprint)
	except frappe.DuplicateEntryError:
		# A start that ran at the same time made it first.
		frappe.db.rollback()
		return _answer_existing(call, name, fingerprint)
	frappe.db.commit()
	started = _start(name)
	return call.answer(
		{
			"data_import": name,
			"status": frappe.db.get_value("Data Import", name, "status"),
			"started": started,
		}
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=CALLS_PER_MINUTE, seconds=60)
def import_report() -> Response:
	"""A control site Data Import's status and, once it finished, its results per grid row (AC-9). Read only,
	so it still answers on a locked site."""
	call = _verified()
	if isinstance(call, Response):
		return call
	name, after = call.body.get("data_import"), call.body.get("after_log_index", -1)
	if not (isinstance(name, str) and DATA_IMPORT_NAME.match(name)) or not isinstance(after, int):
		return call.answer({"status": "bad_request"}, BAD_REQUEST)
	data_import = frappe.db.get_value(
		"Data Import",
		name,
		["status", "payload_count", "template_options", "template_warnings"],
		as_dict=True,
	)
	if not data_import:
		return call.answer({"status": "not_found"}, NOT_FOUND)

	options = json.loads(data_import.template_options or "{}")
	processed = frappe.db.count("Data Import Log", {"data_import": name})
	report = {"status": data_import.status, "total": data_import.payload_count or 0, "processed": processed}
	if data_import.status in FINISHED:
		logs = _report_logs(name, after, options.get("control_row_ids") or [])
		report.update({"logs": logs[:LOGS_PER_PAGE], "more": len(logs) > LOGS_PER_PAGE})
	elif data_import.status == "Pending" and data_import.template_warnings:
		warnings = json.loads(data_import.template_warnings)
		report["blocking_warnings"] = [
			_warning(
				warning, options.get("control_row_ids") or [], options.get("control_csv_keys") or [], True
			)
			for warning in warnings
		]
	return call.answer(report)


def delete_finished_import_file(doc, method=None):
	"""Delete a control site import's private CSV once its Data Import finishes (AC-16). Its logs stay."""
	if not (doc.name or "").startswith(NAME_PREFIX) or doc.status not in FINISHED:
		return
	files = frappe.get_all(
		"File", {"attached_to_doctype": "Data Import", "attached_to_name": doc.name}, pluck="name"
	)
	for file in files:
		frappe.delete_doc("File", file, ignore_permissions=True, force=True)


def importable_doctypes() -> list[str]:
	"""The DocTypes this site imports from the control site, in the wizard's order (AC-3, AC-13)."""
	names = list(IMPORTABLE)
	if frappe.db.get_single_value(INVENTORY_SETTINGS, "enable_inventory"):
		names += STOCK_IMPORTABLE
	by_schema = {template["schema_name"]: template["doctype"] for template in _templates()}
	return [by_schema[name] for name in names if name in by_schema]


def is_importable(doctype) -> bool:
	"""Whether a call may name this DocType: only the site's own list, never User, Role or any other (AC-13)."""
	return isinstance(doctype, str) and doctype in importable_doctypes()


def type_columns(doctype: str) -> list[dict]:
	"""A type's grid columns: the wizard's template columns that still exist, then the site's custom fields.

	Each column carries its `fieldtype` and `options` from the live meta, and the `csv_key` the import CSV
	names it by (None when Frappe names it itself, as a numbered document's name or a child row's id).
	"""
	template = _template(doctype)
	meta = frappe.get_meta(doctype)
	tables = {field.fieldname: field for field in meta.fields if field.fieldtype == "Table"}
	columns = []
	for column in template["columns"]:
		table = column["table"]
		field_meta = frappe.get_meta(tables[table].options) if table in tables else None
		if table and not field_meta:
			continue
		fieldname = column["key"].split(".", 1)[1] if table else column["key"]
		field = (field_meta or meta).get_field(fieldname)
		if fieldname != "name" and not field:
			continue
		columns.append({**column, **_field_type(field)})
	return _with_custom_fields(columns, meta, tables, template)


def formats() -> dict:
	"""The formats Frappe's importer reads cells in for Administrator, the user the import runs as (AC-17).

	Frappe's job sets that user's language with `set_user_lang`, and `frappe.locale` reads the format from the
	Language record, else System Settings. A signed call runs as Guest, so the language is named here.
	"""
	from frappe.locale import get_date_format, get_locale_value
	from frappe.translate import get_user_lang

	language = get_user_lang("Administrator")
	return {
		"date_format": get_date_format(language),
		"number_format": get_locale_value("number_format", language) or "#,###.##",
	}


def build_import_csv(doctype: str, rows: list[dict]) -> tuple[str, list[str]]:
	"""The import CSV the wizard's `getImportFile` makes, and the row id behind each CSV data row (AC-17).

	A leading `docstatus` column has `0` on each document's first row. The rows of one name come together in grid
	order. Each parent cell takes the last non empty value among the document's rows and is blank on the
	following rows. Blank rows are dropped. Dates are written as ISO and numbers in the site's format.
	"""
	columns = [column for column in type_columns(doctype) if column["csv_key"]]
	name_key = _template(doctype)["name_key"]
	cell_format = _CellFormat(formats())
	matrix = [["docstatus", *(column["csv_key"] for column in columns)]]
	row_ids = []
	for document in _documents(rows, name_key):
		parent = {
			column["key"]: _last_value(document, column["key"]) for column in columns if not column["table"]
		}
		for position, row in enumerate(document):
			cells = row["cells"]
			values = [
				cells.get(column["key"], "")
				if column["table"]
				else (parent[column["key"]] if not position else "")
				for column in columns
			]
			formatted = [
				cell_format.text(value, column) for value, column in zip(values, columns, strict=True)
			]
			matrix.append(["" if position else "0", *formatted])
			row_ids.append(row["id"])
	return _csv_text(matrix), row_ids


def valid_rows(rows, doctype: str) -> bool:
	"""Rows the control site may send: a list of `{id, cells}` with unique ids and only this type's keys."""
	if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
		return False
	keys = {column["key"] for column in type_columns(doctype)}
	ids = set()
	for row in rows:
		if not isinstance(row, dict) or not isinstance(row.get("cells"), dict):
			return False
		row_id = row.get("id")
		if not isinstance(row_id, str) or not ROW_ID.match(row_id) or row_id in ids:
			return False
		ids.add(row_id)
		for key, value in row["cells"].items():
			if key not in keys or not isinstance(value, str) or len(value) > MAX_CELL_LENGTH:
				return False
	return True


def body_too_large() -> bool:
	return len(frappe.request.get_data()) > MAX_BODY_BYTES


def _site_locked(call: SignedCall) -> Response:
	return call.answer({"status": "site_locked"}, CONFLICT)


def _refused_write(call: SignedCall) -> Response | None:
	"""The answer that stops a dry run or a start before any write: a locked site, a body over 2 MB, a type
	outside the site's list, or rows that aren't the site's shape (AC-11, AC-12, AC-13)."""
	if clock.is_locked():
		return _site_locked(call)
	if body_too_large():
		return call.answer({"status": "too_large"}, TOO_LARGE)
	doctype = call.body.get("import_type")
	if not is_importable(doctype) or not valid_rows(call.body.get("rows"), doctype):
		return call.answer({"status": "bad_request"}, BAD_REQUEST)
	return None


def _preview_warnings(doctype: str, text: str, row_ids: list[str]) -> list[dict]:
	from frappe.core.doctype.data_import.importer import Importer
	from frappe.core.doctype.data_import.value_mapping import get_blocking_warnings

	if not row_ids:
		return [
			{
				"row_ids": [],
				"column_key": None,
				"message": _("There are no rows to import."),
				"blocking": True,
			}
		]
	csv_keys = next(csv.reader(io.StringIO(text)))
	folder = frappe.get_site_path("private", "files")
	os.makedirs(folder, exist_ok=True)
	path = os.path.join(folder, f"books-bulk-preview-{uuid.uuid4().hex}.csv")
	try:
		with open(path, "w", encoding="utf-8") as file:
			file.write(text)
		data_import = frappe.new_doc("Data Import")
		data_import.update({"reference_doctype": doctype, "import_type": INSERT_NEW})
		with _as_administrator():
			try:
				importer = Importer(doctype, data_import=data_import, file_path=path, console=True)
				# Rows are parsed, and their date and number warnings made, only when payloads are built.
				importer.import_file.get_payloads_for_import()
				warnings = importer.import_file.get_all_warnings()
				blocking = get_blocking_warnings(warnings, importer.import_file, data_import)
			except frappe.ValidationError as error:
				return [{"row_ids": [], "column_key": None, "message": _plain(str(error)), "blocking": True}]
			columns = {column.column_number: column for column in importer.import_file.header.columns}
	finally:
		if os.path.exists(path):
			os.remove(path)
	blocking_ids = {id(warning) for warning in blocking}
	out = []
	for warning in warnings:
		column = columns.get(warning.get("col"))
		if warning.get("type") == "value_mapping" and column and column.invalid_value_items:
			out += _value_warnings(column, row_ids, csv_keys, id(warning) in blocking_ids)
		else:
			out.append(_warning(warning, row_ids, csv_keys, id(warning) in blocking_ids))
	return out


def _value_warnings(column, row_ids: list[str], csv_keys: list[str], blocking: bool) -> list[dict]:
	"""One warning per Link or Select value the site doesn't have, on the rows that hold it."""
	label = column.df.label or column.df.fieldname
	warnings = []
	for item in column.invalid_value_items:
		if column.df.fieldtype == "Select":
			message = _('"{0}" is not an option of {1}').format(item["source"], label)
		else:
			message = _('"{0}" is not a valid {1}').format(item["source"], label)
		warning = {"rows": item["rows"], "col": column.column_number, "message": message}
		warnings.append(_warning(warning, row_ids, csv_keys, blocking))
	return warnings


def _warning(warning: dict, row_ids: list[str], csv_keys: list[str], blocking: bool) -> dict:
	"""A Frappe warning as the grid shows it: its rows as row ids, its column as a column key, plain text."""
	rows = warning.get("rows") or ([warning["row"]] if warning.get("row") else [])
	column = warning.get("col")
	column_key = None
	if isinstance(column, int) and 0 < column <= len(csv_keys) and csv_keys[column - 1] != "docstatus":
		# A sent column's CSV key is its grid column key.
		column_key = csv_keys[column - 1]
	return {
		"row_ids": [row_ids[row - 2] for row in _ints(rows) if 0 <= row - 2 < len(row_ids)],
		"column_key": column_key,
		"message": _plain(str(warning.get("message") or "")),
		"blocking": blocking,
	}


def _ints(values) -> list[int]:
	return [int(value) for value in values if str(value).isdigit()]


def _submits(doctype: str, submit) -> int:
	if doctype in NEVER_SUBMITTED or not frappe.get_meta(doctype).is_submittable:
		return 0
	return 1 if submit else 0


def _fingerprint(doctype: str, submit: int, text: str) -> str:
	return hashlib.sha256(f"{doctype}\n{submit}\n{text}".encode()).hexdigest()


def _answer_existing(call: SignedCall, name: str, fingerprint: str) -> Response:
	options = json.loads(frappe.db.get_value("Data Import", name, "template_options") or "{}")
	if options.get("control_csv_sha256") != fingerprint:
		return call.answer({"status": "ref_conflict", "data_import": name}, CONFLICT)
	status = frappe.db.get_value("Data Import", name, "status")
	started = False
	if status == "Pending" and not frappe.db.exists("Data Import Log", {"data_import": name}):
		if _scheduler_off():
			return call.answer({"status": "scheduler_inactive"}, UNAVAILABLE)
		started = _start(name)
		status = frappe.db.get_value("Data Import", name, "status")
	return call.answer({"data_import": name, "status": status, "started": started})


def _create_data_import(name, doctype, submit, text, row_ids, fingerprint):
	data_import = frappe.new_doc("Data Import")
	data_import.update(
		{
			"reference_doctype": doctype,
			"import_type": INSERT_NEW,
			"submit_after_import": submit,
			"mute_emails": 1,
		}
	)
	data_import.insert(set_name=name)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{name}.csv",
			"is_private": 1,
			"content": text,
			"attached_to_doctype": "Data Import",
			"attached_to_name": name,
		}
	).insert()
	data_import.import_file = file.file_url
	data_import.save()
	# After the save: Data Import clears its template options whenever its file changes.
	options = {
		"control_csv_sha256": fingerprint,
		"control_row_ids": row_ids,
		"control_csv_keys": next(csv.reader(io.StringIO(text))),
	}
	data_import.db_set("template_options", json.dumps(options), update_modified=False)


def _start(name: str) -> bool:
	"""Queue the import as Administrator, so its records' owner is Administrator (AC-7)."""
	with _as_administrator():
		started = frappe.get_doc("Data Import", name).start_import()
	frappe.db.commit()
	return bool(started)


def _scheduler_off() -> bool:
	"""Frappe's own refusal rule in `DataImport.start_import`, checked before anything is created (AC-11)."""
	from frappe.utils.scheduler import is_scheduler_inactive

	return is_scheduler_inactive() and not (frappe.in_test or frappe.conf.developer_mode)


def _report_logs(name: str, after: int, row_ids: list[str]) -> list[dict]:
	logs = frappe.get_all(
		"Data Import Log",
		filters={"data_import": name, "log_index": (">", after)},
		fields=["log_index", "row_indexes", "success", "docname", "messages", "exception"],
		order_by="log_index asc",
		limit=LOGS_PER_PAGE + 1,
	)
	return [
		{
			"log_index": log.log_index,
			"row_ids": [
				row_ids[row - 2]
				for row in _ints(json.loads(log.row_indexes or "[]"))
				if 0 <= row - 2 < len(row_ids)
			],
			"success": bool(log.success),
			"docname": log.docname if log.success else None,
			"message": _log_message(log),
		}
		for log in logs
	]


def _log_message(log) -> str:
	"""The log's messages, else the last line of its exception, as `getLogMessage` in `dataImport.ts` does."""
	try:
		messages = json.loads(log.messages or "[]")
	except ValueError:
		messages = []
	texts = [str(item.get("message")) for item in messages if isinstance(item, dict) and item.get("message")]
	if texts:
		return _plain("\n".join(texts))
	exception = (log.exception or "").strip()
	return _plain(exception.split("\n")[-1]) if exception else ""


def _plain(message: str) -> str:
	"""A site message as plain text: line breaks kept, no HTML (AC-16)."""
	return frappe.utils.strip_html(re.sub(r"<br\s*/?>", "\n", message)).strip()


class _as_administrator:
	"""Run as Administrator, then go back to the caller (Guest for a signed call)."""

	def __enter__(self):
		self.user = frappe.session.user
		frappe.set_user("Administrator")

	def __exit__(self, *exc):
		frappe.set_user(self.user)
		return False


@cache
def _templates_text() -> str:
	return TEMPLATES_FILE.read_text()


def _templates() -> list[dict]:
	return json.loads(_templates_text())


def _template(doctype: str) -> dict:
	return next(template for template in _templates() if template["doctype"] == doctype)


def _public_type(doctype: str) -> dict:
	template = _template(doctype)
	public = ("key", "label", "fieldtype", "required", "options", "table_label")
	return {
		"doctype": doctype,
		"schema_name": template["schema_name"],
		"label": template["label"],
		"submittable": bool(frappe.get_meta(doctype).is_submittable),
		"name_key": template["name_key"],
		"columns": [{key: column[key] for key in public} for column in type_columns(doctype)],
	}


def _field_type(field) -> dict:
	if not field:
		return {"fieldtype": "Data", "options": None}
	options = None
	if field.fieldtype == "Select":
		options = [option for option in (field.options or "").split("\n") if option]
	elif field.fieldtype in ("Link", "Dynamic Link"):
		options = field.options
	return {"fieldtype": field.fieldtype, "options": options}


def _with_custom_fields(columns: list[dict], meta, tables: dict, template: dict) -> list[dict]:
	"""Add the site's own custom fields after their parent's or table's columns, by the wizard's rules."""
	keys = {column["key"] for column in columns}
	parent = [_custom_column(field, None) for field in _custom_fields(meta)]
	columns = _insert_after(columns, None, [column for column in parent if column["key"] not in keys])
	for table in {column["table"] for column in template["columns"] if column["table"]}:
		if table not in tables:
			continue
		child = [
			_custom_column(field, tables[table])
			for field in _custom_fields(frappe.get_meta(tables[table].options))
		]
		columns = _insert_after(columns, table, [column for column in child if column["key"] not in keys])
	return columns


def _custom_fields(meta) -> list:
	return [
		field
		for field in meta.fields
		if field.get("is_custom_field")
		and field.fieldtype not in SKIPPED_FIELDTYPES | LAYOUT_FIELDTYPES
		and not field.get("hidden")
		and not field.get("is_virtual")
		and not (field.get("read_only") and not field.get("reqd"))
	]


def _custom_column(field, table) -> dict:
	key = f"{table.fieldname}.{field.fieldname}" if table else field.fieldname
	return {
		"key": key,
		"label": f"{field.label} ({table.label})" if table else field.label,
		"required": bool(field.reqd) and not table,
		"table": table.fieldname if table else None,
		"table_label": table.label if table else None,
		"csv_key": key,
		**_field_type(field),
	}


def _insert_after(columns: list[dict], table: str | None, added: list[dict]) -> list[dict]:
	if not added:
		return columns
	last = max((i for i, column in enumerate(columns) if column["table"] == table), default=len(columns) - 1)
	return [*columns[: last + 1], *added, *columns[last + 1 :]]


def _documents(rows: list[dict], name_key: str) -> list[list[dict]]:
	"""Rows grouped by the name cell, in the order each name first appears. Blank or unnamed rows are dropped."""
	documents: dict[str, list[dict]] = {}
	for row in rows:
		cells = row["cells"]
		name = (cells.get(name_key) or "").strip()
		if name and any((value or "").strip() for value in cells.values()):
			documents.setdefault(name, []).append(row)
	return list(documents.values())


def _last_value(document: list[dict], key: str) -> str:
	values = [(row["cells"].get(key) or "").strip() for row in document]
	return next((value for value in reversed(values) if value), "")


def _csv_text(matrix: list[list[str]]) -> str:
	out = io.StringIO()
	csv.writer(out, lineterminator="\r\n").writerows(matrix)
	return out.getvalue()


class _CellFormat:
	"""Cells as Frappe's Data Import reads them: dates as ISO, numbers in the site's number format (AC-17)."""

	def __init__(self, site_formats: dict):
		from frappe.utils.number_format import NumberFormat

		self.date_format = _strptime_format(site_formats["date_format"])
		self.number_format = NumberFormat.from_string(site_formats["number_format"])

	def text(self, value: str, column: dict) -> str:
		value = (value or "").strip()
		if not value:
			return ""
		if column["fieldtype"] == "Date":
			return self._date(value) or value
		if column["fieldtype"] == "Datetime":
			return self._datetime(value) or value
		if column["fieldtype"] in NUMBER_FIELDTYPES:
			return self._number(value)
		return value

	def _date(self, value: str) -> str | None:
		from datetime import datetime

		for pattern in ("%Y-%m-%d", self.date_format):
			try:
				return datetime.strptime(value, pattern).date().isoformat()
			except ValueError:
				continue
		return None

	def _datetime(self, value: str) -> str | None:
		from datetime import datetime

		date_part, _, time_part = value.replace("T", " ").partition(" ")
		day = self._date(date_part)
		if not day:
			return None
		time_part = time_part.strip() or "00:00:00"
		for pattern in ("%H:%M:%S", "%H:%M"):
			try:
				return f"{day} {datetime.strptime(time_part, pattern).time().isoformat()}"
			except ValueError:
				continue
		return None

	def _number(self, value: str) -> str:
		return number_text(value, self.number_format)


def number_text(value: str, number_format) -> str:
	"""A number cell as the import CSV writes it, by the number rule of AC-17.

	The cell is read plain (`1234.50`) or in the import's number format (`1.234,50`). It is written as its digits,
	with a leading `-` when negative, no thousands separator, no exponent and no trailing fractional zeros, with
	the format's own decimal separator (`.` for a format with none). A cell that reads differently in the two
	ways, or that is not a finite number (`nan`, `inf`, `1e5`, `(12)`), is sent as typed, so the dry run marks it.
	So is a number whose written form Frappe would itself read two ways (three decimals on a `#.###` site).
	"""
	from frappe.core.doctype.data_import.importer import _parse_number

	value = value.strip()
	plain = _decimal(value) if PLAIN_NUMBER.fullmatch(value) else None
	formatted = _decimal(_plain_number(value, number_format)) if _in_format(value, number_format) else None
	if plain is None and formatted is None:
		return value
	if plain is not None and formatted is not None and plain != formatted:
		return value
	number = plain if plain is not None else formatted
	text = _digits(number, number_format.decimal_separator or ".")
	if _parse_number(text, number_format) != float(number):
		return value
	return text


# A plain number as the exporter writes it: digits, one optional `.`, no exponent.
PLAIN_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")


def _in_format(value: str, number_format) -> bool:
	"""Whether a cell is written in the number format, by the pattern Frappe's `_parse_number` reads."""
	group = re.escape(number_format.thousands_separator)
	decimal = re.escape(number_format.decimal_separator)
	integer = rf"\d+|[1-9]\d{{0,2}}(?:{group}\d{{2,3}})*{group}\d{{3}}" if group else r"\d+"
	fraction = rf"(?:{decimal}\d+)?" if decimal else ""
	return bool(re.fullmatch(rf"[+-]?(?:{integer}){fraction}", value))


def _decimal(value: str) -> Decimal | None:
	try:
		number = Decimal(value)
	except InvalidOperation:
		return None
	return number if number.is_finite() else None


def _digits(number: Decimal, decimal_separator: str) -> str:
	"""Digits only: a leading `-` when negative, no exponent, trailing fractional zeros trimmed."""
	if not number:
		return "0"
	text = format(number, "f")
	if "." in text:
		text = text.rstrip("0").rstrip(".")
	return text.replace(".", decimal_separator)


def _plain_number(value: str, number_format) -> str:
	if number_format.thousands_separator:
		value = value.replace(number_format.thousands_separator, "")
	if number_format.decimal_separator:
		value = value.replace(number_format.decimal_separator, ".")
	return value


def _strptime_format(date_format: str) -> str:
	"""Frappe's `dd-mm-yyyy` style as a `strptime` pattern."""
	pattern = date_format.lower()
	for token, directive in (("yyyy", "%Y"), ("dd", "%d"), ("mm", "%m")):
		pattern = pattern.replace(token, directive)
	return pattern
