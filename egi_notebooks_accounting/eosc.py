"""EOSC EU Node Accounting implementation

EOSC EU Node expects aggregated accounting information for the number of hours
a given flavor of jupyter server has been running over the last day, following
this definition:

{
    "metric_name": "small-environment-2-vcpu-4-gb-ram",
    "metric_description": "total runtime per day (in hours)",
    "metric_type": "aggregated",
    "unit_type": "Hours/day"
}

The report is done by sending records with a POST API call to:
/accounting-system/installations/{installation_id}/metrics

with a JSON like:
{
  "metric_definition_id": "<metric id (depends on the flavor)>”,
  "time_period_start": "2023-01-05T09:13:07Z",
  "time_period_end": "2024-01-05T09:13:07Z",
  "value": 10.2,
  "group_id": "group id", # personal or group project
  "user_id": "user id" # user aai
}

This code goes to the accounting db and aggregates the information for the last 24 hours
and pushes it to the EOSC Accounting

Configuration:
[default]
notebooks_db=<notebooks db file>

[eosc]
token_url=https://proxy.staging.eosc-federation.eu/OIDC/token
client_secret=<client secret>
client_id=<client_id>
accounting_url=https://api.acc.staging.eosc.grnet.gr
installaion_id=<id of the installation to report accounting for>
timestamp_file=<file where the timestamp of the last run is kept>

[eosc.flavors]
# contains a list of flavors and metrics they are mapped to
<name of the flavor>=<metric id>
# example:
small-environment-2-vcpu-4-gb-ram=668bdd5988e1d617b217ecb9
"""

import argparse
import json
import logging
import os
from configparser import ConfigParser
from datetime import date, datetime, timedelta

import dateutil.parser
import pytz
import requests
from requests.auth import HTTPBasicAuth

from .model import VM, db_init

CONFIG = "default"
EOSC_CONFIG = "eosc"
FLAVOR_CONFIG = "eosc.flavors"
DEFAULT_CONFIG_FILE = "config.ini"
DEFAULT_TOKEN_URL = "https://proxy.staging.eosc-federation.eu/OIDC/token"
DEFAULT_ACCOUNTING_URL = "https://api.acc.staging.eosc.grnet.gr"
DEFAULT_TIMESTAMP_FILE = "eosc-accounting.timestamp"


