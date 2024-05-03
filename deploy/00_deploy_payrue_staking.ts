import {HardhatRuntimeEnvironment} from 'hardhat/types';
import {DeployFunction} from 'hardhat-deploy/types';

const func: DeployFunction = async function (hre: HardhatRuntimeEnvironment) {
    let propelTokenAddress: string;
    const {deploy} = hre.deployments;
    const {deployer} = await hre.getNamedAccounts();
    if (hre.network.name == 'hardhat') {
        const result = await deploy('TestToken', {
            from: deployer,
            args: [
                'TestToken',
                'PROPEL',
            ],
            log: true,
        });
        propelTokenAddress = result.address;
        console.log('propelTokenAddress', propelTokenAddress)
    } else if (hre.network.name == 'bsc') {
        propelTokenAddress = '0x9b44df3318972be845d83f961735609137c4c23c';
    } else if (hre.network.name == 'matic') {
        propelTokenAddress = '0xe0ce60af0850bf54072635e66e79df17082a1109';
    } else if (hre.network.name == 'bsc-testnet') {
        // TODO: what's the right testnet propel address?
        console.warn('WARNING: Using zero address for PROPEL');
        propelTokenAddress = '0x0000000000000000000000000000000000000000';
    } else {
        throw new Error("Invalid network");
    }
    console.log('deployer', deployer, typeof deployer);

    await deploy('PayRueStaking', {
        from: deployer,
        args: [
            propelTokenAddress,
            propelTokenAddress,
            1,
            1
        ],
        log: true,
    });
};
export default func;
