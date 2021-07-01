import "@nomiclabs/hardhat-waffle";
import "hardhat-deploy";
import dotenv from "dotenv";
import {task} from "hardhat/config";

dotenv.config();

const INFURA_API_KEY = process.env.INFURA_API_KEY || '';
const DEPLOYER_PRIVATE_KEY = process.env.DEPLOYER_PRIVATE_KEY || '';
const ETHERSCAN_API_KEY = process.env.ETHERSCAN_API_KEY || '';

if (!INFURA_API_KEY) {
  console.warn('INFURA_API_KEY missing, Ethereum networks not working');
}
if (!DEPLOYER_PRIVATE_KEY) {
  console.warn('DEPLOYER_PRIVATE_KEY missing, deployment not working');
}

// This is a sample Hardhat task. To learn how to create your own go to
// https://hardhat.org/guides/create-task.html
task("accounts", "Prints the list of accounts", async (args, hre) => {
  const accounts = await hre.ethers.getSigners();

  for (const account of accounts) {
    console.log(account.address);
  }
});

const privateKeys = DEPLOYER_PRIVATE_KEY ? [DEPLOYER_PRIVATE_KEY] : [];

export default {
  solidity: {
    compilers: [
      {
        version: "0.8.4",
      },
    ]
  },
  networks: {
    hardhat: {},
    mainnet: {
      url: `https://mainnet.infura.io/v3/${INFURA_API_KEY}`,
      accounts: privateKeys,
    },
    rinkeby: {
      url: `https://rinkeby.infura.io/v3/${INFURA_API_KEY}`,
      accounts: privateKeys,
    },
  },
  namedAccounts: {
    deployer: {
      default: 0
    },
  },
  etherscan: {
    apiKey: ETHERSCAN_API_KEY,
  }
};
