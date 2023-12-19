"""add transaction hash

Revision ID: 6b396a3a6334
Revises: ce10bbdbbcee
Create Date: 2023-12-12 00:03:59.517908

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6b396a3a6334"
down_revision = "ce10bbdbbcee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reward_distribution", sa.Column("tx_hash", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("reward_distribution", "tx_hash")
