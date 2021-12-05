PayRue Staking Contracts
========================

Features and assumptions:
- Users stake token A and receive token B. These can be same or different tokens, e.g. PROPEL and PROPEL or PROPEL
  and LP token.
- APY is configurable with rewardNumerator/rewardDenominator -- with 1 and 1 it's 100%, which means
  you stake 10 000 PROPEL, you get 10 000 PROPEL as rewards during the next year.
- Each stake is guaranteed the reward in 365 days, after which they can still get new rewards if
  there is reward money left in the contract. If the reward cannot be guaranteed, the stake will not be accepted.
- Each stake is locked for 365 days, after which it can be unstaked or left in the contract.
