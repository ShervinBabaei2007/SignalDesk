"""Test setup: keep a developer's real .env (production secrets, Postgres URL) out of the test run."""

import os

# config.py loads .env without overriding variables that are already set, so pin them here first.
for _name, _value in {
    "APP_ENV": "development",
    "API_TOKEN": "",
    "CRON_SECRET": "",
    "SCHEDULER_DISABLED": "false",
    "CORS_ORIGINS": "*",
}.items():
    os.environ[_name] = _value
