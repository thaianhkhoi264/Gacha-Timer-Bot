# Claude API Setup Guide

This bot can use Claude API for superior LLM-based event classification and extraction. Claude provides better accuracy than the local GGUF model, especially for complex text parsing.

## Why Use Claude?

- **Better Accuracy**: Claude 3.5 Sonnet is significantly better at understanding event announcements
- **Reduced False Positives**: More reliable classification of events vs filler content
- **Better Date Parsing**: Superior at extracting and formatting dates/times
- **Pay-as-you-go**: Only pay for what you use (~$0.003 per API call for typical events)

## Prerequisites

- Anthropic API account
- Credit card for API billing (very cheap - see pricing below)
- Internet connection on Raspberry Pi

---

## Step 1: Get Your Claude API Key

### 1.1 Create Anthropic Account

1. Go to https://console.anthropic.com
2. Click "Sign Up" and create an account
3. Verify your email address

### 1.2 Add Billing Information

1. Go to https://console.anthropic.com/settings/billing
2. Click "Add Payment Method"
3. Enter your credit card information
4. **Set a spending limit** (recommended: $5-10/month)

### 1.3 Generate API Key

1. Go to https://console.anthropic.com/settings/keys
2. Click "Create Key"
3. Give it a name (e.g., "Gacha Timer Bot")
4. **Copy the API key** (starts with `sk-ant-`)
5. **Save it somewhere secure** - you won't be able to see it again!

---

## Step 2: Install Anthropic SDK

On your Raspberry Pi:

```bash
# Activate your virtual environment
cd ~/Gacha-Timer-Bot
source venv/bin/activate

# Install anthropic package
pip install anthropic

# Verify installation
python -c "import anthropic; print('✓ Anthropic SDK installed')"
```

---

## Step 3: Configure Bot

### Option A: Using .env File (Recommended)

```bash
cd ~/Gacha-Timer-Bot
nano .env
```

Add this line (replace with your actual API key):
```bash
ANTHROPIC_API_KEY=sk-ant-api03-YOUR_KEY_HERE
```

Save (Ctrl+O, Enter) and exit (Ctrl+X).

### Option B: Environment Variable

```bash
# Add to your shell profile (permanent)
echo 'export ANTHROPIC_API_KEY="sk-ant-api03-YOUR_KEY_HERE"' >> ~/.bashrc
source ~/.bashrc
```

---

## Step 4: Test Configuration

```bash
# Test if API key is loaded
python -c "import os; print('API Key:', os.getenv('ANTHROPIC_API_KEY')[:20] + '...' if os.getenv('ANTHROPIC_API_KEY') else 'NOT FOUND')"
```

You should see:
```
API Key: sk-ant-api03-xxxxx...
```

---

## Step 5: Restart Bot

```bash
sudo systemctl restart kanami-bot.service

# Check logs to verify Claude is enabled
sudo journalctl -u kanami-bot.service -n 50 | grep -i claude
```

You should see:
```
[ML_HANDLER] Claude API enabled (will use claude-3-5-sonnet-20241022)
```

---

## Pricing & Usage

### Current Pricing (as of Nov 2025)

Claude 3.5 Sonnet (2024-10-22):
- **Input**: $3.00 per million tokens (~$0.003 per 1000 tokens)
- **Output**: $15.00 per million tokens (~$0.015 per 1000 tokens)

### Typical Costs

**Per Arknights Event Tweet:**
- Input: ~500-800 tokens (prompt + tweet) = $0.0015-0.0024
- Output: ~100-200 tokens (extracted data) = $0.0015-0.003
- **Total per event: ~$0.003-0.005** (less than 1 cent!)

**Monthly Estimate:**
- ~30 Arknights events/month
- 30 events × $0.004 = **~$0.12/month**
- With safety margin: **$0.50/month**

**Recommended spending limit: $5-10/month** (gives you plenty of buffer)

---

## How It Works

### Automatic Fallback

The bot uses a **smart fallback system**:

1. **Try Claude API first** (if configured)
   - Better accuracy
   - More reliable
   
2. **Fall back to local GGUF** (if Claude fails)
   - No API cost
   - Works offline
   - Lower accuracy

### When Claude is Used

Claude API is used for:
- ✅ Arknights event classification (is it an event or filler?)
- ✅ Event data extraction (title, dates, category)
- ✅ Any other LLM inference tasks

