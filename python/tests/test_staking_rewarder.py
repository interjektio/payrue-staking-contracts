import json
import os
import time
from decimal import Decimal

import pytest
from web3 import Web3
from eth_account import Account

from staking_rewarder.service import StakingRewarder, ABI, Reward
from staking_rewarder.models import RewardState

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


@pytest.fixture()
def staking_rewarder(web3, staking_contract):
    return StakingRewarder(
        web3=web3,
        staking_contract_address=staking_contract.address,
    )


def create_account(private_key):
    return Account.from_key(private_key)


def create_stake(amount, token_contract, staking_contract, account):
    token_contract.functions.mint(account.address, amount).transact({'from': account.address})
    token_contract.functions.approve(staking_contract.address, amount).transact({'from': account.address})
    staking_contract.functions.stake(amount).transact({'from': account.address})
    staked = staking_contract.functions.staked(account.address).call()
    return staked


def get_total_amount_staked(staking_contract):
    return staking_contract.functions.totalAmountStaked().call()


def test_stake(web3, staking_contract, token_contract, deployer_account, alice):
    staked_amount = create_stake(web3.to_wei(10000, 'ether'), token_contract, staking_contract, alice)
    assert web3.to_wei(10000, 'ether') == staked_amount
    assert get_total_amount_staked(staking_contract) == staked_amount


def test_staking(web3, staking_contract, token_contract, deployer_account, alice, staking_rewarder, bob):
    amount = web3.to_wei(10000, 'ether')
    alice_staked = create_stake(amount, token_contract, staking_contract, alice)
    assert alice_staked == amount
    assert get_total_amount_staked(staking_contract) == alice_staked

    amount = web3.to_wei(20000, 'ether')
    bob_staked = create_stake(amount, token_contract, staking_contract, bob)
    assert bob_staked == amount
    assert get_total_amount_staked(staking_contract) == alice_staked + bob_staked

    amount = web3.to_wei(30000, 'ether')
    bob_staked = create_stake(amount, token_contract, staking_contract, bob)
    assert bob_staked == web3.to_wei(50000, 'ether')
    assert get_total_amount_staked(staking_contract) == alice_staked + bob_staked


def test_get_rewards_at_block(web3, staking_contract, token_contract, deployer_account, alice, staking_rewarder, bob):
    amount = web3.to_wei(10000, 'ether')
    alice_staked = create_stake(amount, token_contract, staking_contract, alice)
    assert alice_staked == amount
    assert get_total_amount_staked(staking_contract) == alice_staked

    amount = web3.to_wei(20000, 'ether')
    bob_staked = create_stake(amount, token_contract, staking_contract, bob)
    assert bob_staked == amount
    assert get_total_amount_staked(staking_contract) == alice_staked + bob_staked

    amount = web3.to_wei(50000, 'ether')
    bob_staked = create_stake(amount, token_contract, staking_contract, bob)
    assert bob_staked == web3.to_wei(70000, 'ether')
    assert get_total_amount_staked(staking_contract) == alice_staked + bob_staked

    rewarder = staking_rewarder
    block_number = web3.eth.block_number
    print('block_number: ', block_number)
    user_addresses = [alice.address, bob.address]
    rewards = rewarder.get_rewards_at_block(
        user_addresses=user_addresses,
        block_number=block_number,
    )
    expected_output = [
        Reward(user_address='0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
               percentage=Decimal('0.125'),
               state=RewardState.unsent),
        Reward(user_address='0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC',
               percentage=Decimal('0.875'),
               state=RewardState.unsent)
    ]
    assert rewards == expected_output
    sum_rewards = sum(r.percentage for r in rewards)
    print(
        f'sum_rewards_percentage: {sum_rewards}, '
        f'total_amount_staked: {web3.from_wei(get_total_amount_staked(staking_contract), "ether")} ETH')
    assert sum_rewards == 1


def test_get_staker_addresses(web3, staking_contract, token_contract, deployer_account, alice, staking_rewarder, bob):
    amount = web3.to_wei(10000, 'ether')
    alice_staked = create_stake(amount, token_contract, staking_contract, alice)
    assert alice_staked == amount
    assert get_total_amount_staked(staking_contract) == alice_staked

    amount = web3.to_wei(20000, 'ether')
    bob_staked = create_stake(amount, token_contract, staking_contract, bob)
    assert bob_staked == amount
    assert get_total_amount_staked(staking_contract) == alice_staked + bob_staked

    rewarder = staking_rewarder
    block_number = web3.eth.block_number
    user_addresses = rewarder.get_staker_addresses(
        start_block_number=1,
        end_block_number=block_number,
    )
    assert user_addresses == {alice.address, bob.address}


def test_block_state(web3, token_contract, staking_contract, deployer_account, alice, staking_rewarder, bob):
    amount = web3.to_wei(10000, 'ether')
    alice_staked = create_stake(amount, token_contract, staking_contract, alice)
    assert alice_staked == amount
    assert get_total_amount_staked(staking_contract) == alice_staked

    amount = web3.to_wei(20000, 'ether')
    bob_staked = create_stake(amount, token_contract, staking_contract, bob)
    assert bob_staked == amount
    assert get_total_amount_staked(staking_contract) == alice_staked + bob_staked
    block_number = web3.eth.block_number

    amount = web3.to_wei(50000, 'ether')
    bob_staked = create_stake(amount, token_contract, staking_contract, bob)
    assert bob_staked == web3.to_wei(70000, 'ether')
    assert get_total_amount_staked(staking_contract) == alice_staked + bob_staked

    updated_block_number = web3.eth.block_number
    assert updated_block_number > block_number
