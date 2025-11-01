# Systemd Service Files

## ngrok Service

Create `/etc/systemd/system/ngrok.service`:

```ini
[Unit]
Description=ngrok tunnel for Gacha Timer Bot API
After=network.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi
ExecStart=/usr/local/bin/ngrok http 8080 --log stdout
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable ngrok.service
sudo systemctl start ngrok.service
```

**Check status:**
```bash
sudo systemctl status ngrok.service
```

**View logs:**
```bash
journalctl -u ngrok.service -f
```

**Get current URL:**
```bash
curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url'
```

---

## Cloudflare Tunnel Service

Cloudflare provides automatic service installation:

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

**Check status:**
```bash
sudo systemctl status cloudflared
```

**View logs:**
```bash
journalctl -u cloudflared -f
```

---

## Bot Service (with API enabled)

Update your existing bot service or create `/etc/systemd/system/kanami-bot.service`:

```ini
[Unit]
Description=Kanami Discord Bot with API Server
After=network.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/Gacha-Timer-Bot
Environment="PATH=/home/pi/Gacha-Timer-Bot/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="API_ENABLED=true"
Environment="API_HOST=0.0.0.0"
Environment="API_PORT=8080"
ExecStart=/home/pi/Gacha-Timer-Bot/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable kanami-bot.service
sudo systemctl start kanami-bot.service
```

**Check status:**
```bash
sudo systemctl status kanami-bot.service
```

**View logs:**
```bash
journalctl -u kanami-bot.service -f
```

---

## Startup Order

To ensure services start in the correct order:

1. Bot service starts first (with API enabled)
2. Tunnel service starts after bot is ready

**Modify tunnel service to wait for bot:**

For ngrok, update `/etc/systemd/system/ngrok.service`:
```ini
[Unit]
Description=ngrok tunnel for Gacha Timer Bot API
After=network.target kanami-bot.service
Wants=kanami-bot.service

[Service]
# ... rest of config ...
```

For Cloudflare, systemd dependency is already configured automatically.

---

## Managing All Services

**Start all:**
```bash
sudo systemctl start kanami-bot.service
sudo systemctl start ngrok.service  # or cloudflared
```

**Stop all:**
```bash
sudo systemctl stop ngrok.service  # or cloudflared
sudo systemctl stop kanami-bot.service
```

**Restart all:**
```bash
sudo systemctl restart kanami-bot.service
sudo systemctl restart ngrok.service  # or cloudflared
```

**Check all statuses:**
```bash
sudo systemctl status kanami-bot.service ngrok.service
```

---

## Automatic Startup on Boot

Both services are configured to start automatically on boot with `WantedBy=multi-user.target`.

**Verify enabled:**
```bash
sudo systemctl is-enabled kanami-bot.service
sudo systemctl is-enabled ngrok.service  # or cloudflared
```

Should both show: `enabled`

---

## Monitoring

**View all logs together:**
```bash
journalctl -u kanami-bot.service -u ngrok.service -f
```

**Check for errors:**
```bash
journalctl -u kanami-bot.service -p err -n 50
```

**Get ngrok URL from logs:**
```bash
journalctl -u ngrok.service | grep "Forwarding"
```

---

## Troubleshooting

**If ngrok fails to start:**
```bash
# Check if port 8080 is available
sudo lsof -i :8080

# Check ngrok auth
ngrok config check

# Test manually first
ngrok http 8080
```

**If bot fails to start:**
```bash
# Check Python environment
/home/pi/Gacha-Timer-Bot/venv/bin/python --version

# Test manually
cd /home/pi/Gacha-Timer-Bot
source venv/bin/activate
python main.py
```

**If bot starts but API doesn't:**
```bash
# Check environment variables
systemctl show kanami-bot.service | grep Environment

# Check aiohttp is installed
/home/pi/Gacha-Timer-Bot/venv/bin/pip list | grep aiohttp
```
