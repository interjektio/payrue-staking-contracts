import {expect} from 'chai';
import {beforeEach, describe, it} from 'mocha';
import {ethers} from 'hardhat';
import {BigNumber, BigNumberish, constants, Contract, Signer} from 'ethers';
import {
    eth,
    getTokenBalanceChange,
    initTimetravelReferenceBlock,
    timeTravel,
} from './utils';

const CONTRACTS = [
    //'PayRueStaking',
    'InvariantCheckedPayRueStaking'
];

for (let contractName of CONTRACTS) {
    describe(contractName, function() {
        let staking: Contract;
        let adminStaking: Contract;
        let propelToken: Contract;

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

            const TestToken = await ethers.getContractFactory('TestToken');
            propelToken = await TestToken.deploy("Propel", "PROPEL");
            const PayRueStaking = await ethers.getContractFactory(contractName);
            adminStaking = await PayRueStaking.deploy(
                propelToken.address,
                propelToken.address,
            );
            await adminStaking.deployed();
            staking = adminStaking.connect(stakerAccount);
        });

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
            await propelToken.mint(ownerAddress, rewardAmount);
            await propelToken.transfer(staking.address, rewardAmount);

            if (!(stakerBalance as BigNumber).isZero()) {
                await propelToken.mint(stakerAddress, stakerBalance);
                await propelToken.connect(stakerAccount).approve(staking.address, constants.MaxUint256);
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
                await propelToken.setBalance(stakerAddress, eth('30 000').sub(1));
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

            it('cannot stake less more than available reward amount', async () => {
                await propelToken.mint(stakerAddress, eth('1 000 000 000').add(1));
                await expect(
                    staking.stake(eth('1 000 000 000').add(1))
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
                const initialAvailableReward = eth('1 000 000 000');
                expect(await staking.staked(stakerAddress)).to.equal(0);
                expect(await staking.totalAmountStaked()).to.equal(0);
                expect(await staking.totalLockedReward()).to.equal(0);
                expect(await staking.availableToStakeOrReward()).to.equal(initialAvailableReward);

                const amount = eth('11 111');
                await expect(
                    () => staking.stake(amount)
                ).to.changeTokenBalances(
                    propelToken,
                    [staking, stakerAccount],
                    [amount, amount.mul(-1)]
                );
                expect(await staking.staked(stakerAddress)).to.equal(amount);
                expect(await staking.totalAmountStaked()).to.equal(amount);
                expect(await staking.totalLockedReward()).to.equal(amount);
                expect(await staking.availableToStakeOrReward()).to.equal(initialAvailableReward.sub(amount));

                const amount2 = eth('22 222');
                await expect(
                    () => staking.stake(amount2)
                ).to.changeTokenBalances(
                    propelToken,
                    [staking, stakerAccount],
                    [amount2, amount2.mul(-1)]
                );
                expect(await staking.staked(stakerAddress)).to.equal(amount.add(amount2));
                expect(await staking.totalAmountStaked()).to.equal(amount.add(amount2));
                expect(await staking.totalLockedReward()).to.equal(amount.add(amount2));
                expect(await staking.availableToStakeOrReward()).to.equal(initialAvailableReward.sub(amount).sub(amount2));
            });

            it('test multiple stakers', async () => {
                await propelToken.setBalance(anotherAddress, eth('500 000'));
                await propelToken.connect(anotherAccount).approve(staking.address, eth('500 000'));

                const amount = eth('45 000');
                await staking.stake(amount);
                const amount2 = eth('20 500');
                await staking.connect(anotherAccount).stake(amount2);

                expect(await staking.staked(stakerAddress)).to.equal(amount);
                expect(await staking.staked(anotherAddress)).to.equal(amount2);
                expect(await staking.totalAmountStaked()).to.equal(amount.add(amount2));
                expect(await staking.totalLockedReward()).to.equal(amount.add(amount2));
            });
        })

        describe('rewards', () => {
            it('calculating and claiming work but are no-ops for empty state', async () => {
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(0);
                await expect(
                    () => staking.claimReward()
                ).to.changeTokenBalances(
                    propelToken,
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
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(eth('20 000').div(365));

                await timeTravel({ days: 181, hours: 12, mine: true });
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(eth('10 000'));

                await timeTravel({ days: 182, hours: 12, mine: true });
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(eth('20 000'));

                await timeTravel({ days: 1, mine: true });
                expect(await staking.rewardClaimable(stakerAddress)).to.equal(
                    eth('20 000').add(eth('20 000').div(365))
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
                    propelToken,
                    [stakerAccount, staking],
                    [eth('20 000'), eth('-20 000')]
                );

                await expect(tx).to.emit(staking, 'RewardPaid').withArgs(
                    stakerAddress,
                    eth('20 000'),
                );

                await timeTravel({ days: 182, hours: 12 });

                await expect(
                    () => tx = staking.claimReward(),
                ).to.changeTokenBalances(
                    propelToken,
                    [stakerAccount, staking],
                    [eth('10 000'), eth('-10 000')]
                );
            });

            it('claim when there is nothing more to claim', async () => {
                await initTest({
                    rewardAmount: '20 000',
                    stakedAmount: '20 000',
                });

                await timeTravel({ days: 400 }); // more than period

                let tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, propelToken, stakerAccount)).to.equal(eth('20 000'));

                await timeTravel({ days: 182, hours: 12 });

                tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, propelToken, stakerAccount)).to.equal(eth('0'));

                await propelToken.mint(staking.address, eth('10 000'));

                tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, propelToken, stakerAccount)).to.equal(eth('10 000'));
            });

            it('claim with multiple stakers', async () => {
                await propelToken.mint(stakerAddress, eth('10 000'));
                await propelToken.mint(anotherAddress, eth('15 000'));
                await propelToken.connect(stakerAccount).approve(staking.address, eth('10 000'));
                await propelToken.connect(anotherAccount).approve(staking.address, eth('15 000'));

                await initTest({
                    rewardAmount: '25 000',
                    stakedAmount: '0',
                    stakerBalance: '0'
                });

                const referenceBlock = await initTimetravelReferenceBlock();

                let tx = await staking.stake(eth('10 000'));
                expect(await getTokenBalanceChange(tx, propelToken, stakerAccount)).to.equal(eth('-10 000'));

                await timeTravel({ days: 365 / 5, fromBlock: referenceBlock });

                tx = await staking.connect(anotherAccount).stake(eth('15 000'));
                expect(await getTokenBalanceChange(tx, propelToken, anotherAccount)).to.equal(eth('-15 000'));

                await timeTravel({ days: 365 / 5 * 2, fromBlock: referenceBlock });

                // staker1 can claim 40%, staker2 20%
                // staker1: claim 40% of total
                tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, propelToken, stakerAccount)).to.equal(eth('4 000'));

                // staker1 can claim 60%, staker2 40%
                await timeTravel({ days: 365 / 5 * 3, fromBlock: referenceBlock });

                // staker2: claim 40% of total
                tx = await staking.connect(anotherAccount).claimReward();
                expect(await getTokenBalanceChange(tx, propelToken, anotherAccount)).to.equal(eth('6 000'));

                // both can claim 100% of funds left
                await timeTravel({ days: 365 / 5 * 6, fromBlock: referenceBlock });

                // staker2: claim 100% of rest (= 60% of total)
                tx = await staking.connect(anotherAccount).claimReward();
                expect(await getTokenBalanceChange(tx, propelToken, anotherAccount)).to.equal(eth('9 000'));

                // staker1: claim 100% of rest (= 60% of total)
                tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, propelToken, stakerAccount)).to.equal(eth('6 000'));

                // try to claim with both, nothing happens
                tx = await staking.claimReward();
                expect(await getTokenBalanceChange(tx, propelToken, stakerAccount)).to.equal(eth('0'));

                tx = await staking.connect(anotherAccount).claimReward();
                expect(await getTokenBalanceChange(tx, propelToken, anotherAccount)).to.equal(eth('0'));

                await expect(
                    staking.unstake(eth('10 001'))
                ).to.be.reverted;

                tx = await staking.unstake(eth('10 000'));
                expect(await getTokenBalanceChange(tx, propelToken, stakerAccount)).to.equal(eth('10 000'));

                tx = await staking.connect(anotherAccount).exit();
                expect(await getTokenBalanceChange(tx, propelToken, anotherAccount)).to.equal(eth('15 000'));
            });
        });
    });
}
