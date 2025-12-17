"""
Shadowverse Match Logger - API Client
A simple command-line tool to log Shadowverse matches to the Gacha Timer Bot.

Installation:
    pip install requests

Usage:
    python shadowverse_client.py

Configuration:
    Edit the CONFIG section below with your API details.
"""

import requests
import json
import sys
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================

CONFIG = {
    # API Server URL (change to your ngrok/Cloudflare URL if needed)
    "api_url": "http://localhost:8080",

    # Your API key from api_keys.json
    # If using key1/key2/key3, user_id will be automatically mapped
    "api_key": "key1",  # Change this to your actual API key

    # Your Discord user ID (optional if using key1/key2/key3)
    # Right-click your name in Discord (Developer Mode enabled) to copy ID
    "user_id": None,  # e.g., "123456789012345678" or None to use mapping
}

# ============================================================
# API CLIENT CLASS
# ============================================================

class ShadowverseClient:
    """Client for logging Shadowverse matches via the bot's API."""

    def __init__(self, api_url, api_key, user_id=None):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.user_id = user_id

    def _make_request(self, endpoint, data):
        """Makes a POST request to the API."""
        url = f"{self.api_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
        }

        try:
            response = requests.post(url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            return True, response.json()
        except requests.exceptions.HTTPError as e:
            error_msg = e.response.text if e.response else str(e)
            return False, {"error": f"HTTP {e.response.status_code}: {error_msg}"}
        except requests.exceptions.RequestException as e:
            return False, {"error": f"Request failed: {str(e)}"}

    def log_match_simple(self, played_craft, opponent_craft, win, brick=False):
        """
        Logs a match using the simple legacy format.

        Args:
            played_craft (str): Your craft (e.g., "Dragoncraft")
            opponent_craft (str): Opponent's craft
            win (bool): True if you won
            brick (bool): True if you bricked

        Returns:
            (success, response_data)
        """
        data = {
            "played_craft": played_craft,
            "opponent_craft": opponent_craft,
            "win": win,
            "brick": brick
        }

        if self.user_id:
            data["user_id"] = self.user_id

        return self._make_request("/api/shadowverse/log_match", data)

    def log_match_detailed(self, played_craft, opponent_craft, win, brick=False,
                          player_points=None, player_point_type=None,
                          player_rank=None, player_group=None,
                          opponent_points=None, opponent_point_type=None,
                          opponent_rank=None, opponent_group=None):
        """
        Logs a match with detailed metadata using the new format.

        Args:
            played_craft (str): Your craft
            opponent_craft (str): Opponent's craft
            win (bool): True if you won
            brick (bool): True if you bricked
            player_points (int): Your points (optional)
            player_point_type (str): "RP" or "MP" (optional)
            player_rank (str): Your rank, e.g., "A1" (optional)
            player_group (str): Your group, e.g., "Topaz" (optional)
            opponent_points (int): Opponent's points (optional)
            opponent_point_type (str): Opponent's point type (optional)
            opponent_rank (str): Opponent's rank (optional)
            opponent_group (str): Opponent's group (optional)

        Returns:
            (success, response_data)
        """
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "win": win,
            "brick": brick,
            "player": {"craft": played_craft},
            "opponent": {"craft": opponent_craft}
        }

        if self.user_id:
            data["user_id"] = self.user_id

        # Add optional player fields
        if player_points is not None:
            data["player"]["points"] = player_points
        if player_point_type is not None:
            data["player"]["point_type"] = player_point_type
        if player_rank is not None:
            data["player"]["rank"] = player_rank
        if player_group is not None:
            data["player"]["group"] = player_group

        # Add optional opponent fields
        if opponent_points is not None:
            data["opponent"]["points"] = opponent_points
        if opponent_point_type is not None:
            data["opponent"]["point_type"] = opponent_point_type
        if opponent_rank is not None:
            data["opponent"]["rank"] = opponent_rank
        if opponent_group is not None:
            data["opponent"]["group"] = opponent_group

        return self._make_request("/api/shadowverse/log_match", data)

    def check_health(self):
        """Checks if the API server is running."""
        url = f"{self.api_url}/api/health"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return True, response.json()
        except Exception as e:
            return False, {"error": str(e)}

    def get_recent_matches(self, limit=10):
        """
        Gets recent matches for the authenticated user.

        Args:
            limit (int): Maximum number of matches to return (default: 10, max: 50)

        Returns:
            (success, response_data)
        """
        url = f"{self.api_url}/api/shadowverse/matches?limit={limit}"
        headers = {
            "X-API-Key": self.api_key
        }
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return True, response.json()
        except requests.exceptions.HTTPError as e:
            error_msg = e.response.text if e.response else str(e)
            return False, {"error": f"HTTP {e.response.status_code}: {error_msg}"}
        except requests.exceptions.RequestException as e:
            return False, {"error": f"Request failed: {str(e)}"}

    def remove_match(self, match_id):
        """
        Removes a match by its ID.

        Args:
            match_id (int): The ID of the match to remove

        Returns:
            (success, response_data)
        """
        url = f"{self.api_url}/api/shadowverse/match/{match_id}"
        headers = {
            "X-API-Key": self.api_key
        }
        try:
            response = requests.delete(url, headers=headers, timeout=10)
            response.raise_for_status()
            return True, response.json()
        except requests.exceptions.HTTPError as e:
            error_msg = e.response.text if e.response else str(e)
            return False, {"error": f"HTTP {e.response.status_code}: {error_msg}"}
        except requests.exceptions.RequestException as e:
            return False, {"error": f"Request failed: {str(e)}"}

