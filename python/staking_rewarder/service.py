import datetime
import json
import logging
import os
import web3.eth

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Any

from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from eth_account import Account
from hexbytes import HexBytes
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker, scoped_session
from web3 import Web3

from .messengers import Messenger, SlackMessenger
from .models import (
    RewardDistribution,
    DistributionRound,
    RewardState,
    KeyValuePair,
    session_factory,
    autocommit_engine,
)
from .utils import to_address, get_web3, get_events, enable_logging, get_closest_block

abi_path = os.path.join(os.path.dirname(__file__), "abi")
abi_file = os.path.join(abi_path, "PayRueStaking.json")
ABI = json.loads(open(abi_file).read())

token_abi_file = os.path.join(abi_path, "IERC20.json")
TOKEN_ABI = json.loads(open(token_abi_file).read())

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
        self,
        *,
        web3: Web3,
        staking_contract_address: str,
        messenger: Messenger,
        session_factory: sessionmaker[Session],
        token_contract: web3.eth.Contract,
        reward_distributor_account: Account,
        last_scanned_block_number=None,
        auto_commit_engine=None,
    ):
        self.web3 = web3
        self.staking_contract = self.web3.eth.contract(
            abi=ABI, address=to_address(staking_contract_address)
        )
        self.session_factory = session_factory
        self.token_contract = token_contract
        self.db_session = scoped_session(self.session_factory)
        self.auto_commit_session = session_factory(bind=auto_commit_engine)
        self.logger = logging.getLogger(__name__)
        self.min_reward_amount = 0
        self.messenger = messenger
        self.last_scanned_block_number = (
            24199659 if last_scanned_block_number is None else last_scanned_block_number
        )
        self.reward_distributor_account = reward_distributor_account

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

        try:
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
        except Exception as e:
            self.messenger.send_message(
                title="Error while figuring out rewards",
                message=f"Exception: {str(e)}\n",
                msg_type="danger",
            )
            raise e
        return rewards

    def get_unsent_rewards(self):
        return (
            self.db_session.execute(
                select(RewardDistribution).where(
                    RewardDistribution.state == RewardState.unsent
                )
            )
            .scalars()
            .all()
        )

    def distribute_rewards(self):
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

        # TODO: maybe set nonces. or should it be in figure_out_rewards? THIS CAN BE DONE LATER
        nonce = self.web3.eth.get_transaction_count(
            self.reward_distributor_account.address
        )
        with self.auto_commit_session.begin():
            unsent_rewards = (
                self.auto_commit_session.execute(
                    select(RewardDistribution).where(
                        RewardDistribution.state == RewardState.unsent
                    )
                )
                .scalars()
                .all()
            )
        print("amount of unsent rewards: ", len(unsent_rewards))
        try:
            for reward in unsent_rewards:
                with self.auto_commit_session.begin():
                    reward.state = RewardState.sending
                    user_address = self.web3.to_checksum_address(reward.user_address)
                    amount_wei = reward.amount_wei

                # send reward with web3
                tx_hash = self.token_contract.functions.transfer(
                    user_address,
                    amount_wei,
                ).transact(
                    {
                        "from": self.reward_distributor_account.address,
                        "nonce": nonce,
                        "gasPrice": self.web3.eth.gas_price,
                        "gas": 100000,
                    }
                )
                nonce += 1
                with self.auto_commit_session.begin():
                    reward.state = RewardState.sent
                    reward.tx_hash = tx_hash.hex()

            sent_rewards = unsent_rewards
            for reward in sent_rewards:
                with self.auto_commit_session.begin():
                    tx_receipt = self.web3.eth.wait_for_transaction_receipt(
                        HexBytes(reward.tx_hash)
                    )
                    if tx_receipt.status == 0:
                        raise Exception("Transaction failed")
                    elif tx_receipt.status == 1:
                        reward.state = RewardState.confirmed
        except Exception as e:
            self.messenger.send_message(
                title="Error while distributing rewards",
                message=f"Exception: {str(e)}\n",
                msg_type="danger",
            )
            raise e

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
    token_contract_address = web3.to_checksum_address(
        "0x5FbDB2315678afecb367f032d93F642f64180aa3"
    )
    token_contract = web3.eth.contract(address=token_contract_address, abi=TOKEN_ABI)
    reward_distributor_account = web3.eth.account.from_key(
        "0x2d8d3b7e7d6d3a5c4b7e8a3d7e6d3a5c4b7e8a3d7e6d3a5c4b7e8a3d7e6d3a5c"
    )
    rewarder = StakingRewarder(
        web3=web3,
        staking_contract_address=staking_contract_address,
        messenger=SlackMessenger(WEBHOOK_URL),
        session_factory=session_factory,
        token_contract=token_contract,
        reward_distributor_account=reward_distributor_account,
        auto_commit_engine=autocommit_engine,
    )
    rewarder.figure_out_rewards_for_month(
        year=2022,
        month=1,
    )
    rewarder.distribute_rewards()
