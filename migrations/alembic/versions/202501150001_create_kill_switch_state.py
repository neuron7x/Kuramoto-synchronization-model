"""Create kill_switch_state table"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "202501150001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kill_switch_state",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("engaged", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("id = 1", name="ck_kill_switch_state_singleton"),
        sa.PrimaryKeyConstraint("id", name="pk_kill_switch_state"),
    )
    op.create_index(
        "idx_kill_switch_state_updated_at",
        "kill_switch_state",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_kill_switch_state_updated_at", table_name="kill_switch_state")
    op.drop_table("kill_switch_state")
