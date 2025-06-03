#!/usr/bin/env python3
"""
Points Migration Script
Migrates points data from Node.js quick.db format to Python combined bot format
"""

import sqlite3
import json
import os
from pathlib import Path

def inspect_database(db_path):
    """Inspect the database structure to understand the format"""
    print(f"🔍 Inspecting database structure...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"📋 Tables found: {[table[0] for table in tables]}")
    
    # For each table, get column info
    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        print(f"📊 Table '{table_name}' columns:")
        for col in columns:
            print(f"   • {col[1]} ({col[2]})")
        
        # Show sample data
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
        sample_rows = cursor.fetchall()
        print(f"📝 Sample data from '{table_name}':")
        for i, row in enumerate(sample_rows, 1):
            print(f"   Row {i}: {row}")
        print()
    
    conn.close()

def migrate_points_data(old_db_path, new_data_dir="data"):
    """
    Migrate points from quick.db (Node.js) to combined bot format (Python)
    
    Args:
        old_db_path: Path to the json.sqlite file from your Node.js bot
        new_data_dir: Directory where the new points.db should be created
    """
    
    # Ensure the new data directory exists
    Path(new_data_dir).mkdir(parents=True, exist_ok=True)
    new_db_path = Path(new_data_dir) / "points.db"
    
    print(f"🔄 Migrating points from {old_db_path} to {new_db_path}")
    
    try:
        # First, inspect the database to understand its structure
        inspect_database(old_db_path)
        
        # Connect to old database
        print("📖 Reading old database...")
        old_conn = sqlite3.connect(old_db_path)
        old_cursor = old_conn.cursor()
        
        # Try different possible table structures
        old_rows = []
        
        # Method 1: Handle your specific format (ID='points', json='{user_id: points, ...}')
        try:
            old_cursor.execute("SELECT ID, json FROM json WHERE ID = 'points'")
            points_row = old_cursor.fetchone()
            
            if points_row:
                id_value, points_json = points_row
                print(f"📊 Found points data in row with ID='{id_value}'")
                
                try:
                    # Parse the JSON string containing all user points
                    points_data = json.loads(points_json)
                    print(f"🎯 Successfully parsed JSON with {len(points_data)} users")
                    
                    # Extract user IDs and points from the JSON
                    for user_id, points in points_data.items():
                        old_rows.append((user_id, points))
                        
                    print(f"📌 Sample entries:")
                    for i, (user_id, points) in enumerate(old_rows[:5]):
                        print(f"   • User {user_id}: {points} points")
                    if len(old_rows) > 5:
                        print(f"   ... and {len(old_rows) - 5} more users")
                        
                except json.JSONDecodeError as e:
                    print(f"⚠️  Could not parse JSON: {e}")
        except sqlite3.Error as e:
            print(f"⚠️  Method 1 failed: {e}")
        
        # Method 2: Try traditional quick.db format (key-value in json table)
        if not old_rows:
            try:
                old_cursor.execute("SELECT ID, json FROM json WHERE ID LIKE 'points.%'")
                kv_data = old_cursor.fetchall()
                print(f"📊 Found data in traditional format: {len(kv_data)} rows")
                
                for key, value in kv_data:
                    if key.startswith('points.'):
                        user_id = key[7:]  # Remove "points." prefix
                        try:
                            points = json.loads(value)
                            old_rows.append((user_id, points))
                        except json.JSONDecodeError as e:
                            print(f"⚠️  Could not parse JSON for key {key}: {e}")
                            continue
            except sqlite3.Error as e:
                print(f"⚠️  Method 2 failed: {e}")
        
        # Method 3: Try to find any table with user data
        if not old_rows:
            try:
                # Get all data from json table
                old_cursor.execute("SELECT ID, json FROM json")
                all_data = old_cursor.fetchall()
                
                print(f"🔍 Found {len(all_data)} rows in json table")
                for row in all_data:
                    print(f"   Row: ID='{row[0]}', json length={len(row[1])}")
                    
            except sqlite3.Error as e:
                print(f"⚠️  Method 3 failed: {e}")
        
        if not old_rows:
            print("❌ No points data found in any recognizable format!")
            print("💡 Please share the exact structure of your database so I can help you migrate it.")
            return False
        
        print(f"📊 Found {len(old_rows)} point entries to migrate")
        
        # Connect to new database (combined bot format)
        print("📝 Creating new database...")
        new_conn = sqlite3.connect(new_db_path)
        new_cursor = new_conn.cursor()
        
        # Create the points table in the new format
        new_cursor.execute('''
            CREATE TABLE IF NOT EXISTS points (
                user_id TEXT PRIMARY KEY,
                points INTEGER DEFAULT 0
            )
        ''')
        
        # Migrate data
        migrated_count = 0
        for user_id, points in old_rows:
            try:
                # Insert into new database
                new_cursor.execute(
                    "INSERT OR REPLACE INTO points (user_id, points) VALUES (?, ?)",
                    (str(user_id), int(points))
                )
                migrated_count += 1
                print(f"✅ Migrated user {user_id}: {points} points")
                
            except (ValueError, sqlite3.Error) as e:
                print(f"⚠️  Skipping user {user_id}: {e}")
                continue
        
        # Commit changes
        new_conn.commit()
        
        # Close connections
        old_conn.close()
        new_conn.close()
        
        print(f"🎉 Migration complete! Successfully migrated {migrated_count} users' points")
        print(f"📂 New database created at: {new_db_path}")
        
        # Verify migration
        verify_migration(new_db_path)
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    return True

def verify_migration(db_path):
    """Verify the migration was successful"""
    print("🔍 Verifying migration...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM points")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(points) FROM points")
    total_points = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT user_id, points FROM points ORDER BY points DESC LIMIT 5")
    top_users = cursor.fetchall()
    
    conn.close()
    
    print(f"📈 Migration Summary:")
    print(f"   • Total users: {total_users}")
    print(f"   • Total points: {total_points}")
    print(f"   • Top 5 users:")
    for i, (user_id, points) in enumerate(top_users, 1):
        print(f"     {i}. User {user_id}: {points} points")

def find_quickdb_file():
    """Try to automatically find the quick.db file"""
    possible_paths = [
        "json.sqlite",
        "database.sqlite", 
        "db/json.sqlite",
        "data/json.sqlite",
        "../princounter/json.sqlite",  # If running from combined bot directory
        "../json.sqlite"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None

if __name__ == "__main__":
    print("🚀 Points Migration Tool")
    print("=" * 50)
    
    # Try to find the old database automatically
    old_db = find_quickdb_file()
    
    if old_db:
        print(f"📁 Found quick.db file: {old_db}")
        choice = input("Use this file? (y/n): ").lower().strip()
        if choice != 'y':
            old_db = None
    
    # If not found or user declined, ask for path
    if not old_db:
        print("\n📂 Please provide the path to your Node.js bot's database file")
        print("   Common names: json.sqlite, database.sqlite")
        old_db = input("Path to old database: ").strip()
        
        if not os.path.exists(old_db):
            print(f"❌ File not found: {old_db}")
            exit(1)
    
    # Confirm migration
    print(f"\n🔄 Ready to migrate points from:")
    print(f"   Source: {old_db}")
    print(f"   Target: data/points.db")
    
    confirm = input("\nProceed with migration? (y/n): ").lower().strip()
    if confirm != 'y':
        print("❌ Migration cancelled")
        exit(0)
    
    # Perform migration
    success = migrate_points_data(old_db)
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("🔧 You can now start your combined bot with the migrated points data")
        print("\n💡 Next steps:")
        print("   1. Set POINTS_CHANNEL_ID in your .env file")
        print("   2. Start the combined bot: python combinedbot.py")
        print("   3. Test with /checkpoints to verify points are working")
    else:
        print("\n❌ Migration failed. Check the error messages above.")
        exit(1)

def verify_migration(db_path):
    """Verify the migration was successful"""
    print("🔍 Verifying migration...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM points")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(points) FROM points")
    total_points = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT user_id, points FROM points ORDER BY points DESC LIMIT 5")
    top_users = cursor.fetchall()
    
    conn.close()
    
    print(f"📈 Migration Summary:")
    print(f"   • Total users: {total_users}")
    print(f"   • Total points: {total_points}")
    print(f"   • Top 5 users:")
    for i, (user_id, points) in enumerate(top_users, 1):
        print(f"     {i}. User {user_id}: {points} points")

def find_quickdb_file():
    """Try to automatically find the quick.db file"""
    possible_paths = [
        "json.sqlite",
        "database.sqlite", 
        "db/json.sqlite",
        "data/json.sqlite",
        "../princounter/json.sqlite",  # If running from combined bot directory
        "../json.sqlite"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None

if __name__ == "__main__":
    print("🚀 Points Migration Tool")
    print("=" * 50)
    
    # Try to find the old database automatically
    old_db = find_quickdb_file()
    
    if old_db:
        print(f"📁 Found quick.db file: {old_db}")
        choice = input("Use this file? (y/n): ").lower().strip()
        if choice != 'y':
            old_db = None
    
    # If not found or user declined, ask for path
    if not old_db:
        print("\n📂 Please provide the path to your Node.js bot's database file")
        print("   Common names: json.sqlite, database.sqlite")
        old_db = input("Path to old database: ").strip()
        
        if not os.path.exists(old_db):
            print(f"❌ File not found: {old_db}")
            exit(1)
    
    # Confirm migration
    print(f"\n🔄 Ready to migrate points from:")
    print(f"   Source: {old_db}")
    print(f"   Target: data/points.db")
    
    confirm = input("\nProceed with migration? (y/n): ").lower().strip()
    if confirm != 'y':
        print("❌ Migration cancelled")
        exit(0)
    
    # Perform migration
    success = migrate_points_data(old_db)
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("🔧 You can now start your combined bot with the migrated points data")
        print("\n💡 Next steps:")
        print("   1. Set POINTS_CHANNEL_ID in your .env file")
        print("   2. Start the combined bot: python combinedbot.py")
        print("   3. Test with /checkpoints to verify points are working")
    else:
        print("\n❌ Migration failed. Check the error messages above.")
        exit(1)