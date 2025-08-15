# Combined Discord Bot

A unified Discord bot that combines multiple essential functionalities:
1. **Order Command Generation** - Creates formatted commands for Fusion Assist, Fusion Order, Wool Order, and Pump Order with advanced card/email pool management
2. **Channel Management** - Opens/closes channels with rate limiting and announcements  
3. **Webhook Order Tracking** - Automatically detects and caches order confirmations from delivery service webhooks
4. **Advanced Debugging Tools** - Comprehensive debugging commands for troubleshooting webhook detection and embed parsing
5. **Payment Management System** - Dynamic payment method toggles with interactive button displays
6. **Multi-Pool Email System** - Separate email pools for different order types (main, pump_20off25, pump_25off)

## Features

### Order Commands (Owner Only)
- **`/fusion_assist`** - Generate Fusion assist commands with Postmates/UberEats modes
- **`/fusion_order`** - Generate Fusion order commands with email from pool
- **`/wool_order`** - Generate Wool order commands
- **`/pump_order`** - Generate Pump order commands with dedicated pump email pools
- **`/reorder`** - Generate reorder commands with email only (Fusion/Stewardess, no card required)
- **`/finished`** - Mark order as finished and move ticket to completed channel
- **Automatic embed parsing** from ticket bots
- **Order webhook tracking** - Use `/send_tracking` after a webhook posts to send tracking info to the ticket
- **Card & Email pools** with SQLite storage
- **Multi-pool email system** - Separate pools for different order types
- **Comprehensive logging** to JSON, CSV, and TXT files
- **Custom card/email support** - Use your own cards/emails without touching the pool
- **Intelligent webhook caching** - Automatically detects and caches order confirmations from multiple webhook formats

### Advanced Webhook Detection
- **Automatic webhook processing** - Detects tracking and checkout webhooks in real-time
- **Multiple webhook formats supported**:
  - Traditional field-based webhooks (Store, Name, Delivery Address)
  - Checkout webhooks (Account Email, Delivery Information, Items In Bag)  
  - Description-based webhooks (like Stewardess format with embedded markdown)
- **Smart name matching** - Flexible matching system with multiple name variations for improved accuracy
- **Timestamp-based caching** - Only keeps the most recent webhook data for each order
- **Comprehensive parsing** - Extracts store, name, address, items, tracking URLs, and arrival times

### Channel Management
- **`/open`** - Slash command to rename channel to "open🟢🟢" and send announcements
- **`/close`** - Slash command to rename channel to "closed🔴🔴" and send closure notice
- **`/break`** - Slash command to put channel "on-hold🟡🟡"
- **`open`** message - Renames channel to "open🟢🟢" and sends announcements
- **`close`/`closed`** message - Renames channel to "closed🔴🔴" and sends closure notice
- **Rate limiting** - Maximum 2 renames per 10 minutes per Discord's limits
- **Role pinging** and embed announcements
- **Silent mode** - Use `/open mode:silent` to skip role ping announcements

### Admin Pool Management (Owner Only)
- **`/add_card`** - Add single card to pool with validation
- **`/add_email`** - Add single email to specific pool (main, pump_20off25, pump_25off) with priority option
- **`/bulk_cards`** - Upload text or CSV file with multiple cards (supports various CSV formats)
- **`/bulk_emails_main`** - Upload text file with emails for main pool
- **`/bulk_emails_pump20`** - Upload text file with emails for pump_20off25 pool
- **`/bulk_emails_pump25`** - Upload text file with emails for pump_25off pool
- **`/read_cards`** - View all cards in pool
- **`/read_emails`** - View emails in specific pool or all pools
- **`/remove_card`** - Remove specific card from pool
- **`/remove_email`** - Remove specific email from any pool
- **`/remove_bulk_cards`** - Remove multiple cards using text file
- **`/remove_bulk_emails`** - Remove multiple emails from any pool using text file
- **Card validation** - Luhn algorithm validation and CVV format checking

### Webhook & Order Tracking (Owner Only)
- **`/send_tracking`** - Send order tracking info for current ticket using cached webhook data
- **`/scan_webhooks`** - Manually scan channels for webhook order confirmations
- **`/check_cache`** - View current webhook cache contents
- **`/debug_tracking`** - Debug webhook lookup and ticket matching

### Advanced Debugging Tools (Owner Only)
- **`/debug_embed_details`** - Show detailed embed structure for debugging webhook detection
- **`/simple_embed_debug`** - Quick embed analysis without fetching specific messages
- **`/raw_field_debug`** - Show raw field names and values for troubleshooting
- **`/check_specific_message`** - Test detection logic on a specific message ID
- **`/debug_stewardess_webhook`** - Debug specific webhook formats that aren't being detected
- **`/find_ticket`** - Search for ticket embeds in channel
- **`/test_webhook_parsing`** - Test webhook parsing on recent messages
- **`/debug_cache_timestamps`** - Show cache entries with timestamps for debugging recency issues

