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

###