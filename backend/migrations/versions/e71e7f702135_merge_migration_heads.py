"""merge migration heads

Revision ID: e71e7f702135
Revises: d0c26a9b4f10, d903_dataset_review
Create Date: 2026-09-23 09:57:10.229167
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e71e7f702135'
down_revision: Union[str, None] = ('d0c26a9b4f10', 'd903_dataset_review')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
