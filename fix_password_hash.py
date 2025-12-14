"""
Script to fix password_hash column to be nullable in SQLite database
"""
import sqlite3
import os

db_path = os.path.join('instance', 'site.db')

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

print(f"Connecting to database: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check current structure
    cursor.execute("PRAGMA table_info(user)")
    columns = cursor.fetchall()
    print("\nCurrent user table structure:")
    for col in columns:
        # In SQLite: col[3] == 0 means NOT NULL, col[3] == 1 means nullable
        nullable_status = "nullable" if col[3] == 1 else "NOT NULL"
        print(f"  {col[1]}: {nullable_status} (col[3]={col[3]})")

    # Check if password_hash is NOT NULL
    # In SQLite: col[3] == 0 means NOT NULL, col[3] == 1 means nullable
    password_hash_not_null = False
    for col in columns:
        if col[1] == 'password_hash' and col[3] == 0:  # 0 means NOT NULL
            password_hash_not_null = True
            break

    # Force recreation anyway to ensure proper structure
    print("\nRecreating user table with proper nullable constraints...")

    # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
    # Step 1: Create new table with nullable password_hash
    # In SQLite, we need to explicitly set DEFAULT NULL to make it nullable
    cursor.execute("""
        CREATE TABLE user_new (
            id INTEGER NOT NULL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT DEFAULT NULL,
            google_id TEXT DEFAULT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            date_created TEXT NOT NULL,
            profile_image TEXT DEFAULT NULL
        )
    """)
    
    # Verify the new table structure before copying data
    cursor.execute("PRAGMA table_info(user_new)")
    new_cols = cursor.fetchall()
    print("\nNew table structure (before copy):")
    for col in new_cols:
        nullable = "nullable" if col[3] == 1 else "NOT NULL"
        print(f"  {col[1]}: {nullable} (col[3]={col[3]})")

    # Step 2: Copy data from old table (if any exists)
    try:
        cursor.execute("SELECT COUNT(*) FROM user")
        count = cursor.fetchone()[0]
        if count > 0:
            cursor.execute("""
                INSERT INTO user_new (id, username, email, password_hash, google_id, is_admin, date_created, profile_image)
                SELECT id, username, email, password_hash, google_id, is_admin, date_created, profile_image
                FROM user
            """)
            print(f"Copied {count} rows from old table")
        else:
            print("No data to copy")
    except Exception as e:
        print(f"Warning: Could not copy data: {e}")

    # Step 3: Drop old table
    cursor.execute("DROP TABLE user")

    # Step 4: Rename new table
    cursor.execute("ALTER TABLE user_new RENAME TO user")

    # Commit changes
    conn.commit()
    print("[OK] password_hash is now nullable!")

    # Verify
    cursor.execute("PRAGMA table_info(user)")
    columns = cursor.fetchall()
    print("\nNew user table structure:")
    for col in columns:
        # In SQLite: col[3] == 0 means NOT NULL, col[3] == 1 means nullable
        nullable = "nullable" if col[3] == 1 else "NOT NULL"
        print(f"  {col[1]}: {nullable} (col[3]={col[3]})")

    print("\n[OK] Database fixed successfully!")

except Exception as e:
    conn.rollback()
    print(f"\n[ERROR] Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
finally:
    conn.close()

