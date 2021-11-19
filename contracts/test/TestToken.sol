//SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract TestToken is ERC20 {
    constructor(
        string memory name,
        string memory symbol
    )
    ERC20(name, symbol)
    {
    }

    function mint(
        address account,
        uint256 amount
    )
    public
    {
        _mint(account, amount);
    }

    function burn(
        address account,
        uint256 amount
    )
    public
    {
        _burn(account, amount);
    }

    function setBalance(
        address account,
        uint256 balance
    )
    public
    {
        if (balanceOf(account) > balance) {
            burn(account, balanceOf(account) - balance);
        } else if (balanceOf(account) < balance) {
            mint(account, balance - balanceOf(account));
        }
    }
}
