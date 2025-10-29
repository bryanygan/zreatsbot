# Status Monitoring Setup Guide

## Quick Start

This guide will help you set up the status monitoring system for your Discord bot. Follow these steps in order.

## Step 1: Install Dependencies

```bash
cd C:\Users\prinp\Documents\GitHub\combinedbot
pip install -r requirements.txt
```

This will install:
- flask (HTTP server)
- flask-cors (Cross-Origin Resource Sharing)
- psutil (System metrics)
- gunicorn (Production server, for deployment)

## Step 2: Configure Environment Variables

Add these lines to your `.env` file (copy from `.env.example` if needed):

```env
# Status Monitoring
STATUS_API_PORT=5000
STATUS_API_HOST=0.0.0.0
STATUS_API_KEY=your-secure-api-key-here-change-this
CORS_ORIGINS=http://localhost:4321,https://yourportfolio.com
```

**Generate a secure API key:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output and replace `your-secure-api-key-here-change-this` with it.

**Update CORS_ORIGINS:**
- For local development: `http://localhost:4321` (Astro dev server)
- For production: Add your deployed portfolio URL (e.g., `https://yourname.com`)
- You can have multiple origins separated by commas

## Step 3: Test Locally

### Start the Bot

```bash
python combinedbot.py
```

You should see output like:
```
🚀 Starting Discord bot...
📊 Pool Status:
   Cards: X
   main emails: Y
   fusion emails: Z
   wool emails: W
[Status Server] Starting on 0.0.0.0:5000
[Status Server] Started in background thread
📡 Status monitoring API started
🤖 BotName#1234 has connected to Discord (invisible)
✅ Synced X command(s)
```

### Test the API

Open a new terminal and test the endpoints:

```bash
# Health check
curl http://localhost:5000/health

# Get status
curl http://localhost:5000/status

# Get pool counts
curl http://localhost:5000/pools

# Get logs
curl http://localhost:5000/logs?limit=10
```

Expected responses should be JSON data.

### Test Restart (Optional)

```bash
curl -X POST http://localhost:5000/restart \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY_HERE" \
  -d '{"reason": "Testing restart"}'
```

Replace `YOUR_API_KEY_HERE` with your actual API key from `.env`.

## Step 4: Set Up Portfolio Status Page

### Start Portfolio Dev Server

```bash
cd C:\Users\prinp\Documents\GitHub\portfolio
npm run dev
```

### Access the Status Page

Open your browser to: http://localhost:4321/bot-status

### Configure the Page

1. Enter your Bot API URL: `http://localhost:5000`
2. Enter your API Key (from `.env` file)
3. Click "Save Configuration"

The page should now display:
- ✅ Bot uptime
- ✅ Last command executed
- ✅ Pool counts (cards, emails)
- ✅ System metrics (CPU, memory)
- ✅ Recent logs

### Test Real-Time Updates

- The page automatically refreshes every 10 seconds
- Run a command in your Discord bot
- Watch the "Last Command" section update
- Check the logs section for the new entry

### Test Restart Function

1. Click the "Restart Bot" button
2. Confirm the restart
3. Watch the real-time restart progress
4. The bot should restart and reconnect automatically

## Step 5: Deploy to Production

See `MIGRATION_TO_STATUS_MONITORING.md` for deployment options:

- **Railway** (recommended, easiest)
- **Fly.io** (good for scale)
- **VPS** (full control)
- **Local with PM2** (use your own hardware)

### Deploy Bot

Choose your platform and follow the guide. Key points:

1. Set all environment variables in your platform's dashboard
2. Ensure the `STATUS_API_PORT` is exposed
3. Update `CORS_ORIGINS` with your deployed portfolio URL

### Deploy Portfolio

If using Astro with Cloudflare (already configured):

```bash
cd C:\Users\prinp\Documents\GitHub\portfolio
npm run build
# Deploy via your CI/CD or manual upload
```

Update the bot status page configuration:
- API URL: Your deployed bot URL (e.g., `https://your-bot.railway.app`)
- API Key: Same key from your production `.env`

## Troubleshooting

### Bot won't start

**Error:** `ModuleNotFoundError: No module named 'flask'`
**Solution:** Run `pip install -r requirements.txt`

### Status API not accessible

**Error:** Connection refused on port 5000
**Solution:**
- Check if port 5000 is already in use
- Try changing `STATUS_API_PORT` to another port (e.g., 5001)
- Check Windows Firewall settings

