import os
import json
import csv
from datetime import datetime
from typing import Dict, Any

# Create logs directory if it doesn't exist
LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)

def log_command_output(
    command_type: str,
    user_id: int,
    username: str,
    channel_id: int,
    guild_id: int,
    command_output: str,
    tip_amount: str = None,
    card_used: tuple = None,
    email_used: str = None,
    additional_data: Dict[str, Any] = None
):
    """
    Log command output to multiple formats (JSON, CSV, and TXT)
    
    Args:
        command_type: Type of command (fusion_assist, fusion_order, wool_order)
        user_id: Discord user ID
        username: Discord username
        channel_id: Discord channel ID
        guild_id: Discord guild ID
        command_output: The actual command string that was output
        tip_amount: Tip amount from the order
        card_used: Tuple of (card_number, cvv) that was consumed
        email_used: Email that was consumed
        additional_data: Any additional data to log
    """
    timestamp = datetime.now()
    
    # Extract digits 9-16 from card number (0-indexed, so positions 8-15)
    card_digits_9_12 = None
    card_digits_9_16 = None
    card_full = None
    card_cvv = None
    if card_used:
        card_number = card_used[0]
        card_cvv = card_used[1]
        card_full = f"{card_number} CVV:{card_cvv}"
        if len(card_number) >= 12:
            card_digits_9_12 = card_number[8:12]  # Digits 9-12 (0-indexed)
        if len(card_number) >= 16:
            card_digits_9_16 = card_number[8:16]  # Digits 9-16 (0-indexed)
    
    # Prepare log entry
    log_entry = {
        "timestamp": timestamp.isoformat(),
        "command_type": command_type,
        "command_output": command_output,
        "email_used": email_used,
        "card_full": card_full,
        "card_digits_9_12": card_digits_9_12,
        "card_digits_9_16": card_digits_9_16,
        "additional_data": additional_data or {}
    }
    
    # Log to JSON file (detailed structured data)
    json_file = os.path.join(LOGS_DIR, f"commands_{timestamp.strftime('%Y%m')}.json")
    _log_to_json(json_file, log_entry)
    
    # Log to CSV file (for easy analysis)
    csv_file = os.path.join(LOGS_DIR, f"commands_{timestamp.strftime('%Y%m')}.csv")
    _log_to_csv(csv_file, log_entry)
    
    # Log to daily text file (human readable)
    txt_file = os.path.join(LOGS_DIR, f"commands_{timestamp.strftime('%Y%m%d')}.txt")
    _log_to_txt(txt_file, log_entry, timestamp)

def _log_to_json(filename: str, log_entry: Dict[str, Any]):
    """Append log entry to JSON file"""
    try:
        # Read existing data
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = []
        
        # Append new entry
        data.append(log_entry)
        
        # Write back to file
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error logging to JSON: {e}")

def _log_to_csv(filename: str, log_entry: Dict[str, Any]):
    """Append log entry to CSV file"""
    try:
        # Define CSV headers
        headers = [
            "timestamp", "command_type", "command_output", 
            "email_used", "card_full", "card_digits_9_12"
        ]
        
        # Check if file exists
        file_exists = os.path.exists(filename)
        
        # Prepare row data
        row_data = [
            log_entry["timestamp"],
            log_entry["command_type"],
            log_entry["command_output"],
            log_entry["email_used"],
            log_entry["card_full"],
            log_entry["card_digits_9_12"]
        ]
        
        with open(filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Write header if file is new
            if not file_exists:
                writer.writerow(headers)
            writer.writerow(row_data)
    except Exception as e:
        print(f"Error logging to CSV: {e}")

def _log_to_txt(filename: str, log_entry: Dict[str, Any], timestamp: datetime):
    """Append log entry to text file in human-readable format"""
    try:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"TIMESTAMP: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"COMMAND TYPE: {log_entry['command_type']}\n")
            if log_entry['email_used']:
                f.write(f"EMAIL USED: {log_entry['email_used']}\n")
            if log_entry['card_full']:
                f.write(f"CARD USED: {log_entry['card_full']}\n")
            if log_entry['card_digits_9_12']:
                f.write(f"CARD DIGITS 9-12: {log_entry['card_digits_9_12']}\n")
            f.write(f"\nCOMMAND OUTPUT:\n{log_entry['command_output']}\n")
            f.write(f"{'='*80}\n")
    except Exception as e:
        print(f"Error logging to TXT: {e}")

def get_recent_logs(count: int = 10) -> list:
    """
    Get the most recent log entries
    
    Args:
        count: Number of recent logs to retrieve
    
    Returns:
        List of recent log entries
    """
    current_month = datetime.now().strftime('%Y%m')
    json_file = os.path.join(LOGS_DIR, f"commands_{current_month}.json")
    
    if not os.path.exists(json_file):
        return []
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Sort by timestamp (most recent first) and take the requested count
        sorted_data = sorted(data, key=lambda x: x["timestamp"], reverse=True)
        return sorted_data[:count]
    except Exception as e:
        print(f"Error reading log file: {e}")
        return []

def get_full_logs(count: int = 5) -> list:
    """
    Get the most recent log entries with email and full command output
    
    Args:
        count: Number of recent logs to retrieve
    
    Returns:
        List of recent log entries with email and command data
    """
    current_month = datetime.now().strftime('%Y%m')
    json_file = os.path.join(LOGS_DIR, f"commands_{current_month}.json")
    
    if not os.path.exists(json_file):
        return []
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Sort by timestamp (most recent first) and take the requested count
        sorted_data = sorted(data, key=lambda x: x["timestamp"], reverse=True)
        return sorted_data[:count]
    except Exception as e:
        print(f"Error reading log file: {e}")
        return []

def get_log_stats(month: str = None) -> Dict[str, Any]:
    """
    Get statistics about logged commands
    
    Args:
        month: Optional month in YYYYMM format (e.g., "202405")
               If None, uses current month
    
    Returns:
        Dictionary with statistics
    """
    if month is None:
        month = datetime.now().strftime('%Y%m')
    
    json_file = os.path.join(LOGS_DIR, f"commands_{month}.json")
    
    if not os.path.exists(json_file):
        return {"error": "No log file found for specified month"}
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        stats = {
            "total_commands": len(data),
            "command_types": {},
            "emails_used": set(),
            "cards_used": set(),
            "date_range": {"start": None, "end": None}
        }
        
        for entry in data:
            # Count command types
            cmd_type = entry["command_type"]
            stats["command_types"][cmd_type] = stats["command_types"].get(cmd_type, 0) + 1
            
            # Track emails
            if entry.get("email_used"):
                stats["emails_used"].add(entry["email_used"])
            
            # Track cards (digits 9-12)
            if entry.get("card_digits_9_12"):
                stats["cards_used"].add(entry["card_digits_9_12"])
            
            # Track date range
            entry_date = entry["timestamp"]
            if stats["date_range"]["start"] is None or entry_date < stats["date_range"]["start"]:
                stats["date_range"]["start"] = entry_date
            if stats["date_range"]["end"] is None or entry_date > stats["date_range"]["end"]:
                stats["date_range"]["end"] = entry_date
        
        stats["unique_emails"] = len(stats["emails_used"])
        stats["unique_cards"] = len(stats["cards_used"])
        stats["emails_used"] = list(stats["emails_used"])  # Convert set to list for JSON serialization
        stats["cards_used"] = list(stats["cards_used"])  # Convert set to list for JSON serialization
        
        return stats
    except Exception as e:
        return {"error": f"Error reading log file: {e}"}