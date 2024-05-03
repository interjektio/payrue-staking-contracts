"""Add key pair value

Revision ID: 05baa54760ce
Revises: e484dbddeea2
Create Date: 2023-12-01 13:25:03.568088

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "05baa54760ce"
down_revision = "e484dbddeea2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "key_value_pair",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_key_value_pair")),
    )


def downgrade() -> None:
    op.drop_table("key_value_pair")