def get_access_token(token_url, client_id, client_secret):
    response = requests.post(
        token_url,
        auth=HTTPBasicAuth(client_id, client_secret),
        data={
            "grant_type": "client_credentials",
            "scope": "openid email profile voperson_id entitlements",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    return response.json()["access_token"]


def push_metric(accounting_url, token, installation, metric_data):
    logging.debug(f"Pushing to accounting - {installation}")
    response = requests.post(
        f"{accounting_url}/accounting-system/installations/{installation}/metrics",
        headers={"Authorization": f"Bearer {token}"},
        data=json.dumps(metric_data),
    )
    response.raise_for_status()


def update_pod_metric(pod, metrics, flavor_config):
    if not pod.flavor or pod.flavor not in flavor_config:
        # cannot report
        logging.debug(f"Flavor {pod.flavor} does not have a configured metric")
        return
    user, group = (pod.global_user_name, pod.fqan)
    user_metrics = metrics.get((user, group), {})
    flavor_metric = flavor_config[pod.flavor]
    flavor_metric_value = user_metrics.get(flavor_metric, 0)
    user_metrics[flavor_metric] = flavor_metric_value + (pod.wall / (60 * 60))
    metrics[(user, group)] = user_metrics


def get_from_to_dates(args, timestamp_file):
    from_date = None
    if args.from_date:
        from_date = dateutil.parser.parse(args.from_date)
    else:
        try:
            with open(timestamp_file, "r") as tsf:
                try:
                    from_date = dateutil.parser.parse(tsf.read())
                    from_date += timedelta(minutes=1)
                except dateutil.parser.ParserError as e:
                    logging.debug(
                        f"Invalid timestamp content in '{timestamp_file}': {e}"
                    )
        except OSError as e:
            logging.debug(f"Not able to open timestamp file '{timestamp_file}': {e}")
        # no date specified report from yesterday
        if not from_date:
            report_day = date.today() - timedelta(days=1)
            from_date = datetime(
                report_day.year, report_day.month, report_day.day, 0, 0
            )
    if args.to_date:
        to_date = dateutil.parser.parse(args.to_date)
    else:
        # go until last minute of yesterday
        report_day = date.today() - timedelta(days=1)
        to_date = datetime(report_day.year, report_day.month, report_day.day, 23, 59)
    utc = pytz.UTC
    from_date = from_date.replace(tzinfo=utc)
    to_date = to_date.replace(tzinfo=utc)
    return from_date, to_date


def generate_day_metrics(
    period_start,
    period_end,
    accounting_url,
    token,
    flavor_config,
    timestamp_file,
    installation,
    dry_run,
):
    logging.info(f"Generate metrics from {period_start} to {period_end}")
    metrics = {}
    # pods ending in between the reporting times
    for pod in VM.select().where(
        (VM.end_time >= period_start) & (VM.end_time <= period_end)
    ):
        update_pod_metric(pod, metrics, flavor_config)
    # pods starting but not finished between the reporting times
    for pod in VM.select().where(
        (VM.start_time >= period_start) & (VM.end_time is None)
    ):
        update_pod_metric(pod, metrics, flavor_config)
    period_start_str = period_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    period_end_str = period_end.strftime("%Y-%m-%dT%H:%M:%SZ")
    for (user, group), flavors in metrics.items():
        for metric_key, value in flavors.items():
            metric_data = {
                "metric_definition_id": metric_key,
                "time_period_start": period_start_str,
                "time_period_end": period_end_str,
                "user_id": user,
                "group_id": group,
                "value": value,
            }
            logging.debug(f"Sending metric {metric_data} to accounting")
            if dry_run:
                logging.debug("Dry run, not sending")
            else:
                push_metric(accounting_url, token, installation, metric_data)
    if not dry_run:
        try:
            with open(timestamp_file, "w+") as tsf:
                tsf.write(period_end.strftime("%Y-%m-%dT%H:%M:%SZ"))
        except OSError as e:
            e = str(e)
            logging.debug("Failed to write timestamp file '{timestamp_file}': {e}")


def main():
    parser = argparse.ArgumentParser(description="EOSC Accounting metric pusher")
    parser.add_argument(
        "-c", "--config", help="config file", default=DEFAULT_CONFIG_FILE
    )
    parser.add_argument(
        "--dry-run", help="Do not actually send data, just report", action="store_true"
    )
    parser.add_argument("--from-date", help="Start date to report from")
    parser.add_argument("--to-date", help="End date to report to")
    args = parser.parse_args()

    parser = ConfigParser()
    parser.read(args.config)
    config = parser[CONFIG] if CONFIG in parser else {}
    eosc_config = parser[EOSC_CONFIG] if EOSC_CONFIG in parser else {}
    flavor_config = parser[FLAVOR_CONFIG] if FLAVOR_CONFIG in parser else {}
    db_file = os.environ.get("NOTEBOOKS_DB", config.get("notebooks_db", None))
    db_init(db_file)

    verbose = os.environ.get("VERBOSE", config.get("verbose", 0))
    verbose = logging.DEBUG if verbose == "1" else logging.INFO
    logging.basicConfig(level=verbose)

    # EOSC accounting config
    # AAI
    token_url = os.environ.get(
        "TOKEN_URL", eosc_config.get("token_url", DEFAULT_TOKEN_URL)
    )
    client_id = os.environ.get("CLIENT_ID", eosc_config.get("client_id", ""))
    client_secret = os.environ.get(
        "CLIENT_SECRET", eosc_config.get("client_secret", "")
    )
    if args.dry_run:
        logging.debug("Not getting credentials, dry-run")
        token = None
    else:
        token = get_access_token(token_url, client_id, client_secret)

    accounting_url = os.environ.get(
        "ACCOUNTING_URL", eosc_config.get("accounting_url", DEFAULT_ACCOUNTING_URL)
    )
    installation = eosc_config.get("installation_id", "")

    timestamp_file = os.environ.get(
        "TIMESTAMP_FILE", eosc_config.get("timestamp_file", DEFAULT_TIMESTAMP_FILE)
    )

    # ==== queries ====
    from_date, to_date = get_from_to_dates(args, timestamp_file)
    logging.debug(f"Reporting from {from_date} to {to_date}")
    # repeat in 24 hour intervals
    period_start = from_date
    while period_start <= to_date:
        period_end = period_start + timedelta(hours=23, minutes=59)
        generate_day_metrics(
            period_start,
            period_end,
            accounting_url,
            token,
            flavor_config,
            timestamp_file,
            installation,
            args.dry_run,
        )
        period_start = period_end + timedelta(minutes=1)


if __name__ == "__main__":
    main()