### Logging & Analytics (Owner Only)
- **`/print_logs`** - View recent command logs with email and card tracking
- **`/full_logs`** - View recent command logs with complete email and command output
- **`/log_stats`** - View statistics for commands, emails, and cards used
- **Automatic logging** to multiple formats (JSON, CSV, TXT)
- **Monthly log rotation** with detailed tracking
- **Card digit tracking** - Logs digits 9-16 for security while maintaining traceability

### Additional Features
- **`/payments`** - Display payment methods with interactive buttons
- **`/toggle_payment`** - Enable/disable specific payment method buttons (Zelle, Venmo, PayPal, CashApp, Crypto)
- **`/toggle_cashapp`** - Legacy command for CashApp toggle (use `/toggle_payment` instead)
- **`/wool_details`** - Show parsed Wool order details for verification
- **Dynamic payment buttons** - Only show enabled payment methods
- **Comprehensive error handling** with user-friendly messages
- **Smart field validation** - Automatically handles N/A and empty fields
- **Name normalization** - Consistent formatting for commands and matching
- **Invisible bot status** - Bot appears offline for privacy

## Prerequisites

- Python 3.10 or higher
- `pip` for package management

## Installation

1. **Clone or download the bot files**:
   ```bash
   mkdir combined-discord-bot
   cd combined-discord-bot
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. **Environment variables**: Copy `.env.example` to `.env` and fill in your values:

   ```dotenv
   # Required
   BOT_TOKEN=your_bot_token_here
   OWNER_ID=123456789012345678
   
   # Optional - comment out features you don't need
   OPENER_CHANNEL_ID=1234567890123456789  # For open/close commands
   ROLE_PING_ID=1352022044614590494       # Role to ping when opening
   ORDER_CHANNEL_MENTION=<#1350935337269985334>  # Channel mention in announcements
   ```

2. **Database initialization**: On first run, the bot will auto-create:
   - `data/pool.db` for cards and emails
   - `logs/` directory for command logging

## Running the Bot

```bash
python combinedbot.py
```

The bot will display which features are configured:
```
🚀 Starting combined Discord bot...
🔓 Opener channel: 1234567890123456789
👑 Owner ID: 123456789012345678
```

## Running Tests

```bash
pytest
```

## Command Reference

### For Everyone
- In opener channel: Use `/open`, `/close`, or `/break` (or type `open`, `close`, `closed`) to manage channel status

### Admin Only (Owner)
#### Order Management
- `/fusion_assist mode:UberEats email:custom@example.com card_number:1234... card_cvv:123` - Generate assist command with custom card/email
- `/fusion_order custom_email:test@example.com` - Generate order command with custom email
- `/wool_order custom_email:test@example.com custom_card_number:1234... custom_card_cvv:123` - Generate wool command
- `/pump_order custom_email:test@example.com custom_card_number:1234... custom_card_cvv:123 pool:pump_20off25` - Generate pump order with pump pool email
- `/reorder custom_email:test@example.com` - Generate reorder command (email only)
- `/finished` - Mark order as finished and move ticket to completed channel
- `/send_tracking` - Send tracking info for current ticket using cached webhook data

#### Pool Management
- `/add_card number:1234567812345678 cvv:123` - Add single card with validation
- `/add_email email:test@example.com pool:main top:True` - Add email to specific pool (optionally to front)
- `/bulk_cards` - Upload .txt or .csv file with cards (supports multiple CSV formats)
- `/bulk_emails_main` - Upload .txt file with emails for main pool
- `/bulk_emails_pump20` - Upload .txt file with emails for pump_20off25 pool
- `/bulk_emails_pump25` - Upload .txt file with emails for pump_25off pool
- `/read_cards` - View all cards
- `/read_emails pool:main` - View emails in specific pool or all pools
- `/remove_card number:1234567812345678 cvv:123` - Remove card
- `/remove_email email:test@example.com pool:main` - Remove email from specific pool
- `/remove_bulk_cards` - Upload .txt file to remove multiple cards
- `/remove_bulk_emails pool:main` - Upload .txt file to remove emails from specific pool

#### Webhook & Tracking Management
- `/scan_webhooks channel_id:123456789 search_limit:100` - Scan channel for webhook orders
- `/check_cache` - View current webhook cache contents
- `/debug_tracking search_limit:50` - Debug webhook lookup for current ticket

#### Logging & Analytics
- `/print_logs count:50` - Show recent 50 command logs with card digits 9-16
- `/full_logs count:10` - Show recent logs with complete command output
- `/log_stats month:202405` - Show stats for May 2024
- `/log_stats` - Show current month stats

#### Advanced Debugging
- `/debug_embed_details message_id:123456789 search_limit:10` - Detailed embed analysis
- `/simple_embed_debug search_limit:15` - Quick embed overview
- `/raw_field_debug search_limit:5` - Show raw field names and values
- `/check_specific_message message_id:123456789` - Test detection on specific message
- `/debug_stewardess_webhook` - Debug stewardess-format webhooks
- `/find_ticket search_limit:100` - Search for ticket embeds
- `/test_webhook_parsing search_limit:10` - Test parsing on recent webhooks
- `/debug_cache_timestamps name_filter:john` - Debug cache with timestamps

#### Utility Commands
- `/payments` - Display payment method buttons
- `/toggle_payment method:zelle enabled:false` - Enable/disable payment method buttons
- `/toggle_cashapp enabled:false` - Legacy toggle for CashApp button
- `/wool_details` - Show parsed Wool order details

## File Structure

```
combined-discord-bot/
├── combinedbot.py           # Main bot file
├── db.py                    # Database operations
├── logging_utils.py         # Comprehensive logging system
├── requirements.txt         # Python dependencies
├── .env.example            # Sample environment file
├── .env                    # Environment variables you create
├── README.md               # This file
├── bot/                    # Bot module structure
│   ├── __init__.py
│   ├── views.py            # UI components (payment buttons)
│   ├── commands/           # Command modules
│   │   ├── __init__.py
│   │   ├── admin.py        # Pool management commands
│   │   ├── channel.py      # Channel management commands
│   │   └── order.py        # Order generation commands
│   └── utils/              # Utility modules
│       ├── __init__.py
│       ├── card_validator.py    # Credit card validation
│       ├── channel_status.py   # Channel renaming logic
│       └── helpers.py          # Core helper functions
├── data/                   # Auto-created databases
│   └── pool.db            # Cards and emails
├── logs/                  # Auto-created logs
│   ├── commands_202405.json
│   ├── commands_202405.csv
│   └── commands_20240515.txt
└── tests/                 # Test suite
    ├── test_db_connection.py
    ├── test_format_name_csv.py
    ├── test_normalize_name.py
    └── test_parse_webhook_order.py
