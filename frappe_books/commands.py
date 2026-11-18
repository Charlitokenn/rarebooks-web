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


commands = [books_removal_run, books_register_site]
