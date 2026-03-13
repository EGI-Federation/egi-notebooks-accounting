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

Configuration (default and aai sections are common from recordpusher.py):
```
[default]
notebooks_db=<notebooks db file>
timeout=120
timestamp_file=<file where the timestamp of the last run is kept>

[aai]
token_url=https://proxy.staging.eosc-federation.eu/OIDC/token
client_secret=<client secret>
client_id=<client_id>
scope=<scopes>

[eosc]
accounting_url=https://api.acc.staging.eosc.grnet.gr
installation_id=<id of the installation to report accounting for>

[eosc.flavors]
# contains a list of flavors and metrics they are mapped to
<name of the flavor>=<metric id>
# example:
small-environment-2-vcpu-4-gb-ram=668bdd5988e1d617b217ecb9
```
"""

import logging
import json
import os
from datetime import timezone

import requests

from .model import VM
from .recordpusher import RecordPusher

EOSC_CONFIG = "eosc"
FLAVOR_CONFIG = "eosc.flavors"
DEFAULT_ACCOUNTING_URL = "https://api.acc.staging.eosc.grnet.gr"
DEFAULT_TIMESTAMP_FILE = "eosc-accounting.timestamp"
DEFAULT_TOKEN_URL = "https://proxy.staging.eosc-federation.eu/OIDC/token"
DEFAULT_SCOPE = "openid email profile voperson_id entitlements"


class EOSCRecordPusher(RecordPusher):
    description = "EOSC Accounting metric pusher"
    default_token_url = DEFAULT_TOKEN_URL
    default_timestamp_file = DEFAULT_TIMESTAMP_FILE
    default_scope = DEFAULT_SCOPE

    def configure(self, config_file):
        # common values from super
        parser = super().configure(config_file)
        eosc_config = parser[EOSC_CONFIG] if EOSC_CONFIG in parser else {}

        # EOSC accounting config
        self.accounting_url = os.environ.get(
            "ACCOUNTING_URL", eosc_config.get("accounting_url", DEFAULT_ACCOUNTING_URL)
        )
        self.installation = eosc_config.get("installation_id", "")
        # Flavors config
        self.flavor_config = parser[FLAVOR_CONFIG] if FLAVOR_CONFIG in parser else {}

    def push_metric(self, metric_data):
        if self.dry_run:
            logging.debug("Dry run, not sending")
        else:
            logging.debug(f"Pushing to accounting - {self.installation}")
            response = requests.post(
                f"{self.accounting_url}/accounting-system/installations/{self.installation}/metrics",
                headers={"Authorization": f"Bearer {self.token}"},
                data=json.dumps(metric_data),
                timeout=self.timeout,
            )
            response.raise_for_status()

    def update_pod_metric(self, pod, metrics, period_start, period_end):
        if not pod.flavor or pod.flavor not in self.flavor_config:
            # cannot report
            logging.debug(f"Flavor {pod.flavor} does not have a configured metric")
            return
        user, group = (pod.global_user_name, pod.fqan)
        user_metrics = metrics.get((user, group), {})
        flavor_metric = self.flavor_config[pod.flavor]
        metrics[(user, group)] = user_metrics

        if pod.start_time is None:
            report_start_time = period_start
        else:
            report_start_time = max(
                period_start, pod.start_time.replace(tzinfo=timezone.utc)
            )
        if pod.end_time is None:
            report_end_time = period_end
        else:
            report_end_time = min(period_end, pod.end_time.replace(tzinfo=timezone.utc))
        flavor_metric_value = user_metrics.get(flavor_metric, 0)
        user_metrics[flavor_metric] = (
            flavor_metric_value + (report_end_time - report_start_time).total_seconds()
        )

    def generate_day_metrics(self, period_start, period_end):
        logging.info(f"Generate metrics from {period_start} to {period_end}")
        metrics = {}
        # pods ending in between the reporting times
        count = 0
        for pod in VM.select().where(
            (VM.end_time >= period_start) & (VM.end_time < period_end)
        ):
            self.update_pod_metric(
                pod,
                metrics,
                period_start,
                period_end,
            )
            count = count + 1
        logging.debug(f"=> {count} pods ending in between the reporting times")

        # pods starting but not finished between the reporting times
        count = 0
        for pod in VM.select().where(
            (VM.start_time < period_end)
            & (VM.end_time.is_null() | (VM.end_time >= period_end))
        ):
            self.update_pod_metric(
                pod,
                metrics,
                period_start,
                period_end,
            )
            count = count + 1
        logging.debug(
            f"=> {count} pods starting but not finished between the reporting times"
        )
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
                    # Need to convert to hours
                    "value": value / (60 * 60),
                }
                logging.debug(f"Sending metric {metric_data} to accounting")
                self.push_metric(metric_data)


def main(argv=None):
    pusher = EOSCRecordPusher()
    pusher.run(argv)


if __name__ == "__main__":
    main()
