"""Tests for d4science pusher"""

import datetime
from unittest.mock import call, patch

from .. import d4science
from .. import recordpusher
from .conftest import TestHelpers


def test_push_records(requests_mock, config_file):
    requests_mock.post(
        d4science.DEFAULT_ACCOUNTING_URL,
        status_code=200,
    )
    with patch.object(recordpusher.RecordPusher, "get_access_token") as m_token:
        pusher = d4science.D4ScienceRecordPusher()
        pusher.configure(config_file)
        pusher.push_records("foo", [1, 2, 3])
        m_token.assert_called_with(
            d4science.DEFAULT_TOKEN_URL, "", "", "openid d4s-context:foo"
        )
    requests_mock


def test_generate_day_metrics(config_file):
    start_time = datetime.datetime.today()
    # not finished pod
    TestHelpers.pod(0, start_time)
    # finished within the period
    TestHelpers.pod(1, start_time, 5 * 60)
    TestHelpers.pod(2, start_time - datetime.timedelta(minutes=2), 10 * 60)
    TestHelpers.pod(3, start_time + datetime.timedelta(minutes=1), 5 * 60)
    # finished before the period
    TestHelpers.pod(4, start_time - datetime.timedelta(days=1), 20 * 60 * 60)
    with patch.object(d4science.D4ScienceRecordPusher, "push_records") as m_push:
        with patch.object(d4science.D4ScienceRecordPusher, "generate_record") as m_rec:
            pusher = d4science.D4ScienceRecordPusher()
            pusher.configure(config_file)
            m_rec.side_effect = [{"scope": "foo"}, {"scope": "foo"}, {"scope": "bar"}]
            pusher.generate_day_metrics(
                start_time, start_time + datetime.timedelta(days=1)
            )
            assert m_push.mock_calls == [
                call("foo", [{"scope": "foo"}, {"scope": "foo"}]),
                call("bar", [{"scope": "bar"}]),
            ]


def test_generate_record(config_file):
    start_time = datetime.datetime.today()
    start_ts = int(start_time.timestamp() * 1000)
    pusher = d4science.D4ScienceRecordPusher()
    pusher.configure(config_file)
    pod_1 = TestHelpers.pod(
        0,
        start_time,
        100,
        machine="jupyter-helmi-2esaidib4d4f--rname-2d-52-53tudio-53erver-4fption",
    )
    record_1 = pusher.generate_record(pod_1)
    assert record_1 == {
        "aggregated": False,
        "callerQualifier": "TOKEN",
        "consumerId": "gtuser",
        "creationTime": start_ts,
        "duration": 100,
        "endTime": start_ts + 100 * 1000,
        "host": "example.com",
        "id": "00000000-0000-0000-0000-000000000000",
        "jobName": "00000000-0000-0000-0000-000000000000",
        "maxInvocationTime": 100,
        "minInvocationTime": 100,
        "operationCount": 1,
        "operationResult": "SUCCESS",
        "recordType": "JobUsageRecord",
        "scope": "tsuite",
        "serviceClass": "RStudio",
        "serviceName": "Jupyter",
        "startTime": start_ts,
    }
    pod_2 = TestHelpers.pod(1, start_time, 500)
    record_2 = pusher.generate_record(pod_2)
    assert record_2 == {
        "aggregated": False,
        "callerQualifier": "TOKEN",
        "consumerId": "gtuser",
        "creationTime": start_ts,
        "duration": 500,
        "endTime": start_ts + 500 * 1000,
        "host": "example.com",
        "id": "00000000-0000-0000-0000-000000000001",
        "jobName": "00000000-0000-0000-0000-000000000001",
        "maxInvocationTime": 500,
        "minInvocationTime": 500,
        "operationCount": 1,
        "operationResult": "SUCCESS",
        "recordType": "JobUsageRecord",
        "scope": "tsuite",
        "serviceClass": "Jupyter",
        "serviceName": "Jupyter",
        "startTime": start_ts,
    }
