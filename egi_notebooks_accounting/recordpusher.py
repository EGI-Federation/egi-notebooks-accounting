"""Base record generator for various accounting systems

Includes a common configuration that can be expanded by subclasses
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
```


"""

import argparse
import logging
import os
from configparser import ConfigParser
from datetime import datetime, timedelta, timezone

import dateutil.parser
import requests
from requests.auth import HTTPBasicAuth

from .model import db_init

CONFIG = "default"
AAI_CONFIG = "aai"
DEFAULT_CONFIG_FILE = "config.ini"


class RecordPusher:
    """Skeleton for pushing records"""

    description = "Notebooks accounting pusher"
    default_token_url = ""
    default_scope = "openid"
    default_timestamp_file = "egi-notebooks.timestamp"

    def __init__(self):
        self.dry_run = False
        self.config = {}
        self.timestamp_file = ""

    def get_access_token(self, token_url, client_id, client_secret, scope):
        """Gets an access token from the AAI"""
        response = requests.post(
            token_url,
            auth=HTTPBasicAuth(client_id, client_secret),
            data={
                "grant_type": "client_credentials",
                "scope": scope,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=self.timeout,
        )
        return response.json()["access_token"]

    def get_from_to_dates(self, user_from_date, user_to_date):
        """
        Gets the start and end dates for the generation of records

        If there is a timestamp file, it starts from there, else it starts from
        yesterday
        End date is today at 00:00
        """
        from_date = None
        if user_from_date:
            from_date = dateutil.parser.parse(user_from_date).replace(
                tzinfo=timezone.utc
            )
        elif self.timestamp_file:
            try:
                with open(self.timestamp_file, "r") as tsf:
                    try:
                        from_date = dateutil.parser.parse(tsf.read())
                    except dateutil.parser.ParserError as e:
                        logging.debug(
                            f"Invalid timestamp content in '{self.timestamp_file}': {e}"
                        )
            except OSError as e:
                logging.debug(
                    f"Not able to open timestamp file '{self.timestamp_file}': {e}"
                )
        # no date specified report from yesterday
        if not from_date:
            from_date = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        if user_to_date:
            to_date = dateutil.parser.parse(user_to_date).replace(tzinfo=timezone.utc)
        else:
            # go until the very beginning of today
            to_date = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        self.from_date = from_date
        self.to_date = to_date

    def configure(self, config_file):
        parser = ConfigParser()
        parser.read(config_file)

        config = parser[CONFIG] if CONFIG in parser else {}
        aai_config = parser[AAI_CONFIG] if AAI_CONFIG in parser else {}
        db_file = os.environ.get("NOTEBOOKS_DB", config.get("notebooks_db", None))
        db_init(db_file)
        verbose = os.environ.get("VERBOSE", config.get("verbose", 0))
        verbose = logging.DEBUG if verbose == "1" else logging.INFO
        logging.basicConfig(level=verbose)
        timeout = config.get("timeout", None)
        if timeout is not None:
            timeout = int(timeout)
        self.timeout = timeout
        self.timestamp_file = os.environ.get(
            "TIMESTAMP_FILE", config.get("timestamp_file", self.default_timestamp_file)
        )

        # AAI
        token_url = os.environ.get(
            "TOKEN_URL", aai_config.get("token_url", self.default_token_url)
        )
        client_id = os.environ.get("CLIENT_ID", aai_config.get("client_id", ""))
        client_secret = os.environ.get(
            "CLIENT_SECRET", aai_config.get("client_secret", "")
        )
        scope = os.environ.get("SCOPE", aai_config.get("scope", self.default_scope))

        if self.dry_run:
            logging.debug("Not getting credentials, dry-run")
            self.token = None
        else:
            self.token = self.get_access_token(
                token_url, client_id, client_secret, scope
            )
        # return the parser so children can still
        return parser

    def parse_args(self, argv=None):
        parser = argparse.ArgumentParser(description=self.description)
        parser.add_argument(
            "-c", "--config", help="config file", default=DEFAULT_CONFIG_FILE
        )
        parser.add_argument(
            "--dry-run",
            help="Do not actually send data, just report",
            action="store_true",
        )
        parser.add_argument("--from-date", help="Start date to report from")
        parser.add_argument("--to-date", help="End date to report to")
        args = parser.parse_args(argv)
        self.dry_run = args.dry_run
        self.configure(args.config)
        self.get_from_to_dates(args.from_date, args.to_date)

    def generate_day_metrics(self, period_start, period_end):
        raise NotImplementedError

    def generate_records(self):
        logging.debug(f"Reporting from {self.from_date} to {self.to_date}")
        # repeat in 24 hour intervals
        period_start = self.from_date
        while period_start < self.to_date:
            period_end = period_start + timedelta(days=1)
            self.generate_day_metrics(period_start, period_end)
            # generate timestamp
            if not self.dry_run and self.timestamp_file:
                try:
                    with open(self.timestamp_file, "w+") as tsf:
                        timestamp_str = period_end.strftime("%Y-%m-%dT%H:%M:%SZ")
                        logging.debug(
                            f"Writing following timestamp to '{self.timestamp_file}': {timestamp_str}"
                        )
                        # we have open interval at the end => store the time just before the ending
                        tsf.write(timestamp_str)
                except OSError as e:
                    e = str(e)
                    logging.debug(
                        "Failed to write timestamp file '{self.timestamp_file}': {e}"
                    )
            period_start = period_end

    def run(self, argv):
        self.parse_args(argv)
        self.generate_records()
