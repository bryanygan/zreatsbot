"""
Export database to CSV files for backup or migration to Railway.

This script exports your local database to CSV files that can be:
1. Used as a backup
2. Re-imported using Discord /bulk_add commands
3. Imported to Railway after deployment

Usage:
    python export_database.py
"""

import sqlite3
import csv
import os
from pathlib import Path
from datetime import datetime

# Get database path from environment or use default
DB_PATH = Path(os.getenv('DB_PATH', str(Path(__file__).parent / 'data' / 'pool.db')))

def export_database():
    """Export all cards and emails to CSV files."""

    if not DB_PATH.exists():
        print(f"❌ Database not found at: {DB_PATH}")
        print("   Make sure your database exists before exporting.")
        return False

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Create backups directory if it doesn't exist
        backup_dir = Path(__file__).parent / 'backups'
        backup_dir.mkdir(exist_ok=True)

        # Generate timestamp for backup files
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Export cards
        print("📤 Exporting cards...")
        cursor.execute('SELECT number, cvv FROM cards ORDER BY id')
        cards = cursor.fetchall()

        cards_file = backup_dir / f'cards_backup_{timestamp}.csv'
        with open(cards_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['number', 'cvv'])
            writer.writerows(cards)

        print(f"   ✅ Exported {len(cards)} cards to: {cards_file}")

        # Export emails with pools
        print("📤 Exporting emails...")
        cursor.execute('SELECT email, pool_type FROM emails ORDER BY pool_type, id')
        emails = cursor.fetchall()

        emails_file = backup_dir / f'emails_backup_{timestamp}.csv'
        with open(emails_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['email', 'pool_type'])
            writer.writerows(emails)

        # Count emails by pool
        email_counts = {}
        for email, pool_type in emails:
            email_counts[pool_type] = email_counts.get(pool_type, 0) + 1

        print(f"   ✅ Exported {len(emails)} emails to: {emails_file}")
        for pool_type, count in email_counts.items():
            print(f"      - {pool_type}: {count} emails")

        # Create a combined backup info file
        info_file = backup_dir / f'backup_info_{timestamp}.txt'
        with open(info_file, 'w') as f:
            f.write(f"Database Backup - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Source: {DB_PATH}\n\n")
            f.write(f"Cards exported: {len(cards)}\n")
            f.write(f"Emails exported: {len(emails)}\n\n")
            f.write("Email breakdown by pool:\n")
            for pool_type, count in email_counts.items():
                f.write(f"  {pool_type}: {count}\n")
            f.write("\n" + "=" * 60 + "\n")
            f.write("Files created:\n")
            f.write(f"  - {cards_file.name}\n")
            f.write(f"  - {emails_file.name}\n")
            f.write(f"  - {info_file.name}\n")

        conn.close()

        print(f"\n✅ Backup complete!")
        print(f"📁 Files saved in: {backup_dir}")
        print(f"\n💡 To restore this data on Railway:")
        print(f"   1. Deploy your bot to Railway")
        print(f"   2. Use Discord commands:")
        print(f"      /bulk_add_cards - Upload {cards_file.name}")
        print(f"      /bulk_add_emails - Upload {emails_file.name}")

        return True

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Database Export Tool")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print()

    if export_database():
        print("\n🎉 Export successful!")
    else:
        print("\n❌ Export failed!")
