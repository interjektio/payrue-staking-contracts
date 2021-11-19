import {network, ethers} from 'hardhat';
import {BigNumber, Contract, Signer, utils} from 'ethers';
import {TransactionResponse} from "@ethersproject/abstract-provider";

const {parseEther} = utils;

export function eth(s: string): BigNumber {
    return parseEther(s.replace(/ /g, ''));
}

export interface TimeTravelOpts {
    days?: number;
    hours?: number;
    minutes?: number;
    seconds?: number;
    mine?: boolean;
}

export async function timeTravel(opts: TimeTravelOpts) {
    let seconds = opts.seconds ?? 0;
    if (opts.minutes) {
        seconds += opts.minutes * 60;
    }
    if (opts.hours) {
        seconds += opts.hours * 60 * 60;
    }
    if (opts.days) {
        seconds += opts.days * 24 * 60 * 60;
    }

    // evm_increaseTime is flaky since time passed in tests affects it.
    const latestBlock = await ethers.provider.getBlock('latest');
    await network.provider.send("evm_setNextBlockTimestamp", [latestBlock.timestamp + seconds]);

    if (opts.mine) {
        await network.provider.send("evm_mine");
    }
}

export async function getTokenBalanceChange(
    tx: TransactionResponse,
    token: Contract,
    account: string | Signer,
): Promise<BigNumber> {
    if (!tx.blockNumber) {
        throw new Error('transaction has not been mined');
    }
    const address = typeof account === 'string' ? account : (await account.getAddress());
    const before = await token.balanceOf(address, {
        blockTag: tx.blockNumber - 1,
    });
    const after = await token.balanceOf(address, {
        blockTag: tx.blockNumber,
    });
    return after.sub(before);
}
