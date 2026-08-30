"""Fix dealer profile postal code schema.

Makes dealer_profiles.postal_code NOT NULL and adds the
postal_code index to match the SQLAlchemy model.
"""

from alembic import op
import sqlalchemy as sa


revision = "be021d6cc562"
down_revision = "20260801_0011"
branch_labels = None
depends_on = None


def _cleanup_sqlite_batch_table(table_name: str) -> None:
    if op.get_bind().dialect.name != "sqlite":
        return

    op.execute(sa.text(f'DROP TABLE IF EXISTS "_alembic_tmp_{table_name}"'))


def upgrade() -> None:
    _cleanup_sqlite_batch_table("dealer_profiles")

    with op.batch_alter_table("dealer_profiles") as batch_op:
        batch_op.alter_column(
            "postal_code",
            existing_type=sa.String(length=12),
            nullable=False,
        )

    op.create_index(
        "ix_dealer_profiles_postal_code",
        "dealer_profiles",
        ["postal_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dealer_profiles_postal_code",
        table_name="dealer_profiles",
    )

    _cleanup_sqlite_batch_table("dealer_profiles")

    with op.batch_alter_table("dealer_profiles") as batch_op:
        batch_op.alter_column(
            "postal_code",
            existing_type=sa.String(length=12),
            nullable=True,
        )
