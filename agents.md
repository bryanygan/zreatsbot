# agents.md - Combined Discord Bot

## Project Overview

A unified Discord bot for order management, channel control, and webhook tracking. Combines order command generation, channel status management, and automatic webhook order processing with comprehensive debugging tools.

## Architecture

### Core Components

1. **Order Management** (`bot/commands/order.py`)
   - Fusion assist/order command generation
   - Wool order processing
   - Card/email pool management with custom override support
   - Automatic embed parsing from ticket bots

2. **Channel Management** (`bot/commands/channel.py`)
   - Channel status control (open/close/break)
   - Rate-limited channel renaming
   - Role ping announcements with silent mode

3. **Admin Tools** (`bot/commands/admin.py`)
   - Pool management (cards/emails)
   - Bulk upload from text files
   - Logging and analytics commands

4. **Webhook Processing** (`bot/utils/helpers.py`)
   - Automatic webhook order detection and caching
   - Multiple webhook format support
   - Smart name matching with variations
   - Timestamp-based recency tracking

### Database Schema

**SQLite Database** (`data/pool.db`):
```sql
-- Card storage with Luhn validation
CREATE TABLE cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL,  -- Full card number
    cvv TEXT NOT NULL      -- CVV code
);

-- Email storage with priority ordering
CREATE TABLE emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL    -- Email address
);
```

**In-Memory Cache** (`ORDER_WEBHOOK_CACHE`):
```python
# Key: (normalized_name, address)
# Value: {
#   'data': webhook_data,
#   'timestamp': datetime,
#   'message_id': int
# }
```

## Key Functions

### Order Processing Pipeline

1. **Ticket Embed Detection**:
   ```python
   async def fetch_ticket_embed(channel, search_limit=100)
   # Looks for: Group Cart Link, Name fields
   ```

2. **Field Parsing**:
   ```python
   def parse_fields(embed) -> dict
   # Returns: link, name, address, addr2, notes, tip
   ```

3. **Name Normalization**:
   ```python
   def normalize_name(name) -> str
   # "john doe" → "John Doe"
   # "alice" → "Alice A"
   ```

4. **Pool Management**:
   ```python
   def get_and_remove_card() -> (number, cvv, is_last)
   def get_and_remove_email() -> (email, is_last)
   ```

### Webhook Detection System

**Multi-Format Detection**:
- **Tracking**: `{"Store", "Name", "Delivery Address"}` fields
- **Checkout**: `"Account Email"`, `"Delivery Information"`, `"Items In Bag"` fields
- **Description-based**: Markdown patterns in embed description

**Parsing Logic**:
```python
def parse_webhook_fields(embed) -> dict:
    # Handles 3 formats:
    # 1. Traditional tracking (Store/Name/Address fields)
    # 2. Rich checkout (Account Email/Delivery Info fields) 
    # 3. Description-based (markdown in description)
```

**Smart Caching**:
```python
def cache_webhook_data(data, message_timestamp, message_id):
    # Only cache if more recent than existing entry
    # Key: (normalized_name, address)
```

### Name Matching Algorithm

```python
def generate_name_variations(name) -> list:
    # Creates multiple normalized forms:
    # "John, Doe" → ["john doe", "john", "doe", "doe john", "john d"]
    
def find_latest_matching_webhook_data(name, address=""):
    # 1. Generate name variations
    # 2. Try exact matches first
    # 3. Fall back to partial matches
    # 4. Return most recent by timestamp
```

## Command Reference

### Owner-Only Commands

**Order Generation**:
- `/fusion_assist mode:UberEats email:custom@email.com card_number:1234... card_cvv:123`
- `/fusion_order custom_email:test@email.com card_number:1234... card_cvv:123`
- `/wool_order custom_email:test@email.com card_number:1234... card_cvv:123`

**Pool Management**:
- `/add_card number:1234567812345678 cvv:123`
- `/add_email email:test@email.com top:True`
- `/bulk_cards` (upload .txt file: `cardnum,cvv` per line)
- `/bulk_emails` (upload .txt file: one email per line)
- `/read_cards`, `/read_emails`
- `/remove_card`, `/remove_email`

**Webhook & Tracking**:
- `/send_tracking` - Send tracking for current ticket using cached webhook
- `/scan_webhooks channel_id:123 search_limit:100`
- `/check_cache` - View webhook cache contents
- `/debug_tracking` - Debug webhook lookup for current ticket

**Advanced Debugging**:
- `/debug_embed_details message_id:123 search_limit:10`
- `/simple_embed_debug search_limit:15`
- `/raw_field_debug search_limit:5`
- `/check_specific_message message_id:123`
- `/debug_stewardess_webhook`
- `/find_ticket search_limit:100`
- `/test_webhook_parsing search_limit:10`
- `/debug_cache_timestamps name_filter:john`

**Logging & Analytics**:
- `/print_logs count:50` - Show recent logs with card digits 9-16
- `/full_logs count:10` - Show logs with full command output
- `/log_stats month:202405` - Monthly statistics

### Channel Management (Opener Channel Only)
- `/open mode:silent` - Open channel (skip role ping if silent)
- `/close` - Close channel
- `/break` - Put channel on hold
- Text commands: `open`, `close`, `closed` (same as slash commands)

### Utility Commands
- `/payments` - Show payment method buttons
- `/wool_details` - Show parsed Wool order details for verification

## Configuration

