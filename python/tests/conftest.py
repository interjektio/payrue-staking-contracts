import pathlib
import subprocess
import time

import psycopg
import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from web3 import HTTPProvider

from staking_rewarder.models import Base

INIT_VARIABLES = ["default_database_url", "test_db_name", "test_database_url"]


def pytest_addoption(parser):
    for variable in INIT_VARIABLES:
        parser.addini(variable, "", default=None)


def _wait_for_startup(rpc_url):
    while True:
        try:
            response = _request_raw(rpc_url, "eth_chainId", [])
            if response.ok:
                json = response.json()
                if "error" not in json:
                    break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(0.2)


def _request_raw(url, method, params):
    return requests.post(
        url,
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": method,
            "params": params,
        },
    )


root_dir = pathlib.Path(__file__).parent.parent.parent.absolute()
hardhat_executable = root_dir / "node_modules" / ".bin" / "hardhat"


@pytest.fixture(scope="module")
def hardhat_provider():
    # Start the Hardhat node
    hardhat_process = subprocess.Popen(
        [hardhat_executable, "node", "--port", "8546"], stdout=subprocess.PIPE
    )
    # print the pid of hardhat process
    _wait_for_startup("http://localhost:8546")

    # Provide the process some time to start
    provider = HTTPProvider("http://localhost:8546/")
    yield provider
    subprocess.run(["kill", "-9", str(hardhat_process.pid)])


def execute_sql(conn_str, sql_command):
    with psycopg.connect(conn_str, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_command)


def create_test_database(database_url: str, db_name: str):
    execute_sql(database_url, f"CREATE DATABASE {db_name}")


def drop_test_database(database_url: str, db_name: str):
    execute_sql(database_url, f"DROP DATABASE IF EXISTS {db_name}")


@pytest.fixture(scope="module")
def setup_teardown_database(pytestconfig):
    default_database_url = pytestconfig.getini("default_database_url")
    db_name = pytestconfig.getini("test_db_name")
    create_test_database(default_database_url, db_name)
    yield
    drop_test_database(default_database_url, db_name)


@pytest.fixture(scope="module")
def db_engine(setup_teardown_database, pytestconfig):
    test_database_url = pytestconfig.getini("test_database_url")
    engine = create_engine(test_database_url, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def session_factory(db_engine):
    session_factory = sessionmaker(bind=db_engine)
    yield session_factory
    session_factory.close_all()
