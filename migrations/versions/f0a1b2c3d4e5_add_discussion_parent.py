"""add parent_id to discussioncomment

Revision ID: f0a1b2c3d4e5
Revises: e782c5cdf1f1
Create Date: 2026-02-21 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'f0a1b2c3d4e5'
down_revision = 'e782c5cdf1f1'
branch_labels = None
depend_on = None


def upgrade():
    
    op.add_column('discussion_comment', sa.Column('parent_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_discussion_comment_parent',
        'discussion_comment',
        'discussion_comment',
        ['parent_id'],
        ['id'],
    )
    


def downgrade():
    
    op.drop_constraint('fk_discussion_comment_parent', 'discussion_comment', type_='foreignkey')
    op.drop_column('discussion_comment', 'parent_id')
    
