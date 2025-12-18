# Shadowverse Match Tracking API

This bot includes a REST API that allows external applications to log Shadowverse matches programmatically.

## For Bot Administrators

### Quick Setup

1. **Install dependencies:**
   ```bash
   pip install aiohttp
   ```

2. **Create API keys file:**
   ```bash
   cd ~/Gacha-Timer-Bot
   nano api_keys.json
   ```
   
   Add:
   ```json
   {
     "your_secret_key_here": "Description of this key"
   }
   ```

3. **Restart bot:**
   ```bash
   sudo systemctl restart kanami-bot.service
   ```

4. **Setup Cloudflare Tunnel** (for external access):

   For external access, set up a Cloudflare Tunnel pointing to `localhost:8080`.

   **Working Example**: `https://kanami.yourdomain.com` → `http://localhost:8080`

   **Setup Instructions**: See [docs/CLOUDFLARE_SETUP.md](docs/CLOUDFLARE_SETUP.md) for complete tunnel configuration.

   **Client Configuration**:
   ```python
   CONFIG = {
       "api_url": "https://kanami.yourdomain.com",  # Your cloudflare domain
       "api_key": "your-api-key"
   }
   ```

   **Note**: You can use any subdomain (api.domain.com, kanami.domain.com, etc.) - just ensure cloudflared config.yml matches your chosen hostname.

### Configuration

API is **enabled by default**. To disable or change settings, add to `.env`:

```bash
API_ENABLED=true          # Set to false to disable
API_HOST=0.0.0.0         # Leave as 0.0.0.0 for all interfaces
API_PORT=8080            # Change if port conflict
```

### Endpoints

- `GET /api/health` - Check if API and bot are running
- `GET /api/validate_key` - Validate an API key
- `POST /api/shadowverse/log_match` - Log a match (requires API key)

### Security

- **Never commit `api_keys.json`** - It's in `.gitignore`
- Use long, random keys: `openssl rand -hex 32`
- One shared key for all users is fine for small groups
- Revoke compromised keys by removing from `api_keys.json`

---

## For Application Developers

**See [EXTERNAL_APP_GUIDE.md](EXTERNAL_APP_GUIDE.md)** for complete documentation on building applications that use this API.

The guide includes:
- API endpoint documentation
- Complete Python examples (CLI and GUI)
- How to create executables for distribution
- Error handling
- Troubleshooting

### Quick Example

```python
import requests

API_URL = "https://your-cloudflare-domain.com"
API_KEY = "your_secret_key"
USER_ID = "123456789012345678"  # Discord user ID

# Log a match
response = requests.post(
    f"{API_URL}/api/shadowverse/log_match",
    headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
    json={
        "user_id": USER_ID,
        "played_craft": "Dragoncraft",
        "opponent_craft": "Forestcraft",
        "win": True,
        "brick": False
    }
)

print(response.json())
```

---

## Files

- **`api_server.py`** - API server implementation
- **`EXTERNAL_APP_GUIDE.md`** - Complete guide for building client applications
- **`examples/api_client_example.py`** - Basic Python client example
- **`api_keys.json`** - API keys (not in git, create manually)

---

## Architecture

```
External App → Internet → Cloudflare Tunnel → Raspberry Pi → Bot API → Discord
```

The API runs as part of the bot process on port 8080 by default. Cloudflare Tunnel exposes it to the internet with HTTPS.
