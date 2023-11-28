import enum

from sqlalchemy import Column, Integer, String, Float, DOUBLE_PRECISION, Enum

from .metadata import Base


class RewardState(enum.Enum):
    sent = "sent"
    pending = "pending"
    unsent = "unsent"


class Reward(Base):
    __tablename__ = 'reward'
    id = Column(Integer, primary_key=True)
    user_address = Column(String)
    percentage = Column(DOUBLE_PRECISION)
    amount = Column(Float)
    state = Column(Enum(RewardState), nullable=False, default=RewardState.unsent, server_default="unsent")


class DistributionRound(Base):
    __tablename__ = 'distribution_round'
    id = Column(Integer, primary_key=True)
    year = Column(Integer)
    month = Column(Integer)