# ============================================================
# INTERACTIVE CLI
# ============================================================

CRAFTS = [
    "Forestcraft", "Swordcraft", "Runecraft", "Dragoncraft",
    "Shadowcraft", "Bloodcraft", "Havencraft", "Portalcraft", "Abysscraft"
]

def get_craft_input(prompt):
    """Gets a valid craft from user input."""
    print(f"\n{prompt}")
    print("Available crafts:")
    for i, craft in enumerate(CRAFTS, 1):
        print(f"  {i}. {craft}")

    while True:
        choice = input("\nEnter craft name or number: ").strip()

        # Try as number
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(CRAFTS):
                return CRAFTS[idx]

        # Try as name (case-insensitive partial match)
        choice_lower = choice.lower()
        matches = [c for c in CRAFTS if c.lower().startswith(choice_lower)]
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            print(f"  Ambiguous. Did you mean: {', '.join(matches)}?")
        else:
            print(f"  Invalid craft. Please try again.")

def get_yes_no(prompt, default=False):
    """Gets a yes/no answer from user."""
    default_str = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{prompt} [{default_str}]: ").strip().lower()
        if not answer:
            return default
        if answer in ['y', 'yes']:
            return True
        if answer in ['n', 'no']:
            return False
        print("  Please enter 'y' or 'n'")

