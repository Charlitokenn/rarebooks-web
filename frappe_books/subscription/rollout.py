"""Rollout helpers for trial end removal (spec 0007, build plan task 13), run by hand on the hosting server.

`setup_bucket` puts the two R2 lifecycle rules of AC-16 on the export bucket. `preflight` checks a bench before
its `books_removal_mode` goes to `dry_run` or `live`: the secrets file, the root login, that no secret sits in
`common_site_config.json` and server scripts stay off (AC-15), and the hourly cron line under `flock` (AC-3).
Neither one changes a site, and neither prints a secret.
"""

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from frappe.utils import get_sites

from frappe_books.subscription.runner import (
	MODE_KEY,
	MODES,
	SECRETS_FILE,
	RunnerConfigError,
	load_config,
	make_storage,
	read_mode,
)

EXPORT_PREFIX = "exports/"
# The rule IDs this helper owns. Any other rule on the bucket is kept as it is.
EXPIRE_RULE = "books-exports-expire-90-days"
ABORT_RULE = "books-abort-multipart-1-day"
EXPORT_DAYS = 90
ABORT_DAYS = 1
LIFECYCLE_RULES = (
	{
		"ID": EXPIRE_RULE,
		"Status": "Enabled",
		"Filter": {"Prefix": EXPORT_PREFIX},
		"Expiration": {"Days": EXPORT_DAYS},
	},
	{
		"ID": ABORT_RULE,
		"Status": "Enabled",
		"Filter": {"Prefix": ""},
		"AbortIncompleteMultipartUpload": {"DaysAfterInitiation": ABORT_DAYS},
	},
)
# Keys that belong in the secrets file only. Every site reads `common_site_config.json` through `frappe.conf`.
SECRET_KEYS = ("runner_secret", "export_storage", "access_key_id", "secret_access_key", "root_password")
CRON_COMMAND = "books-removal-run"
# Under `exports/`, so the 90 day rule deletes it too: the runner never deletes an R2 object (spec 0007).
PROBE_PREFIX = EXPORT_PREFIX + "preflight/"


class LifecycleError(Exception):
	pass


# R2 bucket lifecycle (AC-16)


def setup_bucket(client, bucket: str, log: Callable[[str], None] = print) -> int:
	"""Put both lifecycle rules on `bucket`, keep every other rule, then read them back. Safe to run again."""
	try:
		kept = [rule for rule in current_rules(client, bucket) if rule.get("ID") not in rule_ids()]
		client.put_bucket_lifecycle_configuration(
			Bucket=bucket, LifecycleConfiguration={"Rules": kept + [dict(rule) for rule in LIFECYCLE_RULES]}
		)
		check_rules(current_rules(client, bucket))
	except LifecycleError as error:
		log(f"FAIL {bucket}: {error}")
		return 1
	except Exception as error:
		log(f"FAIL {bucket}: {type(error).__name__}: {error_code(error)}")
		return 1
	log(f"ok   {bucket}: {EXPORT_PREFIX} objects expire after {EXPORT_DAYS} days")
	log(f"ok   {bucket}: unfinished multipart uploads abort after {ABORT_DAYS} day")
	if kept:
		log(f"ok   {bucket}: kept {len(kept)} other rule(s): {', '.join(str(r.get('ID')) for r in kept)}")
	return 0


def current_rules(client, bucket: str) -> list[dict]:
	try:
		return client.get_bucket_lifecycle_configuration(Bucket=bucket).get("Rules", [])
	except Exception as error:
		if error_code(error) == "NoSuchLifecycleConfiguration":
			return []
		raise


def check_rules(rules: list[dict]):
	"""Raises unless the bucket now holds both rules as written."""
	by_id = {rule.get("ID"): rule for rule in rules}
	expire, abort = by_id.get(EXPIRE_RULE), by_id.get(ABORT_RULE)
	if not expire or not abort:
		raise LifecycleError("the bucket didn't keep both lifecycle rules")
	if (
		expire.get("Status") != "Enabled"
		or _prefix(expire) != EXPORT_PREFIX
		or (expire.get("Expiration") or {}).get("Days") != EXPORT_DAYS
	):
		raise LifecycleError(f"rule {EXPIRE_RULE} reads back different from what was written")
	if (
		abort.get("Status") != "Enabled"
		or _prefix(abort) != ""
		or (abort.get("AbortIncompleteMultipartUpload") or {}).get("DaysAfterInitiation") != ABORT_DAYS
	):
		raise LifecycleError(f"rule {ABORT_RULE} reads back different from what was written")


def rule_ids() -> set[str]:
	return {rule["ID"] for rule in LIFECYCLE_RULES}


def make_admin_client(endpoint_url: str):
	"""An S3 client for R2 with the bucket admin token from the environment, never from argv or a file here.

	Lifecycle rules need more than the runner's object token, so this uses a separate one you hold yourself.
	"""
	import boto3

	if not endpoint_url.startswith("https://"):
		raise LifecycleError("the endpoint URL must start with https://")
	if not os.environ.get("AWS_ACCESS_KEY_ID") or not os.environ.get("AWS_SECRET_ACCESS_KEY"):
		raise LifecycleError("set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY to an R2 admin token first")
	return boto3.client("s3", endpoint_url=endpoint_url, region_name="auto")


