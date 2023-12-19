"""change amount wei type

Revision ID: e484dbddeea2
Revises: 91442a6d6cb2
Create Date: 2023-11-30 14:44:14.309217

"""
from alembic import op
import sqlalchemy as sa
from staking_rewarder.models.types import Uint256

# revision identifiers, used by Alembic.
revision = "e484dbddeea2"
down_revision = "5697db236c94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "reward_distribution",
        "amount_wei",
        existing_type=sa.BIGINT(),
        type_=Uint256(),
        nullable=False,
    )


def downgrade() -> None:
    pass
