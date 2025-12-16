"""Make password_hash nullable for OAuth users

Revision ID: abc123456789
Revises: e782c5cdf1f1
Create Date: 2025-12-14 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'abc123456789'
down_revision = 'e782c5cdf1f1'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
    # Step 1: Create new table with nullable password_hash
    op.execute("""
        CREATE TABLE user_new (
            id INTEGER NOT NULL PRIMARY KEY,
            username VARCHAR(80) NOT NULL UNIQUE,
            email VARCHAR(120) NOT NULL UNIQUE,
            password_hash VARCHAR(128),
            google_id VARCHAR(255),
            is_admin BOOLEAN NOT NULL,
            date_created DATETIME NOT NULL,
            profile_image VARCHAR(500)
        )
    """)
    
    # Step 2: Copy data from old table
    op.execute("""
        INSERT INTO user_new (id, username, email, password_hash, google_id, is_admin, date_created, profile_image)
        SELECT id, username, email, password_hash, google_id, is_admin, date_created, profile_image
        FROM user
    """)
    
    # Step 3: Drop old table
    op.execute("DROP TABLE user")
    
    # Step 4: Rename new table
    op.execute("ALTER TABLE user_new RENAME TO user")


def downgrade():
    # Revert to NOT NULL password_hash
    op.execute("""
        CREATE TABLE user_new (
            id INTEGER NOT NULL PRIMARY KEY,
            username VARCHAR(80) NOT NULL UNIQUE,
            email VARCHAR(120) NOT NULL UNIQUE,
            password_hash VARCHAR(128) NOT NULL,
            google_id VARCHAR(255),
            is_admin BOOLEAN NOT NULL,
            date_created DATETIME NOT NULL,
            profile_image VARCHAR(500)
        )
    """)
    
    op.execute("""
        INSERT INTO user_new (id, username, email, password_hash, google_id, is_admin, date_created, profile_image)
        SELECT id, username, email, COALESCE(password_hash, '') as password_hash, google_id, is_admin, date_created, profile_image
        FROM user
    """)
    
    op.execute("DROP TABLE user")
    op.execute("ALTER TABLE user_new RENAME TO user")


