"""add bot_comments and feedback tables

Revision ID: 1234abcd5678
Revises: 
Create Date: 2026-04-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1234abcd5678'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('bot_comments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('github_comment_id', sa.BigInteger(), nullable=True),
    sa.Column('repo_full_name', sa.String(), nullable=True),
    sa.Column('pr_number', sa.Integer(), nullable=True),
    sa.Column('file_path', sa.String(), nullable=True),
    sa.Column('line', sa.Integer(), nullable=True),
    sa.Column('severity', sa.String(), nullable=True),
    sa.Column('comment_text', sa.Text(), nullable=True),
    sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bot_comments_github_comment_id'), 'bot_comments', ['github_comment_id'], unique=True)
    op.create_index(op.f('ix_bot_comments_pr_number'), 'bot_comments', ['pr_number'], unique=False)
    op.create_index(op.f('ix_bot_comments_repo_full_name'), 'bot_comments', ['repo_full_name'], unique=False)

    op.create_table('feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bot_comment_id', sa.Integer(), nullable=True),
    sa.Column('reaction_type', sa.String(), nullable=True),
    sa.Column('user_login', sa.String(), nullable=True),
    sa.Column('reacted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['bot_comment_id'], ['bot_comments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_feedback_bot_comment_id'), 'feedback', ['bot_comment_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_feedback_bot_comment_id'), table_name='feedback')
    op.drop_table('feedback')
    op.drop_index(op.f('ix_bot_comments_repo_full_name'), table_name='bot_comments')
    op.drop_index(op.f('ix_bot_comments_pr_number'), table_name='bot_comments')
    op.drop_index(op.f('ix_bot_comments_github_comment_id'), table_name='bot_comments')
    op.drop_table('bot_comments')
