# Migration Guide: Adding Status Monitoring & 24/7 Uptime

This guide outlines the changes needed to migrate your Discord bot from terminal-based execution to a production environment with status monitoring and remote restart capabilities.

## Overview

The status monitoring system adds:
- **HTTP API Server** running alongside your Discord bot
- **Status webpage** in your portfolio site
- **Real-time updates** during bot operations and restarts
- **Remote restart** capability
- **24/7 uptime** with automatic recovery

## Architecture

```
┌─────────────────────┐
│   Discord Bot       │
│   (combinedbot.py)  │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│   Status API Server │
│   (Flask/FastAPI)   │
│                     │
│   Endpoints:        │
│   - GET /status     │
│   - GET /logs       │
│   - GET /pools      │
│   - POST /restart   │
│   - GET /stream     │
└──────────┬──────────┘
           │
           │ HTTPS
           │
┌──────────▼──────────┐
│  Portfolio Website  │
│  /bot-status page   │
│                     │
│  Displays:          │
│  - Uptime           │
│  - Last command     │
│  - Logs             │
│  - Pool counts      │
│  - Restart button   │
└─────────────────────┘
```

## Changes Required in Bot Project

### 1. New Dependencies

Add to `requirements.txt`:
```
flask==3.1.0
flask-cors==5.0.0
psutil==6.1.0
gunicorn==23.0.0
```

Install with: `pip install -r requirements.txt`

### 2. New Files to Create

- `status_server.py` - HTTP API server for status monitoring
- `bot_monitor.py` - Bot state tracking and metrics
- `restart_handler.py` - Safe restart mechanism with event streaming

### 3. Environment Variables to Add

Add to `.env`:
```
# Status Monitoring
STATUS_API_PORT=5000
STATUS_API_HOST=0.0.0.0
STATUS_API_KEY=your-secure-api-key-here-change-this
CORS_ORIGINS=https://yourportfolio.com,http://localhost:4321
```

### 4. Code Integration

The bot's main file (`combinedbot.py`) will be modified to:
- Start the status server in a separate thread
- Track uptime and last command executed
- Expose metrics to the status server

## Deployment Options

### Option A: Railway (Recommended - Easiest)

**Pros:**
- Free tier available (500 hours/month)
- GitHub integration (auto-deploy on push)
- Persistent volumes for database
- Built-in logging and monitoring
- HTTPS automatically