### CORS errors in browser

**Error:** `Access to fetch at 'http://localhost:5000/status' from origin 'http://localhost:4321' has been blocked by CORS policy`
**Solution:**
- Ensure `CORS_ORIGINS` in `.env` includes `http://localhost:4321`
- Restart the bot after changing `.env`

### Status page shows "no data"

**Check:**
1. Is the bot running? (Check terminal)
2. Is the API URL correct? (Should be `http://localhost:5000` for local)
3. Open browser DevTools (F12) → Network tab → Check for errors
4. Test API directly with `curl http://localhost:5000/status`

### Restart doesn't work

**Error:** "Unauthorized" or "Invalid API key"
**Solution:**
- Verify the API key matches exactly between `.env` and the status page
- No extra spaces or quotes
- Try regenerating a new key

### Real-time updates not working

**SSE Connection Failed:**
- Check browser console for errors
- Some corporate firewalls block SSE
- Try refreshing the page
- Check if the `/stream` endpoint works: Open `http://localhost:5000/stream` in a new browser tab

## Security Checklist

Before deploying to production:

- [ ] Generated a strong random API key
- [ ] Set `CORS_ORIGINS` to only your domain (remove localhost)
- [ ] Enabled HTTPS for your bot API (via reverse proxy or platform)
- [ ] Don't commit `.env` to Git (it's in `.gitignore`)
- [ ] Consider IP whitelisting for the status API
- [ ] Use environment variables in production (not `.env` file)

## Features Overview

### Available API Endpoints

- `GET /health` - Health check (no auth)
- `GET /status` - Full bot status (no auth for GET)
- `GET /pools` - Pool counts (no auth for GET)
- `GET /logs?limit=N` - Recent logs (no auth for GET)
- `GET /logs?limit=N&full=true` - Full logs with details
- `GET /last-command` - Last command executed
- `POST /restart` - Restart bot (requires API key)
- `GET /stream` - SSE stream for real-time updates

### Status Page Features

- ✅ Real-time uptime tracking
- ✅ Last command display
- ✅ Pool status (cards + emails by pool type)
- ✅ System metrics (CPU, memory, threads)
- ✅ Recent logs viewer
- ✅ Remote restart with live progress
- ✅ Auto-refresh every 10 seconds
- ✅ Server-Sent Events for instant updates
- ✅ Dark mode support
- ✅ Mobile responsive

## Next Steps

1. Test everything locally following this guide
2. Choose a deployment platform from the migration guide
3. Deploy your bot to production
4. Update your portfolio with the production API URL
5. Set up monitoring alerts (optional)
6. Configure automated backups for `data/pool.db`

## Support

If you encounter issues:
1. Check the bot's console output for errors
2. Check browser DevTools console
3. Review `MIGRATION_TO_STATUS_MONITORING.md` for deployment help
4. Verify all environment variables are set correctly

## Architecture Diagram

```
┌─────────────────┐
│  Discord Bot    │ ← Your main bot (combinedbot.py)
│  (Python)       │
└────────┬────────┘
         │
         ├─ Tracks state (bot_monitor.py)
         ├─ Logs commands (logging_utils.py)
         ├─ Handles restarts (restart_handler.py)
         │
┌────────▼────────┐
│  Flask API      │ ← HTTP server (status_server.py)
│  :5000          │    Endpoints: /status, /logs, /pools, /restart
└────────┬────────┘
         │
         │ HTTP/SSE
         │
┌────────▼────────┐
│  Status Page    │ ← Your portfolio site
│  /bot-status    │    http://localhost:4321/bot-status
│  (Astro)        │
└─────────────────┘
```

## Files Created/Modified

### New Files (Bot):
- `bot_monitor.py` - State tracking and metrics
- `status_server.py` - Flask API server
- `restart_handler.py` - Safe restart mechanism
- `MIGRATION_TO_STATUS_MONITORING.md` - Deployment guide
- `SETUP_STATUS_MONITORING.md` - This file

### Modified Files (Bot):
- `combinedbot.py` - Integrated status server
- `logging_utils.py` - Added monitor tracking
- `requirements.txt` - Added dependencies
- `.env.example` - Added status monitoring vars

### New Files (Portfolio):
- `src/pages/bot-status.astro` - Status monitoring page

Enjoy your new status monitoring system!
