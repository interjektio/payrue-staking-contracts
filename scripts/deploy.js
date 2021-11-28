const hre = require("hardhat");


async function main() {
    const PayRueStaking = await hre.ethers.getContractFactory("PayRueStaking");
    const payRueStaking = await PayRueStaking.deploy("0x5FbDB2315678afecb367f032d93F642f64180aa3","0x5FbDB2315678afecb367f032d93F642f64180aa3");
    await payRueStaking.deployed();
    console.log("payRueStaking deployed to:", payRueStaking.address);

}

main()
    .then(() => process.exit(0))
    .catch(error => {
        console.error(error);
        process.exit(1);
    });
