import functools
import json
import logging
import os
import sys
from datetime import datetime
from time import sleep
from typing import Any, Dict, List, Optional, Union

from eth_account.signers.local import LocalAccount
from eth_typing import AnyAddress
from eth_utils import to_checksum_address
from web3 import Web3
from web3.contract import ContractEvent
from web3.middleware import construct_sign_and_send_raw_middleware, geth_poa_middleware
from web3.types import BlockData

logger = logging.getLogger(__name__)
THIS_DIR = os.path.dirname(__file__)
ABI_DIR = os.path.join(THIS_DIR, 'abi')


def get_web3(rpc_url: str, *, account: Optional[LocalAccount] = None, provider_kwargs=None) -> Web3:
    if provider_kwargs is None:
        provider_kwargs = {}
    web3 = Web3(Web3.HTTPProvider(rpc_url, **provider_kwargs))
    if account:
        set_web3_account(
            web3=web3,
            account=account,
        )

    # Fix this (might not be necessary for all chains)
    # web3.exceptions.ExtraDataLengthError:
    # The field extraData is 97 bytes, but should be 32. It is quite likely that  you are connected to a POA chain.
    # Refer to http://web3py.readthedocs.io/en/stable/middleware.html#geth-style-proof-of-authority for more details.
    web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    return web3


def set_web3_account(*, web3: Web3, account: LocalAccount) -> Web3:
    web3.middleware_onion.add(construct_sign_and_send_raw_middleware(account))
    web3.eth.default_account = account.address
    return web3


def load_abi(name: str) -> List[Dict[str, Any]]:
    abi_path = os.path.join(ABI_DIR, f'{name}.json')
    assert os.path.abspath(abi_path).startswith(os.path.abspath(ABI_DIR))
    with open(abi_path) as f:
        return json.load(f)


def get_events(
    *,
    event: ContractEvent,
    from_block: int,
    to_block: int,
    batch_size: int = 1_000,
    argument_filters=None
):
    """Load events in batches"""
    if to_block < from_block:
        raise ValueError(f'to_block {to_block} is smaller than from_block {from_block}')

    logger.info('fetching events from %s to %s with batch size %s', from_block, to_block, batch_size)
    ret = []
    batch_from_block = from_block
    while batch_from_block <= to_block:
        batch_to_block = min(batch_from_block + batch_size, to_block)
        logger.info('fetching batch from %s to %s (up to %s)', batch_from_block, batch_to_block, to_block)

        events = get_event_batch_with_retries(
            event=event,
            from_block=batch_from_block,
            to_block=batch_to_block,
            argument_filters=argument_filters,
        )
        if len(events) > 0:
            logger.info(f'found %s events in batch', len(events))
        ret.extend(events)
        batch_from_block = batch_to_block + 1
    logger.info(f'found %s events in total', len(ret))
    return ret


def get_event_batch_with_retries(event, from_block, to_block, *, argument_filters=None, retries=10):
    initial_retries = retries
    while True:
        try:
            return event.getLogs(
                fromBlock=from_block,
                toBlock=to_block,
                argument_filters=argument_filters
            )
        except Exception as e:
            if retries <= 0:
                raise e
            logger.warning('error in get_all_entries: %s, retrying (%s)', e, retries)
            retries -= 1
            exponential_sleep(initial_retries - retries)


def exponential_sleep(attempt, max_sleep_time=256.0):
    sleep_time = min(2 ** attempt, max_sleep_time)
    sleep(sleep_time)


def retryable(*, max_attempts: int = 10):
    def decorator(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt >= max_attempts:
                        logger.warning('max attempts (%s) exchusted for error: %s', max_attempts, e)
                        raise
                    logger.warning(
                        'Retryable error (attempt: %s/%s): %s',
                        attempt + 1,
                        max_attempts,
                        e,
                        )
                    exponential_sleep(attempt)
                    attempt += 1
        return wrapped
    return decorator


def to_address(a: Union[bytes, str]) -> AnyAddress:
    # Web3.py expects checksummed addresses, but has no support for EIP-1191,
    # so RSK-checksummed addresses are broken
    # Should instead fix web3, but meanwhile this wrapper will help us
    return to_checksum_address(a)


@functools.lru_cache()
@retryable()
def is_contract(*, web3: Web3, address: str) -> bool:
    code = web3.eth.get_code(to_address(address))
    return code != b'\x00' and code != b''


def get_closest_block(
    web3: Web3,
    wanted_datetime: datetime,
    *,
    not_before: bool = False
) -> BlockData:
    wanted_timestamp = int(wanted_datetime.timestamp())
    logger.debug("Wanted timestamp: %s", wanted_timestamp)
    start_block_number = 1
    end_block_number = web3.eth.block_number
    logger.debug("Bisecting between %s and %s", start_block_number, end_block_number)
    closest_block = None
    closest_diff = 2**256 - 1
    while start_block_number <= end_block_number:
        target_block_number = (start_block_number + end_block_number) // 2
        block: BlockData = web3.eth.get_block(target_block_number)
        block_timestamp = block['timestamp']

        diff = block_timestamp - wanted_timestamp
        logger.debug(
            "target: %s, timestamp: %s, diff %s",
            target_block_number,
            block_timestamp,
            diff
        )

        # Only update block when diff actually gets lower
        # This is only necessary in the last steps of the bisect, but we might as well do it every round
        if abs(diff) < closest_diff:
            closest_diff = abs(diff)
            closest_block = block

        if block_timestamp > wanted_timestamp:
            # block is after wanted, move end
            end_block_number = block['number'] - 1
        elif block_timestamp < wanted_timestamp:
            # block is before wanted, move start
            start_block_number = block['number'] + 1
        else:
            # timestamps are exactly the same, just return block
            return block

    if closest_block is None:
        raise LookupError('Unable to determine block closest to ' + wanted_datetime.isoformat())

    if not_before and closest_block["timestamp"] < wanted_timestamp:
        logger.debug("Block is before wanted timestamp and not_before=True, returning next block")
        return web3.eth.get_block(closest_block["number"] + 1)

    return closest_block


def enable_logging(root_name: str = None, level=logging.INFO):
    root = logging.getLogger(root_name)
    root.setLevel(logging.NOTSET)
    formatter = logging.Formatter('%(asctime)s - %(name)s [%(levelname)s] %(message)s')

    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    info_handler = logging.StreamHandler(sys.stdout)
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)
    root.addHandler(info_handler)

    logger.setLevel(level)
