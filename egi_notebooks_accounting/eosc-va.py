#! /usr/bin/python3

import argparse
import json
import logging
import os
import sys
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

    # ==== number of sessions ====
    data["query"] = "jupyterhub_running_servers{" + flt + "}[" + rng + "])"
    sessions = get_max_value(prom.query(data))

    # now push values to EOSC accounting
    print(
        """
             http -A bearer -a $ACCESS_TOKEN
                  -v POST
                  $ARGO_URL/accounting-system/installations/$INSTALLATION/metrics
                  metric_definition_id=$USER_METRIC
                  time_period_start="2023-02-12T15:53:52Z"
                  time_period_end="2023-02-13T15:53:52Z"
                  value=4
         """
    )


if __name__ == "__main__":
    main()
