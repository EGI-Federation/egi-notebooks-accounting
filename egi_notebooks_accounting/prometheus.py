import datetime
import json
import logging
import os
import re
import sys

import requests
import urllib3
from requests.auth import HTTPBasicAuth

# urllib3 1.9.1: from urllib3.exceptions import InsecureRequestWarning
from requests.packages.urllib3.exceptions import InsecureRequestWarning

CONFIG = "prometheus"
DEFAULT_PROMETHEUS_URL = "http://localhost:8080"


class Prometheus:
    DEFAULT_AGENT = "egi-notebooks-client/1.0-dev"
    DEFAULT_HEADERS = {"User-Agent": DEFAULT_AGENT}
    DEFAULT_HEADERS_MIME = {"Content-Type": "application/x-www-form-urlencoded"}

    def __init__(self, parser):
        config = parser[CONFIG] if CONFIG in parser else {}
        url = os.environ.get(
            "PROMETHEUS_URL", config.get("url", DEFAULT_PROMETHEUS_URL)
        )
        if not url.endswith("/"):
            url = url + "/"
        self.url = url + "api/v1"
        user = config.get("user")
        password = config.get("password")
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(user, password)
        self.session.headers.update(Prometheus.DEFAULT_HEADERS)
        verify = os.environ.get("SSL_VERIFY", config.get("verify", 1))
        verify = not (verify != "1" and verify != "True")
        if not verify:
            urllib3.disable_warnings(InsecureRequestWarning)
        self.session.verify = verify
        logging.debug("URL %s", self.url)
        logging.debug("verify %s", verify)
        self.pods = dict()

    def handle_error(self, response):
        response.raise_for_status()

    def get(self, rel_url):
        """REST GET request."""
        url = self.url + rel_url
        response = self.session.get(url)
        self.handle_error(response)
        return response

    def post(self, rel_url, data=None):
        """REST POST request."""
        url = self.url + rel_url
        logging.debug("POST %s", data)
        response = self.session.post(
            url, data=data, headers=Prometheus.DEFAULT_HEADERS_MIME
        )
        self.handle_error(response)
        return response

    def query(self, data=None):
        response = self.post("/query", data=data)
        return json.loads(str(response.content, "utf-8"))

    def get_pod(self, item, uid=None, default=None):
        if "metric" not in item or uid is None and "uid" not in item["metric"]:
            logging.error("missing metric or uid in metric")
            sys.exit(1)
        # expects only matrix or vector resultType
        if "values" not in item and "value" not in item:
            logging.error("missing value(s) in the result")
        if uid is None:
            key = item["metric"]["uid"]
        else:
            key = uid
        if key in self.pods:
            return self.pods[key]
        if default is not None:
            self.pods[key] = default
            default.local_id = key
            return default
        return None

    def parse_range(self, rng):
        factors = {
            "ms": "milliseconds",
            "s": "seconds",
            "m": "minutes",
            "h": "hours",
            "d": "days",
            "w": "weeks",
            # this is not supported by timedelta
            "y": "years",
        }
        kwargs = {}
        for m in re.finditer(r"(\d+)([^\W\d]+)", rng):
            kwargs[factors[m.group(2)]] = int(m.group(1))
        return datetime.timedelta(**kwargs)
