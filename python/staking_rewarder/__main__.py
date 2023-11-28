import configparser
import os
import pathlib
from .service import main

root_dir = pathlib.Path(__file__).parent.parent.absolute()
config_file = os.path.join(root_dir, 'staking_rewarder/config.ini')
config = configparser.ConfigParser()
config.read(config_file)

if __name__ == '__main__':
    main()
