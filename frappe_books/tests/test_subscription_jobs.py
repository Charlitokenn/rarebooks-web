import frappe
from frappe.tests import IntegrationTestCase

from frappe_books.subscription.lock import RUN_SCHEDULED_JOB
from frappe_books.tests.subscription import SubscriptionTestMixin, lock_site, run_jobs

WRITE_AFTER_COMMIT = "frappe_books.tests.subscription.write_after_commit_job"


class IntegrationTestJobLock(SubscriptionTestMixin, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		lock_site()
		self.todo = frappe.get_doc({"doctype": "ToDo", "description": "scheduled marker"}).insert()
		frappe.db.commit()

	def tearDown(self):
		frappe.db.rollback()
		frappe.delete_doc("ToDo", self.todo.name, force=True)
		frappe.db.commit()
		super().tearDown()

	def description(self):
		return frappe.db.get_value("ToDo", self.todo.name, "description")

	def test_a_queued_job_on_a_locked_site_writes_nothing_even_after_a_commit(self):
		(error,) = run_jobs((WRITE_AFTER_COMMIT, {"todo": self.todo.name}, True))
		self.assertIsInstance(error, frappe.InReadOnlyMode)
		self.assertEqual(self.description(), "scheduled marker")

	def test_the_next_unlocked_job_in_the_same_worker_writes(self):
		locked, unlocked = run_jobs(
			(WRITE_AFTER_COMMIT, {"todo": self.todo.name}, True),
			(WRITE_AFTER_COMMIT, {"todo": self.todo.name}, False),
		)
		self.assertIsInstance(locked, frappe.InReadOnlyMode)
		self.assertIsNone(unlocked)
		self.assertEqual(self.description(), "job wrote")

	def test_scheduled_jobs_run_on_a_locked_site(self):
		job_type = frappe.get_doc(
			{
				"doctype": "Scheduled Job Type",
				"method": "frappe_books.tests.subscription.scheduled_write_job",
				"frequency": "Daily",
				"create_log": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		try:
			(error,) = run_jobs((RUN_SCHEDULED_JOB, {"scheduled_job_type": job_type.name}, True))
			self.assertIsNone(error)
			self.assertEqual(self.description(), "job wrote")
		finally:
			frappe.delete_doc("Scheduled Job Type", job_type.name, force=True)
			frappe.db.commit()
