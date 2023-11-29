import datetime
import json
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Set, Any
from web3 import Web3

from sqlalchemy import select
from .models import RewardDistribution, DistributionRound, RewardState, db_session
from .stakerslist import get_staker_list
from .utils import to_address, get_web3, get_events, enable_logging, get_closest_block
from dateutil.relativedelta import relativedelta

abi_path = os.path.join(os.path.dirname(__file__), 'abi')
abi_file = os.path.join(abi_path, 'PayRueStaking.json')
ABI = json.loads(open(abi_file).read())


@dataclass
class Reward:
    user_address: str
    percentage: Decimal
    state: RewardState
    amount: Decimal = Decimal(0)


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
        )
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)

    def get_rewards_at_block(
            self,
            *,
            user_addresses: List[str],
            block_number: int,
    ) -> List[Reward]:
        """
        totalAmountStaked: return the total amount of staked tokens for all users
        staked: return the amount of staked tokens for a user
        """
        rewards: List[Reward] = []
        total_amount_staked = self.staking_contract.functions.totalAmountStaked().call(
            block_identifier=block_number,
        )
        print('total_amount_staked: ', total_amount_staked)
        for user_address in user_addresses:
            staked = self.staking_contract.functions.staked(user_address).call(
                block_identifier=block_number,
            )
            reward_percentage = Decimal(staked) / total_amount_staked
            rewards.append(
                Reward(
                    user_address=user_address,
                    percentage=reward_percentage,
                    state=RewardState.unsent,
                )
            )
        return rewards

    def get_staker_addresses(
            self,
            start_block_number: int,
            end_block_number: int,
    ) -> set[Any]:
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

    @staticmethod
    def get_last_day_of_month(year: int, month: int):
        snapshot_datetime = datetime.datetime(
            year=year,
            month=month,
            day=1,
            tzinfo=datetime.timezone.utc
        )
        last_day_of_month = snapshot_datetime + relativedelta(months=1, microseconds=-1)
        return last_day_of_month

    @staticmethod
    def has_month_passed(last_day_of_month: datetime):
        current_datetime = datetime.datetime.now(datetime.timezone.utc)
        return last_day_of_month <= current_datetime

    def get_distribution_round(self, year: int, month: int) -> DistributionRound:
        """
        Get all distribution rounds
        :return:
        """
        stmt = select(DistributionRound).where(
            DistributionRound.year == year,
            DistributionRound.month == month,
        )
        return self.db_session.execute(stmt).scalars().first()

    def figure_out_rewards_for_month(
            self,
            year: int,
            month: int,
    ):
        """
        Figure out the rewards for the last day of a month and store them in the database, unless they are already stored

        If the month has not yet passed, do nothing
        """
        last_day_of_month = self.get_last_day_of_month(year, month)

        if not self.has_month_passed(last_day_of_month):
            return

        # we only distribute rewards once per user per month
        distribution_round = self.get_distribution_round(
            year=last_day_of_month.year,
            month=last_day_of_month.month,
        )
        if distribution_round:
            self.logger.info('Rewards already distributed for this month')
            return

        closest_block = get_closest_block(
            self.web3,
            last_day_of_month,
        )
        print(
            'closest_block: ',
            closest_block['number'],
            datetime.datetime.utcfromtimestamp(
                closest_block['timestamp'])
        )
        block_number = closest_block['number']
        start_block_number = 24199659  # TODO: should be the end block number of the previous month if it exists in the database
        staker_addresses = self.get_staker_addresses(
            start_block_number=start_block_number,
            end_block_number=block_number,
        )
        rewards = self.get_rewards_at_block(
            user_addresses=list(staker_addresses),
            block_number=block_number,
        )
        # revenue 1_000_000 as an example
        # total_revenue = self.web3.to_wei(1_000_000, 'ether')

        if not distribution_round:
            return rewards

    def distribute_rewards(
            self,
            rewards: List[Reward],
            year: int,
            month: int,
    ):
        """
        Send all unsent rewards to users
        :return:
        """
        if not rewards:
            self.logger.info('No rewards to distribute')
            return

        distribution_round = self.get_distribution_round(
            year=year,
            month=month,
        )
        if not distribution_round:
            distribution_round = DistributionRound(
                year=year,
                month=month,
            )
            self.db_session.add(distribution_round)
            self.db_session.flush()

        for reward in rewards:
            reward_distribution = RewardDistribution(
                user_address=reward.user_address,
                percentage=reward.percentage,
                amount=reward.amount,
                state=RewardState.sent,
            )
            reward_distribution.distribution_round_id = distribution_round.id
            self.db_session.add(reward_distribution)

        self.db_session.commit()


def main():
    enable_logging()
    # polygon network
    rpc_url = 'https://polygon-rpc.com/'
    web3 = get_web3(rpc_url)
    staking_contract_address = web3.to_checksum_address('0x0DC8c9726e7651aFa4D7294Fb2A3d7eE1436DD4a')
    rewarder = StakingRewarder(
        web3=web3,
        staking_contract_address=staking_contract_address,
    )
    rewards = rewarder.figure_out_rewards_for_month(
        year=2022,
        month=1,
    )
    rewarder.distribute_rewards(
        rewards=rewards,
        year=2022,
        month=1,
    )
