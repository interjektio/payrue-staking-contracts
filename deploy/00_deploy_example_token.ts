import {HardhatRuntimeEnvironment} from 'hardhat/types';
import {DeployFunction} from 'hardhat-deploy/types';

const func: DeployFunction = async function (hre: HardhatRuntimeEnvironment) {
  const {deploy} = hre.deployments;
  const {deployer} = await hre.getNamedAccounts();
  await deploy('TestToken', {
    from: deployer,
    args: ['TestToken','TTK'],
    log: true,
  });
};
export default func;