def interactive_mode(client):
    """Interactive CLI for logging matches."""
    print("\n" + "=" * 60)
    print("SHADOWVERSE MATCH LOGGER")
    print("=" * 60)

    # Check API health
    print("\nChecking API connection...")
    success, health = client.check_health()
    if success:
        print(f"✅ Connected to API server")
        print(f"   Bot: {health.get('bot_user', 'Unknown')}")
    else:
        print(f"❌ Cannot connect to API server!")
        print(f"   Error: {health.get('error')}")
        print("\n   Make sure:")
        print("   1. The bot is running")
        print("   2. API server is enabled (API_ENABLED=true)")
        print(f"   3. API URL is correct: {CONFIG['api_url']}")
        return

    while True:
        print("\n" + "-" * 60)

        # Get match details
        played_craft = get_craft_input("What craft did YOU play?")
        opponent_craft = get_craft_input("What craft did your OPPONENT play?")
        win = get_yes_no("Did you win?", default=True)
        brick = get_yes_no("Did you brick?", default=False)

        # Ask if user wants to add detailed metadata
        detailed = get_yes_no("\nAdd detailed match info (rank, points, etc.)?", default=False)

        if detailed:
            print("\n--- Player Details (press Enter to skip) ---")
            player_rank = input("Your rank (e.g., A1, B3, Master): ").strip() or None
            player_group = input("Your group (e.g., Topaz, Diamond): ").strip() or None
            player_points_str = input("Your points: ").strip()
            player_points = int(player_points_str) if player_points_str.isdigit() else None
            player_point_type = input("Point type (RP/MP): ").strip().upper() or None

            print("\n--- Opponent Details (press Enter to skip) ---")
            opponent_rank = input("Opponent rank: ").strip() or None
            opponent_group = input("Opponent group: ").strip() or None
            opponent_points_str = input("Opponent points: ").strip()
            opponent_points = int(opponent_points_str) if opponent_points_str.isdigit() else None
            opponent_point_type = input("Opponent point type (RP/MP): ").strip().upper() or None

            # Log with details
            print("\n📝 Logging match with details...")
            success, response = client.log_match_detailed(
                played_craft, opponent_craft, win, brick,
                player_points=player_points, player_point_type=player_point_type,
                player_rank=player_rank, player_group=player_group,
                opponent_points=opponent_points, opponent_point_type=opponent_point_type,
                opponent_rank=opponent_rank, opponent_group=opponent_group
            )
        else:
            # Log simple format
            print("\n📝 Logging match...")
            success, response = client.log_match_simple(
                played_craft, opponent_craft, win, brick
            )

        # Show result
        if success:
            match_id = response.get('match_id')
            print(f"✅ {response.get('message', 'Match logged successfully!')}")
            print(f"   Match ID: {match_id}")

            # Ask if user wants to undo
            if get_yes_no("\nMade a mistake? Remove this match?", default=False):
                print(f"\n🗑️  Removing match {match_id}...")
                remove_success, remove_response = client.remove_match(match_id)
                if remove_success:
                    print(f"✅ {remove_response.get('message', 'Match removed successfully!')}")
                else:
                    print(f"❌ Failed to remove match")
                    print(f"   Error: {remove_response.get('error')}")
        else:
            print(f"❌ Failed to log match")
            print(f"   Error: {response.get('error')}")

        # Continue?
        if not get_yes_no("\nLog another match?", default=True):
            break

    print("\n" + "=" * 60)
    print("Thanks for using Shadowverse Match Logger!")
    print("=" * 60)

# ============================================================
# EXAMPLE USAGE (PROGRAMMATIC)
# ============================================================

def example_usage():
    """Example of using the client programmatically."""
    client = ShadowverseClient(
        api_url=CONFIG["api_url"],
        api_key=CONFIG["api_key"],
        user_id=CONFIG["user_id"]
    )

    print("Example 1: Simple match logging")
    success, response = client.log_match_simple(
        played_craft="Dragoncraft",
        opponent_craft="Forestcraft",
        win=True,
        brick=False
    )
    print(f"Success: {success}")
    print(f"Response: {response}")
    if success:
        match_id = response.get('match_id')
        print(f"Match ID: {match_id}\n")

    print("Example 2: Detailed match logging")
    success, response = client.log_match_detailed(
        played_craft="Swordcraft",
        opponent_craft="Runecraft",
        win=False,
        brick=True,
        player_points=45095,
        player_point_type="RP",
        player_rank="A1",
        player_group="Topaz",
        opponent_points=50604,
        opponent_point_type="RP",
        opponent_rank="A2",
        opponent_group="Topaz"
    )
    print(f"Success: {success}")
    print(f"Response: {response}")
    if success:
        match_id_to_remove = response.get('match_id')
        print(f"Match ID: {match_id_to_remove}\n")

        # Example 3: Remove a match
        print(f"Example 3: Removing match {match_id_to_remove}")
        success, response = client.remove_match(match_id_to_remove)
        print(f"Success: {success}")
        print(f"Response: {response}\n")

    # Example 4: List recent matches
    print("Example 4: Listing recent matches")
    success, response = client.get_recent_matches(limit=5)
    print(f"Success: {success}")
    if success:
        matches = response.get('matches', [])
        print(f"Found {len(matches)} matches:")
        for match in matches:
            result = "Win" if match['win'] else "Loss"
            brick_status = " (Bricked)" if match['brick'] else ""
            print(f"  ID {match['id']}: {match['played_craft']} vs {match['opponent_craft']} - {result}{brick_status}")
    else:
        print(f"Error: {response.get('error')}")
    print()

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    # Create client
    client = ShadowverseClient(
        api_url=CONFIG["api_url"],
        api_key=CONFIG["api_key"],
        user_id=CONFIG["user_id"]
    )

    # Check if user wants interactive mode or examples
    if len(sys.argv) > 1 and sys.argv[1] == "--example":
        example_usage()
    else:
        interactive_mode(client)
