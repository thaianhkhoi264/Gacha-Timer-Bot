# Gacha Timer Bot - REST API

## What is this?

The REST API allows external programs to log Shadowverse matches programmatically without typing in Discord. Your external game tracker, mobile app, or automation script can directly add matches to the bot's database and automatically update Discord dashboards.

## Key Features

✅ **Log matches from anywhere in the world**  
✅ **Automatic dashboard updates**  
✅ **Secure API key authentication**  
✅ **No port forwarding needed** (using ngrok or Cloudflare Tunnel)  
✅ **Works with any programming language**  
✅ **Real-time synchronization**

## Architecture

```
Your Game Tracker
       ↓
   Internet (HTTPS)
       ↓
ngrok/Cloudflare Tunnel
       ↓
  Raspberry Pi
       ↓
   Bot API Server
       ↓
  Discord Bot
       ↓
  Discord Channel (Dashboard Update)
```

## Quick Start (5 minutes)

### 1. Enable the API

```bash
cd ~/Gacha-Timer-Bot
pip install aiohttp
echo "API_ENABLED=true" >> .env
sudo systemctl restart kanami-bot.service
```

### 2. Configure API Keys

Edit `api_keys.json`:
```json
{
  "my_secret_key_12345": "My Application"
}
```

### 3. Choose a Tunnel

**Option A: ngrok (easiest for testing)**
```bash
ngrok http 8080
```

**Option B: Cloudflare Tunnel (best for production)**
```bash
cloudflared tunnel create gacha-bot-api
# See API_SETUP.md for full configuration
```

### 4. Test It

```bash
# Replace with your ngrok/Cloudflare URL
curl https://your-url.com/api/health
```

### 5. Use It

```python
import requests

requests.post(
    "https://your-url.com/api/shadowverse/log_match",
    headers={"X-API-Key": "my_secret_key_12345"},
    json={
        "user_id": "YOUR_DISCORD_USER_ID",
        "server_id": "YOUR_SERVER_ID",
        "played_craft": "Dragoncraft",
        "opponent_craft": "Forestcraft",
        "win": True,
        "brick": False
    }
)
```

Check your Discord Shadowverse channel - your dashboard is now updated! 🎉

## Documentation

- **📖 [Complete Setup Guide](API_SETUP.md)** - Detailed instructions for ngrok and Cloudflare Tunnel
- **⚡ [Quick Reference](API_QUICK_REFERENCE.md)** - Command cheat sheet
- **💻 [Example Client Code](examples/api_client_example.py)** - Python example

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Check if API is running |
| `/api/validate_key` | GET | Validate your API key |
| `/api/shadowverse/log_match` | POST | Log a match |

## Security

- 🔒 **API keys required** for all requests
- 🔒 **HTTPS only** (provided by ngrok/Cloudflare)
- 🔒 **Keys stored locally** on your Pi (never transmitted)
- 🔒 **Per-application keys** (revoke individually)

## Requirements

- Python 3.8+
- `aiohttp` package
- Raspberry Pi with internet connection
- Discord bot running
- ngrok account (free) OR Cloudflare account (free)

## Support

**Common Issues:**

1. **"Invalid API key"** → Check `api_keys.json` and restart bot
2. **"User not found"** → Verify Discord IDs (enable Developer Mode)
3. **Connection timeout** → Check tunnel is running
4. **Dashboard not updating** → Verify Shadowverse channel is configured

See [API_SETUP.md](API_SETUP.md) for detailed troubleshooting.

## Examples

### Log a Win
```bash
curl -X POST https://your-url.com/api/shadowverse/log_match \
  -H "X-API-Key: your_key" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"123","server_id":"456","played_craft":"Dragoncraft","opponent_craft":"Forestcraft","win":true}'
```

### Log a Bricked Loss
```bash
curl -X POST https://your-url.com/api/shadowverse/log_match \
  -H "X-API-Key: your_key" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"123","server_id":"456","played_craft":"Swordcraft","opponent_craft":"Runecraft","win":false,"brick":true}'
```

### Python
```python
import requests

def log_match(craft, opponent, win, brick=False):
    return requests.post(
        "https://your-url.com/api/shadowverse/log_match",
        headers={"X-API-Key": "your_key"},
        json={
            "user_id": "123",
            "server_id": "456",
            "played_craft": craft,
            "opponent_craft": opponent,
            "win": win,
            "brick": brick
        }
    ).json()

# Usage
log_match("Dragoncraft", "Forestcraft", win=True)
```

### JavaScript
```javascript
async function logMatch(craft, opponent, win, brick = false) {
    const response = await fetch('https://your-url.com/api/shadowverse/log_match', {
        method: 'POST',
        headers: {
            'X-API-Key': 'your_key',
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            user_id: '123',
            server_id: '456',
            played_craft: craft,
            opponent_craft: opponent,
            win: win,
            brick: brick
        })
    });
    return await response.json();
}

// Usage
logMatch('Dragoncraft', 'Forestcraft', true);
```

## Files Added/Modified

**New Files:**
- `api_server.py` - REST API server implementation
- `examples/api_client_example.py` - Example Python client
- `API_SETUP.md` - Complete setup documentation
- `API_QUICK_REFERENCE.md` - Command cheat sheet
- `api_keys.json` - API key storage (auto-generated)

**Modified Files:**
- `main.py` - Added API server startup on bot ready
- `requirements.txt` - Added `aiohttp` dependency
- `.gitignore` - Added `api_keys.json` to prevent leaking secrets

## Why Use This?

### Before (Manual)
1. Play a match in Shadowverse
2. Alt-tab to Discord
3. Type: `Dragon Forest Win`
4. Go back to game

### After (Automated)
1. Play a match in Shadowverse
2. Your game tracker automatically logs it
3. Dashboard updates instantly
4. Keep playing! 🎮

## Comparison: ngrok vs Cloudflare Tunnel

| Feature | ngrok (Free) | Cloudflare Tunnel |
|---------|--------------|-------------------|
| **Setup Time** | 5 minutes | 15 minutes |
| **URL Stability** | Changes on restart | Static forever |
| **Session Limit** | 8 hours | Unlimited |
| **Cost** | Free | Free |
| **Best For** | Testing | Production |

## Getting Started Checklist

- [ ] Install `aiohttp`
- [ ] Create `api_keys.json` with secure keys
- [ ] Enable API in `.env`
- [ ] Restart bot
- [ ] Verify API started (check logs)
- [ ] Install ngrok or cloudflared
- [ ] Start tunnel
- [ ] Test health endpoint
- [ ] Test validate key endpoint
- [ ] Test log match endpoint
- [ ] Verify dashboard updated in Discord
- [ ] Integrate into your external program

## Next Steps

1. Read [API_SETUP.md](API_SETUP.md) for detailed setup instructions
2. Choose between ngrok (quick) or Cloudflare Tunnel (production)
3. Test with the example client in `examples/api_client_example.py`
4. Build your integration!

---

**Questions?** Check [API_SETUP.md](API_SETUP.md) for troubleshooting and detailed documentation.

**Security Concern?** API keys never leave your Pi and all traffic is encrypted with HTTPS.

**Need Help?** All setup steps are documented with copy-paste commands in API_SETUP.md.
