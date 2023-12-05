import datetime
import json
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Any

from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from sqlalchemy import select
from web3 import Web3

from .messengers import Messenger, SlackMessenger
from .models import (
    RewardDistribution,
    DistributionRound,
    RewardState,
    KeyValuePair,
    db_session,
    session_factory,
    autocommit_engine,
)
from .utils import to_address, get_web3, get_events, enable_logging, get_closest_block

abi_path = os.path.join(os.path.dirname(__file__), "abi")
abi_file = os.path.join(abi_path, "PayRueStaking.json")
ABI = json.loads(open(abi_file).read())

load_dotenv()
WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

if not WEBHOOK_URL:
    print("No Slack webhook URL provided")


@dataclass
class Reward:
    user_address: str
    percentage: Decimal
    state: RewardState
    amount_wei: Decimal = Decimal(0)


# TODO: add transaction management (ZOPE)

class StakingRewarder:
    def __init__(
        self, *, web3: Web3, staking_contract_address: str, messenger: Messenger
    ):
        self.web3 = web3
        self.staking_contract = self.web3.eth.contract(
            abi=ABI, address=to_address(staking_contract_address)
        )
        self.db_session = db_session
        self.auto_commit_session = session_factory(bind=autocommit_engine)
        self.logger = logging.getLogger(__name__)
        self.min_reward_amount = 0
        self.messenger = messenger
        self.last_scanned_block_number = 24199659

    def get_distribution_round(self, year: int, month: int) -> DistributionRound:
        """
        Get all distribution rounds
        :return:
        """
        conditions = [
            DistributionRound.year == year,
            DistributionRound.month == month,
        ]
        stmt = select(DistributionRound).where(
            *conditions,
        )
        return self.db_session.execute(stmt).scalars().first()

    def get_rewards_at_block(
        self,
        *,
        user_addresses: List[str],
        block_number: int,
    ) -> List[Reward]:
        """
        Get the rewards for a list of users at a specific block number

        totalAmountStaked: return the total amount of staked tokens for all users
        staked: return the amount of staked tokens for a user
        """
        if not user_addresses:
            self.logger.info("No user addresses provided")
            return []

        rewards: List[Reward] = []
        total_amount_staked = self.staking_contract.functions.totalAmountStaked().call(
            block_identifier=block_number,
        )
        for user_address in user_addresses:
            staked = self.staking_contract.functions.staked(user_address).call(
                block_identifier=block_number,
            )
            reward_percentage = Decimal(str(staked)) / total_amount_staked
            rewards.append(
                Reward(
                    user_address=user_address,
                    percentage=reward_percentage,
                    state=RewardState.unsent,
                )
            )
        return rewards

    def get_staker_addresses_from_events(
        self,
        start_block_number: int,
        end_block_number: int,
    ) -> set[Any]:
        events = get_events(
            event=self.staking_contract.events.Staked(),
            from_block=start_block_number,
            to_block=end_block_number,
        )
        print(len(events), "events")
        return set(e.args.user for e in events)

    @staticmethod
    def get_last_day_of_month(year: int, month: int):
        snapshot_datetime = datetime.datetime(
            year=year, month=month, day=1, tzinfo=datetime.timezone.utc
        )
        last_day_of_month = snapshot_datetime + relativedelta(months=1, microseconds=-1)
        return last_day_of_month

    @staticmethod
    def has_month_passed(last_day_of_month: datetime):
        current_datetime = datetime.datetime.now(datetime.timezone.utc)
        return last_day_of_month <= current_datetime

    def get_stakers(self, end_block_number: int) -> list:
        """
        Get stakers by address
        :return:
        """

        stakers_last_scanned_block_number = self.db_session.get(
            KeyValuePair, "stakers_last_scanned_block_number"
        )

        staker_addresses_from_last_scanned_block = self.db_session.get(
            KeyValuePair, "staker_addresses"
        )
        if stakers_last_scanned_block_number:
            self.last_scanned_block_number = stakers_last_scanned_block_number.value

        if end_block_number < self.last_scanned_block_number:
            if not staker_addresses_from_last_scanned_block:
                return []
            return staker_addresses_from_last_scanned_block.value

        new_stakers = self.get_staker_addresses_from_events(
            self.last_scanned_block_number + 1, end_block_number
        )
        self.last_scanned_block_number = end_block_number

        if (
            staker_addresses_from_last_scanned_block
            and stakers_last_scanned_block_number
        ):
            staker_addresses_from_last_scanned_block.value = list(new_stakers)
            stakers_last_scanned_block_number.value = self.last_scanned_block_number
        else:
            staker_addresses_from_last_scanned_block = KeyValuePair(
                key="staker_addresses",
                value=list(new_stakers),
            )
            stakers_last_scanned_block_number = KeyValuePair(
                key="stakers_last_scanned_block_number",
                value=self.last_scanned_block_number,
            )
            self.db_session.add(staker_addresses_from_last_scanned_block)
            self.db_session.add(stakers_last_scanned_block_number)
        self.db_session.flush()
        return staker_addresses_from_last_scanned_block.value

    def figure_out_rewards_for_month(
        self,
        year: int,
        month: int,
    ):
        """
        Figure out the rewards for the last day of a month and store them in the database, unless they are already stored

        If the month has not yet passed, do nothing
        """
        # TODO: add transaction management
        last_day_of_month = self.get_last_day_of_month(year, month)

        if not self.has_month_passed(last_day_of_month):
            self.logger.info("Month has not yet passed")
            return

        # we only distribute rewards once per user per month
        distribution_round = self.get_distribution_round(
            year=last_day_of_month.year,
            month=last_day_of_month.month,
        )
        if distribution_round:
            self.logger.info("Rewards already distributed for this month")
            return

        distribution_round = DistributionRound(
            year=year,
            month=month,
        )
        self.db_session.add(distribution_round)
        self.db_session.flush()
        closest_block = get_closest_block(
            self.web3,
            last_day_of_month,
        )
        print(
            "closest_block: ",
            closest_block["number"],
            datetime.datetime.utcfromtimestamp(closest_block["timestamp"]),
        )
        end_block_number = closest_block["number"]

        staker_addresses = self.get_stakers(end_block_number)

        rewards = self.get_rewards_at_block(
            user_addresses=list(staker_addresses),
            block_number=self.last_scanned_block_number,
        )
        if not rewards:
            self.logger.info("No rewards to distribute")
            return

        # TODO: Get the revenue from chains
        monthly_revenue = self.web3.to_wei(1_000_000, "ether")
        total_reward_to_distribute = int(monthly_revenue * Decimal("0.25"))
        for reward in rewards:
            reward.amount_wei = int(total_reward_to_distribute * reward.percentage)
            if reward.amount_wei < self.min_reward_amount:
                continue

            reward_distribution = RewardDistribution(
                user_address=reward.user_address,
                percentage=reward.percentage,
                amount_wei=reward.amount_wei,
                state=RewardState.unsent,
            )
            reward_distribution.distribution_round_id = distribution_round.id
            self.db_session.add(reward_distribution)
        self.db_session.commit()
        return rewards

    def distribute_rewards(self):
        # TODO: maybe set nonces. or should it be in figure_out_rewards? THIS CAN BE DONE LATER
        sending_rewards = (
            self.db_session.execute(
                select(RewardDistribution).where(
                    RewardDistribution.state == RewardState.sending
                )
            )
            .scalars()
            .all()
        )
        if sending_rewards:
            self.messenger.send_message(
                title="Error while distributing rewards",
                message="Sending rewards already in progress",
                msg_type="danger",
            )
            raise Exception("Sending rewards already in progress")

        with self.auto_commit_session as session:
            with session.begin():
                unsent_rewards = (
                    session.execute(
                        select(RewardDistribution).where(
                            RewardDistribution.state == RewardState.unsent
                        )
                    )
                    .scalars()
                    .all()
                )
            print("unsent_rewards: ", unsent_rewards)
            try:
                for reward in unsent_rewards:
                    with session.begin():
                        reward.state = RewardState.sending
                    # send reward with web3
                    with session.begin():
                        reward.state = RewardState.sent
            except Exception as e:
                self.messenger.send_message(
                    title="Error while distributing rewards",
                    message=f"Exception: {str(e)}\n",
                    msg_type="danger",
                )
                raise e

        # # THIS STEP OPTIONAL, WRITE LATER
        # sent_rewards = unsent_rewards
        # for reward in sent_rewards:
        #     check that the reward tx was successful and update state to "confirmed" or mined

        # ==========INSTRUCTIONS==============
        # sending_rewards = select rewards that are in state "sending"
        # if sending_rewards:
        #     RAISE HELL. send message to slack. but not every minute!
        #
        # # TODO: maybe set nonces. or should it be in figure_out_rewards? THIS CAN BE DONE LATER
        # with self.transaction_manager:
        #     unsent_rewards = select from db, should be ordered
        # try:
        #     for reward in unsent_rewards:
        #         with self.transaction_manager:
        #             update reward state to "sending" IN A TRANSACTION
        #         send reward with web3
        #         with self.transaction_manager:
        #             update reward state to "sent" IN A TRANSACTION and store transaction hash in reward
        # except Exception as e:
        #     send message to slack
        #     raise
        #
        # # THIS STEP OPTIONAL, WRITE LATER
        # sent_rewards = unsent_rewards
        # for reward in sent_rewards:
        #     check that the reward tx was successful and update state to "confirmed" or mined


def main():
    enable_logging()
    # polygon network
    rpc_url = "https://polygon-rpc.com/"
    web3 = get_web3(rpc_url)
    staking_contract_address = web3.to_checksum_address(
        "0x0DC8c9726e7651aFa4D7294Fb2A3d7eE1436DD4a"
    )
    rewarder = StakingRewarder(
        web3=web3,
        staking_contract_address=staking_contract_address,
        messenger=SlackMessenger(WEBHOOK_URL),
    )
    rewards = rewarder.figure_out_rewards_for_month(
        year=2022,
        month=1,
    )
    rewarder.distribute_rewards()
