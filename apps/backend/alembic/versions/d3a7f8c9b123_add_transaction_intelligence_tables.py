"""Add transaction intelligence tables

Revision ID: d3a7f8c9b123
Revises: 82e1b0bc46b2
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3a7f8c9b123'
down_revision: Union[str, None] = '82e1b0bc46b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # transaction_sessions — one per visitor visit
    op.create_table(
        'transaction_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('visitor_uuid', sa.String(36), nullable=False, index=True),
        sa.Column('track_id', sa.Integer, nullable=False, index=True),
        sa.Column('camera_id', sa.String(36), nullable=False, index=True),
        sa.Column('store_id', sa.String(36), nullable=True),
        sa.Column('state', sa.String(64), nullable=False, server_default='ENTERED_STORE'),
        sa.Column('confidence_score', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('transaction_probability', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('confidence_level', sa.String(32), nullable=False, server_default='UNLIKELY'),
        sa.Column('detected_signals', sa.Text, nullable=True),
        sa.Column('entered_at', sa.DateTime, nullable=False),
        sa.Column('exited_at', sa.DateTime, nullable=True),
        sa.Column('last_updated', sa.DateTime, nullable=False),
        sa.Column('is_complete', sa.Boolean, nullable=False, server_default='0'),
        sa.Column('synced', sa.Boolean, nullable=False, server_default='0', index=True),
    )
    op.create_index('ix_txn_session_camera_date', 'transaction_sessions', ['camera_id', 'entered_at'])

    # transaction_signals — individual detected signals within a session
    op.create_table(
        'transaction_signals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), nullable=False, index=True),
        sa.Column('signal_type', sa.String(64), nullable=False, index=True),
        sa.Column('score', sa.Integer, nullable=False),
        sa.Column('zone_name', sa.String(128), nullable=True),
        sa.Column('detected_at', sa.DateTime, nullable=False, index=True),
        sa.Column('x', sa.Float, nullable=True),
        sa.Column('y', sa.Float, nullable=True),
        sa.Column('metadata_json', sa.Text, nullable=True),
        sa.Column('synced', sa.Boolean, nullable=False, server_default='0', index=True),
    )

    # transaction_predictions — confidence snapshots at each level-up
    op.create_table(
        'transaction_predictions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), nullable=False, index=True),
        sa.Column('visitor_uuid', sa.String(36), nullable=False),
        sa.Column('camera_id', sa.String(36), nullable=False),
        sa.Column('store_id', sa.String(36), nullable=True),
        sa.Column('transaction_probability', sa.Float, nullable=False),
        sa.Column('confidence_level', sa.String(32), nullable=False),
        sa.Column('detected_signals', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('synced', sa.Boolean, nullable=False, server_default='0', index=True),
    )

    # transaction_statistics — pre-aggregated daily/hourly rollups
    op.create_table(
        'transaction_statistics',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('camera_id', sa.String(36), nullable=True, index=True),
        sa.Column('date', sa.Date, nullable=False, index=True),
        sa.Column('hour', sa.Integer, nullable=True),
        sa.Column('total_sessions', sa.Integer, nullable=False, server_default='0'),
        sa.Column('likely_purchases', sa.Integer, nullable=False, server_default='0'),
        sa.Column('checkout_visitors', sa.Integer, nullable=False, server_default='0'),
        sa.Column('checkout_abandonment', sa.Integer, nullable=False, server_default='0'),
        sa.Column('avg_confidence', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('queue_success_rate', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('payment_type_distribution', sa.Text, nullable=True),
        sa.Column('computed_at', sa.DateTime, nullable=False),
        sa.Column('synced', sa.Boolean, nullable=False, server_default='0', index=True),
    )
    op.create_index('ix_txn_stat_camera_date_hour', 'transaction_statistics', ['camera_id', 'date', 'hour'])


def downgrade() -> None:
    op.drop_index('ix_txn_stat_camera_date_hour', table_name='transaction_statistics')
    op.drop_table('transaction_statistics')
    op.drop_table('transaction_predictions')
    op.drop_table('transaction_signals')
    op.drop_index('ix_txn_session_camera_date', table_name='transaction_sessions')
    op.drop_table('transaction_sessions')