### Environment Variables (.env)
```bash
# Required
BOT_TOKEN=your_bot_token_here
OWNER_ID=123456789012345678

# Optional - comment out what you don't use
OPENER_CHANNEL_ID=1234567890123456789
ROLE_PING_ID=1352022044614590494
ORDER_CHANNEL_MENTION=<#1350935337269985334>
```

### Hardcoded Constants
```python
EXP_MONTH = '06'          # Credit card expiration month
EXP_YEAR = '35'           # Credit card expiration year  
ZIP_CODE = '19104'        # ZIP code for orders
```

## Validation & Security

### Card Validation
```python
class CardValidator:
    @staticmethod
    def validate_card_number(card_number) -> (bool, str):
        # Luhn algorithm validation
        # Length check (13-19 digits)
        
    @staticmethod
    def validate_cvv(cvv, card_number=None) -> (bool, str):
        # 3-4 digit validation
        # AmEx requires 4 digits, others 3
```

### Security Features
- All admin commands require `OWNER_ID` match
- Ephemeral responses (only command user sees)
- Card digits 9-16 logged for traceability (not full numbers in logs)
- Input validation on all fields
- Rate limiting on channel renames (Discord's 2 per 10 minutes)

## Logging System

### Multi-Format Logging
```python
def log_command_output(command_type, user_id, username, channel_id, 
                      guild_id, command_output, tip_amount=None,
                      card_used=None, email_used=None, additional_data=None):
    # Logs to:
    # - JSON: commands_YYYYMM.json (structured data)
    # - CSV: commands_YYYYMM.csv (analysis-friendly)
    # - TXT: commands_YYYYMMDD.txt (human-readable)
```

### Log Data Structure
```python
{
    "timestamp": "2024-05-15T14:30:00",
    "command_type": "fusion_order",
    "command_output": "/order uber order_details:...",
    "email_used": "user@example.com",
    "card_full": "1234567812345678 CVV:123",
    "card_digits_9_12": "5678",
    "card_digits_9_16": "56781234",
    "additional_data": {...}
}
```

## Error Handling Patterns

### Graceful Degradation
- Pool empty → Custom card/email prompts
- Embed not found → Clear error messages with suggestions
- Webhook missing → Manual scanning options
- Rate limit hit → Clear timeout explanation

### Debug Command Strategy
- Simple overview commands (`/simple_embed_debug`)
- Detailed analysis (`/debug_embed_details`)
- Specific message testing (`/check_specific_message`)
- Step-by-step debugging (`/debug_stewardess_webhook`)

## File Structure
```
combined-discord-bot/
├── combinedbot.py           # Main bot entry point
├── db.py                    # Database operations
├── logging_utils.py         # Comprehensive logging
├── requirements.txt         # Dependencies
├── .env.example            # Configuration template
├── README.md               # User documentation
├── bot/                    # Bot modules
│   ├── commands/           # Command implementations
│   │   ├── admin.py        # Pool & log management
│   │   ├── channel.py      # Channel status control
│   │   └── order.py        # Order generation & debugging
│   ├── utils/              # Utility modules
│   │   ├── card_validator.py    # Credit card validation
│   │   ├── channel_status.py   # Channel renaming logic
│   │   └── helpers.py          # Core helper functions
│   └── views.py            # UI components (payment buttons)
├── data/                   # Auto-created databases
│   └── pool.db            # SQLite database
├── logs/                  # Auto-created logs
│   ├── commands_YYYYMM.json
│   ├── commands_YYYYMM.csv
│   └── commands_YYYYMMDD.txt
└── tests/                 # Test suite
    ├── test_db_connection.py
    ├── test_format_name_csv.py
    ├── test_normalize_name.py
    └── test_parse_webhook_order.py
```

## Integration Points

### Discord Event Handlers
```python
@bot.event
async def on_message(message):
    # 1. Channel status text commands (open/close/closed)
    # 2. Webhook order processing (automatic caching)
    # 3. Standard command processing
```

### External Dependencies
- `discord.py>=2.5.1` - Discord API wrapper
- `python-dotenv>=1.0.0` - Environment variable loading
- `pytest>=8.0.0` - Testing framework

### Database Integration
- SQLite for persistent storage (cards, emails)
- In-memory cache for webhook data (performance)
- Automatic schema creation on first run

## Development Workflow

### Testing Strategy
- Unit tests for core functions (name normalization, parsing)
- Mock Discord objects for testing
- Database connection testing
- Validation logic testing

### Extension Points
- New webhook formats: Update `parse_webhook_fields()`
- Additional card types: Extend `CardValidator`
- New command types: Add to respective command modules
- Enhanced matching: Modify `generate_name_variations()`

### Debugging Workflow
1. Use `/simple_embed_debug` for quick overview
2. Use `/debug_embed_details` for detailed analysis
3. Use `/find_ticket` to debug ticket detection
4. Use `/scan_webhooks` to refresh webhook cache
5. Use `/debug_tracking` to compare ticket vs webhook data
6. Use specific debug commands for targeted issues

## Common Issues & Solutions

### Webhook Not Detected
- **Check**: Use `/debug_embed_details` to see actual structure
- **Solution**: May need to add new detection pattern in `parse_webhook_fields()`

### Name Matching Fails
- **Check**: Use `/debug_cache_timestamps` with name filter
- **Solution**: Name variations may need adjustment in `generate_name_variations()`

### Channel Rename Fails
- **Check**: Bot permissions and rate limiting
- **Solution**: Max 2 renames per 10 minutes (Discord limitation)

### Pool Management Issues
- **Check**: Use `/read_cards` and `/read_emails` to verify pool state
- **Solution**: Use bulk upload commands or manual add commands
