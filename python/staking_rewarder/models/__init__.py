from .metadata import Base, metadata
from .rewards import RewardDistribution, DistributionRound, RewardState
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

__all__ = [
    'Base',
    'metadata',
    'RewardDistribution',
    'DistributionRound',
    'RewardState'
]

from .. import config

"""Initialize database tables."""
db_connection_string = config['database']['sqlalchemy.url']

engine = create_engine(db_connection_string)  # Use connection string from config
Session = sessionmaker(bind=engine)
db_session = Session()
