import logging
import uuid
from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ..model import VM, db_init

CONFIG_FILE_NAME: str = "config-tests.ini"


def pytest_configure(config):
    """Declare global configuration variables for tests."""
    parser = ConfigParser()
    config_file = (
        Path(__file__).relative_to(Path.cwd()).parent.parent.joinpath(CONFIG_FILE_NAME)
    )
    parser.read(config_file)
    config.config: dict = parser["default"] if "default" in parser else {}
    config.eosc_config: dict = parser["eosc"] if "eosc" in parser else {}
    config.flavor_config: dict = (
        parser["eosc.flavors"] if "eosc.flavors" in parser else {}
    )
    config.config_file = config_file
    config.db_file: str = config.config.get("notebooks_db")
    TestHelpers.flavor_name = list(config.flavor_config.keys())[0]
    TestHelpers.flavor_metric = list(config.flavor_config.values())[0]


@pytest.fixture(autouse=True, scope="session")
def db(pytestconfig):
    """Initialize and connect testing local accounting database."""
    logging.info(f"Config file: {pytestconfig.config_file}")
    logging.info(f"DB file: {pytestconfig.db_file}")
    db = db_init(pytestconfig.db_file)
    db.connect()
    yield db
    db.close()


@pytest.fixture(autouse=True, scope="function")
def truncate(db):
    """Cleanup the data before testing."""
    VM.truncate_table()


class TestHelpers:
    flavor_name = None
    flavor_metric = None
    LUSER = "ltuser"
    USER = "gtuser"
    FQAN = "tsuite"

    @staticmethod
    def pod(i: int, start_time: datetime, wall: float | None) -> VM:
        """
        Insert pod into local accounting database.

        :param i:
            Number (index) of the testing pod.

        :param start_time:
            Starting time.

        :param wall:
            Running duration time. ``None`` means still running, ``0`` means ended immediatelly, but some walltime is used.
        """
        local_id = uuid.UUID(int=i)
        if wall is not None:
            end_time = start_time + timedelta(seconds=wall)
            # the trick to play with time intervals, but still count the pod in metrics
            if wall == 0:
                wall = 1
        else:
            end_time = None
            # long running pod
            wall = 7 * 24 * 3600
        return VM.create(
            local_id=local_id,
            machine=f"machine{i}",
            local_user_id=TestHelpers.LUSER,
            global_user_name=TestHelpers.USER,
            fqan=TestHelpers.FQAN,
            namespace="testsuite",
            start_time=start_time,
            end_time=end_time,
            wall=wall,
            flavor=TestHelpers.flavor_name,
            cpu_duration=0.1 * wall,
        )
