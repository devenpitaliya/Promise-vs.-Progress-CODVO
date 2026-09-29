"""initial schema: users, meetings, tasks, integrations, scheduled audits and email logs

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.Column('gemini_api_key_encrypted', sa.Text(), nullable=True),
    sa.Column('openai_api_key_encrypted', sa.Text(), nullable=True),
    sa.Column('preferred_llm_provider', sa.String(length=20), nullable=True),
    sa.Column('default_tracker', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table('integrations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('secrets_encrypted', sa.Text(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('last_tested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_test_ok', sa.Boolean(), nullable=True),
    sa.Column('last_test_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('owner_id', 'kind', name='uq_integrations_owner_kind')
    )
    with op.batch_alter_table('integrations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_integrations_owner_id'), ['owner_id'], unique=False)

    op.create_table('meetings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('meeting_type', sa.String(length=50), nullable=True),
    sa.Column('meeting_date', sa.Date(), nullable=False),
    sa.Column('meeting_time', sa.String(length=5), nullable=True),
    sa.Column('participants', sa.JSON(), nullable=False),
    sa.Column('transcript', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('extraction_source', sa.String(length=20), nullable=False),
    sa.Column('langfuse_trace_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_meetings_owner_id'), ['owner_id'], unique=False)

    op.create_table('scheduled_audits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('meeting_id', sa.Integer(), nullable=True),
    sa.Column('recipient_email', sa.String(length=255), nullable=True),
    sa.Column('post_to_slack', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('schedule_type', sa.String(length=20), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('daily_time', sa.String(length=5), nullable=True),
    sa.Column('custom_instructions', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('runs_count', sa.Integer(), nullable=False),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('scheduled_audits', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_scheduled_audits_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_scheduled_audits_status'), ['status'], unique=False)

    op.create_table('tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('meeting_id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('assignee', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('source_quote', sa.Text(), nullable=True),
    sa.Column('target_date', sa.Date(), nullable=True),
    sa.Column('speech_status', sa.String(length=30), nullable=False),
    sa.Column('priority', sa.Integer(), server_default='2', nullable=False),
    sa.Column('target_system', sa.String(length=20), nullable=False),
    sa.Column('repository', sa.String(length=200), nullable=True),
    sa.Column('external_ref', sa.String(length=100), nullable=True),
    sa.Column('approval_status', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('sync_status', sa.String(length=20), nullable=False),
    sa.Column('sync_error', sa.Text(), nullable=True),
    sa.Column('is_simulated', sa.Boolean(), nullable=False),
    sa.Column('github_url', sa.String(length=500), nullable=True),
    sa.Column('github_issue_number', sa.Integer(), nullable=True),
    sa.Column('github_pr_number', sa.Integer(), nullable=True),
    sa.Column('external_key', sa.String(length=50), nullable=True),
    sa.Column('app_closed_marker', sa.String(length=64), nullable=True),
    sa.Column('verification_status', sa.String(length=30), nullable=False),
    sa.Column('github_state', sa.String(length=30), nullable=True),
    sa.Column('verification_note', sa.Text(), nullable=True),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tasks_approval_status'), ['approval_status'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_meeting_id'), ['meeting_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_priority'), ['priority'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_verification_status'), ['verification_status'], unique=False)

    op.create_table('email_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('audit_id', sa.Integer(), nullable=True),
    sa.Column('meeting_id', sa.Integer(), nullable=True),
    sa.Column('recipient_email', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('html_body', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['audit_id'], ['scheduled_audits.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('email_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_logs_owner_id'), ['owner_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('email_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_logs_owner_id'))

    op.drop_table('email_logs')
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tasks_verification_status'))
        batch_op.drop_index(batch_op.f('ix_tasks_status'))
        batch_op.drop_index(batch_op.f('ix_tasks_priority'))
        batch_op.drop_index(batch_op.f('ix_tasks_owner_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_meeting_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_approval_status'))

    op.drop_table('tasks')
    with op.batch_alter_table('scheduled_audits', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_scheduled_audits_status'))
        batch_op.drop_index(batch_op.f('ix_scheduled_audits_owner_id'))

    op.drop_table('scheduled_audits')
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_meetings_owner_id'))

    op.drop_table('meetings')
    with op.batch_alter_table('integrations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_integrations_owner_id'))

    op.drop_table('integrations')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
