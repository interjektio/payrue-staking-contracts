import {expect} from 'chai';
import {beforeEach, describe, it, Test} from 'mocha';
import {ethers} from 'hardhat';
import {BigNumber, constants, Contract, ContractFactory, Signer} from 'ethers';
import {
    eth,
    getTokenBalanceChange,
    initTimetravelReferenceBlock,
    timeTravel,
} from './utils';

interface TestConfig {
    contractName: string;
    stakingTokenIsRewardToken: boolean;
    rewardNumerator?: number;
    rewardDenominator?: number;
}

// The same contract adapts for multiple different use cases:
// - same token for staking and rewarding
// - different tokens for staking and rewarding
// - reward payout of 1:1
// - reward payout different than 1:1
// We test all combinations.
// In addition, we have a version of the contract that checks for invariants when calling functions.
// We run all tests both with the regular contract and that contract, to catch even more bugs.
const CONFIGS: TestConfig[] = [
    {
        contractName: 'PayRueStaking',
        stakingTokenIsRewardToken: true,
    },
    {
        contractName: 'PayRueStaking',
        stakingTokenIsRewardToken: false,
    },
    {
        contractName: 'InvariantCheckedPayRueStaking',
        stakingTokenIsRewardToken: true,
    },
    {
        contractName: 'InvariantCheckedPayRueStaking',
        stakingTokenIsRewardToken: false,
    },
    {
        contractName: 'PayRueStaking',
        stakingTokenIsRewardToken: false,
        rewardNumerator: 1249_653022,
        rewardDenominator:  1_000000,
    },
    {
        contractName: 'PayRueStaking',
        stakingTokenIsRewardToken: true,
        rewardNumerator: 1249_653022,
        rewardDenominator:  1_000000,
    },
    {
        contractName: 'InvariantCheckedPayRueStaking',
        stakingTokenIsRewardToken: false,
        rewardNumerator: 1249_653022,
        rewardDenominator:  1_000000,
    },
    {
        contractName: 'InvariantCheckedPayRueStaking',
        stakingTokenIsRewardToken: true,
        rewardNumerator: 1249_653022,
        rewardDenominator:  1_000000,
    },
];

