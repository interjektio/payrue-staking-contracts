import datetime
import json
import os
from decimal import Decimal
from typing import List, Set, Any
from dataclasses import dataclass

from web3 import Web3

from .stakerslist import get_staker_list
from .utils import to_address, get_web3, get_events, enable_logging

# read the PayRueStaking.json file and get the abi object
abi_path = os.path.join(os.path.dirname(__file__), 'abi')
abi_file = os.path.join(abi_path, 'PayRueStaking.json')
ABI = json.loads(open(abi_file).read())


@dataclass
class Reward:
    # TODO: fill this. Also this might actually be an SQLAlchemy model
    user_address: str
    reward_percentage: Decimal


class StakingRewarder:
    def __init__(
            self,
            *,
            web3: Web3,
            staking_contract_address: str
    ):
        self.web3 = web3
        self.staking_contract = self.web3.eth.contract(
            abi=ABI,
            address=to_address(staking_contract_address)
        )  # TODO: fill this

    def get_rewards_at_block(
            self,
            *,
            user_addresses: List[str],
            block_number: int,
    ) -> List[Reward]:
        print(self.staking_contract.all_functions())
        reward_list: List[Reward] = []
        total_amount_staked = self.staking_contract.functions.totalAmountStaked().call(
            block_identifier=block_number,
        )
        for user_address in user_addresses:
            staked = self.staking_contract.functions.staked(user_address).call()
            print('staked: ', staked)
            reward_percentage = staked / total_amount_staked
            reward_list.append(
                Reward(
                    user_address=user_address,
                    reward_percentage=reward_percentage,
                )
            )
        return reward_list

    def get_staker_addresses(
            self,
            start_block_number: int,
            end_block_number: int,
    ) -> set[Any]:
        # TODO: fill this, copy from tools/staking_snapshot.py
        # Also copy the utils to this folder
        print('self.staking_contract.events.Staked(): ', self.staking_contract.events.Staked())
        events = get_events(
            event=self.staking_contract.events.Staked(),
            from_block=start_block_number,
            to_block=end_block_number,
        )
        print(len(events), 'events')
        return set(
            e.args['user']
            for e in events
        )

    def figure_out_rewards_for_month(
            self,
            year: int,
            month: int,
    ):
        """
        Figure out the rewards for the last day of a month and store them in the database, unless they are already stored

        If the month has not yet passed, do nothing
        """
        # TODO: fill later
        pass

    def distribute_rewards(
            self,
    ):
        """
        Send all unsent rewards to users
        :return:
        """


def main():
    enable_logging()
    # Local testnet with hardhat
    # web3 = Web3(Web3.HTTPProvider("http://localhost:8545/"))
    # staking_contract_address = web3.to_checksum_address('0x5FbDB2315678afecb367f032d93F642f64180aa3')

    # polygon network
    rpc_url = 'https://polygon-rpc.com/'
    web3 = get_web3(rpc_url)
    staking_contract_address = web3.to_checksum_address('0x0DC8c9726e7651aFa4D7294Fb2A3d7eE1436DD4a')
    rewarder = StakingRewarder(
        web3=web3,
        staking_contract_address=staking_contract_address,
    )
    block_number = 30170208
    print('block_number: ', block_number)

    # enable this to get the pre-mined stakers list.
    # user_addresses = get_staker_list()

    user_addresses = []
    if not user_addresses:
        user_addresses = rewarder.get_staker_addresses(
            start_block_number=24199659,
            end_block_number=block_number,
        )
    print("Stakers:", user_addresses)
    rewards = rewarder.get_rewards_at_block(
        user_addresses=user_addresses,
        block_number=block_number,
    )

    for reward in rewards:
        print(reward)
    sum_rewards = sum(r.reward_percentage for r in rewards)
    print('sum_rewards: ', sum_rewards)
