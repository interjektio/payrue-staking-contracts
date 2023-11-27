import json
import os
import time

import pytest
from web3 import Web3
from eth_account import Account

from staking_rewarder.service import StakingRewarder, ABI

token_path = os.path.join(os.path.dirname(__file__), 'abi')
token_file = os.path.join(token_path, 'TestToken.json')
TOKEN_ABI = json.loads(open(token_file).read())['abi']
TOKEN_BYTECODE = json.loads(open(token_file).read())['bytecode']


@pytest.fixture()
def web3(hardhat_provider):
    w3 = Web3(hardhat_provider)
    # take a snapshot...
    result = w3.provider.make_request('evm_snapshot', [])
    snapshot_id = result['result']
    print(result)
    yield w3
    # ...and revert to it
    w3.provider.make_request('evm_revert', [snapshot_id])


@pytest.fixture()
def deployer_account():
    return Account.from_key('0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80')


@pytest.fixture()
def alice():
    return Account.from_key('0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d')


@pytest.fixture()
def bob():
    return Account.from_key('0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a')


@pytest.fixture()
def token_contract(web3):
    token_contract_address = web3.to_checksum_address("0x5FbDB2315678afecb367f032d93F642f64180aa3")
    return web3.eth.contract(
        address=token_contract_address,
        abi=TOKEN_ABI
    )


@pytest.fixture()
def staking_contract(web3, token_contract, deployer_account):
    staking_contract_address = web3.to_checksum_address('0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512')
    token_contract.functions.mint(
        staking_contract_address,
        web3.to_wei(1_000_000, 'ether')
    ).transact({'from': deployer_account.address})
    return web3.eth.contract(abi=ABI, address=staking_contract_address)


def create_account(private_key):
    return Account.from_key(private_key)


def test_stake(web3, staking_contract, token_contract, deployer_account, alice):
    amount = web3.to_wei(10000, 'ether')
    token_contract.functions.mint(alice.address, amount).transact({'from': alice.address})
    token_contract.functions.approve(staking_contract.address, amount).transact({'from': alice.address})
    staking_contract.functions.stake(amount).transact({'from': alice.address})
    staked = staking_contract.functions.staked(alice.address).call()
    assert staked == amount

    total_amount_staked = staking_contract.functions.totalAmountStaked().call()
    assert total_amount_staked == amount
