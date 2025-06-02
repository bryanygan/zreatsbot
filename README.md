# Combined Discord Bot

A unified Discord bot that combines three essential functionalities:
1. **Order Command Generation** - Creates formatted commands for Fusion Assist, Fusion Order, and Wool Order with card/email pool management
2. **Points System** - Awards points for image posts and tracks leaderboards
3. **Channel Management** - Opens/closes channels with rate limiting and announcements

## Features

### Order Commands (Owner Only)
- **`/fusion_assist`** - Generate Fusion assist commands with Postmates/UberEats modes
- **`/fusion_order`** - Generate Fusion order commands with email from pool
- **`/wool_order`** - Generate Wool order commands
- **Automatic embed parsing** from ticket bots
- **Card & Email pools** with SQLite storage
- **Comprehensive logging** to JSON, CSV, and TXT files

### Points System
- **Automatic point awards** for image posts in designated channel
- **`/checkpoints`** - View your or others' points
- **`/leaderboard`** - Show top point earners (admin only)
- **`/setpoints`** - Override user points (admin only)
- **`/clearpoints`** - Clear points for user or all users (admin only)
- **`/redeem`** - Redeem points for rewards with VIP role assignment (admin only)
- **`/backfill`** - Award points retroactively from channel history (admin only)

### Channel Management
- **`open`** message - Renames channel to "open🟢🟢" and sends announcements
- **`close`/`closed`** message - Renames channel to "closed🔴🔴" and sends closure notice
- **Rate limiting** - Maximum 2 renames per 10 minutes per Discord's limits
- **Role pinging** and embed announcements

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
   POINTS_CHANNEL_ID=1234567890123456789
   OPENER_CHANNEL_ID=1234567890123456789
   ROLE_PING_ID=1352022044614590494
   VIP_ROLE_ID=1371247728646033550
   ORDER_CHANNEL_MENTION=<#1350935337269985334>
   ```

2. **Database initialization**: On first run, the bot will auto-create:
   - `data/pool.db` for cards and emails
   - `data/points.db` for user points
   - `logs/` directory for command logging

## Running the Bot

```bash
python combined_bot.py
```

The bot will display which features are configured:
```
🚀 Starting combined Discord bot...
📍 Points channel: 1234567890123456789
🔓 Opener channel: 1234567890123456789
👑 Owner ID: 123456789012345678
```

## Command Reference

### For Everyone
- In points channel: Post images to earn points
- In opener channel: Type `open`, `close`, or `closed` to manage channel status
- `/checkpoints` - View your points

### Admin Only (Owner)
#### Order Management
- `/fusion_assist mode:UberEats email:custom@example.com` - Generate assist command
- `/fusion_order` - Generate order command with pool email
- `/wool_order` - Generate wool command

#### Points Management  
- `/setpoints user:@someone points:50` - Set user's points
- `/checkpoints user:@someone` - Check anyone's points
- `/leaderboard limit:20` - Show top 20 users
- `/clearpoints user:@someone` - Clear specific user's points
- `/clearpoints` - Clear all points
- `/redeem user:@someone reward:Free Order` - Redeem rewards
- `/backfill` - Award points from message history

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
├── combined_bot.py        # Main bot file
├── requirements.txt       # Python dependencies
├── .env                  # Environment variables (create this)
├── README.md             # This file
├── data/                 # Auto-created databases
│   ├── pool.db           # Cards and emails
│   └── points.db         # User points
└── logs/                 # Auto-created logs
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

## Migrating from Separate Bots

### From Order Command Bot (Python)
1. **Database migration**: Copy your existing `data/pool.db` file to the new bot directory
2. **Logs migration**: Copy your `logs/` directory to preserve command history
3. **Environment variables**: Copy `BOT_TOKEN` and `OWNER_ID` from your `.env` file

### From Counter Bot (Node.js) 
1. **Points migration**: The Node.js bot used `quick.db` which stores data in `json.sqlite`. You'll need to migrate this data:
   ```python
   # Migration script (run once)
   import sqlite3
   import json
   
   # Read from quick.db format
   conn_old = sqlite3.connect('json.sqlite')  # Your old Node.js bot's DB
   cursor_old = conn_old.cursor()
   cursor_old.execute("SELECT key, value FROM json WHERE key LIKE 'points.%'")
   rows = cursor_old.fetchall()
   
   # Write to new format
   conn_new = sqlite3.connect('data/points.db')
   cursor_new = conn_new.cursor()
   for key, value in rows:
       user_id = key.replace('points.', '')
       points = json.loads(value)
       cursor_new.execute("INSERT OR REPLACE INTO points (user_id, points) VALUES (?, ?)", (user_id, points))
   
   conn_new.commit()
   conn_old.close()
   conn_new.close()
   ```
2. **Channel ID**: Set `POINTS_CHANNEL_ID` in `.env` to your existing points channel

### From Channel Opener Bot (Python)
1. **Channel ID**: Set `OPENER_CHANNEL_ID` in `.env` to your existing opener channel
2. **Role configuration**: Update `ROLE_PING_ID`, `VIP_ROLE_ID`, and `ORDER_CHANNEL_MENTION` as needed

## Configuration Options

### Required Settings
- `BOT_TOKEN` - Your Discord bot token
- `OWNER_ID` - Discord user ID for admin commands

### Optional Settings (comment out if not using)
- `POINTS_CHANNEL_ID` - Channel where images earn points
- `OPENER_CHANNEL_ID` - Channel where open/close commands work
- `ROLE_PING_ID` - Role to ping when opening (default: 1352022044614590494)
- `VIP_ROLE_ID` - Role assigned with "Perm Fee" redemption (default: 1371247728646033550)
- `ORDER_CHANNEL_MENTION` - Channel mention in open announcement (default: <#1350935337269985334>)

### Card/Email Pool Constants
The following are hardcoded in the bot but can be modified in the source:
- `EXP_MONTH = '06'` - Credit card expiration month
- `EXP_YEAR = '30'` - Credit card expiration year  
- `ZIP_CODE = '19104'` - ZIP code for orders

## Troubleshooting

### Common Issues

**"Card pool is empty" or "Email pool is empty"**
- Use `/add_card` and `/add_email` commands or bulk upload files
- Check that your databases were properly migrated

**"Could not find order embed"**
- Ensure the ticket bot's first message contains at least 2 embeds
- The bot looks for the second embed in the first message of the channel

**Points not being awarded**
- Verify `POINTS_CHANNEL_ID` is set correctly
- Check that the bot has permissions to read messages and send replies in that channel
- Ensure images have proper MIME types (image/*)

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
  - Manage Roles (for VIP role assignment)

### Database Issues

**Corrupted pool.db**
- The bot automatically detects and recreates corrupted SQLite files
- Your data will be lost if this happens - keep backups of working databases

**Points not persisting**
- Check that `data/` directory has write permissions
- Ensure `data/points.db` is being created and is writable

### Logging Issues

**No log files created**
- Logs are only created when order commands are used
- Check that `logs/` directory has write permissions
- Use `/log_stats` to verify logging is working

**Log commands showing no data**
- Logs are organized by month (YYYYMM format)
- Use `/log_stats month:202405` for specific months
- JSON files must be valid - corruption will cause read errors

## Security Considerations

- All command responses are ephemeral (only visible to command user)
- Only the configured `OWNER_ID` can execute admin commands
- Card numbers and emails are logged in full - secure your log files appropriately
- Database files contain sensitive payment information - implement appropriate backups and security
- Consider rotating cards/emails regularly and removing old entries

## Advanced Usage

### Custom Reward Types
To add new reward types to the `/redeem` command, modify the choices in the command definition:
```python
@app_commands.choices(reward=[
    app_commands.Choice(name='Free Order', value='Free Order'),
    app_commands.Choice(name='Perm Fee', value='Perm Fee'),
    app_commands.Choice(name='Custom Reward', value='Custom Reward'),  # Add this
])
```

### Changing Point Values
To award different point amounts, modify the points tracking section:
```python
# Change from 1 to any value
new_points = bot.add_user_points(user_id, 2)  # Awards 2 points instead of 1
```

### Custom Card Expiration
Update the constants at the top of the file:
```python
EXP_MONTH = '12'  # December
EXP_YEAR = '25'   # 2025
ZIP_CODE = '90210'  # Beverly Hills
```

## Support & Contributing

For issues, feature requests, or contributions:
1. Check the troubleshooting section above
2. Verify your configuration matches the examples
3. Test with minimal configuration first
4. Check Discord bot permissions thoroughly

The combined bot maintains all functionality from the original three bots while providing a unified interface and simplified deployment.