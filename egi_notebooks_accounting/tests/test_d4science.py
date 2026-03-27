"""Tests for the RecordPusher base class"""

import datetime
from unittest.mock import Mock, call, mock_open, patch

import dateutil.parser
from freezegun import freeze_time

from .. import d4science


def test_configure():
    pusher = d4science.D4ScienceRecordPusher()
    pusher.configure("")


def test_push_records(requests_mock):
    aai_url = "http://example.com/path/"
    requests_mock.post(
        aai_url,
        json={"access_token": "token-of-accounting"},
        status_code=200,
    )
    pusher = recordpusher.RecordPusher()
    token = pusher.get_access_token(aai_url, "client_id", "client_secret", "scope")
    assert len(requests_mock.request_history) == 1, "a HTTP call has been made"
    r = requests_mock.request_history[0]
    assert r.url == aai_url, f"URL is '{aai_url}'"
    assert r.method == "POST", "Method is POST"
    assert token == "token-of-accounting", "Token is correct"


def test_set_from_to_dates_today():
    from_date = dateutil.parser.parse("2026-02-27T00:10:00Z")
    pusher = recordpusher.RecordPusher()
    with freeze_time(from_date):
        pusher.set_from_to_dates(None, None)
    assert pusher.from_date == datetime.datetime(
        2026, 2, 26, 0, 0, 0, tzinfo=datetime.timezone.utc
    ), "From date is yesterday"
    assert pusher.to_date == datetime.datetime(
        2026, 2, 27, 0, 0, 0, tzinfo=datetime.timezone.utc
    ), "To date is today"


def test_set_from_to_dates_user_from():
    today = dateutil.parser.parse("2026-02-27T00:10:00Z")
    pusher = recordpusher.RecordPusher()
    with freeze_time(today):
        pusher.set_from_to_dates("2026-02-25T01:00:00Z", None)
    assert pusher.from_date == datetime.datetime(
        2026, 2, 25, 1, 0, 0, tzinfo=datetime.timezone.utc
    ), "From date is as specified by user"
    assert pusher.to_date == datetime.datetime(
        2026, 2, 27, 0, 0, 0, tzinfo=datetime.timezone.utc
    ), "To date is today"


def test_set_from_to_dates_user_from_and_to():
    today = dateutil.parser.parse("2026-02-27T00:10:00Z")
    pusher = recordpusher.RecordPusher()
    with freeze_time(today):
        pusher.set_from_to_dates("2026-02-25T01:00:00Z", "2026-02-28")
    assert pusher.from_date == datetime.datetime(
        2026, 2, 25, 1, 0, 0, tzinfo=datetime.timezone.utc
    ), "From date is as specified by user"
    assert pusher.to_date == datetime.datetime(
        2026, 2, 28, 0, 0, 0, tzinfo=datetime.timezone.utc
    ), "To date is as specified by user"


def test_set_from_to_dates_with_timestamp():
    today = dateutil.parser.parse("2026-02-27T00:10:00Z")
    pusher = recordpusher.RecordPusher()
    pusher.timestamp_file = "foo"
    with freeze_time(today):
        with patch(
            "builtins.open", mock_open(read_data="2026-02-20T00:10:00Z")
        ) as mock_file:
            pusher.set_from_to_dates(None, None)
            mock_file.assert_called_with("foo", "r")
    assert pusher.from_date == datetime.datetime(
        2026, 2, 20, 0, 10, 0, tzinfo=datetime.timezone.utc
    ), "From date is taken from timestamp"
    assert pusher.to_date == datetime.datetime(
        2026, 2, 27, 0, 0, 0, tzinfo=datetime.timezone.utc
    ), "To date is today"


def test_generate_records():
    pusher = recordpusher.RecordPusher()
    pusher.generate_day_metrics = Mock()
    pusher.from_date = datetime.datetime(
        2026, 2, 20, 0, 0, 0, tzinfo=datetime.timezone.utc
    )
    pusher.to_date = datetime.datetime(
        2026, 2, 23, 0, 0, 0, tzinfo=datetime.timezone.utc
    )
    pusher.generate_records()
    pusher.generate_day_metrics.assert_has_calls(
        [
            call(
                datetime.datetime(2026, 2, 20, 0, 0, tzinfo=datetime.timezone.utc),
                datetime.datetime(2026, 2, 21, 0, 0, tzinfo=datetime.timezone.utc),
            ),
            call(
                datetime.datetime(2026, 2, 21, 0, 0, tzinfo=datetime.timezone.utc),
                datetime.datetime(2026, 2, 22, 0, 0, tzinfo=datetime.timezone.utc),
            ),
            call(
                datetime.datetime(2026, 2, 22, 0, 0, tzinfo=datetime.timezone.utc),
                datetime.datetime(2026, 2, 23, 0, 0, tzinfo=datetime.timezone.utc),
            ),
        ]
    )


def test_generate_timestamp():
    from_date = dateutil.parser.parse("2026-02-27T00:10:00Z")
    pusher = recordpusher.RecordPusher()
    pusher.generate_day_metrics = Mock()
    with freeze_time(from_date):
        with patch("builtins.open", mock_open()) as mock_file:
            pusher.set_from_to_dates(None, None)
            pusher.timestamp_file = "foo"
            pusher.generate_records()
            mock_file.assert_called_once_with("foo", "w+")
            handle = mock_file()
            handle.write.assert_called_once_with("2026-02-27T00:00:00Z")
            pusher.generate_day_metrics.assert_called_once_with(
                datetime.datetime(2026, 2, 26, 0, 0, tzinfo=datetime.timezone.utc),
                datetime.datetime(2026, 2, 27, 0, 0, tzinfo=datetime.timezone.utc),
            )
