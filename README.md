# Combined Discord Bot

A unified Discord bot that combines three essential functionalities:
1. **Order Command Generation** - Creates formatted commands for Fusion Assist, Fusion Order, and Wool Order with card/email pool management
2. **Channel Management** - Opens/closes channels with rate limiting and announcements
3. **Role Assignment** - Automatically assigns roles to users who post images

## Features

### Order Commands (Owner Only)
- **`/fusion_assist`** - Generate Fusion assist commands with Postmates/UberEats modes
- **`/fusion_order`** - Generate Fusion order commands with email from pool
- **`/wool_order`** - Generate Wool order commands
- **Automatic embed parsing** from ticket bots
- **Card & Email pools** with SQLite storage
- **Comprehensive logging** to JSON, CSV, and TXT files
- **Custom card/email support** - Use your own cards/emails without touching the pool

### Channel Management
- **`/open`** - Slash command to rename channel to "open🟢🟢" and send announcements
- **`/close`** - Slash command to rename channel to "closed🔴🔴" and send closure notice
- **`open`** message - Renames channel to "open🟢🟢" and sends announcements
- **`close`/`closed`** message - Renames channel to "closed🔴🔴" and sends closure notice
- **Rate limiting** - Maximum 2 renames per 10 minutes per Discord's limits
- **Role pinging** and embed announcements

### Role Assignment
- **Automatic role assignment** for image posts in designated channel
- **Silent operation** - No messages or notifications
- **Smart role checking** - Only adds role if user doesn't already have it

### Admin Pool Management (Owner Only)
- **`/add_card`** - Add single card to pool
- **`/add_email`** - Add single email to pool (with priority option)
- **`/bulk_cards`** - Upload text file with multiple cards
- **`/bulk_emails`** - Upload text file with multiple emails
- **`/read_cards`** - View all cards in pool
- **`/read_emails`** - View all emails in pool
- **`/remove_card`** - Remove specific card from pool
- **`/remove_email`** - Remove specific email from pool

### Logging & Analytics (Owner Only)
- **`/print_logs`** - View recent command logs with email and card tracking
- **`/log_stats`** - View statistics for commands, emails, and cards used
- **Automatic logging** to multiple formats (JSON, CSV, TXT)
- **Monthly log rotation** with detailed tracking

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

1. **Environment variables**: Create a `.env` file in the project root:

   ```dotenv
   # Required
   BOT_TOKEN=your_bot_token_here
   OWNER_ID=123456789012345678
   
   # Optional - comment out features you don't need
   POINTS_CHANNEL_ID=1234567890123456789  # For role assignment
   OPENER_CHANNEL_ID=1234567890123456789  # For open/close commands
   ROLE_PING_ID=1352022044614590494       # Role to ping when opening
   VIP_ROLE_ID=1371247728646033550        # VIP role for redemptions
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
📍 Points channel: 1234567890123456789
🔓 Opener channel: 1234567890123456789
👑 Owner ID: 123456789012345678
```

## Running Tests

```bash
pytest
```

## Command Reference

### For Everyone
- In points channel: Post images to get role assignment (silent)
- In opener channel: Use `/open` or `/close` (or type `open`, `close`, `closed`) to manage channel status

### Admin Only (Owner)
#### Order Management
- `/fusion_assist mode:UberEats email:custom@example.com card_number:1234... card_cvv:123` - Generate assist command with custom card/email
- `/fusion_order custom_email:test@example.com` - Generate order command with custom email
- `/wool_order` - Generate wool command

#### Pool Management
- `/add_card number:1234567812345678 cvv:123` - Add single card
- `/add_email email:test@example.com top:True` - Add email (optionally to front)
- `/bulk_cards` - Upload .txt file with cards (format: `cardnum,cvv` per line)
- `/bulk_emails` - Upload .txt file with emails (one per line)
- `/read_cards` - View all cards
- `/read_emails` - View all emails
- `/remove_card number:1234567812345678 cvv:123` - Remove card
- `/remove_email email:test@example.com` - Remove email

#### Logging & Analytics
- `/print_logs count:50` - Show recent 50 command logs
- `/log_stats month:202405` - Show stats for May 2024
- `/log_stats` - Show current month stats

## File Structure

```
combined-discord-bot/
├── combinedbot.py        # Main bot file
├── requirements.txt      # Python dependencies
├── .env                 # Environment variables (create this)
├── README.md            # This file
├── data/                # Auto-created databases
│   └── pool.db          # Cards and emails
└── logs/                # Auto-created logs
    ├── commands_202405.json
    ├── commands_202405.csv
    └── commands_20240515.txt
```

## Bulk File Formats

### Cards (bulk_cards)
Create a `.txt` file with one card per line:
```
1234567812345678,123
9876543210987654,456
5555444433332222,789
```

### Emails (bulk_emails)
Create a `.txt` file with one email per line:
```
user1@example.com
user2@example.com
user3@example.com
```

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

## Configuration Options

### Required Settings
- `BOT_TOKEN` - Your Discord bot token
- `OWNER_ID` - Discord user ID for admin commands

### Optional Settings (comment out if not using)
- `POINTS_CHANNEL_ID` - Channel where images trigger role assignment
- `OPENER_CHANNEL_ID` - Channel where open/close commands work
- `ROLE_PING_ID` - Role to ping when opening (default: 1352022044614590494)
- `VIP_ROLE_ID` - Role assigned with "Perm Fee" redemption (default: 1371247728646033550)
- `ORDER_CHANNEL_MENTION` - Channel mention in open announcement (default: <#1350935337269985334>)

### Pool Constants
The following are hardcoded but can be modified in the source:
- `EXP_MONTH = '06'` - Credit card expiration month
- `EXP_YEAR = '30'` - Credit card expiration year
- `ZIP_CODE = '19104'` - ZIP code for orders

## Troubleshooting

### Common Issues

**"Card pool is empty" or "Email pool is empty"**
- Use `/add_card` and `/add_email` commands or bulk upload files
- Alternatively, use custom cards/emails to bypass pools entirely

**"Could not find order embed"**
- Ensure the ticket bot's first message contains at least 2 embeds
- The bot looks for the second embed in the first message of the channel

**Role assignment not working**
- Verify `POINTS_CHANNEL_ID` is set correctly
- Check that the bot has permissions to manage roles
- Ensure the target role ID (1350935336435449969) exists and bot can assign it

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
  - Manage Roles (for role assignment)

## Security Considerations

- All command responses are ephemeral (only visible to command user)
- Only the configured `OWNER_ID` can execute admin commands
- Card numbers and emails are logged in full - secure your log files appropriately
- Database files contain sensitive payment information - implement appropriate backups and security
- Consider rotating cards/emails regularly and removing old entries

## Advanced Usage

### Custom Card Expiration
Update the constants in the source file:
```python
EXP_MONTH = '12'  # December
EXP_YEAR = '25'   # 2025
ZIP_CODE = '90210'  # Beverly Hills
```

### Changing Role Assignment Target
Modify the role ID in the source file:
```python
# In the on_message event
target_role_id = 1350935336435449969  # Change this ID
```

## Support & Contributing

For issues, feature requests, or contributions:
1. Check the troubleshooting section above
2. Verify your configuration matches the examples
3. Test with minimal configuration first
4. Check Discord bot permissions thoroughly

The combined bot provides streamlined order management and channel automation while maintaining security and comprehensive logging.
