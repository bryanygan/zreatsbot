import sqlite3
import os
from pathlib import Path

# Database path - supports both local development and Railway/production
DB_PATH = Path(os.getenv('DB_PATH', str(Path(__file__).parent / 'data' / 'pool.db')))

def add_cards(cards):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executemany(
        'INSERT INTO cards (number, cvv) VALUES (?, ?)',
        cards
    )
    conn.commit()
    conn.close()

def add_emails(emails):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executemany(
        'INSERT INTO emails (email) VALUES (?)',
        [(e,) for e in emails]
    )
    conn.commit()
    conn.close()

if __name__ == '__main__':
    # Example data—replace these lists with your real values.
    cards_to_add = [
    ]

    emails_to_add = [
    'JillSouthern90@hotmail.com',
    'KeiranSzewc96@hotmail.com',
    'JacklynKrivanek7735@hotmail.com',
    'JanitaDonerson567@hotmail.com',
    'JanettaJohn0030@hotmail.com',
    'JosetteTwiner64@hotmail.com',
    'JaylaLevron1969@hotmail.com',
    'JosephineMeyerhoff671@hotmail.com',
    'KathryneLuckett06@hotmail.com',
    'JuanLeskovac465@hotmail.com',
    'JoyaSemonick6069@hotmail.com',
    'JasminDobiesz31@hotmail.com',
    'KeniaSessums2516@hotmail.com',
    'KatherinArqueta8469@hotmail.com',
    ]


    add_cards(cards_to_add)
    add_emails(emails_to_add)
    print("Done inserting cards and emails!")
