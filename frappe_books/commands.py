"""Bench commands of frappe_books. Bench loads the module level `commands` list from each app."""

import sys

import click


@click.command("books-removal-run")
def books_removal_run():
	"""Report this bench's hosted sites to the control site and carry out its removal instructions (spec 0007).

	Does nothing while `books_removal_mode` in common_site_config.json is missing or `off`. Host cron runs it
	hourly under flock, so two runs never overlap.
	"""
	from frappe_books.subscription.runner import run

	sys.exit(run(log=click.echo))


@click.command("books-register-site")
@click.argument("site")
@click.option("--owner-email", required=True, help="The site owner's email, for receipts")
@click.option("--site-url", required=True, help="The site's public https:// URL")
def books_register_site(site, owner_email, site_url):
	"""Register a site of this bench with the control site and store its secret (spec 0008).

	Signs with this bench's runner secret from config/books-runner.json. Running it again changes nothing.
	"""
	from frappe_books.subscription.registration import register

	sys.exit(register(site, owner_email, site_url, log=click.echo))


@click.command("books-removal-check")
@click.option("--upload-probe", is_flag=True, help="Also upload a tiny object to R2 with the runner's token")
def books_removal_check(upload_probe):
	"""Check this bench is ready for trial end removal before its mode goes to dry_run or live (spec 0007).

	Reads the secrets file, common_site_config.json, every site's server script setting and the crontab. Changes
	nothing, except the probe upload when asked, which lands under exports/ so the 90 day rule removes it.
	"""
	from frappe.utils import get_bench_path

	from frappe_books.subscription.rollout import preflight

	sys.exit(preflight(get_bench_path(), upload_probe=upload_probe, log=click.echo))


@click.command("books-removal-setup-bucket")
@click.option(
	"--endpoint-url", required=True, help="The R2 S3 endpoint, https://<account id>.r2.cloudflarestorage.com"
)
@click.option("--bucket", required=True, help="The private export bucket")
def books_removal_setup_bucket(endpoint_url, bucket):
	"""Put the two lifecycle rules of spec 0007 AC-16 on the R2 export bucket. Safe to run again.

	Takes an R2 admin token from AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, never from the command line.
	"""
	from frappe_books.subscription.rollout import LifecycleError, make_admin_client, setup_bucket

	try:
		client = make_admin_client(endpoint_url)
	except LifecycleError as error:
		click.echo(f"FAIL {bucket}: {error}")
		sys.exit(1)
	sys.exit(setup_bucket(client, bucket, log=click.echo))


commands = [books_removal_run, books_register_site, books_removal_check, books_removal_setup_bucket]
