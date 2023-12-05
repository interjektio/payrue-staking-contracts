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
    "session_factory",
]

from .. import config

"""Initialize database tables."""
db_connection_string = config["database"]["sqlalchemy.url"]

engine = create_engine(db_connection_string)  # Use connection string from config
session_factory = sessionmaker(bind=engine)
db_session = scoped_session(session_factory)

autocommit_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
