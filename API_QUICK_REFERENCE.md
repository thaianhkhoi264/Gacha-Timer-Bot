# API Quick Reference

## Setup Commands

```bash
# Install dependencies
pip install aiohttp

# Configure API keys
nano api_keys.json

# Enable API (in .env)
API_ENABLED=true
API_HOST=0.0.0.0
API_PORT=8080

# Restart bot
sudo systemctl restart kanami-bot.service
```

## ngrok Quick Start

```bash
# Install
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz
sudo tar xvzf ngrok-v3-stable-linux-arm.tgz -C /usr/local/bin

# Authenticate
ngrok config add-authtoken YOUR_TOKEN

# Start tunnel
ngrok http 8080

# Get URL
curl http://localhost:4040/api/tunnels | jq '.tunnels[0].public_url'
```

## Cloudflare Tunnel Quick Start

```bash
# Install
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm
chmod +x cloudflared-linux-arm
sudo mv cloudflared-linux-arm /usr/local/bin/cloudflared

# Login
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create gacha-bot-api

# Configure (edit ~/.cloudflared/config.yml)
# See API_SETUP.md for details

# Create DNS
cloudflared tunnel route dns gacha-bot-api gacha-bot.yourdomain.com

# Start tunnel
cloudflared tunnel run gacha-bot-api
```

## API Endpoints

### Health Check
```bash
curl https://your-url.com/api/health
```

### Validate Key
```bash
curl -H "X-API-Key: your_key" https://your-url.com/api/validate_key
```

### Log Match
```bash
curl -X POST https://your-url.com/api/shadowverse/log_match \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_key" \
  -d '{
    "user_id": "123456789012345678",
    "server_id": "987654321098765432",
    "played_craft": "Dragoncraft",
    "opponent_craft": "Forestcraft",
    "win": true,
    "brick": false
  }'
```

## Python Client

```python
import requests

API_URL = "https://your-url.com"
API_KEY = "your_key"

# Log a match
requests.post(
    f"{API_URL}/api/shadowverse/log_match",
    headers={"X-API-Key": API_KEY},
    json={
        "user_id": "123",
        "server_id": "456",
        "played_craft": "Dragoncraft",
        "opponent_craft": "Forestcraft",
        "win": True,
        "brick": False
    }
)
```

## Valid Crafts

- Forestcraft
- Swordcraft
- Runecraft
- Dragoncraft
- Abysscraft
- Havencraft
- Portalcraft

## Troubleshooting

```bash
# Check bot logs
journalctl -u kanami-bot.service -f

# Check if port is in use
sudo lsof -i :8080

# Test local API
curl http://localhost:8080/api/health

# Check ngrok status
curl http://localhost:4040/api/tunnels

# Check Cloudflare status
sudo systemctl status cloudflared
```

## Getting Discord IDs

1. Enable Developer Mode in Discord Settings → Advanced
2. Right-click user/server → Copy ID
