from .metadata import Base, metadata
from .rewards import Reward, DistributionRound
from sqlalchemy.orm import sessionmaker

from ..__main__ import config
from sqlalchemy import create_engine

__all__ = [
    'Base',
    'metadata',
    'Reward',
    'DistributionRound',
]
"""Initialize database tables."""
db_connection_string = config['database']['sqlalchemy.url']

engine = create_engine(db_connection_string)  # Use connection string from config
Session = sessionmaker(bind=engine)
db_session = Session()
