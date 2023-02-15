#! /usr/bin/python3

import argparse
import json
import logging
import os
import time
from configparser import ConfigParser
from datetime import datetime

import requests
from requests.auth import HTTPBasicAuth

from .prometheus import Prometheus

PROM_CONFIG = "prometheus"
EOSC_CONFIG = "eosc"
DEFAULT_CONFIG_FILE = "config.ini"
DEFAULT_FILTER = ""
DEFAULT_RANGE = "4h"
DEFAULT_TOKEN_URL = (
    "https://aai-demo.eosc-portal.eu/auth/realms/core/protocol/openid-connect/token"
)
DEFAULT_ARGO_URL = "https://accounting.devel.argo.grnet.gr"


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
    response = requests.post(
        f"{argo_url}/accounting-system/installations/{installation}/metrics",
        headers={"Authorization": f"Bearer {token}"},
        data=json.dumps(data),
    )
    response.raise_for_status()


def get_max_value(prom_response):
    v = 0
    for item in prom_response["data"]["result"]:
        # just take max
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
    prom_config = parser[PROM_CONFIG] if PROM_CONFIG in parser else {}
    eosc_config = parser[EOSC_CONFIG] if EOSC_CONFIG in parser else {}

    verbose = os.environ.get("VERBOSE", prom_config.get("verbose", 0))
    verbose = logging.DEBUG if verbose == "1" else logging.INFO
    logging.basicConfig(level=verbose)
    flt = os.environ.get("FILTER", prom_config.get("filter", DEFAULT_FILTER))
    rng = os.environ.get("RANGE", prom_config.get("range", DEFAULT_RANGE))

    # EOSC accounting config in a separate section
    # AAI
    token_url = os.environ.get(
        "TOKEN_URL", eosc_config.get("token_url", DEFAULT_TOKEN_URL)
    )
    refresh_token = os.environ.get(
        "REFRESH_TOKEN", eosc_config.get("refresh_token", "")
    )
    client_id = os.environ.get("CLIENT_ID", eosc_config.get("client_id", ""))
    client_secret = os.environ.get(
        "CLIENT_SECRET", eosc_config.get("client_secret", "")
    )

    # ARGO
    argo_url = os.environ.get("ARGO_URL", eosc_config.get("argo_url", DEFAULT_ARGO_URL))
    installation = eosc_config.get("installation_id", "")
    users_metric = eosc_config.get("users_metric", "")
    sessions_metric = eosc_config.get("sessions_metric", "")

    prom = Prometheus(parser)
    tnow = time.time()
    data = {
        "time": tnow,
    }

    # ==== number of users ====
    data["query"] = "jupyterhub_total_users{" + flt + "}[" + rng + "]"
    users = get_max_value(prom.query(data))

    # ==== number of sessions ====
    data["query"] = "jupyterhub_running_servers{" + flt + "}[" + rng + "]"
    sessions = get_max_value(prom.query(data))

    # now push values to EOSC accounting
    to_date = datetime.utcfromtimestamp(tnow)
    from_date = to_date - prom.parse_range(rng)
    token = get_access_token(token_url, client_id, client_secret, refresh_token)
    push_metric(argo_url, token, installation, users_metric, from_date, to_date, users)
    push_metric(
        argo_url, token, installation, sessions_metric, from_date, to_date, sessions
    )


if __name__ == "__main__":
    main()
