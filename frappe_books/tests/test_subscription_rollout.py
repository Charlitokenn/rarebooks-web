"""Rollout helpers for trial end removal (spec 0007, build plan task 13): the R2 lifecycle rules and the bench
preflight. No database and no network: a fake S3 client and throwaway bench folders."""

import copy
import json
import os
import shutil
import tempfile
from unittest.mock import patch

from botocore.exceptions import ClientError
from frappe.tests import UnitTestCase

from frappe_books.subscription.rollout import (
	ABORT_RULE,
	EXPIRE_RULE,
	PROBE_PREFIX,
	check_cron,
	preflight,
	setup_bucket,
)
from frappe_books.tests.removal import ROOT_PASSWORD, STORAGE, FakeStorage, runner_secrets

BUCKET = "books-exports"
CRON_LINE = (
	"0 * * * * cd /home/frappe/bench && flock -n /tmp/books-removal.lock "
	"bench books-removal-run >> logs/books-removal.log 2>&1"
)
R2_DEFAULT_RULE = {
	"ID": "Default Multipart Abort Rule",
	"Status": "Enabled",
	"Filter": {"Prefix": ""},
	"AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
}


class FakeS3:
	"""Holds one bucket's lifecycle rules, as the S3 API on R2 answers them."""

	def __init__(self, rules=None, drop_on_put=None):
		self.rules = rules
		self.puts = 0
		self.drop_on_put = drop_on_put

	def get_bucket_lifecycle_configuration(self, Bucket):
		if self.rules is None:
			error = {"Error": {"Code": "NoSuchLifecycleConfiguration", "Message": "none"}}
			raise ClientError(error, "GetBucketLifecycleConfiguration")
		return {"Rules": copy.deepcopy(self.rules)}

	def put_bucket_lifecycle_configuration(self, Bucket, LifecycleConfiguration):
		self.puts += 1
		rules = copy.deepcopy(LifecycleConfiguration["Rules"])
		self.rules = [rule for rule in rules if rule["ID"] != self.drop_on_put]


class UnitTestLifecycleRules(UnitTestCase):
	def setUp(self):
		self.lines = []

	def setup(self, client):
		return setup_bucket(client, BUCKET, log=self.lines.append)

	def by_id(self, client):
		return {rule["ID"]: rule for rule in client.rules}

	def test_a_bucket_with_no_rules_gets_both(self):
		# covers: AC-16
		client = FakeS3()
		self.assertEqual(self.setup(client), 0)
		rules = self.by_id(client)
		self.assertEqual(rules[EXPIRE_RULE]["Filter"], {"Prefix": "exports/"})
		self.assertEqual(rules[EXPIRE_RULE]["Expiration"], {"Days": 90})
		self.assertEqual(rules[ABORT_RULE]["AbortIncompleteMultipartUpload"], {"DaysAfterInitiation": 1})
		self.assertTrue(all(line.startswith("ok") for line in self.lines))

	def test_running_it_again_changes_nothing_and_keeps_other_rules(self):
		# covers: AC-16
		client = FakeS3(rules=[R2_DEFAULT_RULE])
		self.setup(client)
		first = copy.deepcopy(client.rules)
		self.assertEqual(self.setup(client), 0)
		self.assertEqual(client.rules, first)
		self.assertEqual(len(client.rules), 3)
		self.assertIn(R2_DEFAULT_RULE["ID"], self.by_id(client))

	def test_an_older_copy_of_its_own_rule_is_replaced(self):
		# covers: AC-16
		stale = {
			"ID": EXPIRE_RULE,
			"Status": "Disabled",
			"Filter": {"Prefix": "x/"},
			"Expiration": {"Days": 5},
		}
		client = FakeS3(rules=[stale])
		self.assertEqual(self.setup(client), 0)
		self.assertEqual([rule["ID"] for rule in client.rules].count(EXPIRE_RULE), 1)
		self.assertEqual(self.by_id(client)[EXPIRE_RULE]["Expiration"], {"Days": 90})

	def test_a_rule_the_bucket_did_not_keep_fails(self):
		# covers: AC-16
		client = FakeS3(drop_on_put=ABORT_RULE)
		self.assertEqual(self.setup(client), 1)
		self.assertIn("didn't keep both", self.lines[-1])

	def test_an_s3_error_reports_only_its_code(self):
		# covers: AC-16
		client = FakeS3()
		error = {"Error": {"Code": "AccessDenied", "Message": "token abc123 can't"}}
		client.put_bucket_lifecycle_configuration = patch_raise(ClientError(error, "Put"))
		self.assertEqual(self.setup(client), 1)
		self.assertEqual(self.lines, [f"FAIL {BUCKET}: ClientError: AccessDenied"])


def patch_raise(error):
	def raise_it(**_kwargs):
		raise error

	return raise_it