**Setup:**
1. Create account at [railway.app](https://railway.app)
2. Connect your GitHub repository
3. Add environment variables in Railway dashboard
4. Deploy!

**Railway Config File** (`railway.json`):
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python combinedbot.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### Option B: Fly.io (Good for Scale)

**Pros:**
- Generous free tier (3 shared CPUs, 256MB RAM)
- Global edge deployment
- Persistent volumes
- Good for low-latency worldwide

**Setup:**
1. Install Fly CLI: `powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"`
2. `fly auth signup` or `fly auth login`
3. `fly launch` in your bot directory
4. Configure persistent volume for database

**Fly Config** (`fly.toml` - auto-generated, modify as needed)

### Option C: Local Server with PM2

**Pros:**
- Complete control
- No cost
- Use your own hardware

**Cons:**
- Need to keep PC running 24/7
- No built-in HTTPS (need ngrok or Cloudflare Tunnel)
- Manual updates

**Setup:**
1. Install Node.js (for PM2): https://nodejs.org
2. Install PM2: `npm install -g pm2 pm2-windows-startup`
3. Configure PM2 startup: `pm2-startup install`
4. Create `ecosystem.config.js`:

```javascript
module.exports = {
  apps: [{
    name: 'combinedbot',
    script: 'combinedbot.py',
    interpreter: 'python',
    cwd: 'C:\\Users\\prinp\\Documents\\GitHub\\combinedbot',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '500M',
    env: {
      NODE_ENV: 'production'
    },
    error_file: 'logs/pm2-error.log',
    out_file: 'logs/pm2-out.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
  }]
};
```

5. Start: `pm2 start ecosystem.config.js`
6. Save: `pm2 save`
7. Setup startup: `pm2 startup`

**Expose to Internet:**
- Use **ngrok** (easiest): `ngrok http 5000`
- Or **Cloudflare Tunnel** (free, permanent URL)

### Option D: VPS (DigitalOcean, Linode, etc.)

**Pros:**
- Full Linux environment
- Root access
- Predictable pricing ($5-10/month)

**Setup:**
1. Create Ubuntu/Debian VPS
2. SSH into server
3. Install Python 3.10+
4. Clone repository
5. Setup systemd service (see below)

**Systemd Service** (`/etc/systemd/system/combinedbot.service`):
```ini
[Unit]
Description=Combined Discord Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/combinedbot
Environment="PATH=/home/your-username/combinedbot/venv/bin"
ExecStart=/home/your-username/combinedbot/venv/bin/python combinedbot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable: `sudo systemctl enable combinedbot && sudo systemctl start combinedbot`

## Database Considerations

Your SQLite database (`data/pool.db`) needs to persist across restarts:

### Railway/Fly.io
- Mount a persistent volume to `/data` directory
- Ensure database path points to volume

### PM2 (Local)
- No changes needed (already persistent)

### VPS
- Keep database in project directory (already persistent)

## Security Considerations

1. **API Key**: Generate a strong random key for `STATUS_API_KEY`
   - Use: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

2. **CORS**: Restrict `CORS_ORIGINS` to your portfolio domain only

3. **Firewall**: Only expose the status API port (5000) if needed externally

4. **HTTPS**: Use a reverse proxy (nginx/Caddy) or platform's built-in HTTPS

5. **Rate Limiting**: The status API includes built-in rate limiting

## Testing the Setup

1. Start bot locally: `python combinedbot.py`
2. Verify Discord bot connects
3. Test status API: `curl http://localhost:5000/status`
4. Check logs endpoint: `curl http://localhost:5000/logs?limit=10`
5. Test restart (with caution): `curl -X POST http://localhost:5000/restart -H "X-API-Key: your-key"`

## Monitoring & Logs

### Railway
- Built-in log viewer in dashboard
- Export to external services (Datadog, etc.)

### PM2
- View logs: `pm2 logs combinedbot`
- Monitor: `pm2 monit`
- Web dashboard: `pm2 install pm2-server-monit`

### Systemd
- View logs: `journalctl -u combinedbot -f`
- Status: `systemctl status combinedbot`

## Rollback Plan

If something goes wrong:

1. **Stop new system**: Kill the process or stop the service
2. **Restore old method**: Run `python combinedbot.py` in terminal
3. **Check database**: Ensure `data/pool.db` is intact
4. **Review logs**: Check what went wrong in error logs

## Next Steps After Migration

1. ✅ Implement status_server.py (see new files created)
2. ✅ Modify combinedbot.py to start status server
3. ✅ Deploy to chosen platform (Railway recommended)
4. ✅ Update portfolio website with bot-status page
5. ✅ Set up monitoring alerts (optional)
6. ✅ Configure backup system for database (recommended)

## Estimated Timeline

- **Code changes**: 1-2 hours
- **Testing locally**: 30 minutes
- **Deployment setup**: 30 minutes - 1 hour
- **Portfolio integration**: 1 hour
- **Total**: 3-4 hours

## Support & Troubleshooting

Common issues:

1. **Port already in use**: Change `STATUS_API_PORT` in `.env`
2. **Bot won't start**: Check Discord token is valid
3. **API not accessible**: Check firewall settings
4. **Database locked**: Ensure only one bot instance is running

## Recommended Choice

**For your use case, I recommend Railway:**
- Easiest setup (< 30 minutes)
- Free tier is sufficient
- Automatic HTTPS
- GitHub integration
- Built-in monitoring
- No need to keep your PC running

The implementation is ready to deploy once you've created the new files (status_server.py, bot_monitor.py, restart_handler.py) which will be generated next.

---

# Railway Deployment Tutorial - Step by Step

This section provides a complete step-by-step guide for deploying your Discord bot backend to Railway.

## Prerequisites Checklist
- [x] GitHub account with your bot repository pushed
- [x] Discord bot token (BOT_TOKEN)
- [ ] All local changes committed to Git
- [x] Status monitoring files created (status_server.py, bot_monitor.py, restart_handler.py)
- [x] railway.json configuration file created
- [x] db.py updated to support environment variable for DB path
- [x] .env.example created for documentation

## Step 1: Create Railway Account
**Status:** ⏳ Pending

1. Go to https://railway.app
2. Click "Login with GitHub"
3. Authorize Railway to access your GitHub account
4. Select the repository access (you can grant access to specific repos)

## Step 2: Create a New Project
**Status:** ⏳ Pending

1. From Railway dashboard, click "New Project"
2. Select "Deploy from GitHub repo"
3. Choose your repository: `combinedbot` (or your repo name)
4. Railway will automatically detect Python and start analyzing

**Note:** Railway now uses **Railpack** as the default builder (Nixpacks is deprecated). Railpack will:
- Auto-detect Python from your `requirements.txt`
- Install all dependencies automatically
- Use the start command from your `Procfile` or `railway.json`

## Step 3: Configure Build Settings
**Status:** ⏳ Pending

Railway will automatically detect Python and use **Railpack** (their new default builder). You have two configuration options:

### Option A: Use Procfile (Recommended - Simplest)

A `Procfile` has been created in your repo:
```
web: python combinedbot.py
```

**Important:** Use `web:` not `worker:` because:
- `web:` - Railway routes HTTP traffic to this process (required for status API)
- `worker:` - Background process, no HTTP routing (won't work for our API)

Even though this is a Discord bot, we need `web:` so Railway's load balancer routes requests to the status API.

### Option B: Use railway.json (Alternative)

A `railway.json` file has been created with:
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "deploy": {
    "startCommand": "python combinedbot.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**Note:** We don't specify a builder - Railway will automatically use **Railpack** (the new default, replacing deprecated Nixpacks). Dependencies are installed automatically from `requirements.txt`.

### Option C: Manual Dashboard Configuration

If you get errors about build/start commands:

1. In Railway dashboard, go to your service
2. Click "Settings" tab
3. Scroll to "Deploy" section
4. **Clear any Build Command** (leave it empty)
5. Set **Start Command** to: `python combinedbot.py`
6. **Watch Command** should be empty
7. Click "Deploy" to redeploy

### Troubleshooting: "buildCommand and startCommand cannot be the same"

If you see this error:

**Solution 1:** Delete `railway.json`, commit, and push. Use `Procfile` instead.

**Solution 2:** In Railway dashboard:
- Go to Settings → Deploy
- Manually clear the Build Command field (make it empty)
- Keep Start Command as `python combinedbot.py`
- Save and redeploy

**Solution 3:** Use only the `Procfile` method and remove `railway.json`

**After fixing, commit and push:**
```bash
git add Procfile railway.json
git commit -m "Fix Railway configuration"
git push origin main
```

Railway will auto-deploy with the new configuration.

## Step 4: Add Environment Variables
**Status:** ⏳ Pending

1. In your Railway service, go to "Variables" tab
2. Click "New Variable" and add each of these:

| Variable Name | Example Value | Description |
|---------------|---------------|-------------|
| `BOT_TOKEN` | `Your.Discord.Bot.Token` | Discord bot token |
| `OWNER_ID` | `123456789012345678` | Your Discord user ID |
| `OPENER_CHANNEL_ID` | `987654321098765432` | Channel for open/close commands |
| `ROLE_PING_ID` | `1352022044614590494` | Role to ping for orders |
| `ORDER_CHANNEL_MENTION` | `<#1350935337269985334>` | Order channel mention |
| `STATUS_API_HOST` | `0.0.0.0` | Host (must be 0.0.0.0 for Railway) |
| `STATUS_API_KEY` | Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"` | API key for status endpoints |
| `CORS_ORIGINS` | `https://yourportfolio.com,http://localhost:4321` | Allowed origins for CORS |
| `DB_PATH` | `/app/data/pool.db` | Database path on Railway volume |

**Important Notes:**
- Click "Add" after each variable. They'll be available on next deployment.
- **DO NOT** set `PORT` or `STATUS_API_PORT` - Railway automatically sets `PORT` and the bot will use it
- **DO NOT** set a custom port in Railway's Networking settings - Railway handles this automatically

## Step 5: Configure Persistent Storage (Database)
**Status:** ✅ Complete

Your SQLite database needs to persist across deployments.

1. In your Railway service, click "New" → "Volume"
2. Configure the volume:
   - **Mount Path**: `/app/data`
   - **Size**: 1 GB (more than enough for SQLite)
3. Click "Add Volume"

**✅ Database Path Updated:** All files have been updated to support environment variable:
- `db.py` - Main database module
- `combinedbot.py` - Bot entry point
- `add_to_pool.py` - Pool management script
- `bot/commands/admin.py` - Admin commands
- `bot/commands/order.py` - Order commands

The code now uses: `DB_PATH = os.getenv('DB_PATH', 'default/local/path')`

Then set environment variable `DB_PATH=/app/data/pool.db` in Railway.

## Step 6: Get Your Railway URL
**Status:** ✅ Complete (In Progress)

1. Go to "Settings" tab in your Railway service
2. Under "Networking" section, click "Generate Domain"
3. Railway will provide a public URL like: `your-project.up.railway.app`
4. **Copy this URL** - you'll need it for your portfolio site

**Note:** This is your status API endpoint. The full status URL will be:
```
https://your-project.up.railway.app/status
```

**Important:** Make sure the domain is generated and the service shows as "Active" with a green indicator.

## Step 7: Deploy
**Status:** ⏳ Pending

1. Railway automatically deploys when you push to your GitHub repo
2. To manually trigger deployment:
   - Click "Deployments" tab
   - Click "Deploy" button
3. Watch the build logs in real-time
4. Wait for "Success" status

### Troubleshooting Common Deployment Issues

**Build fails with "No module found":**
- Ensure `requirements.txt` is in repo root
- Verify all dependencies are listed
- Check Python version compatibility

**Bot doesn't start:**
- Check environment variables are set correctly
- View logs in Railway dashboard
- Ensure BOT_TOKEN is valid

**Database errors:**
- Verify volume is mounted to `/app/data`
- Check DB_PATH environment variable
- Ensure database initialization runs on first start

## Step 7.5: Migrate Local Database to Railway
**Status:** ⏳ Pending

After your first deployment succeeds, you'll want to migrate your existing local database (cards and emails) to Railway.

### Option A: Using Railway CLI (Recommended - Fastest)

1. **Install Railway CLI:**
   ```bash
   npm install -g @railway/cli
   ```

2. **Login to Railway:**
   ```bash
   railway login
   ```

3. **Link to your project:**
   ```bash
   cd C:\Users\prinp\Documents\GitHub\combinedbot
   railway link
   ```
   Select your project from the list.

4. **Check your local database has data:**
   ```bash
   # Windows PowerShell
   Get-Item .\data\pool.db | Select-Object Name, Length
   ```

5. **Upload database to Railway volume:**
   ```bash
   railway run --service combinedbot "mkdir -p /app/data"
   railway run --service combinedbot "cat > /app/data/pool.db" < .\data\pool.db
   ```

6. **Verify upload (optional):**
   ```bash
   railway run --service combinedbot "ls -lh /app/data/pool.db"
   ```

7. **Restart the bot to use new database:**
   - In Railway dashboard, go to your service
   - Click "..." menu → "Restart"

### Option B: Export and Re-import Data (If CLI doesn't work)

1. **Export your local data to CSV:**

   Create a file `export_database.py`:
   ```python
   import sqlite3
   import csv
   from pathlib import Path

   DB_PATH = Path(__file__).parent / 'data' / 'pool.db'

   conn = sqlite3.connect(DB_PATH)
   cursor = conn.cursor()

   # Export cards
   cursor.execute('SELECT number, cvv FROM cards')
   cards = cursor.fetchall()
   with open('cards_backup.csv', 'w', newline='') as f:
       writer = csv.writer(f)
       writer.writerow(['number', 'cvv'])
       writer.writerows(cards)

   # Export emails with pools
   cursor.execute('SELECT email, pool_type FROM emails')
   emails = cursor.fetchall()
   with open('emails_backup.csv', 'w', newline='') as f:
       writer = csv.writer(f)
       writer.writerow(['email', 'pool_type'])
       writer.writerows(emails)

   conn.close()
   print(f"✅ Exported {len(cards)} cards to cards_backup.csv")
   print(f"✅ Exported {len(emails)} emails to emails_backup.csv")
   ```

   Run it:
   ```bash
   python export_database.py
   ```

2. **After Railway deployment, use Discord commands to re-add data:**

   You can use the bulk upload commands via Discord:
   - `/bulk_add_cards` - Upload `cards_backup.csv`
   - `/bulk_add_emails` - Upload `emails_backup.csv`

### Option C: Use Railway Shell (Advanced)

1. **Open Railway dashboard → your service**

2. **Click "Shell" tab** (if available in your plan)

3. **Check if database directory exists:**
   ```bash
   ls -la /app/data
   ```

4. **You can then use `scp` or upload via a temporary endpoint**

### Verification After Migration

After migrating, verify your data in Railway:

1. **Check pool counts via Discord:**
   - Run `/pool_status` command in Discord
   - Should show your cards and emails

2. **Or check via status API:**
   ```bash
   curl https://your-project.up.railway.app/pools
   ```

3. **Expected output:**
   ```json
   {
     "success": true,
     "pools": {
       "cards": 50,
       "emails": {
         "main": 100,
         "fusion": 25,
         "wool": 10
       }
     }
   }
   ```

### Important Notes

- **Backup first:** Always keep a local backup of `data/pool.db`
- **Empty database:** Railway starts with an empty database (initialized tables, no data)
- **No downtime:** Your bot will work fine with an empty database initially
- **Test first:** You can deploy and test without migrating data, then migrate later
- **One-time process:** You only need to do this once

### What if something goes wrong?

If the migration fails:
1. Your local database is unchanged
2. Railway's database is just empty (not corrupted)
3. You can retry the migration process
4. Or manually re-add data using Discord commands

## Step 8: Verify Deployment
**Status:** ⏳ Pending

Test your deployed bot:

1. **Check Discord Connection:**
   - Open Discord
   - Verify bot is online (or invisible if configured)
   - Test a command like `/pool_status`

2. **Test Status API:**
   ```bash
   curl https://your-project.up.railway.app/status
   ```
   Should return:
   ```json
   {
     "status": "online",
     "uptime": 123.45,
     "last_command": "pool_status",
     ...
   }
   ```

3. **Check Logs:**
   - In Railway dashboard, go to "Deployments"
   - Click on the active deployment
   - View logs to ensure no errors

## Step 9: Set Up GitHub Auto-Deploy
**Status:** ⏳ Pending

Railway automatically deploys on push, but you can configure it:

1. Go to "Settings" tab
2. Under "GitHub Integration":
   - **Branch**: Set to `main` or your deployment branch
   - **Auto-deploy**: Toggle ON
3. Now every push to your branch auto-deploys to Railway

**Recommended workflow:**
```bash
# Make changes locally
git add .
git commit -m "Update bot feature"
git push origin main

# Railway automatically deploys (30-60 seconds later)
```

## Step 10: Update Portfolio to Use Railway Backend
**Status:** ⏳ Pending

Update your portfolio's bot status page to fetch from Railway:

1. Find your status page (likely in `src/pages/bot-status.astro`)
2. Update the API endpoint:
   ```javascript
   const API_URL = 'https://your-project.up.railway.app';

   // Fetch status
   const response = await fetch(`${API_URL}/status`);
   ```

3. Update CORS environment variable in Railway:
   ```
   CORS_ORIGINS=https://yourportfolio.com
   ```

4. Deploy portfolio and test

## Step 11: Set Up Monitoring & Alerts (Optional)
**Status:** ⏳ Pending

Railway provides built-in monitoring:

1. In Railway dashboard, click "Observability"
2. View metrics:
   - CPU usage
   - Memory usage
   - Network traffic
   - Deployment history

**Optional: Set up external monitoring**
- Use UptimeRobot or similar to ping your `/status` endpoint
- Get alerts if bot goes down
- Free tier available at https://uptimerobot.com

## Step 12: Database Backup Strategy
**Status:** ⏳ Pending

Since Railway volumes persist, set up periodic backups:

**Option 1: Manual Backup**
1. Install Railway CLI: `npm install -g @railway/cli`
2. Login: `railway login`
3. Connect to project: `railway link`
4. Download database:
   ```bash
   railway run cat /app/data/pool.db > backup_$(date +%Y%m%d).db
   ```

**Option 2: Automated Backup (Advanced)**
- Add a scheduled task to your bot that exports database to cloud storage
- Use AWS S3, Google Cloud Storage, or Dropbox API
- Schedule with `apscheduler` in Python

## Cost Estimation

Railway pricing (as of 2024):
- **Free Trial**: $5 credit (enough for testing)
- **Hobby Plan**: $5/month for 500 hours
- **Your bot usage**: ~730 hours/month (24/7)
  - Cost: ~$7-10/month
  - Includes: 8GB RAM, 8 vCPU, 100GB network

**Optimization to stay under $10/month:**
- Use minimal resources (bot doesn't need much)
- Monitor usage in Railway dashboard
- Scale down if needed

## Deployment Checklist

Before going live, verify:

- [ ] All environment variables set in Railway
- [ ] Persistent volume configured and mounted (mount path: `/app/data`)
- [ ] `DB_PATH=/app/data/pool.db` environment variable set
- [ ] Bot connects to Discord successfully
- [ ] Status API responds to requests
- [ ] **Database migrated from local** (use `export_database.py` or Railway CLI)
- [ ] Verify pool counts match local database
- [ ] Database persists across restarts
- [ ] CORS configured for portfolio domain
- [ ] Auto-deploy enabled for GitHub pushes
- [ ] Logs show no errors
- [ ] Portfolio site fetches status correctly
- [ ] Restart endpoint works (test with caution)

## Next Steps After Successful Deployment

1. Monitor bot for 24 hours to ensure stability
2. Test all Discord commands
3. Verify database operations (add/remove cards, emails)
4. Check status page on portfolio updates in real-time
5. Test remote restart functionality
6. Set up UptimeRobot monitoring
7. Document any issues encountered

## Rolling Back a Deployment

If a deployment breaks something:

1. In Railway dashboard, go to "Deployments"
2. Find the last working deployment
3. Click "..." menu → "Redeploy"
4. Railway restores that version

Alternatively, revert in Git:
```bash
git revert HEAD
git push origin main
# Railway auto-deploys the reverted version
```

## Success Criteria

Your deployment is successful when:
- ✅ Bot shows online in Discord
- ✅ All slash commands work
- ✅ Status API returns correct data
- ✅ Portfolio site displays real-time status
- ✅ Database persists across restarts
- ✅ Bot runs for 24+ hours without issues
- ✅ Remote restart works
- ✅ Logs are accessible in Railway dashboard

---

**Current Status:** Ready to begin deployment
**Estimated Time:** 30-45 minutes for first-time setup
**Support:** Railway has great documentation at https://docs.railway.app
