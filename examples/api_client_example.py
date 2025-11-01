"""
Example client for the Gacha Timer Bot API
Demonstrates how to log Shadowverse matches programmatically from an external program.

Requirements:
    pip install requests

Usage:
    python api_client_example.py
"""

import requests
import json

# Configuration
API_BASE_URL = "http://localhost:8080"  # Change this to your ngrok/Cloudflare URL
API_KEY = "YOUR_API_KEY_HERE"  # Get this from api_keys.json on the bot server

# Your Discord IDs (right-click user/server in Discord with Developer Mode enabled)
USER_ID = "123456789012345678"  # Your Discord user ID
SERVER_ID = "987654321098765432"  # The Discord server/guild ID

def log_match(played_craft, opponent_craft, win, brick=False):
    """
    Logs a Shadowverse match to the bot's database.
    
    Args:
        played_craft (str): The craft you played (Forestcraft, Swordcraft, etc.)
        opponent_craft (str): The craft your opponent played
        win (bool): True if you won, False if you lost
        brick (bool): True if you bricked, False otherwise
    
    Returns:
        dict: API response with success status and details
    """
    url = f"{API_BASE_URL}/api/shadowverse/log_match"
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    payload = {
        "user_id": USER_ID,
        "server_id": SERVER_ID,
        "played_craft": played_craft,
        "opponent_craft": opponent_craft,
        "win": win,
        "brick": brick
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error logging match: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return None

def check_health():
    """
    Checks if the API server is running and responsive.
    
    Returns:
        dict: Health check response
    """
    url = f"{API_BASE_URL}/api/health"
    
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error checking health: {e}")
        return None

def validate_api_key():
    """
    Validates your API key without performing any actions.
    
    Returns:
        dict: Validation response
    """
    url = f"{API_BASE_URL}/api/validate_key"
    
    headers = {
        "X-API-Key": API_KEY
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error validating key: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return None

# Example usage
if __name__ == "__main__":
    print("Gacha Timer Bot API Client Example")
    print("=" * 50)
    
    # 1. Check API health
    print("\n1. Checking API health...")
    health = check_health()
    if health:
        print(f"   Status: {health.get('status')}")
        print(f"   Bot connected: {health.get('bot_connected')}")
        print(f"   Bot user: {health.get('bot_user')}")
    else:
        print("   ❌ API server is not reachable!")
        print("   Make sure the bot is running and API_ENABLED=true")
        exit(1)
    
    # 2. Validate API key
    print("\n2. Validating API key...")
    validation = validate_api_key()
    if validation and validation.get('valid'):
        print(f"   ✅ API key is valid!")
        print(f"   Description: {validation.get('description')}")
    else:
        print("   ❌ API key is invalid!")
        print("   Update API_KEY in this script with a valid key from api_keys.json")
        exit(1)
    
    # 3. Log example matches
    print("\n3. Logging example matches...")
    
    # Example 1: Win with Dragoncraft against Forestcraft
    print("\n   Match 1: Dragoncraft vs Forestcraft (Win)")
    result = log_match("Dragoncraft", "Forestcraft", win=True, brick=False)
    if result and result.get('success'):
        print(f"   ✅ {result.get('message')}")
    else:
        print(f"   ❌ Failed to log match")
    
    # Example 2: Loss with Swordcraft against Runecraft (bricked)
    print("\n   Match 2: Swordcraft vs Runecraft (Loss, Bricked)")
    result = log_match("Swordcraft", "Runecraft", win=False, brick=True)
    if result and result.get('success'):
        print(f"   ✅ {result.get('message')}")
    else:
        print(f"   ❌ Failed to log match")
    
    print("\n" + "=" * 50)
    print("Done! Check your Discord Shadowverse channel for updated dashboard.")
