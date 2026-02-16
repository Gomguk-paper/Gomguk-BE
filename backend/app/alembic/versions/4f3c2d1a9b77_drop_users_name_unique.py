"""drop users.name unique constraint

Revision ID: 4f3c2d1a9b77
Revises: 85505e1fedd6
Create Date: 2026-02-16 23:45:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "4f3c2d1a9b77"
down_revision = "85505e1fedd6"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(op.f("users_name_key"), "users", type_="unique")


def downgrade():
    op.create_unique_constraint(op.f("users_name_key"), "users", ["name"])
