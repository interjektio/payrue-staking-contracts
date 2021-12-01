PayRue Staking Contracts
========================

Features and assumptions:
- Users stake PROPEL and also receive PROPEL (though it also supports other tokens with 1:1 reward ratio)
- APY is always 100% - you stake 10 000 PROPEL, you get 10 000 PROPEL as rewards during the next year
- Each stake is guaranteed the 100% reward in 365 days, after which they can still get new rewards if
  there is reward money left in the contract. If the reward cannot be guaranteed, the stake will not be accepted.
- Each stake is locked for 365 days, after which it can be unstaked or left in the contract

