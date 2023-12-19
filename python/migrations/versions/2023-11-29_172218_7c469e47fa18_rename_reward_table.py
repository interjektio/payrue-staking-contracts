"""rename_reward_table

Revision ID: 7c469e47fa18
Revises: 6db13531250e
Create Date: 2023-11-29 14:37:04.022484

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '7c469e47fa18'
down_revision = '6db13531250e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table('reward', 'reward_distribution')


def downgrade() -> None:
    op.rename_table('reward_distribution', 'reward')