```

## Bulk File Formats

### Cards (bulk_cards)
**Text format** - Create a `.txt` file with one card per line:
```
1234567812345678,123
9876543210987654,456
5555444433332222,789
```

**CSV format** - Upload a `.csv` file with card data:
- Expects card number at column 6 (index 5)
- Expects CVV at column 9 (index 8)
- Automatically skips header rows
- Made for AYCD CSV exports

### Emails (bulk_emails_main, bulk_emails_pump20, bulk_emails_pump25)
Create a `.txt` file with one email per line:
```
user1@example.com
user2@example.com
user3@example.com
```

Each bulk email command adds emails to its respective pool:
- `bulk_emails_main` → main pool
- `bulk_emails_pump20` → pump_20off25 pool  
- `bulk_emails_pump25` → pump_25off pool
- (Feel free to rename, this was when Pump was semi decent)

## Using Custom Cards/Emails

All order commands now support custom cards and emails that bypass the pool:

```bash
# Use custom card and email (doesn't consume from pool)
/fusion_assist mode:UberEats email:custom@gmail.com card_number:1234567812345678 card_cvv:123

# Use custom email with pool card
/fusion_order custom_email:custom@gmail.com

# Use pool resources (consumes from pool)
/fusion_order
```

## Webhook Detection & Caching

The bot automatically detects and caches order confirmations from delivery service webhooks:

### Supported Webhook Formats
1. **Tracking Webhooks** - Traditional format with Store, Name, Delivery Address fields
2. **Checkout Webhooks** - Rich format with Account Email, Delivery Information, Items In Bag
3. **Description-based Webhooks** - Stewardess format with markdown embedded in description

### Smart Matching System
- **Multiple name variations** - Handles different name formats and orderings
- **Flexible matching** - Partial matches and name component matching
- **Timestamp priority** - Always uses the most recent webhook data
- **Address consideration** - Optional address matching for improved accuracy

### Cache Management
- **Automatic processing** - Webhooks are cached as they arrive
- **Manual scanning** - Use `/scan_webhooks` to process historical messages
- **Cache inspection** - Use `/check_cache` to view current cached orders
- **Debug tools** - Multiple commands for troubleshooting detection issues

## Configuration Options

### Required Settings
- `BOT_TOKEN` - Your Discord bot token
- `OWNER_ID` - Discord user ID for admin commands

### Optional Settings (comment out if not using)
- `OPENER_CHANNEL_ID` - Channel where open/close commands work
- `ROLE_PING_ID` - Role to ping when opening (default: 1352022044614590494)
- `ORDER_CHANNEL_MENTION` - Channel mention in open announcement (default: <#1350935337269985334>)

### Pool Constants
The following are hardcoded but can be modified in the source:
- `EXP_MONTH = '08'` - Credit card expiration month
- `EXP_YEAR = '30'` - Credit card expiration year
- `ZIP_CODE = '07724'` - ZIP code for orders

## Troubleshooting

### Common Issues

**"Card pool is empty" or "Email pool is empty"**
- Use `/add_card` and `/add_email` commands or bulk upload files
- Alternatively, use custom cards/emails to bypass pools entirely

**"Could not find order embed"**
- Use `/find_ticket` to debug ticket embed detection
- Ensure the ticket bot's message contains Group Cart Link and Name fields
- Try `/debug_embed_details` to see what embeds are actually present

**Webhook not being detected**
- Use `/debug_embed_details` to analyze webhook structure
- Try `/simple_embed_debug` for a quick overview
- Use `/check_specific_message` with the webhook message ID
- For stewardess webhooks, try `/debug_stewardess_webhook`

**Tracking command not finding webhook data**
- Use `/debug_tracking` to see what's in the cache vs. what's expected
- Try `/scan_webhooks` to manually process recent webhooks
- Use `/check_cache` to see all cached webhook data
- Check name variations with `/debug_cache_timestamps`

**Channel rename not working**
- Check bot has "Manage Channels" permission
- Verify `OPENER_CHANNEL_ID` matches the intended channel
- Remember there's a 2 renames per 10 minutes rate limit (Discord's limitation)

**Commands not appearing**
- Bot needs "applications.commands" scope when invited
- Commands sync automatically on startup
- Try `/` in Discord to see if commands appear

**Permission errors**
- Bot needs appropriate permissions in each channel it operates in:
  - View Channel, Send Messages, Read Message History (all channels)
  - Manage Channels (opener channel)

### Debug Commands for Troubleshooting

For webhook detection issues:
- `/debug_embed_details` - Comprehensive embed analysis
- `/simple_embed_debug` - Quick overview of recent embeds
- `/raw_field_debug` - Show exact field names and values
- `/check_specific_message message_id:123` - Test specific webhook

For tracking issues:
- `/debug_tracking` - Compare ticket vs. cached data
- `/scan_webhooks` - Manually process webhook history
- `/check_cache` - View all cached webhook data
- `/debug_cache_timestamps` - Debug timestamp and matching issues

## Security Considerations

- All command responses are ephemeral (only visible to command user)
- Only the configured `OWNER_ID` can execute admin commands
- Bot runs in invisible status (appears offline) for privacy
- Card numbers and emails are logged in full - secure your log files appropriately
- Database files contain sensitive payment information - implement appropriate backups and security
- Consider rotating cards/emails regularly and removing old entries
- Card digits 9-16 are logged for traceability while maintaining some security
- Multiple email pools allow for separation of different order types
- Payment methods can be dynamically enabled/disabled without code changes

## Advanced Usage

### Custom Card Expiration
Update the constants in the source files (combinedbot.py and bot/commands/order.py):
```python
EXP_MONTH = '12'  # December
EXP_YEAR = '25'   # 2025
ZIP_CODE = '90210'  # Beverly Hills
```

### Webhook Processing Customization
The webhook detection logic can be customized in `bot/utils/helpers.py`:
- Modify detection patterns in `parse_webhook_fields()`
- Adjust name matching logic in `generate_name_variations()`
- Customize caching behavior in `cache_webhook_data()`

### Logging Customization
Logging behavior can be modified in `logging_utils.py`:
- Change log file formats and naming
- Modify what data is logged
- Adjust log rotation schedules

### Payment Method Customization
Payment methods can be customized in `bot/views.py`:
- Add new payment methods to `PAYMENT_METHODS_ENABLED` dictionary
- Modify payment button labels, colors, and emojis
- Update payment information in button callbacks
- Dynamic toggle system allows runtime changes without restarts

## Support & Contributing

For issues, feature requests, or contributions:
1. Check the troubleshooting section above
2. Use the debug commands to gather detailed information
3. Verify your configuration matches the examples
4. Test with minimal configuration first
5. Check Discord bot permissions thoroughly

The combined bot provides streamlined order management, automatic webhook tracking, and comprehensive debugging tools while maintaining security and detailed logging.