def error_code(error: Exception) -> str:
	"""The S3 error code alone, so no request detail reaches the log."""
	response = getattr(error, "response", None)
	if isinstance(response, dict):
		return str((response.get("Error") or {}).get("Code") or "")
	return ""


def _prefix(rule: dict) -> str:
	return (rule.get("Filter") or {}).get("Prefix") or rule.get("Prefix") or ""


# Bench preflight (AC-3, AC-15)


@dataclass
class Check:
	name: str
	ok: bool
	detail: str


def preflight(bench_path: str, upload_probe: bool = False, log: Callable[[str], None] = print) -> int:
	"""Check this bench is ready for `dry_run` or `live`. Returns 1 when any check fails."""
	checks = [check_mode(bench_path)]
	config_check, config = check_secrets_file(bench_path)
	checks.append(config_check)
	if config:
		checks.append(check_root_login(config))
	checks.append(check_common_config(bench_path))
	checks.append(check_server_scripts(bench_path))
	checks.append(check_cron(read_crontab()))
	if upload_probe:
		checks.append(check_probe(config))
	for check in checks:
		log(f"{'ok  ' if check.ok else 'FAIL'} {check.name}: {check.detail}")
	return 0 if all(check.ok for check in checks) else 1


def check_mode(bench_path: str) -> Check:
	path = os.path.join(bench_path, "sites", "common_site_config.json")
	raw = _read_json(path).get(MODE_KEY)
	if raw is not None and raw not in MODES:
		return Check(
			"mode", False, f"{MODE_KEY} is {raw!r}, the runner reads that as off; use {', '.join(MODES)}"
		)
	return Check("mode", True, f"{MODE_KEY} is {read_mode(bench_path)}")


def check_secrets_file(bench_path: str):
	try:
		config = load_config(bench_path)
	except RunnerConfigError as error:
		return Check("secrets file", False, str(error)), None
	return Check("secrets file", True, f"{SECRETS_FILE} is mode 600, runner {config.runner_name}"), config


def check_root_login(config) -> Check:
	if not config.root_login or not config.root_password:
		return Check(
			"root login", False, f"root_login and root_password are needed in {SECRETS_FILE} to drop"
		)
	return Check("root login", True, f"set for {config.root_login}")


def check_common_config(bench_path: str) -> Check:
	conf = _read_json(os.path.join(bench_path, "sites", "common_site_config.json"))
	found = sorted(key for key in SECRET_KEYS if key in conf)
	if found:
		return Check(
			"common_site_config.json",
			False,
			f"move {', '.join(found)} to {SECRETS_FILE}, every site reads it",
		)
	return Check("common_site_config.json", True, "holds no runner secret")


def check_server_scripts(bench_path: str) -> Check:
	sites_path = os.path.join(bench_path, "sites")
	if _read_json(os.path.join(sites_path, "common_site_config.json")).get("server_script_enabled"):
		return Check("server scripts", False, "server_script_enabled is on in common_site_config.json")
	on = [
		site
		for site in get_sites(sites_path)
		if _read_json(os.path.join(sites_path, site, "site_config.json")).get("server_script_enabled")
	]
	if on:
		return Check("server scripts", False, f"server_script_enabled is on for {', '.join(sorted(on))}")
	return Check("server scripts", True, "off on every site")


def check_cron(crontab: str | None) -> Check:
	if crontab is None:
		return Check("cron", False, "couldn't read the bench user's crontab")
	lines = [line.strip() for line in crontab.splitlines() if not line.strip().startswith("#")]
	runs = [line for line in lines if CRON_COMMAND in line]
	if not runs:
		return Check("cron", False, f"no line runs bench {CRON_COMMAND}")
	if not all("flock" in line for line in runs):
		return Check("cron", False, f"run bench {CRON_COMMAND} under flock -n, so two runs never overlap")
	if len(runs) > 1:
		return Check("cron", False, f"{len(runs)} lines run bench {CRON_COMMAND}, keep one")
	if not shutil.which("flock"):
		return Check("cron", False, "flock isn't installed")
	return Check("cron", True, runs[0])


def check_probe(config) -> Check:
	"""A tiny upload with the runner's own token, under `exports/` so the lifecycle rule removes it."""
	if not config:
		return Check("R2 upload", False, "skipped, the secrets file didn't load")
	key = f"{PROBE_PREFIX}{config.runner_name}-{uuid4()}.txt"
	folder = tempfile.mkdtemp(prefix="books-preflight-")
	try:
		path = os.path.join(folder, "probe.txt")
		with open(path, "w") as handle:
			handle.write("books-removal-check\n")
		make_storage(config.export_storage).upload(path, key)
	except Exception as error:
		text = f"{type(error).__name__}: {error}"
		for secret in config.secrets():
			text = text.replace(secret, "***")
		return Check("R2 upload", False, text[:500])
	finally:
		shutil.rmtree(folder, ignore_errors=True)
	return Check("R2 upload", True, f"wrote {key} to {config.export_storage['bucket']}")


def read_crontab() -> str | None:
	try:
		result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
	except (OSError, subprocess.SubprocessError):
		return None
	# `crontab -l` exits 1 with "no crontab for <user>" when there is none: that reads as an empty one.
	return result.stdout if result.returncode in (0, 1) else None


def _read_json(path: str) -> dict:
	try:
		with open(path) as handle:
			data = json.load(handle)
	except (OSError, ValueError):
		return {}
	return data if isinstance(data, dict) else {}
