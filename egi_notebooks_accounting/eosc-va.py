#! /usr/bin/python3

import argparse
from datetime import datetime
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
DEFAULT_TOKEN_URL = (
    "https://aai-demo.eosc-portal.eu/auth/realms/core/protocol/openid-connect/token"
)


def get_access_token(refresh_url, client_id, client_secret, refresh_token):
    response = requests.post(
        refresh_url,
        auth=HTTPBasicAuth(client_id, client_secret),
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "openid email profile voperson_id eduperson_entitlement",
        },
    )
    return response.json()["access_token"]


def push_metric(argo_url, token, installation, metric, date_from, date_to, value):
    data = {
        "metric_definition_id": metric,
        "time_period_start": date_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "time_period_end": date_to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "value": value,
    }
    requests.post(
        f"%argo_url/accounting-system/installations/%installation/metrics",
        headers={"Authorization": f"Bearer %token"},
        data=json.dumps(data),
    )
    # do we care about result?


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

    # EOSC accounting config in a separate section
    # AAI
    token_url = os.environ.get(
        "TOKEN_URL", config["eosc"].get("token_url", DEFAULT_TOKEN_URL)
    )
    refresh_token = os.environ.get(
        "REFRESH_TOKEN", config["eosc"].get("refresh_token", "")
    )
    client_id = os.environ.get("CLIENT_ID", config["eosc"].get("client_id", ""))
    client_secret = os.environ.get(
        "CLIENT_SECRET", config["eosc"].get("client_secret", "")
    )

    # ARGO
    argo_url = os.environ.get("ARGO_URL", config["eosc"].get("argo_url", ""))
    installation = config["eosc"].get("installation_id", "")
    users_metric = config["eosc"].get("user_metric", "")
    sessions_metric = config["eosc"].get("sessions_metric", "")

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
    from_date = datetime.utcfromtimestamp(tnow)
    to_date = from_date - prom.parse_range(rng)
    token = get_access_token(token_url, client_id, client_secret, refresh_token)
    push_metric(argo_url, token, installation, users_metric, from_date, to_date, users)
    push_metric(
        argo_url, token, installation, sessions_metric, from_date, to_date, sessions
    )


if __name__ == "__main__":
    main()
