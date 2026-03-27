"""Tests for d4science pusher"""

from unittest.mock import patch

from .. import d4science
from .. import recordpusher


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


def test_go():
    assert True