class UnitTestPreflight(UnitTestCase):
	def setUp(self):
		self.bench = tempfile.mkdtemp(prefix="books-preflight-bench-")
		self.addCleanup(shutil.rmtree, self.bench, ignore_errors=True)
		os.makedirs(os.path.join(self.bench, "config"))
		self.write_common({"books_removal_mode": "dry_run"})
		self.write_site("one.example.com", {"books_control_url": "https://control.example.com"})
		self.write_secrets(runner_secrets())
		self.crontab = CRON_LINE + "\n"
		self.lines = []

	def write_common(self, conf):
		self.write_json(os.path.join(self.bench, "sites", "common_site_config.json"), conf)

	def write_site(self, site, conf):
		self.write_json(os.path.join(self.bench, "sites", site, "site_config.json"), conf)

	def write_secrets(self, values, mode=0o600):
		path = os.path.join(self.bench, "config", "books-runner.json")
		self.write_json(path, values)
		os.chmod(path, mode)

	def write_json(self, path, data):
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "w") as handle:
			json.dump(data, handle)

	def run_check(self, **kwargs):
		with (
			patch("frappe_books.subscription.rollout.read_crontab", return_value=self.crontab),
			patch("frappe_books.subscription.rollout.shutil.which", return_value="/usr/bin/flock"),
		):
			return preflight(self.bench, log=self.lines.append, **kwargs)

	def failed(self):
		return [line for line in self.lines if line.startswith("FAIL")]

	def test_a_ready_bench_passes_every_check(self):
		# covers: AC-3, AC-15
		self.assertEqual(self.run_check(), 0)
		self.assertEqual(self.failed(), [])
		self.assertIn("ok   mode: books_removal_mode is dry_run", self.lines)

	def test_no_line_ever_shows_a_secret(self):
		# covers: AC-15
		self.write_common({"books_removal_mode": "live", "runner_secret": "x" * 40})
		self.run_check()
		text = "\n".join(self.lines)
		for secret in (
			ROOT_PASSWORD,
			STORAGE["secret_access_key"],
			runner_secrets()["runner_secret"],
			"x" * 40,
		):
			self.assertNotIn(secret, text)

	def test_a_secrets_file_others_can_read_fails(self):
		# covers: AC-15
		self.write_secrets(runner_secrets(), mode=0o644)
		self.assertEqual(self.run_check(), 1)
		self.assertIn("mode 600", self.failed()[0])

	def test_a_missing_root_login_fails(self):
		# covers: AC-10
		self.write_secrets(runner_secrets(root_password=None))
		self.assertEqual(self.run_check(), 1)
		self.assertIn("root login", self.failed()[0])

	def test_a_secret_in_common_site_config_fails(self):
		# covers: AC-15
		self.write_common({"books_removal_mode": "dry_run", "export_storage": STORAGE})
		self.assertEqual(self.run_check(), 1)
		self.assertIn("move export_storage", self.failed()[0])

	def test_a_site_with_server_scripts_on_fails(self):
		# covers: AC-15
		self.write_site("two.example.com", {"server_script_enabled": 1})
		self.assertEqual(self.run_check(), 1)
		self.assertIn("two.example.com", self.failed()[0])

	def test_an_unknown_mode_fails(self):
		# covers: AC-3
		self.write_common({"books_removal_mode": "on"})
		self.assertEqual(self.run_check(), 1)
		self.assertIn("reads that as off", self.failed()[0])

	def test_the_probe_uploads_under_exports_with_the_runner_token(self):
		# covers: AC-7, AC-16
		storage = FakeStorage()
		with patch("frappe_books.subscription.rollout.make_storage", return_value=storage) as make:
			self.assertEqual(self.run_check(upload_probe=True), 0)
		make.assert_called_once_with(STORAGE)
		[key] = storage.objects
		self.assertTrue(key.startswith(PROBE_PREFIX))

	def test_a_failed_probe_is_scrubbed_of_secrets(self):
		# covers: AC-15
		storage = FakeStorage(error=RuntimeError(f"denied for {STORAGE['access_key_id']}"))
		with patch("frappe_books.subscription.rollout.make_storage", return_value=storage):
			self.assertEqual(self.run_check(upload_probe=True), 1)
		self.assertIn("denied for ***", self.failed()[0])


class UnitTestCronLine(UnitTestCase):
	def check(self, crontab):
		with patch("frappe_books.subscription.rollout.shutil.which", return_value="/usr/bin/flock"):
			return check_cron(crontab)

	def test_the_spec_line_passes(self):
		# covers: AC-3
		self.assertTrue(self.check(CRON_LINE).ok)

	def test_no_line_or_a_commented_one_fails(self):
		# covers: AC-3
		self.assertFalse(self.check("").ok)
		self.assertFalse(self.check("# " + CRON_LINE).ok)

	def test_a_line_without_flock_fails(self):
		# covers: AC-3
		self.assertIn("flock", self.check("0 * * * * cd /b && bench books-removal-run").detail)

	def test_two_lines_fail(self):
		# covers: AC-3
		self.assertIn("keep one", self.check(f"{CRON_LINE}\n{CRON_LINE}").detail)

	def test_an_unreadable_crontab_fails(self):
		# covers: AC-3
		self.assertFalse(self.check(None).ok)
