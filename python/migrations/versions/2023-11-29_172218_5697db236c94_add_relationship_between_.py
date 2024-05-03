"""add relationship between rewarddistribution and distribution round

Revision ID: 5697db236c94
Revises: 7c469e47fa18
Create Date: 2023-11-29 15:21:26.923543

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '5697db236c94'
down_revision = '7c469e47fa18'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reward_distribution', sa.Column('distribution_round_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_reward_distribution_distribution_round_id_distribution_round'),
                          'reward_distribution', 'distribution_round', ['distribution_round_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(op.f('fk_reward_distribution_distribution_round_id_distribution_round'), 'reward_distribution',
                       type_='foreignkey')
    op.drop_column('reward_distribution', 'distribution_round_id')

