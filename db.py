import sqlite3
from pathlib import Path

# Path to the SQLite database file
DB_PATH = Path(__file__).parent / 'data' / 'pool.db'


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


def get_and_remove_card():
    """
    Fetch the oldest card (by id) from the pool and remove it from the database.
    Returns:
        tuple: (card_number, cvv) if available, or None if no cards left.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT id, number, cvv FROM cards ORDER BY id LIMIT 1')
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    card_id, number, cvv = row
    cursor.execute('DELETE FROM cards WHERE id = ?', (card_id,))
    conn.commit()
    conn.close()
    return number, cvv


def get_and_remove_email():
    """
    Fetch the oldest email from the pool and remove it from the database.
    Returns:
        str: email address if available, or None if no emails left.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT id, email FROM emails ORDER BY id LIMIT 1')
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    email_id, email = row
    cursor.execute('DELETE FROM emails WHERE id = ?', (email_id,))
    conn.commit()
    conn.close()
    return email


# Initialize DB on import
init_db()