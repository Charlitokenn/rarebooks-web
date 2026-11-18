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


commands = [books_removal_run]