for (let {
    contractName,
    stakingTokenIsRewardToken,
    rewardNumerator = 1,
    rewardDenominator = 1
} of CONFIGS) {
    let description = contractName;
    if (stakingTokenIsRewardToken) {
        description += ` (same token for staking + reward; reward multiplier ${rewardNumerator/rewardDenominator})`
    } else {
        description += ` (different tokens for staking + reward; reward multiplier ${rewardNumerator/rewardDenominator})`
    }

    describe(description, function() {
        let staking: Contract;
        let adminStaking: Contract;
        let stakingToken: Contract;
        let rewardToken: Contract;
        let TestToken: ContractFactory;

        let ownerAccount: Signer;
        let stakerAccount: Signer;
        let anotherAccount: Signer;
        let ownerAddress: string;
        let stakerAddress: string;
        let anotherAddress: string;

        beforeEach(async () => {
            const accounts = await ethers.getSigners();
            ownerAccount = accounts[0];
            stakerAccount = accounts[1];
            anotherAccount = accounts[2];
            ownerAddress = await ownerAccount.getAddress();
            stakerAddress = await stakerAccount.getAddress();
            anotherAddress = await anotherAccount.getAddress();

            TestToken = await ethers.getContractFactory('TestToken');
            stakingToken = await TestToken.deploy("Staking token", "STAKING");
            if (stakingTokenIsRewardToken) {
                rewardToken = stakingToken;
            } else {
                rewardToken = await TestToken.deploy("Reward token", "REWARD");
            }

            const PayRueStaking = await ethers.getContractFactory(contractName);
            adminStaking = await PayRueStaking.deploy(
                stakingToken.address,
                rewardToken.address,
                rewardNumerator,
                rewardDenominator
            );
            await adminStaking.deployed();
            staking = adminStaking.connect(stakerAccount);
        });

        function multiplyByRewardRatio(number: BigNumber): BigNumber {
            return number.mul(BigNumber.from(rewardNumerator)).div(BigNumber.from(rewardDenominator));
        }

        function divideByRewardRatio(number: BigNumber): BigNumber {
            return number.mul(BigNumber.from(rewardDenominator)).div(BigNumber.from(rewardNumerator));
        }

        interface InitTestOpts {
            rewardAmount?: BigNumber|string,
            stakerBalance?: BigNumber|string,
            stakedAmount?: BigNumber|string,
        }
        async function initTest({
            rewardAmount = '1 000 000 000',
            stakerBalance = '10 000 000 000',
            stakedAmount
        }: InitTestOpts) {
            if (typeof rewardAmount === 'string') {
                rewardAmount = eth(rewardAmount);
            }
            if (typeof stakerBalance === 'string') {
                stakerBalance = eth(stakerBalance);
            }
            if (typeof stakedAmount === 'string') {
                stakedAmount = eth(stakedAmount);
            }
            await rewardToken.mint(ownerAddress, rewardAmount);
            await rewardToken.transfer(staking.address, rewardAmount);

            if (!(stakerBalance as BigNumber).isZero()) {
                await stakingToken.mint(stakerAddress, stakerBalance);
                await stakingToken.connect(stakerAccount).approve(staking.address, constants.MaxUint256);
            }

            if (stakedAmount && !(stakedAmount as BigNumber).isZero()) {
                await staking.stake(stakedAmount);
            }
        }

        it("initial state", async () => {
            expect(await staking.totalAmountStaked()).to.be.equal(0);
            expect(await staking.totalLockedReward()).to.be.equal(0);
        });

        describe('stake', () => {
            beforeEach(async () => {
                await initTest({
                    rewardAmount: '1 000 000 000',
                });
            });

            it('cannot stake more than balance', async () => {
                await stakingToken.setBalance(stakerAddress, eth('30 000').sub(1));
                await expect(
                    staking.stake(eth('30 000'))
                ).to.be.revertedWith('ERC20: transfer amount exceeds balance');
            });

            it('cannot stake less than min amount', async () => {
                const minAmount = await staking.minStakeAmount();
                await expect(
                    staking.stake(minAmount.sub(1))
                ).to.be.revertedWith('Minimum stake amount not met');
            });

            it('cannot stake more than available reward amount', async () => {
                await stakingToken.mint(stakerAddress, eth('1 000 000 000').add(1));
                const maxAmount = divideByRewardRatio(eth('1 000 000 000'));
                await expect(
                    staking.stake(maxAmount.add(1))
                ).to.be.revertedWith('Not enough rewards left to accept new stakes for given amount');
            });

            it('emits the Staked event', async () => {
                await expect(
                    staking.stake(eth('12 345'))
                ).to.emit(staking, 'Staked').withArgs(
                    stakerAddress,
                    eth('12 345')
                );
            });

            it('changes token balances and updates internal amounts', async () => {
                const initialAvailableReward = divideByRewardRatio(eth('1 000 000 000'));
                expect(await staking.staked(stakerAddress)).to.equal(0);
                expect(await staking.totalAmountStaked()).to.equal(0);
                expect(await staking.totalLockedReward()).to.equal(0);
                expect(await staking.availableToStakeOrReward()).to.equal(initialAvailableReward);

                const amount = eth('11 111');
                await expect(
                    () => staking.stake(amount)
                ).to.changeTokenBalances(
                    stakingToken,
                    [staking, stakerAccount],
                    [amount, amount.mul(-1)]
                );
                expect(await staking.staked(stakerAddress)).to.equal(amount);
                expect(await staking.totalAmountStaked()).to.equal(amount);
                expect(await staking.totalLockedReward()).to.equal(multiplyByRewardRatio(amount));
                expect(await staking.availableToStakeOrReward()).to.equal(initialAvailableReward.sub(amount));

                const amount2 = eth('22 222');
                await expect(
                    () => staking.stake(amount2)
                ).to.changeTokenBalances(
                    stakingToken,
                    [staking, stakerAccount],
                    [amount2, amount2.mul(-1)]
                );
                expect(await staking.staked(stakerAddress)).to.equal(amount.add(amount2));
                expect(await staking.totalAmountStaked()).to.equal(amount.add(amount2));
                expect(await staking.totalLockedReward()).to.equal(multiplyByRewardRatio(amount.add(amount2)));
                expect(await staking.availableToStakeOrReward()).to.equal(initialAvailableReward.sub(amount).sub(amount2));
            });

            it('test multiple stakers', async () => {
                await stakingToken.setBalance(anotherAddress, eth('500 000'));
                await stakingToken.connect(anotherAccount).approve(staking.address, eth('500 000'));

                const amount = eth('45 000');
                await staking.stake(amount);
                const amount2 = eth('20 500');
                await staking.connect(anotherAccount).stake(amount2);

                expect(await staking.staked(stakerAddress)).to.equal(amount);
                expect(await staking.staked(anotherAddress)).to.equal(amount2);
                expect(await staking.totalAmountStaked()).to.equal(amount.add(amount2));
                expect(await staking.totalLockedReward()).to.equal(multiplyByRewardRatio(amount.add(amount2)));
            });
        })

        describe('rewards', () => {
            it('calculating and claiming work but are no-ops for empty state', async () => {
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(0);
                await expect(
                    () => staking.claimReward()
                ).to.changeTokenBalances(
                    rewardToken,
                    [stakerAccount, staking],
                    [0, 0]
                );
                await expect(
                    staking.claimReward()
                ).to.not.emit(staking, 'RewardPaid');
            });

            it('calculating works after staking', async () => {
                await initTest({
                    stakedAmount: '20 000',
                });
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(0);

                await timeTravel({ days: 1, mine: true });
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(
                    multiplyByRewardRatio(eth('20 000')).div(365)
                );

                await timeTravel({ days: 181, hours: 12, mine: true });
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(
                    multiplyByRewardRatio(eth('10 000'))
                );

                await timeTravel({ days: 182, hours: 12, mine: true });
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(
                    multiplyByRewardRatio(eth('20 000'))
                );

                await timeTravel({ days: 1, mine: true });
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(
                    multiplyByRewardRatio(eth('20 000')).add(
                        multiplyByRewardRatio(eth('20 000')).div(365)
                    )
                );
            });

            it('claiming works after staking', async () => {
                await initTest({
                    stakedAmount: '20 000',
                });

                await timeTravel({ days: 181, hours: 12, mine: true });
                await timeTravel({ days: 183, hours: 12 });

                let tx: any;
                await expect(
                    () => tx = staking.claimReward(),
                ).to.changeTokenBalances(
                    rewardToken,
                    [stakerAccount, staking],
                    [multiplyByRewardRatio(eth('20 000')), multiplyByRewardRatio(eth('-20 000'))]
                );

                await expect(tx).to.emit(staking, 'RewardPaid').withArgs(
                    stakerAddress,
                    multiplyByRewardRatio(eth('20 000')),
                );

                await timeTravel({ days: 182, hours: 12 });


                await expect(
                    () => tx = staking.claimReward(),
                ).to.changeTokenBalances(
                    rewardToken,
                    [stakerAccount, staking],
                    [multiplyByRewardRatio(eth('10 000')), multiplyByRewardRatio(eth('-10 000'))]
                );
            });

            it('claim when there is nothing more to claim', async () => {
                await initTest({
                    rewardAmount: multiplyByRewardRatio(eth('20 000')),
                    stakedAmount: '20 000',
                });

                await timeTravel({ days: 400 }); // more than period

                let tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, rewardToken, stakerAccount)).to.equal(
                    multiplyByRewardRatio(eth('20 000'))
                );

                await timeTravel({ days: 182, hours: 12 });

                tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, rewardToken, stakerAccount)).to.equal(eth('0'));

                await rewardToken.mint(staking.address, multiplyByRewardRatio(eth('10 000')));

                tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, rewardToken, stakerAccount)).to.equal(
                    multiplyByRewardRatio(eth('10 000'))
                );
            });

            it('claim with multiple stakers', async () => {
                await stakingToken.mint(stakerAddress, eth('10 000'));
                await stakingToken.mint(anotherAddress, eth('15 000'));
                await stakingToken.connect(stakerAccount).approve(staking.address, eth('10 000'));
                await stakingToken.connect(anotherAccount).approve(staking.address, eth('15 000'));

                await initTest({
                    rewardAmount: multiplyByRewardRatio(eth('25 000')),
                    stakedAmount: '0',
                    stakerBalance: '0'
                });

                const referenceBlock = await initTimetravelReferenceBlock();

                let tx = await staking.stake(eth('10 000'));
                expect(await getTokenBalanceChange(tx, stakingToken, stakerAccount)).to.equal(eth('-10 000'));

                await timeTravel({ days: 365 / 5, fromBlock: referenceBlock });

                tx = await staking.connect(anotherAccount).stake(eth('15 000'));
                expect(await getTokenBalanceChange(tx, stakingToken, anotherAccount)).to.equal(eth('-15 000'));

                await timeTravel({ days: 365 / 5 * 2, fromBlock: referenceBlock });

                // staker1 can claim 40%, staker2 20%
                // staker1: claim 40% of total
                tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, rewardToken, stakerAccount)).to.equal(
                    multiplyByRewardRatio(eth('4 000'))
                );

                // staker1 can claim 60%, staker2 40%
                await timeTravel({ days: 365 / 5 * 3, fromBlock: referenceBlock });

                // staker2: claim 40% of total
                tx = await staking.connect(anotherAccount).claimReward();
                expect(await getTokenBalanceChange(tx, rewardToken, anotherAccount)).to.equal(
                    multiplyByRewardRatio(eth('6 000'))
                );

                // both can claim 100% of funds left
                await timeTravel({ days: 365 / 5 * 6, fromBlock: referenceBlock });

                // staker2: claim 100% of rest (= 60% of total)
                tx = await staking.connect(anotherAccount).claimReward();
                expect(await getTokenBalanceChange(tx, rewardToken, anotherAccount)).to.equal(
                    multiplyByRewardRatio(eth('9 000'))
                );

                // staker1: claim 100% of rest (= 60% of total)
                tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, rewardToken, stakerAccount)).to.equal(
                    multiplyByRewardRatio(eth('6 000'))
                );

                // try to claim with both, nothing happens
                tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, rewardToken, stakerAccount)).to.equal(eth('0'));

                tx = await staking.connect(anotherAccount).claimReward();
                expect(await getTokenBalanceChange(tx, rewardToken, anotherAccount)).to.equal(eth('0'));

                await expect(
                    staking.unstake(eth('10 001'))
                ).to.be.reverted;

                tx = await staking.unstake(eth('10 000'));
                expect(await getTokenBalanceChange(tx, stakingToken, stakerAccount)).to.equal(eth('10 000'));

                tx = await staking.connect(anotherAccount).exit();
                expect(await getTokenBalanceChange(tx, stakingToken, anotherAccount)).to.equal(eth('15 000'));
            });
        });

        describe('exit', () => {
            let referenceBlock: number;

            beforeEach(async () => {
                await initTest({
                    rewardAmount: multiplyByRewardRatio(eth('30 000')),
                    stakerBalance: '20 000',
                });

                referenceBlock = await initTimetravelReferenceBlock();
                await staking.stake(eth('10 000'));
            });

            it('does not work before locked period has passed', async () => {
                await timeTravel({
                    days: 364,
                    hours: 23,
                    minutes: 59,
                    seconds: 59,
                    fromBlock: referenceBlock
                });
               await expect(
                   staking.exit()
               ).to.be.revertedWith('Unstaking is only allowed after the locked period has expired')
            });

            it('works after locked period has passed', async () => {
                await timeTravel({ days: 365, fromBlock: referenceBlock });
                let tx = await staking.exit();
                if (stakingTokenIsRewardToken) {
                    expect(
                        await getTokenBalanceChange(tx, stakingToken, stakerAddress)
                    ).to.equal(
                        eth('10 000').add(multiplyByRewardRatio(eth('10 000')))
                    );
                } else {
                    expect(
                        await getTokenBalanceChange(tx, stakingToken, stakerAddress)
                    ).to.equal(eth('10 000'));
                    expect(
                        await getTokenBalanceChange(tx, rewardToken, stakerAddress)
                    ).to.equal(multiplyByRewardRatio(eth('10 000')));
                }
                expect(await staking.totalAmountStaked()).to.equal(0);
                expect(await staking.availableToStake()).to.equal(eth('20 000'));
            });

            it('works after more than locked period has passed', async () => {
                await timeTravel({ days: 365/5*6, fromBlock: referenceBlock });

                const tx = await staking.exit();

                if (stakingTokenIsRewardToken) {
                    expect(
                        await getTokenBalanceChange(tx, stakingToken, stakerAddress)
                    ).to.equal(
                        eth('10 000').add(multiplyByRewardRatio(eth('12 000')))
                    );
                } else {
                    expect(
                        await getTokenBalanceChange(tx, stakingToken, stakerAddress)
                    ).to.equal(eth('10 000'));
                    expect(
                        await getTokenBalanceChange(tx, rewardToken, stakerAddress)
                    ).to.equal(
                        multiplyByRewardRatio(eth('12 000'))
                    );
                }

                expect(await staking.totalAmountStaked()).to.equal(0);
                expect(await staking.availableToStake()).to.equal(eth('18 000'));
            });
        });

        describe('withdrawTokens', () => {
            beforeEach(async () => {
                await initTest({
                    rewardAmount: multiplyByRewardRatio(eth('20 000')),
                    stakerBalance: '10 000',
                    stakedAmount: '10 000'
                });
            });

            it('non-owners cannot withdraw', async () => {
                await expect(
                    staking.withdrawTokens(stakingToken.address, eth('1 000'))
                ).to.be.revertedWith('Ownable: caller is not the owner');
            });

            it('owner can withdraw rewardToken up to locked amount', async () => {
                const maxAmount = multiplyByRewardRatio(eth('10 000'));
                await expect(
                    adminStaking.withdrawTokens(rewardToken.address, maxAmount.add(1))
                ).to.be.revertedWith('Can only withdraw up to balance minus locked amount');

                await expect(
                    () => adminStaking.withdrawTokens(rewardToken.address, maxAmount)
                ).to.changeTokenBalances(
                    rewardToken,
                    [ownerAccount, staking],
                    [maxAmount, maxAmount.mul(-1)]
                );

                expect(await adminStaking.availableToReward()).to.equal(0);

                await expect(
                    adminStaking.withdrawTokens(rewardToken.address, 1)
                ).to.be.revertedWith('Can only withdraw up to balance minus locked amount');

                await rewardToken.mint(adminStaking.address, 1000);
                await expect(
                    () => adminStaking.withdrawTokens(rewardToken.address, 1000)
                ).to.changeTokenBalances(
                    rewardToken,
                    [ownerAccount, staking],
                    [1000, -1000]
                );
            });

            it('owner can withdraw random tokens', async() => {
                const randomToken = await TestToken.deploy('Random token', 'RANDOM');
                await expect(
                    adminStaking.withdrawTokens(randomToken.address, 1)
                ).to.be.reverted;

                await randomToken.mint(adminStaking.address, 1234);

                await expect(
                    adminStaking.withdrawTokens(randomToken.address, 1235)
                ).to.be.reverted;

                await expect(
                    () => adminStaking.withdrawTokens(randomToken.address, 1234)
                ).to.changeTokenBalances(
                    randomToken,
                    [ownerAccount, staking],
                    [1234, -1234]
                );
            });

            if (!stakingTokenIsRewardToken) {
                it('owner can withdraw stakingToken up to non-staked amount', async () => {
                    await expect(
                        adminStaking.withdrawTokens(stakingToken.address, 1)
                    ).to.be.revertedWith('Cannot withdraw staked tokens');

                    await stakingToken.mint(adminStaking.address, 1000);
                    await expect(
                        adminStaking.withdrawTokens(stakingToken.address, 1001)
                    ).to.be.revertedWith('Cannot withdraw staked tokens');

                    await expect(
                        () => adminStaking.withdrawTokens(stakingToken.address, 1000)
                    ).to.changeTokenBalances(
                        stakingToken,
                        [ownerAccount, staking],
                        [1000, -1000]
                    );

                    await expect(
                        adminStaking.withdrawTokens(stakingToken.address, 1)
                    ).to.be.revertedWith('Cannot withdraw staked tokens');
                });
            }
        });

        describe('emergency withdrawal', () => {
            beforeEach(async () => {
                await initTest({
                    rewardAmount: multiplyByRewardRatio(eth('30 000')),
                    stakerBalance: '20 000',
                    stakedAmount: '10 000'
                });
            });

            it('non-owners cannot initiate', async () => {
                await expect(
                    staking.initiateEmergencyWithdrawal()
                ).to.be.revertedWith('Ownable: caller is not the owner');
            });

            it('owners can initiate', async () => {
                await adminStaking.initiateEmergencyWithdrawal();
                expect(await adminStaking.emergencyWithdrawalInProgress()).to.be.true;
            });

            it('emits correct event', async () => {
                await expect(
                    adminStaking.initiateEmergencyWithdrawal()
                ).to.emit(adminStaking, 'EmergencyWithdrawalInitiated');
            });

            it('prevents new stakes', async () => {
                await adminStaking.initiateEmergencyWithdrawal();
                await expect(
                    staking.stake(eth('10 000'))
                ).to.be.revertedWith('Emergency withdrawal in progress, no new stakes accepted');
            });

            it('prevents new stakes', async () => {
                await adminStaking.initiateEmergencyWithdrawal();
                await expect(
                    staking.stake(eth('10 000'))
                ).to.be.revertedWith('Emergency withdrawal in progress, no new stakes accepted');
            });

            it('forcibly exiting users does not work without emergency withdrawal', async () => {
                await expect(
                    adminStaking.forceExitUser(stakerAddress)
                ).to.be.revertedWith('Emergency withdrawal not in progress');
            });

            it('only owner can forcibly exit users', async () => {
                await adminStaking.initiateEmergencyWithdrawal();
                await expect(
                    staking.forceExitUser(stakerAddress)
                ).to.be.revertedWith('Ownable: caller is not the owner');
            });

            it('forcibly exiting users works when emergency withdrawal is in progress', async () => {
                await adminStaking.initiateEmergencyWithdrawal();

                let tx = await adminStaking.forceExitUser(stakerAddress);

                if (stakingTokenIsRewardToken) {
                    expect(
                        await getTokenBalanceChange(tx, stakingToken, stakerAddress)
                    ).to.equal(
                        eth('10 000').add(
                            multiplyByRewardRatio(eth('10 000'))
                        )
                    ); // stake + reward
                } else {
                    expect(
                        await getTokenBalanceChange(tx, stakingToken, stakerAddress)
                    ).to.equal(eth('10 000'));
                    expect(
                        await getTokenBalanceChange(tx, rewardToken, stakerAddress)
                    ).to.equal(multiplyByRewardRatio(eth('10 000')));
                }

                expect(await staking.totalAmountStaked()).to.equal(0);
                expect(await staking.totalStoredReward()).to.equal(0);
                expect(await staking.totalGuaranteedReward()).to.equal(0);
                expect(await staking.totalLockedReward()).to.equal(0);

                if (stakingTokenIsRewardToken) {
                    const balance = await stakingToken.balanceOf(staking.address);
                    tx = await adminStaking.withdrawTokens(stakingToken.address, balance);
                    expect(await getTokenBalanceChange(tx, stakingToken, ownerAddress)).to.equal(balance);
                } else {
                    const stakingTokenBalance = await stakingToken.balanceOf(staking.address);
                    const rewardTokenBalance = await rewardToken.balanceOf(staking.address);
                    tx = await adminStaking.withdrawTokens(stakingToken.address, stakingTokenBalance);
                    expect(await getTokenBalanceChange(tx, stakingToken, ownerAddress)).to.equal(stakingTokenBalance);
                    tx = await adminStaking.withdrawTokens(rewardToken.address, rewardTokenBalance);
                    expect(await getTokenBalanceChange(tx, rewardToken, ownerAddress)).to.equal(rewardTokenBalance);
                }
            });
        });

        describe('pause', () => {
            it('non-owners cannot set paused', async () => {
                await expect(
                    staking.setPaused(true)
                ).to.be.revertedWith('Ownable: caller is not the owner');
            });

            it('owners can set paused', async () => {
                await adminStaking.setPaused(true);
                expect(await adminStaking.paused()).to.be.true;
                await adminStaking.setPaused(false);
                expect(await adminStaking.paused()).to.be.false;
            });

            it('pause prevents new stakes', async () => {
                await initTest({
                    rewardAmount: multiplyByRewardRatio(eth('30 000')),
                    stakerBalance: '20 000',
                    stakedAmount: '10 000'
                });
                await adminStaking.setPaused(true);
                await expect(
                    staking.stake(eth('10 000'))
                ).to.be.revertedWith('Staking is temporarily paused, no new stakes accepted');

                await adminStaking.setPaused(false);
                await staking.stake(eth('10 000'))
            });
        });

        describe('setMinStakeAmount', () => {
            it('non-owners cannot change minStakeAmount', async () => {
                await expect(
                    staking.setMinStakeAmount(123)
                ).to.be.revertedWith('Ownable: caller is not the owner');
            });

            it('owners can change minStakeAmount', async () => {
                await adminStaking.setMinStakeAmount(123);
                expect(await adminStaking.minStakeAmount()).to.equal(123);
            });

            it('minStakeAmount cannot be set to 0', async () => {
                await expect(
                    adminStaking.setMinStakeAmount(0)
                ).to.be.revertedWith('Minimum stake amount must be at least 1');
            });
        });

        describe('VERY SLOW tests', () => {
            it('test claiming very small amounts and then unstaking (rounding errors)', async () => {
                // The reward per second is 50 000 000 / 365*24*60*60 = 1.5854895991882294,
                // which gets rounded down by solidity to 1 with a significant (58,5%) rounding error
                // Note that this amount is in wei, not ether / 10^18 units
                const rewardAmount = BigNumber.from(50_000_000);
                const minStakeAmount = divideByRewardRatio(rewardAmount);
                await adminStaking.setMinStakeAmount(minStakeAmount);
                const totalAmountStaked = minStakeAmount;

                await initTest({
                    rewardAmount: rewardAmount,
                    stakerBalance: totalAmountStaked,
                });

                const referenceBlock = await initTimetravelReferenceBlock();
                await staking.stake(totalAmountStaked);
                expect(await rewardToken.balanceOf(stakerAddress)).to.equal(0);

                const iterations = 250;
                for(let i = 1; i <= iterations; i++) {
                    await timeTravel({ seconds: i, fromBlock: referenceBlock });
                    const tx = await staking.claimReward();
                    // >>> (20_000 * 10**18) / (365 * 24 * 60 * 60)
                    // 634195839675291.8
                    // Which will get truncated to 634195839675291 by bignumber arithmetic
                    // So this causes a small but compounding rounding error
                    const balanceChange = await getTokenBalanceChange(tx, rewardToken, stakerAddress);
                    expect(
                        balanceChange
                    ).to.equal(
                        multiplyByRewardRatio(minStakeAmount).div(365 * 24 * 60 * 60)
                    );
                    // next line is sanity check, can be skipped
                    expect(balanceChange).to.equal(1);
                }

                // more sanity checks, total change is close to, but LESS THAN the actual change
                const expectedTotalChange = multiplyByRewardRatio(minStakeAmount).div(365 * 24 * 60 * 60 / iterations)
                const rewardTokenBalance = await rewardToken.balanceOf(stakerAddress);
                expect(
                    rewardTokenBalance
                ).to.be.closeTo(expectedTotalChange, 150);
                expect(
                    rewardTokenBalance.lt(expectedTotalChange)
                ).to.be.true;

                await timeTravel({ days: 365, fromBlock: referenceBlock });
                await staking.unstake(totalAmountStaked);
                await staking.claimReward();

                if (stakingTokenIsRewardToken) {
                    expect(
                        await rewardToken.balanceOf(stakerAddress)
                    ).to.equal(
                        totalAmountStaked.add(
                            multiplyByRewardRatio(totalAmountStaked)
                        )
                    );
                } else {
                    expect(
                        await rewardToken.balanceOf(stakerAddress)
                    ).to.equal(
                        multiplyByRewardRatio(totalAmountStaked)
                    );
                }
                expect(await staking.totalAmountStaked()).to.equal(0);
                expect(await staking.totalGuaranteedReward()).to.equal(0);
                expect(await staking.totalLockedReward()).to.equal(0);
            });

            if (rewardNumerator === rewardDenominator) {
                // This test tests precise amounts and is too hard to get right with reward multipliers
                it('test claiming very small amounts that result in zero rewards (rounding errors)', async () => {
                    // The reward per second is 0.1 (3 153 600 / 365*24*60*60)
                    // which gets rounded down by solidity to 0.
                    // This should be accounted for, so that claiming only every second returns in a reward of 1
                    // every 10 times.
                    // Note that this amount is in wei, not ether
                    const minStakeAmount = BigNumber.from(3_153_600);
                    await adminStaking.setMinStakeAmount(minStakeAmount);
                    const totalAmountStaked = minStakeAmount;

                    await initTest({
                        rewardAmount: totalAmountStaked,
                        stakerBalance: totalAmountStaked,
                    });

                    const referenceBlock = await initTimetravelReferenceBlock();
                    await staking.stake(totalAmountStaked);
                    expect(await rewardToken.balanceOf(stakerAddress)).to.equal(0);

                    const iterations = 50;
                    for (let i = 1; i <= iterations; i++) {
                        await timeTravel({seconds: i, fromBlock: referenceBlock});
                        const tx = await staking.claimReward();
                        // >>> (20_000 * 10**18) / (365 * 24 * 60 * 60)
                        // 634195839675291.8
                        // Which will get truncated to 634195839675291 by bignumber arithmetic
                        // So this causes a small but compounding rounding error
                        const balanceChange = await getTokenBalanceChange(tx, rewardToken, stakerAddress);
                        if (i % 10 == 0) {
                            expect(balanceChange).to.equal(1);
                        } else {
                            expect(balanceChange).to.equal(0);
                        }
                    }

                    expect(
                        await rewardToken.balanceOf(stakerAddress)
                    ).to.be.equal(5);

                    await timeTravel({days: 365, fromBlock: referenceBlock});
                    const tx = await staking.claimReward();
                    expect(
                        await getTokenBalanceChange(tx, rewardToken, stakerAccount)
                    ).to.equal(totalAmountStaked.sub(iterations / 10));
                    expect(
                        await rewardToken.balanceOf(stakerAddress)
                    ).to.equal(totalAmountStaked);
                    expect(await staking.totalGuaranteedReward()).to.equal(0);
                    expect(await staking.totalLockedReward()).to.equal(0);

                    await staking.unstake(totalAmountStaked);

                    expect(await staking.totalAmountStaked()).to.equal(0);
                    expect(await staking.totalGuaranteedReward()).to.equal(0);
                    expect(await staking.totalLockedReward()).to.equal(0);
                });
            }
        });
    });
}
