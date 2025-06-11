import sqlite3
from pathlib import Path
from queue import SimpleQueue, Empty

# Path to the SQLite database file
DB_PATH = Path(__file__).parent / 'data' / 'pool.db'

# Module-level database connection
DB_CONN = None
_POOL_SIZE = 3
_POOL: SimpleQueue[sqlite3.Connection] = SimpleQueue()


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

    # Table for storing cards: card number and CVV
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL,
            cvv    TEXT NOT NULL
        )
    ''')

    # Table for storing emails
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT    NOT NULL
        )
    ''')

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


def get_and_remove_email():
    """
    Fetch the oldest email from the pool and remove it from the database.
    Returns:
        str: email address if available, or None if no emails left.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id, email FROM emails ORDER BY id LIMIT 1')
    row = cursor.fetchone()
    if not row:
        return None

    email_id, email = row
    cursor.execute('DELETE FROM emails WHERE id = ?', (email_id,))
    conn.commit()
    return email


def get_pool_counts() -> tuple:
    """Return the current counts of cards and emails."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM cards')
    card_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM emails')
    email_count = cursor.fetchone()[0]
    return card_count, email_count


# Initialize DB on import and create the shared connection
init_db()
DB_CONN = sqlite3.connect(DB_PATH, check_same_thread=False)
_init_pool()