### When Local Model is Used

Local GGUF model is used when:
- ❌ Claude API key not configured
- ❌ API request fails (network issues)
- ❌ Rate limit reached
- ❌ Anthropic API is down

---

## Monitoring Usage

### Check Usage on Anthropic Console

1. Go to https://console.anthropic.com/settings/usage
2. View your current month's usage
3. Set up email alerts for spending thresholds

### Check Bot Logs

```bash
# See which LLM is being used
sudo journalctl -u kanami-bot.service -f | grep ML_HANDLER

# Look for these messages:
# [ML_HANDLER] Claude API enabled
# [ML_HANDLER] Attempting Claude API call...
# [ML_HANDLER] Claude response preview: ...
# [ML_HANDLER] Falling back to local GGUF model... (if Claude fails)
```

---

## Troubleshooting

### "Claude API not configured"

**Problem**: Bot logs show local GGUF model is being used

**Solution**:
```bash
# Check if API key is set
echo $ANTHROPIC_API_KEY

# If empty, add to .env file
cd ~/Gacha-Timer-Bot
nano .env
# Add: ANTHROPIC_API_KEY=sk-ant-api03-YOUR_KEY_HERE

# Restart bot
sudo systemctl restart kanami-bot.service
```

### "anthropic package not found"

**Problem**: Import error when starting bot

**Solution**:
```bash
source venv/bin/activate
pip install anthropic
```

### "API key invalid"

**Problem**: Claude API returns authentication error

**Solution**:
1. Verify API key at https://console.anthropic.com/settings/keys
2. Make sure you copied the entire key (starts with `sk-ant-`)
3. Check for extra spaces in .env file
4. Regenerate key if needed

### "Rate limit exceeded"

**Problem**: Too many API calls

**Solution**:
- Wait a few minutes
- Check usage at https://console.anthropic.com/settings/usage
- Increase your rate limit (if on paid plan)
- Bot will automatically fall back to local model

---

## Disabling Claude API

To go back to local-only model:

```bash
# Remove from .env
nano .env
# Delete the ANTHROPIC_API_KEY line

# Or unset environment variable
unset ANTHROPIC_API_KEY

# Restart bot
sudo systemctl restart kanami-bot.service
```

---

## Security Best Practices

### Protect Your API Key

- ✅ **Never commit .env to git** (already in .gitignore)
- ✅ **Don't share your API key** with anyone
- ✅ **Use separate keys** for testing and production
- ✅ **Rotate keys regularly** (every 3-6 months)

### Set Spending Limits

1. Go to https://console.anthropic.com/settings/billing
2. Set a monthly spending limit (e.g., $10)
3. Set up email alerts at 50%, 75%, 100% of limit

### Monitor Usage

- Check usage weekly: https://console.anthropic.com/settings/usage
- Review bot logs for unexpected API calls
- Revoke and regenerate key if compromised

---

## FAQ

**Q: Do I need Claude API for the bot to work?**  
A: No! The bot works fine with the local GGUF model. Claude just improves accuracy.

**Q: How much will this cost me?**  
A: Typically less than $1/month for normal usage. Set a $5-10 spending limit to be safe.

**Q: What happens if I run out of credits?**  
A: The bot automatically falls back to the local GGUF model. No downtime!

**Q: Can I use a different Claude model?**  
A: Yes, edit `ml_handler.py` and change the model name. Options:
- `claude-3-5-sonnet-20241022` (recommended - best balance)
- `claude-3-opus-20240229` (most capable, more expensive)
- `claude-3-haiku-20240307` (fastest, cheapest, less accurate)

**Q: Is my data sent to Anthropic?**  
A: Yes, tweets are sent to Claude API for processing. Anthropic's privacy policy: https://www.anthropic.com/privacy

**Q: Can I use this for other games?**  
A: Yes! The LLM handler is used by all modules that need text classification/extraction.

---

## Summary

**Quick Setup:**
1. Get API key from https://console.anthropic.com
2. `pip install anthropic`
3. Add `ANTHROPIC_API_KEY=sk-ant-...` to `.env`
4. Restart bot
5. Check logs for `[ML_HANDLER] Claude API enabled`

**Expected Cost:** ~$0.50/month for typical usage

**Fallback:** Local GGUF model (always available)

You're all set! 🎉
