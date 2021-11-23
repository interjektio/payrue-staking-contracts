// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import "hardhat/console.sol";

/*
TODO:
[x] Stake VPROPEL, receive PROPEL
[x] Fixed staking duration (1 year, 365 days)
[x] Fixed APY per duration (100% per year)
[x] Max total staked amount which will either (do what?)
[x] Unstake is possible after 1 year has passed from the staking
[x] On unstake, get back VPROPEL
[x] Min stake amount 10k VPROPEL
[ ] Withdraw non-locked tokens by admin
[ ] Withdraw other tokens by admin
[ ] Emergency withdraw (by admin) ??
[ ] Upgradeable ??
[ ] Pause ??
[ ] Force unstake user?
*/

// Features and assumptions:
// - Users stake PROPEL and receive PROPEL
// - APY is always 100% - you stake 10 000 VPROPEL, you get 10 000 PROPEL during the next year
// - Each stake is guaranteed the 100% reward in 365 days, after which they can still get new rewards if
//   there is reward money left in the contract. If the reward cannot be guaranteed, the stake will not be accepted.
// - Each stake is locked for 365 days, after which it can be unstaked or left in the contract
contract PayRueStaking is ReentrancyGuard, Ownable {
    event Staked(
        address indexed user,
        uint256 amount
    );

    event Unstaked(
        address indexed user,
        uint256 amount
    );

    event RewardPaid(
        address indexed user,
        uint256 amount
    );

    struct Stake {
        uint256 amount;
        uint256 timestamp;
    }

    struct UserStakingData {
        uint256 amountStaked;
        uint256 guaranteedReward;
        uint256 storedReward;
        uint256 storedRewardUpdatedOn;
        uint256 firstActiveStakeIndex; // for gas optimization if many stakes
        Stake[] stakes;
    }

    uint256 public constant lockedPeriod = 365 days;
    uint256 public constant yieldPeriod = 365 days;
    uint256 public constant dustAmount = 1 ether;  // Amount of PROPEL/VPROPEL considered insignificant
    uint256 public constant minStakeAmount = 10_000 ether; // should be at least 1

    IERC20 public stakingToken;
    IERC20 public rewardToken;
    bool internal _stakingTokenIsRewardToken;

    mapping(address => UserStakingData) stakingDataByUser;

    uint256 public totalAmountStaked = 0;
    uint256 public totalGuaranteedReward = 0;
    uint256 public totalStoredReward = 0;

    constructor(
        address _stakingToken,
        address _rewardToken
    )
    Ownable()
    {
        stakingToken = IERC20(_stakingToken);
        rewardToken = IERC20(_rewardToken);
        _stakingTokenIsRewardToken = _stakingToken == _rewardToken;
    }

    // PUBLIC USER API
    // ===============

    function stake(
        uint256 amount
    )
    public
    virtual
    nonReentrant
    {
        require(amount >= minStakeAmount, "Minimum stake amount not met");
        // This needs to be checked before accepting the stake, in case stakedToken and rewardToken are the same
        require(
            availableToStakeOrReward() >= amount,
            "Not enough rewards left to accept new stakes for given amount"
        );
        require(
            stakingToken.transferFrom(msg.sender, address(this), amount),
            "Cannot transfer balance"
        );

        UserStakingData storage userData = stakingDataByUser[msg.sender];

        // Update stored reward, in case the user has already staked
        _updateStoredReward(userData);

        userData.stakes.push(Stake({
            amount: amount,
            timestamp: block.timestamp
        }));
        userData.amountStaked += amount;
        totalAmountStaked += amount;
        userData.guaranteedReward += amount;
        totalGuaranteedReward += amount;
        userData.storedRewardUpdatedOn = block.timestamp;  // may waste some gas, but would rather be safe than sorry


        emit Staked(
            msg.sender,
            amount
        );
    }

    function claimReward()
    public
    virtual
    nonReentrant
    {
        _rewardUser(msg.sender);
    }

    function unstake(
        uint256 amount
    )
    public
    virtual
    nonReentrant
    {
        _unstakeUser(msg.sender, amount);
    }

    function exit()
    public
    virtual
    nonReentrant
    {
        UserStakingData storage userData = stakingDataByUser[msg.sender];
        if (userData.amountStaked > 0) {
            _unstakeUser(msg.sender, userData.amountStaked);
        }
        _rewardUser(msg.sender);
        require(userData.storedReward == 0, "Invariant for storedReward failed");
        require(userData.amountStaked == 0, "Invariant for amountStaked failed");
        require(userData.guaranteedReward == 0, "Invariant for guaranteedReward failed");
        delete stakingDataByUser[msg.sender];
    }

    // PUBLIC VIEWS AND UTILITIES
    // ==========================

    function availableToStakeOrReward()
    public
    view
    returns (uint256 stakeable)
    {
        stakeable = rewardToken.balanceOf(address(this)) - totalLockedReward();
        if (_stakingTokenIsRewardToken) {
            stakeable -= totalAmountStaked;
        }
    }


    function totalLockedReward()
    public
    view
    returns (uint256 locked)
    {
        locked = totalStoredReward + totalGuaranteedReward;
    }

    function rewardClaimable(
        address user
    )
    public
    view
    returns (uint256 reward)
    {
        UserStakingData storage userData = stakingDataByUser[user];
        reward = userData.storedReward;
        reward += _calculateStoredRewardToAdd(userData);
    }

    function staked(
        address user
    )
    public
    view
    returns (uint256 amount)
    {
        UserStakingData storage userData = stakingDataByUser[user];
        return userData.amountStaked;
    }

    // OWNER API
    // =========

    function payRewardToUser(
        address user
    )
    public
    virtual
    onlyOwner
    nonReentrant
    {
        _rewardUser(user);
    }

    // INTERNAL API
    // ============

    function _rewardUser(
        address user
    )
    internal
    {
        UserStakingData storage userData = stakingDataByUser[user];
        _updateStoredReward(userData);

        uint256 reward = userData.storedReward;
        if (reward == 0) {
            return;
        }

        userData.storedReward = 0;
        totalStoredReward -= reward;

        require(
            rewardToken.transfer(user, reward),
            "Sending reward failed"
        );

        emit RewardPaid(
            user,
            reward
        );
    }


    function _unstakeUser(
        address user,
        uint256 amount
    )
    private
    {
        require(amount > 0, "Cannot unstake zero amount");

        UserStakingData storage userData = stakingDataByUser[user];
        _updateStoredReward(userData);

        uint256 amountLeft = amount;

        uint256 i = userData.firstActiveStakeIndex;
        for (; i < userData.stakes.length; i++) {
            if (userData.stakes[i].amount == 0) {
                continue;
            }

            require(
                userData.stakes[i].timestamp < block.timestamp - lockedPeriod,
                "Unstaking is only allowed after the locked period has expired"
            );
            if (userData.stakes[i].amount > amountLeft) {
                userData.stakes[i].amount -= amountLeft;
                amountLeft = 0;
                break;
            } else {
                // stake amount equal to or smaller than amountLeft
                amountLeft -= userData.stakes[i].amount;
                userData.stakes[i].amount = 0;
                delete userData.stakes[i];  // this should be safe and saves a little bit of gas, but also leaves a gap in the array
            }
        }

        require(
            amountLeft == 0,
            "Not enough staked balance left to unstake all of wanted amount"
        );

        userData.firstActiveStakeIndex = i;
        userData.amountStaked -= amount;
        totalAmountStaked -= amount;

        // If the user has a very low staked amount or guaranteed reward left, just pay all reward.
        // This is probably necessary since we might get small rounding errors when handling rewards,
        // and we might even end up in a state where the user has guaranteed reward and 0 staked amount, which would
        // mean that the guaranteed reward can never be cleared.
        if (
            userData.guaranteedReward > 0 && (userData.amountStaked <= dustAmount || userData.guaranteedReward <= dustAmount)
        ) {
            userData.storedReward += userData.guaranteedReward;
            userData.guaranteedReward = 0;
            userData.storedRewardUpdatedOn = block.timestamp;
        }

        require(
            stakingToken.transfer(msg.sender, amount),
            "Transferring staked token back to sender failed"
        );

        emit Unstaked(
            msg.sender,
            amount
        );
    }

    function _updateStoredReward(
        UserStakingData storage userData
    )
    internal
    {
        uint256 addedStoredReward = _calculateStoredRewardToAdd(userData);
        if (addedStoredReward != 0) {
            userData.storedReward += addedStoredReward;
            totalStoredReward += addedStoredReward;
            if (addedStoredReward > userData.guaranteedReward) {
                totalGuaranteedReward -= userData.guaranteedReward;
                userData.guaranteedReward = 0;
            } else {
                userData.guaranteedReward -= addedStoredReward;
                totalGuaranteedReward -= addedStoredReward;
            }
            userData.storedRewardUpdatedOn = block.timestamp;
        }
    }

    function _calculateStoredRewardToAdd(
        UserStakingData storage userData
    )
    internal
    view
    returns (uint256 storedRewardToAdd) {
        if (userData.storedRewardUpdatedOn == 0 || userData.storedRewardUpdatedOn == block.timestamp) {
            // safety check -- don't want to accidentally multiply everything by the unix epoch instead of time passed
            return 0;
        }
        uint256 timePassedFromLastUpdate = block.timestamp - userData.storedRewardUpdatedOn;
        storedRewardToAdd = (userData.amountStaked * timePassedFromLastUpdate) / yieldPeriod;

        // We can pay out more than guaranteed, but only if we have enough non-locked funds for it
        if (storedRewardToAdd > userData.guaranteedReward) {
            uint256 excess = storedRewardToAdd - userData.guaranteedReward;
            uint256 available = availableToStakeOrReward();
            if (excess > available) {
                storedRewardToAdd = storedRewardToAdd - excess + available;
            }
        }
    }
}