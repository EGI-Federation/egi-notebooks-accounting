"""D4Science Accounting implementation


D4Science has its own format for accounting records, that needs to be posted to
https://accounting-service.d4science.org/accounting-service/record with a valid
token.

Each record is a object as follows:

```
{
    "recordType": "JobUsageRecord",
    "jobName": "<JOB NAME>",
    "operationCount": 1,
    "creationTime": 1677252097731,  /* milliseconds since Unix Epoch */
    "serviceClass": "ServiceClass", /* The service class of the service launching the JOB */
    "callerQualifier": "TOKEN",
    "consumerId": "<USERNAME>",
    "aggregated": true,
    "serviceName": "ServiceName", /* The service name of the service launching the JOB */
    "duration": 376,
    "maxInvocationTime": 376,
    "scope": "<CONTEXT>",
    "host": "<HOST>",
    "startTime": 1677252097729,
    "id": "dd458c96-b54e-4d52-afd5-0b430966d9ca",
    "endTime": 1677252097729,
    "minInvocationTime": 376,
    "operationResult": "SUCCESS"
}
```

These can be sent when the job is over.

This code goes to the accounting db and sends the records for the jobs finished
on the last 24 hours

Configuration:
[default]
notebooks_db=<notebooks db file>
timestamp_file=<file where the timestamp of the last run is kept>
timeout=120

[aai]
token_url=https://proxy.staging.eosc-federation.eu/OIDC/token
client_secret=<client secret>
client_id=<client_id>
scope=<scopes>


[d4science]
accounting_url=https://accounting-service.d4science.org/accounting-service/record
"""

import json
import logging
import os
from datetime import timezone

import escapism
import requests

from .model import VM
from .recordpusher import RecordPusher

D4SCIENCE_CONFIG = "d4science"
DEFAULT_ACCOUNTING_URL = "https://api.acc.staging.eosc.grnet.gr"


class D4ScienceRecordPusher(RecordPusher):
    description = "D4Science Accounting metric pusher"
    default_token_url = "https://accounts.d4science.org/auth/realms/d4science/protocol/openid-connect/token"

    def configure(self, config_file):
        # common values from super
        parser = super().configure(config_file)
        d4science_config = (
            parser[D4SCIENCE_CONFIG] if D4SCIENCE_CONFIG in parser else {}
        )
        self.accounting_url = os.environ.get(
            "ACCOUNTING_URL",
            d4science_config.get("accounting_url", DEFAULT_ACCOUNTING_URL),
        )

    def push_records(self, records):
        logging.debug(f"Pushing {len(records)} to accounting")
        if self.dry_run:
            logging.debug("Dry run, not sending")
            return
        response = requests.post(
            f"{self.accounting_url}/",
            headers={"Authorization": f"Bearer {self.token}"},
            data=json.dumps(records),
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

    def generate_record(self, pod):
        # Fields that we are not considering right now:
        # minInvocationTime
        # maxInvocationTime
        service_class = "Jupyter"
        service_name = "Jupyter"
        split_machine = pod.machine.split("--rname-2d", 1)
        if len(split_machine) > 1:
            service_class = escapism.unescape(split_machine[1], escape_char="-")
        record = {
            "recordType": "JobUsageRecord",
            "jobName": str(pod.local_id),  # XXX is this one ok?
            "operationCount": 1,
            "serviceClass": service_class,
            "callerQualifier": "TOKEN",
            "consumerId": pod.global_user_name,
            "aggregated": True,
            "serviceName": service_name,
            "scope": pod.fqan,
            "host": "jupyterhub.d4science.org",  #
            "id": str(pod.local_id),
            "duration": int(pod.wall),
            # these are in miliseconds
            "startTime": int(pod.start_time.timestamp() * 1000),
            "endTime": int(pod.end_time.timestamp() * 1000),
            # we don't have a different creation and start time
            "creationTime": int(pod.start_time.timestamp() * 1000),
            "operationResult": "SUCCESS",
        }
        logging.debug(f"Generated record: {record}")
        return record

    def generate_day_metrics(self, period_start, period_end):
        logging.info(f"Generate metrics from {period_start} to {period_end}")
        # pods ending in between the reporting times
        records = []
        for pod in VM.select().where(
            (VM.end_time >= period_start) & (VM.end_time < period_end)
        ):
            records.append(self.generate_record(pod))
        logging.debug(
            f"=> {len(records)} records for pods ending in between the reporting times"
        )
        self.push_records(records)


def main(argv=None):
    pusher = D4ScienceRecordPusher()
    pusher.run(argv)


if __name__ == "__main__":
    main()
