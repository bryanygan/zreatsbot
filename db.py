import sqlite3
import os
from pathlib import Path
from queue import SimpleQueue, Empty
from typing import Optional, Tuple

# Path to the SQLite database file
# Support both local development and Railway/production environments
# Railway will use: /app/data/pool.db via environment variable
DB_PATH = Path(os.getenv('DB_PATH', str(Path(__file__).parent / 'data' / 'pool.db')))

# Module-level database connection
DB_CONN = None
_POOL_SIZE = 3
_POOL: SimpleQueue[sqlite3.Connection] = SimpleQueue()

# Email pool types
VALID_EMAIL_POOLS = ['main', 'fusion', 'wool']
DEFAULT_EMAIL_POOL = 'main'

def init_db():
    """
    Initialize the SQLite database and ensure the tables exist.
    If an existing pool.db file is corrupted or not a valid SQLite database, it will be removed and recreated.
    """
    # Create data directory if it doesn't exist
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # If the database file exists but isn't a valid SQLite DB, delete it
    if DB_PATH.exists():
        try:
            with DB_PATH.open('rb') as f:
                header = f.read(16)
            # SQLite files start with "SQLite format 3\0"
            if not header.startswith(b"SQLite format 3\x00"):
                DB_PATH.unlink()
        except Exception:
            # On any error, remove the file so it can be recreated
            try:
                DB_PATH.unlink()
            except Exception:
                pass

    # Connect and create tables
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table for storing cards: card number and CVV (unchanged)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL,
            cvv    TEXT NOT NULL
        )
    ''')

    # Updated table for storing emails with pool support
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            email     TEXT    NOT NULL,
            pool_type TEXT    NOT NULL DEFAULT 'main'
        )
    ''')

    # Migrate existing emails to main pool if no pool_type column exists
    try:
        cursor.execute("SELECT pool_type FROM emails LIMIT 1")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it and set existing emails to 'main'
        cursor.execute("ALTER TABLE emails ADD COLUMN pool_type TEXT NOT NULL DEFAULT 'main'")
        cursor.execute("UPDATE emails SET pool_type = 'main' WHERE pool_type IS NULL OR pool_type = ''")

    conn.commit()
    conn.close()


def _init_pool(size: int = _POOL_SIZE):
    """Pre-open a small pool of SQLite connections."""
    for _ in range(size):
        _POOL.put(sqlite3.connect(DB_PATH, check_same_thread=False))


def get_connection():
    """Return the module-level SQLite connection."""
    return DB_CONN


def acquire_connection() -> sqlite3.Connection:
    """Get a connection from the pool or fall back to the shared connection."""
    try:
        return _POOL.get_nowait()
    except Empty:
        return DB_CONN


def release_connection(conn: sqlite3.Connection) -> None:
    """Return a connection to the pool if it's not the shared singleton."""
    if conn is DB_CONN:
        return
    _POOL.put(conn)


def close_connection():
    """Close the module-level SQLite connection."""
    global DB_CONN
    if DB_CONN is not None:
        DB_CONN.close()
        DB_CONN = None
    while True:
        try:
            conn = _POOL.get_nowait()
        except Empty:
            break
        else:
            conn.close()


def get_and_remove_email(pool_type: str = DEFAULT_EMAIL_POOL, fallback_to_main: bool = False):
    """
    Fetch the oldest email from the specified pool and remove it from the database.
    If the pool is empty and fallback_to_main is True, will try the main pool.

    Args:
        pool_type: The email pool to use ('main', 'fusion', 'wool')
        fallback_to_main: If True and pool is empty, try main pool (default: False)

    Returns:
        str: email address if available, or None if no emails left in the specified pool.
    """
    if pool_type not in VALID_EMAIL_POOLS:
        raise ValueError(f"Invalid pool type: {pool_type}. Valid pools: {VALID_EMAIL_POOLS}")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id, email FROM emails WHERE pool_type = ? ORDER BY id LIMIT 1', (pool_type,))
    row = cursor.fetchone()

    # If no email found and fallback is enabled, try main pool
    if not row and fallback_to_main and pool_type != 'main':
        cursor.execute('SELECT id, email FROM emails WHERE pool_type = ? ORDER BY id LIMIT 1', ('main',))
        row = cursor.fetchone()

    if not row:
        return None

    email_id, email = row
    cursor.execute('DELETE FROM emails WHERE id = ?', (email_id,))
    conn.commit()
    return email


