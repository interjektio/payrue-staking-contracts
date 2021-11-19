import {network} from 'hardhat';
import {BigNumber, Contract, Signer, utils} from 'ethers';

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
    await network.provider.send("evm_increaseTime", [seconds]);

    if (opts.mine) {
        await network.provider.send("evm_mine");
    }
}
