import {HardhatRuntimeEnvironment} from 'hardhat/types';
import {DeployFunction} from 'hardhat-deploy/types';

const func: DeployFunction = async function (hre: HardhatRuntimeEnvironment) {
    let mercTokenAddress: string;
    if (hre.network.name == 'hardhat') {
        console.warn('WARNING: Using zero address for MERC');
        mercTokenAddress = '0x0000000000000000000000000000000000000000';
    } else if (hre.network.name == 'mainnet') {
        mercTokenAddress = '0xa203eB78Fee91c8459C6d4eF3a899d8724Ee5B35';
    } else {
        throw new Error("Mercury Staking can only be deployed to Ethereum mainnet");
    }
    const {deploy} = hre.deployments;
    const {deployer} = await hre.getNamedAccounts();
    await deploy('MercuryStaking', {
        from: deployer,
        args: [
            mercTokenAddress,
            mercTokenAddress,
            1,
            10
        ],
        log: true,
    });
};
export default func;