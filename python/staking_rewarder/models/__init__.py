from .metadata import Base, metadata
from .rewards import RewardDistribution, DistributionRound, RewardState, KeyValuePair
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import create_engine

__all__ = [
    "Base",
    "metadata",
    "RewardDistribution",
    "DistributionRound",
    "RewardState",
    "KeyValuePair",
    "db_session",
    "autocommit_engine",
    "Session",
]

from .. import config

"""Initialize database tables."""
db_connection_string = config["database"]["sqlalchemy.url"]

engine = create_engine(db_connection_string)  # Use connection string from config
Session = sessionmaker(bind=engine)
db_session = Session()

autocommit_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
