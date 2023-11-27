import time
import os
import pathlib
import pytest
import subprocess
from web3 import HTTPProvider

import requests


def _wait_for_startup(rpc_url):
    while True:
        try:
            response = _request_raw(rpc_url, 'eth_chainId', [])
            if response.ok:
                json = response.json()
                if 'error' not in json:
                    break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(0.2)


def _request_raw(url, method, params):
    return requests.post(url, json={
        'jsonrpc': '2.0',
        'id': '1',
        'method': method,
        'params': params,
    })


root_dir = pathlib.Path(__file__).parent.parent.parent.absolute()
hardhat_executable = root_dir / 'node_modules' / '.bin' / 'hardhat'


@pytest.fixture(scope="module")
def hardhat_provider():
    # Start the Hardhat node
    hardhat_process = subprocess.Popen([hardhat_executable, "node", '--port', '8546'], stdout=subprocess.PIPE)
    # print the pid of hardhat process
    _wait_for_startup('http://localhost:8546')

    # Provide the process some time to start
    provider = HTTPProvider('http://localhost:8546/')
    yield provider
    subprocess.run(["kill", "-9", str(hardhat_process.pid)])
