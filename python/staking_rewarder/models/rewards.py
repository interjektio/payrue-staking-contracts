import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DOUBLE_PRECISION,
    Enum,
    ForeignKey,
    BigInteger,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .metadata import Base
from .types import Uint256


class RewardState(enum.Enum):
    sent = "sent"
    sending = "sending"
    unsent = "unsent"


class RewardDistribution(Base):
    __tablename__ = "reward_distribution"
    id = Column(Integer, primary_key=True)
    user_address = Column(String)
    percentage = Column(DOUBLE_PRECISION)
    amount_wei = Column(Uint256, nullable=False)
    state = Column(
        Enum(RewardState),
        nullable=False,
        default=RewardState.unsent,
        server_default="unsent",
    )
    distribution_round_id = Column(Integer, ForeignKey("distribution_round.id"))
    distribution_round = relationship(
        "DistributionRound", back_populates="reward_distributions"
    )


class DistributionRound(Base):
    __tablename__ = "distribution_round"
    id = Column(Integer, primary_key=True)
    year = Column(Integer)
    month = Column(Integer)
    reward_distributions = relationship(
        "RewardDistribution", back_populates="distribution_round"
    )


class KeyValuePair(Base):
    __tablename__ = "key_value_pair"
    key = Column(String, primary_key=True)
    value = Column(JSONB)
