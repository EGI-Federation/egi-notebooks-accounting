#! /usr/bin/python3

import argparse
import json
import logging
import os
import time
from configparser import ConfigParser

import requests
import urllib3
from requests.auth import HTTPBasicAuth

# urllib3 1.9.1: from urllib3.exceptions import InsecureRequestWarning
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from .prometheus import Prometheus

CONFIG = "prometheus"
DEFAULT_CONFIG_FILE = "config.ini"
DEFAULT_FILTER = ""
DEFAULT_RANGE = "4h"


def refresh_token():
    #
    print("Get this done...")
    return ""


def push_metric(argo_url, token, installation, metric, date_from, date_to, value):
    data = {
        "metric_definition_id": metric,
        "time_period_start": date_from,
        "time_period_end": date_to,
        "value": value,
    }  # should look like 2023-02-12T15:53:52Z
    requests.post(
        f"%argo_url/accounting-system/installations/%installation/metrics",
        headers={"Authorization": f"Bearer %token"},
        data=json.dumps(data),
    )


def get_max_value(prom_response):
    v = 0
    for item in prom_response["data"]["result"]:
        # just take max
        print(item)
        v += max(int(r[1]) for r in item["values"])
    return v


def main():
    parser = argparse.ArgumentParser(
        description="Kubernetes Prometheus metrics harvester"
    )
    parser.add_argument(
        "-c", "--config", help="config file", default=DEFAULT_CONFIG_FILE
    )
    args = parser.parse_args()

    parser = ConfigParser()
    parser.read(args.config)
    config = parser[CONFIG] if CONFIG in parser else {}

    verbose = os.environ.get("VERBOSE", config.get("verbose", 0))
    verbose = logging.DEBUG if verbose == "1" else logging.INFO
    logging.basicConfig(level=verbose)
    flt = os.environ.get("FILTER", config.get("filter", DEFAULT_FILTER))
    rng = os.environ.get("RANGE", config.get("range", DEFAULT_RANGE))

    prom = Prometheus(parser)
    tnow = time.time()
    data = {
        "time": tnow,
    }

    # ==== number of users ====
    data["query"] = "jupyterhub_total_users{" + flt + "}[" + rng + "])"
    users = get_max_value(prom.query(data))
    print(users)

    # ==== number of sessions ====
    data["query"] = "jupyterhub_running_servers{" + flt + "}[" + rng + "])"
    sessions = get_max_value(prom.query(data))
    print(sessions)

    # now push values to EOSC accounting
    token = get_refresh_token()
    push_metric(
        "ARGO_URL", token, "installation", "METRIC", "tnow - range", tnow, users
    )
    push_metric(
        "ARGO_URL", token, "installation", "METRIC-2", "tnow - range", tnow, sessions
    )


if __name__ == "__main__":
    main()
