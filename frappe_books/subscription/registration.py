"""`bench books-register-site` (spec 0008 AC-1): registers one site of this hosting bench with the control site
and writes the control URL and the site's secret into its `site_config.json`.

It signs with the bench's runner secret from `<bench>/config/books-runner.json` (spec 0007), like the removal
runner, and never prints or logs the site secret.
"""

import re
from collections.abc import Callable

import frappe
from frappe.installer import update_site_config
from frappe.utils import get_bench_path, validate_email_address

from frappe_books.subscription import runner
from frappe_books.subscription.runner import ControlRefused, RunnerConfigError

REGISTER_SITE = "rarebooks_control.api.register_site"
# 32 random bytes as hex, as the control site makes them.
SECRET_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def register(
	site: str,
	owner_email: str,
	site_url: str,
	bench_path: str | None = None,
	log: Callable[[str], None] = print,
) -> int:
	"""Register `site` and store its secret. Returns the process exit code. Safe to run again."""
	problem = _argument_problem(site, owner_email, site_url)
	if problem:
		log(f"stopped: {problem}")
		return 1
	try:
		config = runner.load_config(bench_path or get_bench_path(), need_storage=False)
	except RunnerConfigError as error:
		log(f"stopped: {error}")
		return 1

	payload = {"site": site, "site_url": site_url.rstrip("/"), "owner_email": owner_email}
	try:
		answer = runner.signed_call(config, REGISTER_SITE, payload)
	except ControlRefused as error:
		log(f"stopped: {error}")
		return 1
	secret = answer.get("secret")
	if answer.get("site") != site or not isinstance(secret, str) or not SECRET_PATTERN.match(secret):
		log("stopped: register_site answered without this site's secret")
		return 1

	with runner.open_site(site):
		already = frappe.conf.get("books_control_secret") == secret
		update_site_config("books_control_url", config.control_url)
		update_site_config("books_control_secret", secret)

	if already:
		log(
			f"{site}: already registered, nothing changed. The control site keeps its owner email and "
			"site URL; edit them there if they are wrong"
		)
	else:
		log(f"{site}: registered with {config.control_url}")
	return 0


def _argument_problem(site: str, owner_email: str, site_url: str) -> str | None:
	"""Checked before any call to the control site."""
	if not site_url.startswith("https://"):
		return "--site-url must start with https://"
	if not validate_email_address(owner_email):
		return "--owner-email is not a valid email address"
	if site not in runner.bench_sites():
		return f"{site} is not a site of this bench"
	return None