def add_email_to_pool(email: str, pool_type: str = DEFAULT_EMAIL_POOL, top: bool = False):
    """
    Add an email to the specified pool.

    Args:
        email: Email address to add
        pool_type: Pool to add email to ('main', 'fusion', 'wool')
        top: If True, add to the top of the pool (lower ID)

    Returns:
        bool: True if successful, False if email already exists in pool
    """
    if pool_type not in VALID_EMAIL_POOLS:
        raise ValueError(f"Invalid pool type: {pool_type}. Valid pools: {VALID_EMAIL_POOLS}")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if email already exists in this pool
    cursor.execute("SELECT COUNT(*) FROM emails WHERE email = ? AND pool_type = ?", (email, pool_type))
    exists = cursor.fetchone()[0] > 0
    
    if exists:
        return False
    
    if top:
        cursor.execute("SELECT MIN(id) FROM emails WHERE pool_type = ?", (pool_type,))
        row = cursor.fetchone()
        min_id = row[0] if row and row[0] is not None else None
        if min_id is None:
            cursor.execute("INSERT INTO emails (email, pool_type) VALUES (?, ?)", (email, pool_type))
        else:
            new_id = min_id - 1
            cursor.execute("INSERT INTO emails (id, email, pool_type) VALUES (?, ?, ?)", (new_id, email, pool_type))
    else:
        cursor.execute("INSERT INTO emails (email, pool_type) VALUES (?, ?)", (email, pool_type))
    
    conn.commit()
    return True


def remove_email_from_pool(email: str, pool_type: str = DEFAULT_EMAIL_POOL):
    """
    Remove an email from the specified pool.
    
    Args:
        email: Email address to remove
        pool_type: Pool to remove email from
    
    Returns:
        bool: True if email was removed, False if not found
    """
    if pool_type not in VALID_EMAIL_POOLS:
        raise ValueError(f"Invalid pool type: {pool_type}. Valid pools: {VALID_EMAIL_POOLS}")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM emails WHERE email = ? AND pool_type = ?", (email, pool_type))
    deleted = cursor.rowcount
    conn.commit()
    return deleted > 0


def get_emails_in_pool(pool_type: str = DEFAULT_EMAIL_POOL):
    """
    Get all emails in the specified pool.
    
    Args:
        pool_type: Pool to get emails from
    
    Returns:
        list: List of email addresses in the pool
    """
    if pool_type not in VALID_EMAIL_POOLS:
        raise ValueError(f"Invalid pool type: {pool_type}. Valid pools: {VALID_EMAIL_POOLS}")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM emails WHERE pool_type = ? ORDER BY id", (pool_type,))
    rows = cursor.fetchall()
    return [email for (email,) in rows]


def get_pool_counts() -> dict:
    """
    Return the current counts of cards and emails by pool.

    Returns:
        dict: {'cards': int, 'emails': {'main': int, 'fusion': int, 'wool': int}}
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get card count
    cursor.execute('SELECT COUNT(*) FROM cards')
    card_count = cursor.fetchone()[0]
    
    # Get email counts by pool
    email_counts = {}
    for pool_type in VALID_EMAIL_POOLS:
        cursor.execute('SELECT COUNT(*) FROM emails WHERE pool_type = ?', (pool_type,))
        email_counts[pool_type] = cursor.fetchone()[0]
    
    return {
        'cards': card_count,
        'emails': email_counts
    }


def get_all_emails_with_pools():
    """
    Get all emails with their pool information.
    
    Returns:
        list: List of tuples (email, pool_type)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email, pool_type FROM emails ORDER BY pool_type, id")
    return cursor.fetchall()

def get_and_remove_card():
    """
    Fetch the oldest card (by id) from the pool and remove it from the database.
    Returns:
        tuple: (card_number, cvv) if available, or None if no cards left.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id, number, cvv FROM cards ORDER BY id LIMIT 1')
    row = cursor.fetchone()
    if not row:
        return None

    card_id, number, cvv = row
    cursor.execute('DELETE FROM cards WHERE id = ?', (card_id,))
    conn.commit()
    return number, cvv

# Legacy function for backward compatibility
def get_and_remove_email_legacy():
    """Legacy function that uses the main pool - for backward compatibility"""
    return get_and_remove_email('main')


# Initialize DB on import and create the shared connection
init_db()
DB_CONN = sqlite3.connect(DB_PATH, check_same_thread=False)
_init_pool()
