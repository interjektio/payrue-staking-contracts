import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Set
#from .bsc_users import BSC_USERS

from .utils import enable_logging, get_web3, load_abi, get_closest_block, retryable, to_address, get_events

PAYRUE_STAKING_ABI = load_abi('PayRueStaking')
ERC20_ABI = load_abi('IERC20')


def main():
    enable_logging(level=logging.DEBUG)
    bsc_stakers = determine_stakers(
        chain='BSC',
        rpc_url=os.getenv('BSC_RPC_URL', 'https://bsc-dataseed.binance.org/'),
        contract_address='0x0DC8c9726e7651aFa4D7294Fb2A3d7eE1436DD4a',
        start_block=13038838,
        snapshot_datetime=datetime(2022, 3, 1, 10, 0, tzinfo=timezone.utc),
    )
    polygon_stakers = determine_stakers(
        chain='Polygon',
        rpc_url='https://matic-mainnet.chainstacklabs.com',
        contract_address='0x0DC8c9726e7651aFa4D7294Fb2A3d7eE1436DD4a',
        start_block=24171570,
        snapshot_datetime=datetime(2022, 3, 1, 10, 0, tzinfo=timezone.utc),
    )
    print("===========================")
    print("= BSC                     =")
    print("===========================")
    for address, amount in bsc_stakers:
        if amount >= Decimal(1_000_000):
            print(f"{address};{amount}")
    print("")
    print("===========================")
    print("= POLYGON                 =")
    print("===========================")
    for address, amount in polygon_stakers:
        if amount >= Decimal(1_000_000):
            print(f"{address};{amount}")


def determine_stakers(
    *,
    chain: str,
    rpc_url: str,
    contract_address: str,
    start_block: int,
    snapshot_datetime: datetime,
):
    web3 = get_web3(rpc_url)
    print(f"Chain {chain}, rpc url {rpc_url}")
    print("Determining block closest to", snapshot_datetime)
    closest_block = get_closest_block(web3, snapshot_datetime, not_before=True)
    snapshot_block_number = closest_block['number']
    print(
        "Closest block:",
        snapshot_block_number,
        "with timestamp",
        datetime.utcfromtimestamp(closest_block['timestamp']).isoformat()
    )

    print("Staking contract at", contract_address)
    staking_contract = web3.eth.contract(
        address=to_address(contract_address),
        abi=PAYRUE_STAKING_ABI,
    )
    staking_token = web3.eth.contract(
        address=to_address(staking_contract.functions.stakingToken().call()),
        abi=ERC20_ABI
    )
    print("Staking token:", staking_token.functions.symbol().call(), "at", staking_token.address)
    staking_token_decimals = staking_token.functions.decimals().call()
    print(staking_token_decimals, "decimals")
    user_addresses = load_user_addresses(
        chain=chain,
        staking_contract=staking_contract,
        start_block=start_block,
        snapshot_block_number=snapshot_block_number,
    )
    print(user_addresses)
    print(len(user_addresses), 'stakers in total')
    ret = []

    @retryable()
    def get_staked_amount(user_address: str) -> int:
        # Note: we don't use block_identifier since BSC nodes are pruned too eagerly for our needs
        #return staking_contract.functions.staked(user_address).call(block_identifier=snapshot_block_number)
        return staking_contract.functions.staked(user_address).call()

    for u in user_addresses:
        staked_amount = get_staked_amount(u)
        print(u, staked_amount)
        ret.append((u, Decimal(staked_amount) / 10**staking_token_decimals))
    ret.sort(
        key=lambda t: t[1],
        reverse=True,
    )
    return ret


def load_user_addresses(*, chain, staking_contract, start_block, snapshot_block_number) -> Set[str]:
    print(f"Loading Staking events from {start_block} to {snapshot_block_number} to determine users")
    #if chain == 'BSC':
    #    return BSC_USERS
    events = get_events(
        event=staking_contract.events.Staked(),
        from_block=start_block,
        to_block=snapshot_block_number,
    )
    print(len(events), 'events')
    return set(
        e.args['user']
        for e in events
    )


if __name__ == '__main__':
    main()
