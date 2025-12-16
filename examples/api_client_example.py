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

# Your Discord ID (right-click user in Discord with Developer Mode enabled)
USER_ID = "123456789012345678"  # Your Discord user ID (OPTIONAL if using key1/key2/key3)

# Note: server_id is no longer needed! The API automatically uses the development server.
# Note: If you use key1, key2, or key3, user_id is automatically mapped:
#   - key1 -> Narisurii (680653908259110914)
#   - key2 -> Alfabem (264758014198808577)
#   - key3 -> Naito (443416461457883136)

def log_match(played_craft, opponent_craft, win, brick=False, user_id=None):
    """
    Logs a Shadowverse match to the bot's database using the legacy format.

    Args:
        played_craft (str): The craft you played (Forestcraft, Swordcraft, etc.)
        opponent_craft (str): The craft your opponent played
        win (bool): True if you won, False if you lost
        brick (bool): True if you bricked, False otherwise
        user_id (str): Optional - Discord user ID. If not provided, uses API key mapping.

    Returns:
        dict: API response with success status and details
    """
    url = f"{API_BASE_URL}/api/shadowverse/log_match"

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }

    payload = {
        "played_craft": played_craft,
        "opponent_craft": opponent_craft,
        "win": win,
        "brick": brick
    }

    # Only include user_id if explicitly provided
    if user_id:
        payload["user_id"] = user_id

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error logging match: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return None

def log_match_detailed(played_craft, opponent_craft, win, brick=False,
                       player_points=None, player_point_type=None, player_rank=None, player_group=None,
                       opponent_points=None, opponent_point_type=None, opponent_rank=None, opponent_group=None,
                       user_id=None):
    """
    Logs a Shadowverse match to the bot's database using the new detailed format.

    Args:
        played_craft (str): The craft you played
        opponent_craft (str): The craft your opponent played
        win (bool): True if you won, False if you lost
        brick (bool): True if you bricked, False otherwise
        player_points (int): Your points (optional)
        player_point_type (str): Type of points, e.g., 'RP', 'MP' (optional)
        player_rank (str): Your rank, e.g., 'A1', 'Master' (optional)
        player_group (str): Your group, e.g., 'Topaz', 'Diamond' (optional)
        opponent_points (int): Opponent's points (optional)
        opponent_point_type (str): Opponent's point type (optional)
        opponent_rank (str): Opponent's rank (optional)
        opponent_group (str): Opponent's group (optional)
        user_id (str): Optional - Discord user ID. If not provided, uses API key mapping.

    Returns:
        dict: API response with success status and details
    """
    from datetime import datetime

    url = f"{API_BASE_URL}/api/shadowverse/log_match"

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }

    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "win": win,
        "brick": brick,
        "player": {
            "craft": played_craft
        },
        "opponent": {
            "craft": opponent_craft
        }
    }

    # Only include user_id if explicitly provided
    if user_id:
        payload["user_id"] = user_id

    # Add optional player fields
    if player_points is not None:
        payload["player"]["points"] = player_points
    if player_point_type is not None:
        payload["player"]["point_type"] = player_point_type
    if player_rank is not None:
        payload["player"]["rank"] = player_rank
    if player_group is not None:
        payload["player"]["group"] = player_group

    # Add optional opponent fields
    if opponent_points is not None:
        payload["opponent"]["points"] = opponent_points
    if opponent_point_type is not None:
        payload["opponent"]["point_type"] = opponent_point_type
    if opponent_rank is not None:
        payload["opponent"]["rank"] = opponent_rank
    if opponent_group is not None:
        payload["opponent"]["group"] = opponent_group

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
    print("\nNote: The API automatically uses the development server.")
    print("You only need to provide your user_id!\n")
    
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
    
    # 3. Log example matches using LEGACY format
    print("\n3. Logging example matches (Legacy Format)...")

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

    # 4. Log example matches using NEW DETAILED format
    print("\n4. Logging example matches (New Detailed Format)...")

    # Example 3: Win with detailed metadata
    print("\n   Match 3: Dragoncraft vs Abysscraft (Win with detailed metadata)")
    result = log_match_detailed(
        "Dragoncraft", "Abysscraft", win=True, brick=False,
        player_points=45095, player_point_type="RP", player_rank="A1", player_group="Topaz",
        opponent_points=50604, opponent_point_type="RP", opponent_rank="A2", opponent_group="Topaz"
    )
    if result and result.get('success'):
        print(f"   ✅ {result.get('message')}")
    else:
        print(f"   ❌ Failed to log match")

    # Example 4: Loss with partial metadata
    print("\n   Match 4: Havencraft vs Portalcraft (Loss with partial metadata)")
    result = log_match_detailed(
        "Havencraft", "Portalcraft", win=False, brick=False,
        player_rank="B3", opponent_rank="B2"
    )
    if result and result.get('success'):
        print(f"   ✅ {result.get('message')}")
    else:
        print(f"   ❌ Failed to log match")

    print("\n" + "=" * 50)
    print("Done! Check your Discord Shadowverse channel for updated dashboard.")
    print("\nNote: The new detailed format allows you to track additional metadata like:")
    print("  - Match timestamp")
    print("  - Player/opponent points and point type (RP, MP)")
    print("  - Player/opponent rank (A1, Master, etc.)")
    print("  - Player/opponent group (Topaz, Diamond, etc.)")
    print("\nAll metadata fields are optional except timestamp, win, and crafts!")
