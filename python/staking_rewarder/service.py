from decimal import Decimal
from typing import List
from dataclasses import dataclass

from web3 import Web3


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
        self.staking_contract = self.web3.eth.contract(...) # TODO: fill this

    def get_rewards_at_block(
        self,
        *,
        user_addresses: List[str],
        block_number: int,
    ) -> List[Reward]:
        # TODO: fill this
        pass

    def get_staker_addresses(
        self,
        start_block_number: int,
        end_block_number: int,
    ) -> List[str]:
        # TODO: fill this, copy from tools/staking_snapshot.py
        # Also copy the utils to this folder
        pass

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
    web3 = ...
    staking_contract_address = ...
    rewarder = StakingRewarder(
        web3=web3,
        staking_contract_address=staking_contract_address,
    )

    block_number = ...
    user_addresses = rewarder.get_staker_addresses(
        start_block_number=24171570,
        end_block_number=block_number,
    )
    print("Stakers:", user_addresses)
    rewards = rewarder.get_rewards_at_block(
        user_addresses=user_addresses,
        block_number=block_number,
    )
    for reward in rewards:
        print(reward)