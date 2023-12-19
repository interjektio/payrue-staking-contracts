"""initialize_database

Revision ID: 6db13531250e
Revises: 
Create Date: 2023-11-28 15:35:50.392973

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '6db13531250e'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    reward_state_type = postgresql.ENUM(
        'sent', 'sending', 'unsent', name="rewardstate", create_type=False
    )
    reward_state_type.create(op.get_bind(), checkfirst=True)
    op.create_table('distribution_round',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('year', sa.Integer(), nullable=True),
                    sa.Column('month', sa.Integer(), nullable=True),
                    sa.PrimaryKeyConstraint('id', name=op.f('pk_distribution_round'))
                    )
    op.create_table('reward',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_address', sa.String(), nullable=True),
                    sa.Column('percentage', sa.DOUBLE_PRECISION(), nullable=True),
                    sa.Column('amount_wei', sa.BigInteger(), nullable=True),
                    sa.Column('state', reward_state_type,
                              server_default='unsent', nullable=False),
                    sa.PrimaryKeyConstraint('id', name=op.f('pk_reward'))
                    )


def downgrade() -> None:
    op.drop_table('reward')
    op.drop_table('distribution_round')
    reward_state_type = postgresql.ENUM(
        'sent', 'sending', 'unsent', name="rewardstate", create_type=False
    )
    reward_state_type.drop(op.get_bind(), checkfirst=True)
