"""The runner's `rotate_secret` step (spec 0008 AC-15): write the site's new control secret, then tell the
control site, before any removal instruction."""

import secrets
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from frappe_books.subscription.runner import run
from frappe_books.tests.removal import RemovalControlStub, runner_bench
from frappe_books.tests.subscription import SubscriptionTestMixin, lock_site

CASE = "RC-00001"


class IntegrationTestRunnerRotation(SubscriptionTestMixin, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.lines = []
		self.secret = secrets.token_hex(32)
		lock_site()
		writes = patch("frappe_books.subscription.runner.update_site_config")
		self.update_site_config = writes.start()
		self.addCleanup(writes.stop)

	def run_bench(self, stub, **options):
		with runner_bench(stub, **options) as bench:
			return run(bench_path=bench, log=self.lines.append)

	def rotation(self, **values):
		return {"site": frappe.local.site, "action": "rotate_secret", "secret": self.secret, **values}

	def test_writes_the_secret_then_calls_secret_rotated_before_any_clear(self):
		# covers: AC-15
		clear = {"site": frappe.local.site, "case": CASE, "action": "clear"}
		stub = RemovalControlStub([clear, self.rotation()])
		self.assertEqual(self.run_bench(stub), 0)
		self.update_site_config.assert_called_once_with("books_control_secret", self.secret)
		self.assertEqual(stub.methods(), ["report_sites", "secret_rotated"])
		self.assertEqual(stub.bodies("secret_rotated")[0]["site"], frappe.local.site)
		self.assertNotIn("secret", stub.bodies("secret_rotated")[0])
		log = "\n".join(self.lines)
		self.assertIn("rotate_secret done", log)
		self.assertLess(log.index("rotate_secret done"), log.index(f"clear {CASE}"))
		self.assertNotIn(self.secret, log)

	def test_rotates_in_dry_run_too(self):
		# covers: AC-15 (a rotation is billing, not a removal write)
		stub = RemovalControlStub([self.rotation()])
		self.run_bench(stub, mode="dry_run")
		self.update_site_config.assert_called_once_with("books_control_secret", self.secret)
		self.assertEqual(stub.methods(), ["report_sites", "secret_rotated"])

	def test_a_bad_secret_or_another_site_is_ignored_and_never_logged(self):
		# covers: AC-15 (no secret written to any log)
		bad = [
			self.rotation(secret="short"),
			self.rotation(secret=self.secret.upper()),
			self.rotation(secret=None),
			self.rotation(site="other.example.com"),
		]
		stub = RemovalControlStub(bad)
		self.run_bench(stub)
		self.update_site_config.assert_not_called()
		self.assertEqual(stub.methods(), ["report_sites"])
		log = "\n".join(self.lines)
		self.assertEqual(log.count("ignored an instruction"), 4)
		self.assertNotIn(self.secret, log)
		self.assertNotIn(self.secret.upper(), log)

	def test_an_unheard_secret_rotated_is_noted_and_the_run_goes_on(self):
		# covers: AC-15 (the next report carries the same instruction)
		stub = RemovalControlStub([self.rotation()], badly_signed=("secret_rotated",))
		self.assertEqual(self.run_bench(stub), 0)
		self.update_site_config.assert_called_once()
		self.assertIn("secret_rotated wasn't heard", "\n".join(self.lines))
		self.assertNotIn(self.secret, "\n".join(self.lines))
