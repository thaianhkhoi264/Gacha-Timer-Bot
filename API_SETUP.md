# API Server Setup Guide

This guide explains how to enable and use the REST API for the Gacha Timer Bot, allowing external programs to log Shadowverse matches programmatically.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Bot Setup](#bot-setup)
4. [Exposing the API (ngrok)](#exposing-the-api-ngrok)
5. [Exposing the API (Cloudflare Tunnel)](#exposing-the-api-cloudflare-tunnel)
6. [Using the API](#using-the-api)
7. [Security Best Practices](#security-best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The API server allows external programs to:
- Log Shadowverse matches to the bot's database
- Automatically update Discord dashboards
- Work from anywhere in the world (not just your local network)

**Architecture:**
```
External Program → Internet → ngrok/Cloudflare Tunnel → Your Raspberry Pi → Bot API → Discord
```

---

## Prerequisites

Before starting, ensure you have:

1. **Bot running on Raspberry Pi**
   - Python 3.8 or higher
   - Discord bot properly configured
   - Shadowverse module set up with `Kanami shadowverse` command

2. **Required Python packages:**
   ```bash
   pip install aiohttp
   ```

3. **Discord Developer Mode enabled** (to get IDs):
   - Discord Settings → Advanced → Enable Developer Mode
   - Right-click users/servers to copy IDs

---

## Bot Setup

### Step 1: Install Required Package

On your Raspberry Pi, install aiohttp:

```bash
cd ~/Gacha-Timer-Bot  # Or wherever your bot is located
source venv/bin/activate  # If using virtual environment
pip install aiohttp
```

### Step 2: Configure API Keys

The bot uses `api_keys.json` to authenticate API requests. This file is automatically created on first run.

1. **Start the bot once** to generate the default file:
   ```bash
   python main.py
   ```

2. **Edit `api_keys.json`**:
   ```bash
   nano api_keys.json
   ```

3. **Replace the default key** with your own secure keys:
   ```json
   {
     "my_secret_key_12345": "My Game Tracker App",
     "another_key_67890": "Friend's Application"
   }
   ```

   **Important:**
   - Use long, random strings for keys (like passwords)
   - Each key can have a description to remember what it's for
   - You can have multiple keys for different applications/users

4. **Save and exit** (Ctrl+X, Y, Enter in nano)

### Step 3: Enable the API Server

The API server is **enabled by default**, but you can control it with environment variables.

**Option A: Using environment variables (recommended)**

Create or edit `.env` file in your bot directory:
```bash
nano .env
```

Add these lines:
```
API_ENABLED=true
API_HOST=0.0.0.0
API_PORT=8080
```

**Option B: Set environment variables directly**

```bash
export API_ENABLED=true
export API_HOST=0.0.0.0
export API_PORT=8080
```

**Settings explanation:**
- `API_ENABLED`: Set to `true` to enable, `false` to disable
- `API_HOST`: Use `0.0.0.0` to listen on all network interfaces
- `API_PORT`: Port number (default 8080)

### Step 4: Restart the Bot

```bash
# If running manually:
python main.py

# If using systemd:
sudo systemctl restart kanami-bot.service

# Check logs to confirm API started:
journalctl -u kanami-bot.service -f
```

You should see:
```
==================================================
API Server Status: ENABLED
Listening on: http://0.0.0.0:8080
==================================================
```

### Step 5: Test Locally

From your Raspberry Pi, test the health endpoint:

```bash
curl http://localhost:8080/api/health
```

Expected response:
```json
{
  "status": "ok",
  "bot_connected": true,
  "bot_user": "YourBotName#1234"
}
```

---

## Exposing the API (ngrok)

ngrok creates a secure tunnel from the internet to your Raspberry Pi without port forwarding.

### Installation

1. **Sign up for ngrok** (free): https://ngrok.com/

2. **Install ngrok on Raspberry Pi:**
   ```bash
   # Download ngrok
   wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz
   
   # Extract
   sudo tar xvzf ngrok-v3-stable-linux-arm.tgz -C /usr/local/bin
   
   # Verify installation
   ngrok version
   ```

3. **Authenticate ngrok** (get your auth token from https://dashboard.ngrok.com/):
   ```bash
   ngrok config add-authtoken YOUR_AUTH_TOKEN_HERE
   ```

### Usage

#### Method 1: Manual (for testing)

Start ngrok in a terminal:
```bash
ngrok http 8080
```

You'll see output like:
```
Session Status                online
Account                       yourname@example.com
Version                       3.x.x
Region                        United States (us)
Forwarding                    https://abc123.ngrok.io -> http://localhost:8080
```

**Your API URL is:** `https://abc123.ngrok.io`

**Test it:**
```bash
curl https://abc123.ngrok.io/api/health
```

#### Method 2: Background Service (recommended for permanent use)

Create a systemd service for ngrok:

```bash
sudo nano /etc/systemd/system/ngrok.service
```

Paste this content:
```ini
[Unit]
Description=ngrok tunnel
After=network.target

[Service]
ExecStart=/usr/local/bin/ngrok http 8080 --log stdout
Restart=always
RestartSec=5
User=pi
Group=pi

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable ngrok.service
sudo systemctl start ngrok.service
```

**Get your ngrok URL:**
```bash
curl http://localhost:4040/api/tunnels | jq '.tunnels[0].public_url'
```

**View logs:**
```bash
journalctl -u ngrok.service -f
```

### ngrok Configuration (Optional)

For a **static subdomain** (requires paid plan), create `~/.ngrok2/ngrok.yml`:

```yaml
version: "2"
authtoken: YOUR_AUTH_TOKEN
tunnels:
  gacha-bot-api:
    proto: http
    addr: 8080
    subdomain: your-custom-name
```

Then start with:
```bash
ngrok start gacha-bot-api
```

Your URL will be: `https://your-custom-name.ngrok.io`

### ngrok Limitations (Free Tier)

- ⚠️ **URL changes on restart** (unless you have a paid plan)
- Session limit of 8 hours (reconnects automatically)
- Some features require paid plan

---

## Exposing the API (Cloudflare Tunnel)

Cloudflare Tunnel is a free alternative to ngrok with static URLs and no session limits.

### Installation

1. **Install cloudflared on Raspberry Pi:**
   ```bash
   # Download
   wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm
   
   # Make executable
   chmod +x cloudflared-linux-arm
   
   # Move to system path
   sudo mv cloudflared-linux-arm /usr/local/bin/cloudflared
   
   # Verify installation
   cloudflared --version
   ```

2. **Login to Cloudflare:**
   ```bash
   cloudflared tunnel login
   ```
   
   This opens a browser window. Login and authorize cloudflared.

### Setup

1. **Create a tunnel:**
   ```bash
   cloudflared tunnel create gacha-bot-api
   ```
   
   Note the **Tunnel ID** that appears (looks like: `12345678-1234-1234-1234-123456789abc`)

2. **Create configuration file:**
   ```bash
   mkdir -p ~/.cloudflared
   nano ~/.cloudflared/config.yml
   ```

3. **Add this configuration:**
   ```yaml
   tunnel: YOUR_TUNNEL_ID_HERE
   credentials-file: /home/pi/.cloudflared/YOUR_TUNNEL_ID_HERE.json
   
   ingress:
     - hostname: gacha-bot.yourdomain.com
       service: http://localhost:8080
     - service: http_status:404
   ```

4. **Create a DNS record** (replace with your tunnel ID and domain):
   ```bash
   cloudflared tunnel route dns gacha-bot-api gacha-bot.yourdomain.com
   ```

5. **Start the tunnel:**
   ```bash
   cloudflared tunnel run gacha-bot-api
   ```

### Running as a Service (Recommended)

1. **Install as a system service:**
   ```bash
   sudo cloudflared service install
   ```

2. **Start the service:**
   ```bash
   sudo systemctl start cloudflared
   sudo systemctl enable cloudflared
   ```

3. **Check status:**
   ```bash
   sudo systemctl status cloudflared
   ```

**Your API URL is:** `https://gacha-bot.yourdomain.com`

**Test it:**
```bash
curl https://gacha-bot.yourdomain.com/api/health
```

### Cloudflare Tunnel Advantages

- ✅ **Free forever** (no paid plan needed)
- ✅ **Static URL** (doesn't change on restart)
- ✅ **No session limits**
- ✅ **Built-in DDoS protection**
- ✅ **Better for production use**

### Cloudflare Tunnel Limitations

- Requires a domain name (can use a free subdomain from various providers)
- Slightly more complex initial setup

---

## Using the API

### API Endpoints

#### 1. Health Check
**GET** `/api/health`

Check if the API is running and the bot is connected.

**Request:**
```bash
curl https://your-api-url.com/api/health
```

**Response:**
```json
{
  "status": "ok",
  "bot_connected": true,
  "bot_user": "BotName#1234"
}
```

---

#### 2. Validate API Key
**GET** `/api/validate_key`

Test if your API key is valid.

**Request:**
```bash
curl -H "X-API-Key: your_secret_key" \
     https://your-api-url.com/api/validate_key
```

**Response (valid):**
```json
{
  "valid": true,
  "description": "My Game Tracker App"
}
```

**Response (invalid):**
```json
{
  "valid": false,
  "error": "Invalid API key."
}
```

---

#### 3. Log Match
**POST** `/api/shadowverse/log_match`

Log a Shadowverse match and update the dashboard.

**Important:** The API automatically uses the development server. You only need to provide your user_id!

**Request Headers:**
```
Content-Type: application/json
X-API-Key: your_secret_key
```

**Request Body:**
```json
{
  "user_id": "123456789012345678",
  "played_craft": "Dragoncraft",
  "opponent_craft": "Forestcraft",
  "win": true,
  "brick": false
}
```

**Parameters:**
- `user_id` (string, required): Discord user ID
- `played_craft` (string, required): One of: `Forestcraft`, `Swordcraft`, `Runecraft`, `Dragoncraft`, `Abysscraft`, `Havencraft`, `Portalcraft`
- `opponent_craft` (string, required): Same options as `played_craft`
- `win` (boolean, required): `true` for win, `false` for loss
- `brick` (boolean, optional): `true` if bricked, default `false`

**Example using curl:**
```bash
curl -X POST https://your-api-url.com/api/shadowverse/log_match \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secret_key" \
  -d '{
    "user_id": "123456789012345678",
    "played_craft": "Dragoncraft",
    "opponent_craft": "Forestcraft",
    "win": true,
    "brick": false
  }'
```

**Success Response (200):**
```json
{
  "success": true,
  "message": "Match logged successfully and dashboard updated",
  "details": {
    "user_id": "123456789012345678",
    "played_craft": "Dragoncraft",
    "opponent_craft": "Forestcraft",
    "result": "win",
    "brick": false
  }
}
```

**Error Responses:**

*Missing API Key (401):*
```json
{
  "success": false,
  "error": "Missing API key. Provide via 'X-API-Key' header or 'api_key' in body."
}
```

*Invalid Craft (400):*
```json
{
  "success": false,
  "error": "Invalid played_craft. Must be one of: Forestcraft, Swordcraft, ..."
}
```

*User Not Found (404):*
```json
{
  "success": false,
  "error": "User 123456789012345678 not found in server. Are they a member?"
}
```

---

### Example Client Code

See `examples/api_client_example.py` for a complete Python example.

**Quick Python example:**

```python
import requests

API_URL = "https://your-api-url.com"
API_KEY = "your_secret_key"
USER_ID = "123456789012345678"

def log_match(played, opponent, win, brick=False):
    response = requests.post(
        f"{API_URL}/api/shadowverse/log_match",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={
            "user_id": USER_ID,
            "played_craft": played,
            "opponent_craft": opponent,
            "win": win,
            "brick": brick
        }
    )
    return response.json()

# Log a win
result = log_match("Dragoncraft", "Forestcraft", win=True)
print(result)
```

---

## Security Best Practices

### 1. Protect Your API Keys

- **Never commit `api_keys.json` to git**
  - Add to `.gitignore`
- **Use strong, random keys**
  - Generate with: `openssl rand -hex 32`
- **Rotate keys periodically**
- **Use separate keys for different applications**

### 2. Monitor API Usage

Check logs regularly:
```bash
# Bot logs
journalctl -u kanami-bot.service -f | grep "API"

# ngrok logs
journalctl -u ngrok.service -f

# Cloudflare Tunnel logs
journalctl -u cloudflared -f
```

### 3. Rate Limiting (Optional)

For production use, consider adding rate limiting to prevent abuse. This can be done in `api_server.py` using libraries like `aiohttp-ratelimit`.

### 4. HTTPS Only

Both ngrok and Cloudflare Tunnel provide HTTPS by default. **Never use plain HTTP** for production API access.

### 5. Firewall Rules

Keep port 8080 closed to external access - only ngrok/Cloudflare Tunnel should access it locally.

```bash
# Check firewall status
sudo ufw status

# If port 8080 is open, close it:
sudo ufw deny 8080
```

---

## Troubleshooting

### Problem: API server won't start

**Check:**
1. Is port 8080 already in use?
   ```bash
   sudo lsof -i :8080
   ```
2. Is `aiohttp` installed?
   ```bash
   pip list | grep aiohttp
   ```
3. Check bot logs:
   ```bash
   journalctl -u kanami-bot.service -f
   ```

**Solution:**
- Kill conflicting process or change `API_PORT` in `.env`
- Install aiohttp: `pip install aiohttp`
- Check error messages in logs

---

### Problem: "Invalid API key" error

**Check:**
1. Is your key in `api_keys.json`?
   ```bash
   cat api_keys.json
   ```
2. Are you using the correct header or body field?

**Solution:**
- Add your key to `api_keys.json` and restart the bot
- Use `X-API-Key` header (preferred) or `api_key` in request body

---

### Problem: ngrok URL changes frequently

**Why:** Free ngrok accounts get random URLs that change on restart.

**Solutions:**
1. **Use Cloudflare Tunnel** (free static URLs)
2. **Upgrade to ngrok paid plan** (static subdomains)
3. **Use a dynamic DNS updater** to track URL changes

---

### Problem: "User not found in server"

**Check:**
1. Is the user ID correct?
   - Enable Developer Mode in Discord
   - Right-click user → Copy ID
2. Is the bot in the same server as the user?
3. Does the bot have proper permissions?

**Solution:**
- Verify IDs are correct
- Ensure bot is in the server with appropriate roles

---

### Problem: Dashboard not updating

**Check:**
1. Is Shadowverse channel configured?
   ```
   Kanami shadowverse #channel
   ```
2. Does the bot have permission to edit messages?
3. Check bot logs for errors

**Solution:**
- Set Shadowverse channel if not configured
- Grant bot "Manage Messages" permission
- Check logs: `journalctl -u kanami-bot.service -f`

---

### Problem: Connection timeout from external program

**Check:**
1. Is ngrok/Cloudflare Tunnel running?
   ```bash
   # ngrok
   curl http://localhost:4040/api/tunnels
   
   # Cloudflare
   sudo systemctl status cloudflared
   ```
2. Is the bot's API server running?
   ```bash
   curl http://localhost:8080/api/health
   ```
3. Is the URL correct in your client?

**Solution:**
- Restart tunnel service
- Restart bot
- Verify URL is correct (check ngrok dashboard or Cloudflare DNS)

---

## Getting Your Discord IDs

### User ID
1. Enable Developer Mode: Discord Settings → Advanced → Developer Mode
2. Right-click your username → Copy ID

**Note:** You only need your User ID to use the API. The server ID is automatically configured to the development server.

---

## Additional Resources

- **ngrok Documentation:** https://ngrok.com/docs
- **Cloudflare Tunnel Docs:** https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
- **Discord Developer Portal:** https://discord.com/developers/applications
- **aiohttp Documentation:** https://docs.aiohttp.org/

---

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review bot logs: `journalctl -u kanami-bot.service -f`
3. Test each component individually (local API → tunnel → external access)
4. Verify all IDs and API keys are correct

---

## Summary

**Quick Start Checklist:**

- [ ] Install `aiohttp`: `pip install aiohttp`
- [ ] Configure `api_keys.json` with secure keys
- [ ] Enable API in `.env`: `API_ENABLED=true`
- [ ] Restart bot and verify API started
- [ ] Choose tunnel solution (ngrok or Cloudflare)
- [ ] Install and configure tunnel
- [ ] Test with health check endpoint
- [ ] Validate API key
- [ ] Use example client code to log a match
- [ ] Verify dashboard updated in Discord

**Recommended Setup:**
- **Development/Testing:** ngrok (quick setup, temporary URLs)
- **Production:** Cloudflare Tunnel (free, static URLs, more reliable)

Enjoy automated match logging! 🎮
