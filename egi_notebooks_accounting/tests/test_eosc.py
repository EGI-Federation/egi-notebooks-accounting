import logging
from datetime import datetime, timedelta
from pathlib import Path

import dateutil.parser
import pytest
from freezegun import freeze_time

from .. import eosc
from ..model import VM
from .conftest import TestHelpers


@pytest.fixture(scope="function")
def delete_timestamp(pytestconfig):
    """Delete EOSC last report timestamp file."""
    timestamp_file = pytestconfig.eosc_config.get(
        "timestamp_file", eosc.DEFAULT_TIMESTAMP_FILE
    )
    Path.unlink(timestamp_file, missing_ok=True)


def pod(i: int, start_time: datetime, wall: float | None) -> VM:
    """Insert pod into local accounting database."""
    logging.info(f"Inserting pod start_time {start_time}, wall {wall}")
    return TestHelpers.pod(i, start_time, wall)


def check_request(captured, url: str, message: str) -> None:
    """
    Check the captured request.

    :param captured:
        Captured request.

    :param url:
        Exptected URL.

    :param message:
        Log message prefix.
    """
    assert captured is not None, f"{message} is not None"
    logging.info(f"{message} HTTP call: {captured.method} {captured.url}")
    assert captured.method == "POST", f"{message} method is POST"
    assert captured.url == url, f"{message} URL is {url}"


def launch_eosc(
    pytestconfig,
    requests_mock,
    from_date: datetime,
    start_times: list[datetime] = [],
    wall_times: list[float] = [],
    results: list[float] = [],
) -> None:
    """
    Launch eosc.py utility in mock mode and check the results.

    Only one unique user is used in the test.

    :param pytestconfig:
        Pytest fixture, configuration object.

    :param request_mock:
        Pytest fixture, request mock object.

    :param from_date:
        Start time of the first interval

    :param start_times:
        Pod starting times.

    :param wall_times:
        Pod wall time durations.

    :param results:
        Expected metric result for each interval (in hours), including zero metrics.
    """
    # pods into accounting database
    for i in range(0, len(start_times)):
        pod(i + 1, start_times[i], wall_times[i])

    # call accounting EOSC metric pusher
    accounting_url = pytestconfig.eosc_config.get(
        "accounting_url", eosc.DEFAULT_ACCOUNTING_URL
    )
    installation_id = pytestconfig.eosc_config["installation_id"]
    token_url = pytestconfig.eosc_config.get("token_url", eosc.DEFAULT_TOKEN_URL)
    accounting_metrics_url = (
        f"{accounting_url}/accounting-system/installations/{installation_id}/metrics"
    )
    requests_mock.post(
        token_url,
        json={"access_token": "token-of-accounting"},
        status_code=200,
    )
    requests_mock.post(
        accounting_metrics_url,
        text="OK",
        status_code=200,
    )
    args: list[str] = ["-c", str(pytestconfig.config_file)]
    logging.info(f"Command: python -m egi_notebooks_accounting.eosc {' '.join(args)}")
    for i in range(0, len(results)):
        with freeze_time(from_date):
            eosc.main(args)
        from_date += timedelta(hours=24)

    # check results
    logging.info(f"HTTP requests history: {len(requests_mock.request_history)}")
    assert len(requests_mock.request_history) > 0, "any HTTP call has been made"
    metrics_count = sum(v is not None and v != 0 for v in results)
    # token is always asked, metrics are sent only when not zero
    assert (
        len(requests_mock.request_history) == len(results) + metrics_count
    ), f"number of token requests is {len(results)} and pushed metrics is {metrics_count}"
    i = 1
    h: int = 0
    for result in results:
        # token
        captured = requests_mock.request_history[h]
        h = h + 1
        check_request(captured, token_url, "Token captured")
        if result is None or not result:
            continue
        # metrics
        captured = requests_mock.request_history[h]
        h = h + 1
        check_request(captured, accounting_metrics_url, f"{i}. captured")
        logging.info(f"{i}. captured body: {captured.body}")
        json = captured.json()
        assert json is not None, f"{i}. captured has a json body"
        assert "value" in json, f"{i}. captured has a value metric"
        assert json["value"] == result, f"{i}. captured metric has the expected value"
        i = i + 1


def test_basic(pytestconfig, requests_mock, delete_timestamp) -> None:
    """Basic test with two pods inside the interval."""
    from_date = dateutil.parser.parse("2026-02-28T00:00:00Z")
    start_times: list[datetime] = [
        dateutil.parser.parse("2026-02-27T13:00:00Z"),
        dateutil.parser.parse("2026-02-27T13:30:00Z"),
    ]
    wall_times: list[float] = [
        3600,
        3600,
    ]
    results: list[float] = [2.0]

    launch_eosc(
        pytestconfig, requests_mock, from_date, start_times, wall_times, results
    )


def test_over(pytestconfig, requests_mock, delete_timestamp) -> None:
    """Test with a pod between two intervals."""
    from_date = dateutil.parser.parse("2026-02-28T00:00:00Z")
    start_times: list[datetime] = [
        dateutil.parser.parse("2026-02-27T23:00:00Z"),
    ]
    wall_times: list[float] = [
        2 * 3600,
    ]
    results: list[float] = [0, 2.0]

    launch_eosc(
        pytestconfig, requests_mock, from_date, start_times, wall_times, results
    )
