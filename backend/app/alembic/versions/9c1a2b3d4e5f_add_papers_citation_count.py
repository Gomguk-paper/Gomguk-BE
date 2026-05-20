"""add papers citation_count

Revision ID: 9c1a2b3d4e5f
Revises: 5eb755506b34
Create Date: 2026-05-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9c1a2b3d4e5f"
down_revision = "5eb755506b34"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            "ALTER TABLE papers "
            "ADD COLUMN IF NOT EXISTS citation_count INTEGER NOT NULL DEFAULT 0"
        )
    )


def downgrade():
    op.execute(sa.text("ALTER TABLE papers DROP COLUMN IF EXISTS citation_count"))
