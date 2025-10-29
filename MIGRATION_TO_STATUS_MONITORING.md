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
