"""
REST API Server for Gacha Timer Bot
Allows external programs to log Shadowverse matches programmatically.
"""

from aiohttp import web
import aiosqlite
import json
import os
import asyncio
import discord
from shadowverse_handler import (
    record_match,
    update_dashboard_message,
    get_sv_channel_id,
    remove_match_by_id,
    get_recent_matches,
    CRAFTS
)
from global_config import DEV_SERVER_ID, OWNER_USER_ID
import event_manager
import logging

# Configure logging
api_logger = logging.getLogger("api_server")
api_logger.setLevel(logging.INFO)

# Bot instance will be set by main.py to avoid circular imports
bot_instance = None

# Try to import aiohttp_cors (Plan C requirement)
try:
    import aiohttp_cors
except ImportError:
    aiohttp_cors = None
    api_logger.warning("aiohttp-cors not installed. CORS will be disabled.")

# Track active API match notifications (temporary messages that auto-delete after 30s)
# Format: {user_id: {"message": discord.Message, "count": int, "timer": asyncio.Task}}
active_api_notifications = {}

# Load API keys from environment or config file
API_KEYS_FILE = "api_keys.json"

# Map user descriptions (from api_keys.json) to Discord user IDs
# When an API key is used, we look up its description and map it to a Discord ID
USER_DESCRIPTION_TO_ID = {
    "Narisurii": "680653908259110914",  # Owner
    "Alfabem": "264758014198808577",
    "Naito": "443416461457883136",
    "SteveGHShadow": "220457675475910656"
}

def load_api_keys():
    """
    Loads API keys from api_keys.json file.
    Format: {"key1": "user_description", "key2": "another_user"}
    """
    if os.path.exists(API_KEYS_FILE):
        with open(API_KEYS_FILE, 'r') as f:
            return json.load(f)
    else:
        # Create default file with example
        default_keys = {
            "CHANGE_ME_secret_key_123": "Example API Key - REPLACE THIS"
        }
        with open(API_KEYS_FILE, 'w') as f:
            json.dump(default_keys, f, indent=2)
        api_logger.warning(f"Created default {API_KEYS_FILE}. Please update with your own API keys!")
        return default_keys

VALID_API_KEYS = load_api_keys()

def get_user_id_from_api_key(api_key_name):
    """
    Maps an API key to a Discord user ID by looking up the description in api_keys.json.

    Flow:
    1. Get the description for the API key from api_keys.json (e.g., "Narisurii")
    2. Look up the Discord user ID using USER_DESCRIPTION_TO_ID

    Returns: Discord user ID string or None if no mapping found
    """
    if api_key_name not in VALID_API_KEYS:
        return None

    description = VALID_API_KEYS[api_key_name]
    return USER_DESCRIPTION_TO_ID.get(description)

def validate_api_key(request):
    """
    Validates the API key from the request.
    Checks both 'X-API-Key' header and 'api_key' in JSON body.
    Returns (is_valid, error_message, api_key_name)
    """
    # Check header first
    api_key = request.headers.get('X-API-Key')

    # If not in header, check body (will be checked later when parsing JSON)
    if not api_key:
        return False, "Missing API key. Provide via 'X-API-Key' header or 'api_key' in body.", None

    if api_key not in VALID_API_KEYS:
        api_logger.warning(f"Invalid API key attempt: {api_key[:10]}...")
        return False, "Invalid API key.", None

    return True, None, api_key

async def delete_notification_after_delay(user_id, delay_seconds=30):
    """
    Waits for the specified delay, then deletes the notification message
    and removes it from the active_api_notifications dict.
    """
    await asyncio.sleep(delay_seconds)

    # Check if notification still exists (might have been replaced)
    if user_id in active_api_notifications:
        notification_data = active_api_notifications[user_id]
        message = notification_data["message"]

        try:
            await message.delete()
            api_logger.info(f"Deleted API notification for user {user_id} after {delay_seconds}s")
        except discord.NotFound:
            api_logger.debug(f"Notification message for user {user_id} already deleted")
        except Exception as e:
            api_logger.error(f"Failed to delete notification for user {user_id}: {e}")

        # Remove from tracking dict
        del active_api_notifications[user_id]

async def send_or_update_api_notification(channel, user_id, bot_name):
    """
    Sends a new notification or updates an existing one for API match logging.

    - First match: Creates new message "Kanami has received a match from @User"
    - Subsequent matches: Updates message to show count "Kanami has received 3 matches from @User"
    - Message auto-deletes after 30 seconds of no new matches
    """
    if user_id in active_api_notifications:
        # Update existing notification
        notification_data = active_api_notifications[user_id]
        notification_data["count"] += 1
        count = notification_data["count"]
        message = notification_data["message"]

        # Cancel the old timer
        if notification_data["timer"] and not notification_data["timer"].done():
            notification_data["timer"].cancel()

        # Update message content
        match_word = "match" if count == 1 else "matches"
        new_content = f"{bot_name} has received **{count} {match_word}** from <@{user_id}>"

        try:
            await message.edit(content=new_content)
            api_logger.info(f"Updated API notification for user {user_id} (count: {count})")
        except discord.NotFound:
            api_logger.warning(f"Notification message for user {user_id} was deleted, creating new one")
            # Message was deleted, create new one
            del active_api_notifications[user_id]
            await send_or_update_api_notification(channel, user_id, bot_name)
            return
        except Exception as e:
            api_logger.error(f"Failed to update notification for user {user_id}: {e}")
            return

        # Start new timer
        notification_data["timer"] = asyncio.create_task(delete_notification_after_delay(user_id, 30))
    else:
        # Send new notification (first match)
        content = f"{bot_name} has received a match from <@{user_id}>"

        try:
            # Use allowed_mentions to make it a silent ping
            allowed_mentions = discord.AllowedMentions(users=False)
            message = await channel.send(content, allowed_mentions=allowed_mentions)
            api_logger.info(f"Sent new API notification for user {user_id}")

            # Track notification
            timer = asyncio.create_task(delete_notification_after_delay(user_id, 30))
            active_api_notifications[user_id] = {
                "message": message,
                "count": 1,
                "timer": timer
            }
        except Exception as e:
            api_logger.error(f"Failed to send notification for user {user_id}: {e}")

async def handle_log_match(request):
    """
    POST /api/shadowverse/log_match

    Logs a Shadowverse match and updates the user's dashboard.
    Automatically uses the development server (DEV_SERVER_ID from global_config.py).

    Request Body Format 1 (Legacy - backward compatible):
    {
        "api_key": "your_secret_key",  // Optional if using X-API-Key header
        "user_id": "123456789012345678",  // Discord user ID (string) - optional if API key has user mapping
        "played_craft": "Dragoncraft",  // One of: Forestcraft, Swordcraft, Runecraft, Dragoncraft, Abysscraft, Havencraft, Portalcraft
        "opponent_craft": "Forestcraft",  // Same options as above
        "win": true,  // Boolean: true for win, false for loss
        "brick": false  // Boolean: true if bricked, false otherwise (optional, defaults to false)
    }

    Request Body Format 2 (New - with detailed metadata):
    {
        "api_key": "your_secret_key",  // Optional if using X-API-Key header
        "user_id": "123456789012345678",  // Discord user ID (string) - optional if API key has user mapping
        "timestamp": "2025-12-15T22:02:32.378327",  // ISO format timestamp (required in new format)
        "win": true,  // Boolean: true for win, false for loss (required)
        "brick": false,  // Boolean: true if bricked (optional)
        "player": {  // Player data (required)
            "craft": "Dragoncraft",  // Required
            "points": 45095,  // Optional
            "point_type": "RP",  // Optional (e.g., "RP", "MP")
            "rank": "A1",  // Optional
            "group": "Topaz"  // Optional
        },
        "opponent": {  // Opponent data (required)
            "craft": "Abysscraft",  // Required
            "points": 50604,  // Optional
            "point_type": "RP",  // Optional
            "rank": "A2",  // Optional
            "group": "Topaz"  // Optional
        }
    }

    API Key User Mapping:
    - key1 -> Narisurii (680653908259110914)
    - key2 -> Alfabem (264758014198808577)
    - key3 -> Naito (443416461457883136)
    When using one of these keys, user_id is automatically set to the mapped Discord ID.

    Response (JSON):
    {
        "success": true,
        "message": "Match logged successfully",
        "details": {
            "user_id": "123456789012345678",
            "server_id": "1374399849574961152",
            "played_craft": "Dragoncraft",
            "opponent_craft": "Forestcraft",
            "result": "win",
            "brick": false
        }
    }
    """
    try:
        # Parse JSON body
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"success": False, "error": "Invalid JSON in request body"},
                status=400
            )
        
        # Validate API key (check header first, then body)
        is_valid, error_msg, api_key_name = validate_api_key(request)
        if not is_valid:
            # Try to get from body if header validation failed
            api_key_body = data.get('api_key')
            if api_key_body and api_key_body in VALID_API_KEYS:
                is_valid = True
                api_key_name = api_key_body
            else:
                api_logger.warning(f"Unauthorized API request from {request.remote}")
                return web.json_response(
                    {"success": False, "error": error_msg},
                    status=401
                )

        # Map API key to Discord user ID
        # If user_id is provided in request, it will override this
        api_key_user_id = get_user_id_from_api_key(api_key_name)

        # Detect format: check if using new nested format (has 'player' and 'opponent' keys)
        is_new_format = 'player' in data and 'opponent' in data

        # Extract and validate data based on format
        if is_new_format:
            # New format with nested player/opponent objects
            # Required fields for new format
            if 'win' not in data:
                return web.json_response(
                    {"success": False, "error": "Missing required field: 'win'"},
                    status=400
                )
            if 'player' not in data or 'craft' not in data['player']:
                return web.json_response(
                    {"success": False, "error": "Missing required field: 'player.craft'"},
                    status=400
                )
            if 'opponent' not in data or 'craft' not in data['opponent']:
                return web.json_response(
                    {"success": False, "error": "Missing required field: 'opponent.craft'"},
                    status=400
                )
            if 'timestamp' not in data:
                return web.json_response(
                    {"success": False, "error": "Missing required field: 'timestamp' (required in new format)"},
                    status=400
                )

            # Extract user_id: use provided value, or fall back to API key mapping
            user_id = data.get('user_id')
            if user_id:
                user_id = str(user_id)
            elif api_key_user_id:
                user_id = api_key_user_id
                api_logger.info(f"Using user_id from API key mapping: {api_key_name} -> {user_id}")
            else:
                return web.json_response(
                    {"success": False, "error": "Missing 'user_id'. Either provide it in the request or use an API key with a mapped user_id."},
                    status=400
                )
            server_id = str(DEV_SERVER_ID)
            played_craft = data['player']['craft']
            opponent_craft = data['opponent']['craft']
            win = bool(data['win'])
            brick = bool(data.get('brick', False))

            # Extract optional metadata
            timestamp = data.get('timestamp')
            player_points = data['player'].get('points')
            player_point_type = data['player'].get('point_type')
            player_rank = data['player'].get('rank')
            player_group = data['player'].get('group')
            opponent_points = data['opponent'].get('points')
            opponent_point_type = data['opponent'].get('point_type')
            opponent_rank = data['opponent'].get('rank')
            opponent_group = data['opponent'].get('group')
        else:
            # Legacy format with flat structure
            # user_id is now optional if API key has a mapping
            required_fields = ['played_craft', 'opponent_craft', 'win']
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                return web.json_response(
                    {"success": False, "error": f"Missing required fields: {', '.join(missing_fields)}"},
                    status=400
                )

            # Extract user_id: use provided value, or fall back to API key mapping
            user_id = data.get('user_id')
            if user_id:
                user_id = str(user_id)
            elif api_key_user_id:
                user_id = api_key_user_id
                api_logger.info(f"Using user_id from API key mapping: {api_key_name} -> {user_id}")
            else:
                return web.json_response(
                    {"success": False, "error": "Missing 'user_id'. Either provide it in the request or use an API key with a mapped user_id."},
                    status=400
                )
            server_id = str(DEV_SERVER_ID)
            played_craft = data['played_craft']
            opponent_craft = data['opponent_craft']
            win = bool(data['win'])
            brick = bool(data.get('brick', False))

            # No optional metadata in legacy format
            timestamp = None
            player_points = None
            player_point_type = None
            player_rank = None
            player_group = None
            opponent_points = None
            opponent_point_type = None
            opponent_rank = None
            opponent_group = None
        
        # Validate crafts
        if played_craft not in CRAFTS:
            return web.json_response(
                {"success": False, "error": f"Invalid played_craft. Must be one of: {', '.join(CRAFTS)}"},
                status=400
            )
        
        if opponent_craft not in CRAFTS:
            return web.json_response(
                {"success": False, "error": f"Invalid opponent_craft. Must be one of: {', '.join(CRAFTS)}"},
                status=400
            )
        
        # Log the match to database
        api_logger.info(f"Logging match: user={user_id}, server={server_id} (DEV), played={played_craft}, opponent={opponent_craft}, win={win}, brick={brick}")
        match_id = await record_match(
            user_id, server_id, played_craft, opponent_craft, win, brick,
            source="api",
            timestamp=timestamp,
            player_points=player_points,
            player_point_type=player_point_type,
            player_rank=player_rank,
            player_group=player_group,
            opponent_points=opponent_points,
            opponent_point_type=opponent_point_type,
            opponent_rank=opponent_rank,
            opponent_group=opponent_group
        )
        
        # Get the guild and channel for dashboard update
        if not bot_instance:
            api_logger.error("Bot instance not available")
            return web.json_response(
                {"success": False, "error": "Bot not initialized"},
                status=503
            )
        
        guild = bot_instance.get_guild(DEV_SERVER_ID)
        if not guild:
            api_logger.error(f"Development server (ID: {DEV_SERVER_ID}) not found")
            return web.json_response(
                {"success": False, "error": f"Development server not found. Is the bot in the server?"},
                status=404
            )
        
        member = guild.get_member(int(user_id))
        if not member:
            api_logger.error(f"Member {user_id} not found in development server")
            return web.json_response(
                {"success": False, "error": f"User {user_id} not found in development server. Are they a member?"},
                status=404
            )
        
        # Get the Shadowverse channel
        sv_channel_id = await get_sv_channel_id(server_id)
        if not sv_channel_id:
            api_logger.error(f"No Shadowverse channel configured for development server")
            return web.json_response(
                {"success": False, "error": f"No Shadowverse channel configured for development server. Use 'Kanami shadowverse' command first."},
                status=404
            )
        
        channel = guild.get_channel(sv_channel_id)
        if not channel:
            api_logger.error(f"Shadowverse channel {sv_channel_id} not found in development server")
            return web.json_response(
                {"success": False, "error": f"Shadowverse channel not found."},
                status=404
            )
        
        # Update the dashboard
        api_logger.info(f"Updating dashboard for user {user_id}")
        await update_dashboard_message(member, channel)

        # Send or update API match notification
        bot_name = bot_instance.user.name if bot_instance.user else "Kanami"
        await send_or_update_api_notification(channel, user_id, bot_name)

        # Return success response
        response_data = {
            "success": True,
            "message": "Match logged successfully and dashboard updated",
            "match_id": match_id,
            "details": {
                "user_id": user_id,
                "server_id": server_id,
                "played_craft": played_craft,
                "opponent_craft": opponent_craft,
                "result": "win" if win else "loss",
                "brick": brick
            }
        }
        
        api_logger.info(f"Successfully logged match for user {user_id}")
        return web.json_response(response_data, status=200)
        
    except ValueError as e:
        api_logger.error(f"ValueError in log_match: {e}")
        return web.json_response(
            {"success": False, "error": str(e)},
            status=400
        )
    except Exception as e:
        api_logger.error(f"Unexpected error in log_match: {e}", exc_info=True)
        return web.json_response(
            {"success": False, "error": "Internal server error. Check bot logs."},
            status=500
        )

async def handle_log_batch(request):
    """
    POST /api/shadowverse/log_batch

    Logs multiple Shadowverse matches in a single request.
    Useful for logging a batch of matches after a play session.

    Request Body:
    {
        "api_key": "your_secret_key",  // Optional if using X-API-Key header
        "user_id": "123456789012345678",  // Optional if API key has user mapping
        "matches": [
            {
                // Same format as single match (legacy or detailed)
                "played_craft": "Dragoncraft",
                "opponent_craft": "Forestcraft",
                "win": true,
                "brick": false
            },
            {
                // Can mix legacy and detailed formats in same batch
                "timestamp": "2025-12-18T10:30:00Z",
                "win": false,
                "brick": true,
                "player": {
                    "craft": "Swordcraft",
                    "points": 45000,
                    "point_type": "RP",
                    "rank": "A1",
                    "group": "Topaz"
                },
                "opponent": {
                    "craft": "Runecraft",
                    "points": 46000,
                    "point_type": "RP"
                }
            }
        ]
    }

    Response:
    {
        "success": true,
        "message": "5 matches logged successfully",
        "count": 5,
        "match_ids": [123, 124, 125, 126, 127]
    }
    """
    try:
        # Validate API key
        is_valid, error_msg, api_key_name = validate_api_key(request)
        if not is_valid:
            api_logger.warning(f"Batch: {error_msg}")
            return web.json_response(
                {"success": False, "error": error_msg},
                status=401
            )

        # Parse request body
        try:
            data = await request.json()
        except Exception as e:
            return web.json_response(
                {"success": False, "error": f"Invalid JSON: {str(e)}"},
                status=400
            )

        # Get matches array
        matches = data.get('matches', [])
        if not matches:
            return web.json_response(
                {"success": False, "error": "No matches provided. Include 'matches' array in request body."},
                status=400
            )

        if not isinstance(matches, list):
            return web.json_response(
                {"success": False, "error": "'matches' must be an array."},
                status=400
            )

        if len(matches) > 100:
            return web.json_response(
                {"success": False, "error": "Too many matches. Maximum 100 per batch."},
                status=400
            )

        # Get user_id (from request or API key mapping)
        user_id = data.get('user_id')
        if not user_id:
            user_id = get_user_id_from_api_key(api_key_name)

        if not user_id:
            return web.json_response(
                {"success": False, "error": "user_id required (provide in body or use API key with user mapping)"},
                status=400
            )

        # Server ID is always DEV_SERVER_ID
        server_id = str(DEV_SERVER_ID)

        api_logger.info(f"Batch request from user {user_id}: {len(matches)} matches")

        # Validate all matches first before recording any
        validated_matches = []
        for idx, match in enumerate(matches):
            # Detect format (legacy vs detailed)
            has_legacy_format = 'played_craft' in match and 'opponent_craft' in match
            has_detailed_format = 'player' in match and 'opponent' in match

            if not has_legacy_format and not has_detailed_format:
                return web.json_response(
                    {"success": False, "error": f"Match {idx}: Must have either (played_craft, opponent_craft) or (player, opponent)"},
                    status=400
                )

            # Parse based on format
            if has_detailed_format:
                # Detailed format
                player = match.get('player', {})
                opponent = match.get('opponent', {})

                played_craft = player.get('craft')
                opponent_craft = opponent.get('craft')

                if not played_craft or not opponent_craft:
                    return web.json_response(
                        {"success": False, "error": f"Match {idx}: player.craft and opponent.craft are required"},
                        status=400
                    )

                # Optional metadata
                timestamp = match.get('timestamp')
                player_points = player.get('points')
                player_point_type = player.get('point_type')
                player_rank = player.get('rank')
                player_group = player.get('group')
                opponent_points = opponent.get('points')
                opponent_point_type = opponent.get('point_type')
                opponent_rank = opponent.get('rank')
                opponent_group = opponent.get('group')
            else:
                # Legacy format
                played_craft = match.get('played_craft')
                opponent_craft = match.get('opponent_craft')
                timestamp = None
                player_points = None
                player_point_type = None
                player_rank = None
                player_group = None
                opponent_points = None
                opponent_point_type = None
                opponent_rank = None
                opponent_group = None

            # Validate required fields
            win = match.get('win')
            if win is None:
                return web.json_response(
                    {"success": False, "error": f"Match {idx}: 'win' field is required"},
                    status=400
                )

            brick = match.get('brick', False)

            # Validate crafts
            if played_craft not in CRAFTS:
                return web.json_response(
                    {"success": False, "error": f"Match {idx}: Invalid played_craft '{played_craft}'. Must be one of: {', '.join(CRAFTS)}"},
                    status=400
                )

            if opponent_craft not in CRAFTS:
                return web.json_response(
                    {"success": False, "error": f"Match {idx}: Invalid opponent_craft '{opponent_craft}'. Must be one of: {', '.join(CRAFTS)}"},
                    status=400
                )

            # Add to validated list
            validated_matches.append({
                'played_craft': played_craft,
                'opponent_craft': opponent_craft,
                'win': win,
                'brick': brick,
                'timestamp': timestamp,
                'player_points': player_points,
                'player_point_type': player_point_type,
                'player_rank': player_rank,
                'player_group': player_group,
                'opponent_points': opponent_points,
                'opponent_point_type': opponent_point_type,
                'opponent_rank': opponent_rank,
                'opponent_group': opponent_group
            })

        # All matches validated, now record them
        match_ids = []
        for match_data in validated_matches:
            match_id = await record_match(
                user_id, server_id,
                match_data['played_craft'],
                match_data['opponent_craft'],
                match_data['win'],
                match_data['brick'],
                source="api",
                timestamp=match_data['timestamp'],
                player_points=match_data['player_points'],
                player_point_type=match_data['player_point_type'],
                player_rank=match_data['player_rank'],
                player_group=match_data['player_group'],
                opponent_points=match_data['opponent_points'],
                opponent_point_type=match_data['opponent_point_type'],
                opponent_rank=match_data['opponent_rank'],
                opponent_group=match_data['opponent_group']
            )
            match_ids.append(match_id)

        # Get guild, channel, and member for dashboard update
        if not bot_instance:
            api_logger.error("Bot instance not available")
            return web.json_response(
                {"success": False, "error": "Bot not initialized"},
                status=503
            )

        guild = bot_instance.get_guild(DEV_SERVER_ID)
        if not guild:
            api_logger.error(f"Development server (ID: {DEV_SERVER_ID}) not found")
            return web.json_response(
                {"success": False, "error": "Development server not found"},
                status=404
            )

        member = guild.get_member(int(user_id))
        if not member:
            api_logger.error(f"Member {user_id} not found in development server")
            return web.json_response(
                {"success": False, "error": f"User {user_id} not found in development server"},
                status=404
            )

        sv_channel_id = await get_sv_channel_id(server_id)
        if not sv_channel_id:
            api_logger.error(f"No Shadowverse channel configured for development server")
            return web.json_response(
                {"success": False, "error": "No Shadowverse channel configured for development server"},
                status=404
            )

        channel = guild.get_channel(sv_channel_id)
        if not channel:
            api_logger.error(f"Shadowverse channel {sv_channel_id} not found in development server")
            return web.json_response(
                {"success": False, "error": "Shadowverse channel not found"},
                status=404
            )

        # Update dashboard once
        api_logger.info(f"Updating dashboard for user {user_id} (batch: {len(match_ids)} matches)")
        await update_dashboard_message(member, channel)

        # Send/update notification once with total count
        bot_name = bot_instance.user.name if bot_instance.user else "Kanami"

        # Update notification count by the batch size
        if user_id in active_api_notifications:
            # Increment existing notification by batch size
            notification_data = active_api_notifications[user_id]
            notification_data["count"] += len(match_ids)
            count = notification_data["count"]
            message = notification_data["message"]

            # Cancel old timer
            if notification_data["timer"] and not notification_data["timer"].done():
                notification_data["timer"].cancel()

            # Update message
            match_word = "match" if count == 1 else "matches"
            new_content = f"{bot_name} has received **{count} {match_word}** from <@{user_id}>"

            try:
                await message.edit(content=new_content)
                api_logger.info(f"Updated API notification for user {user_id} (batch: +{len(match_ids)}, total: {count})")
            except discord.NotFound:
                # Message was deleted, create new one
                del active_api_notifications[user_id]
                await send_or_update_api_notification(channel, user_id, bot_name)
                for _ in range(len(match_ids) - 1):  # -1 because first one already sent
                    await send_or_update_api_notification(channel, user_id, bot_name)
            except Exception as e:
                api_logger.error(f"Failed to update notification for user {user_id}: {e}")

            # Start new timer
            notification_data["timer"] = asyncio.create_task(delete_notification_after_delay(user_id, 30))
        else:
            # Send new notification with batch count
            for _ in range(len(match_ids)):
                await send_or_update_api_notification(channel, user_id, bot_name)

        # Return success response
        count = len(match_ids)
        match_word = "match" if count == 1 else "matches"
        response_data = {
            "success": True,
            "message": f"{count} {match_word} logged successfully and dashboard updated",
            "count": count,
            "match_ids": match_ids
        }

        api_logger.info(f"Successfully logged {count} matches for user {user_id}")
        return web.json_response(response_data, status=200)

    except ValueError as e:
        api_logger.error(f"ValueError in log_batch: {e}")
        return web.json_response(
            {"success": False, "error": str(e)},
            status=400
        )
    except Exception as e:
        api_logger.error(f"Unexpected error in log_batch: {e}", exc_info=True)
        return web.json_response(
            {"success": False, "error": "Internal server error. Check bot logs."},
            status=500
        )

async def handle_health_check(request):
    """
    GET /api/health
    
    Simple health check endpoint to verify the API is running.
    
    Response (JSON):
    {
        "status": "ok",
        "bot_connected": true,
        "bot_user": "BotName#1234"
    }
    """
    return web.json_response({
        "status": "ok",
        "bot_connected": bot_instance.is_ready() if bot_instance else False,
        "bot_user": str(bot_instance.user) if (bot_instance and bot_instance.user) else "Not connected"
    })

async def handle_validate_key(request):
    """
    GET /api/validate_key

    Validates an API key without performing any actions.
    Useful for testing authentication.

    Headers:
        X-API-Key: your_secret_key

    Response (JSON):
    {
        "valid": true,
        "description": "user_description",
        "mapped_user_id": "123456789012345678"
    }
    """
    is_valid, error_msg, api_key_name = validate_api_key(request)

    if is_valid:
        mapped_user_id = get_user_id_from_api_key(api_key_name)
        return web.json_response({
            "valid": True,
            "description": VALID_API_KEYS.get(api_key_name, "Unknown"),
            "mapped_user_id": mapped_user_id if mapped_user_id else None
        })
    else:
        return web.json_response({
            "valid": False,
            "error": error_msg
        }, status=401)

async def handle_remove_match(request):
    """
    DELETE /api/shadowverse/match/{match_id}

    Removes a match by its ID. Only the user who created the match can remove it.

    Headers:
        X-API-Key: your_secret_key

    Path Parameters:
        match_id: The ID of the match to remove

    Response (JSON):
    {
        "success": true,
        "message": "Match removed successfully",
        "match": {
            "id": 123,
            "played_craft": "Dragoncraft",
            "opponent_craft": "Forestcraft",
            "win": true,
            "brick": false
        }
    }
    """
    # Validate API key
    is_valid, error_msg, api_key_name = validate_api_key(request)
    if not is_valid:
        api_logger.warning(f"Unauthorized match removal attempt from {request.remote}")
        return web.json_response(
            {"success": False, "error": error_msg},
            status=401
        )

    # Get user_id from API key mapping
    user_id = get_user_id_from_api_key(api_key_name)
    if not user_id:
        return web.json_response(
            {"success": False, "error": "API key is not mapped to a user_id"},
            status=400
        )

    # Get match_id from path
    match_id_str = request.match_info.get('match_id')
    try:
        match_id = int(match_id_str)
    except (ValueError, TypeError):
        return web.json_response(
            {"success": False, "error": "Invalid match_id. Must be an integer."},
            status=400
        )

    # Remove the match
    try:
        success, message, match_data = await remove_match_by_id(match_id, user_id)

        if success:
            # Get the guild and channel for dashboard update
            if bot_instance:
                guild = bot_instance.get_guild(DEV_SERVER_ID)
                if guild:
                    member = guild.get_member(int(user_id))
                    if member:
                        sv_channel_id = await get_sv_channel_id(str(DEV_SERVER_ID))
                        if sv_channel_id:
                            channel = guild.get_channel(sv_channel_id)
                            if channel:
                                await update_dashboard_message(member, channel)
                                api_logger.info(f"Dashboard updated after match removal for user {user_id}")

            api_logger.info(f"Match {match_id} removed by user {user_id}")
            return web.json_response({
                "success": True,
                "message": message,
                "match": match_data
            }, status=200)
        else:
            api_logger.warning(f"Failed to remove match {match_id} for user {user_id}: {message}")
            return web.json_response({
                "success": False,
                "error": message
            }, status=404 if "not found" in message.lower() else 403)

    except Exception as e:
        api_logger.error(f"Error removing match {match_id}: {e}", exc_info=True)
        return web.json_response(
            {"success": False, "error": f"Internal server error: {str(e)}"},
            status=500
        )

async def handle_list_matches(request):
    """
    GET /api/shadowverse/matches

    Lists recent matches for the authenticated user.

    Headers:
        X-API-Key: your_secret_key

    Query Parameters:
        limit: Maximum number of matches to return (default: 10, max: 50)

    Response (JSON):
    {
        "success": true,
        "matches": [
            {
                "id": 123,
                "played_craft": "Dragoncraft",
                "opponent_craft": "Forestcraft",
                "win": true,
                "brick": false,
                "timestamp": "2025-12-16T23:22:20.266767",
                "player": {"points": 45000, "point_type": "RP", "rank": "A1", "group": "Topaz"},
                "opponent": {"points": 48000, "point_type": "RP", "rank": "A2", "group": "Topaz"},
                "created_at": "2025-12-16 23:22:20"
            },
            ...
        ]
    }
    """
    # Validate API key
    is_valid, error_msg, api_key_name = validate_api_key(request)
    if not is_valid:
        api_logger.warning(f"Unauthorized match list request from {request.remote}")
        return web.json_response(
            {"success": False, "error": error_msg},
            status=401
        )

    # Get user_id from API key mapping
    user_id = get_user_id_from_api_key(api_key_name)
    if not user_id:
        return web.json_response(
            {"success": False, "error": "API key is not mapped to a user_id"},
            status=400
        )

    # Get limit from query parameters
    limit_str = request.rel_url.query.get('limit', '10')
    try:
        limit = int(limit_str)
        limit = max(1, min(limit, 50))  # Clamp between 1 and 50
    except ValueError:
        limit = 10

    # Get recent matches
    try:
        matches = await get_recent_matches(user_id, str(DEV_SERVER_ID), limit)
        api_logger.info(f"Returning {len(matches)} matches for user {user_id}")

        return web.json_response({
            "success": True,
            "matches": matches,
            "count": len(matches)
        }, status=200)

    except Exception as e:
        api_logger.error(f"Error listing matches for user {user_id}: {e}", exc_info=True)
        return web.json_response(
            {"success": False, "error": f"Internal server error: {str(e)}"},
            status=500
        )

# --- Plan C: Event Management Routes ---

async def handle_list_events(request):
    is_valid, error_msg, _ = validate_api_key(request)
    if not is_valid:
        return web.json_response({"success": False, "error": error_msg}, status=401)

    profile = request.match_info["profile"].upper()
    if profile not in event_manager.PROFILE_CONFIG:
        return web.json_response({"success": False, "error": "Invalid profile"}, status=404)
    
    try:
        events = await event_manager.get_events(profile)
        # Convert local image paths to API-accessible URLs
        _base = os.path.dirname(os.path.abspath(__file__))
        for ev in events:
            img = ev.get('image')
            if img and not img.startswith(('http://', 'https://')):
                img_clean = img.replace('\\', '/')
                # Prefer horizontal combined image for the web control panel
                if 'combined_v_' in img_clean:
                    h_img = img_clean.replace('combined_v_', 'combined_h_')
                    if os.path.exists(os.path.join(_base, h_img)):
                        img_clean = h_img
                ev['image'] = '/' + img_clean
        return web.json_response({"success": True, "events": events})
    except Exception as e:
        api_logger.error(f"Error listing events: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_get_event(request):
    is_valid, error_msg, _ = validate_api_key(request)
    if not is_valid:
        return web.json_response({"success": False, "error": error_msg}, status=401)

    profile = request.match_info["profile"].upper()
    event_id = request.match_info["event_id"]
    
    if profile not in event_manager.PROFILE_CONFIG:
        return web.json_response({"success": False, "error": "Invalid profile"}, status=404)

    try:
        event = await event_manager.get_event_by_id(profile, event_id)
        if not event:
            return web.json_response({"success": False, "error": "Event not found"}, status=404)
        img = event.get('image')
        if img and not img.startswith(('http://', 'https://')):
            img_clean = img.replace('\\', '/')
            if 'combined_v_' in img_clean:
                h_img = img_clean.replace('combined_v_', 'combined_h_')
                _base = os.path.dirname(os.path.abspath(__file__))
                if os.path.exists(os.path.join(_base, h_img)):
                    img_clean = h_img
            event['image'] = '/' + img_clean
        return web.json_response({"success": True, "event": event})
    except Exception as e:
        api_logger.error(f"Error getting event: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_add_event(request):
    is_valid, error_msg, _ = validate_api_key(request)
    if not is_valid:
        return web.json_response({"success": False, "error": error_msg}, status=401)

    profile = request.match_info["profile"].upper()
    if profile not in event_manager.PROFILE_CONFIG:
        return web.json_response({"success": False, "error": "Invalid profile"}, status=404)

    try:
        data = await request.json()
        # Validate required fields
        required = ["title", "category", "start_unix", "end_unix"]
        if not all(k in data for k in required):
             return web.json_response({"success": False, "error": "Missing fields"}, status=400)

        # Construct event_data for add_event
        event_data = {
            "title": data["title"],
            "category": data["category"],
            "start": str(data["start_unix"]),
            "end": str(data["end_unix"]),
            "image": data.get("image"),
            "description": data.get("description", "")
        }

        # Create a dummy context for add_event (it expects ctx.author.id)
        class DummyCtx:
            class Author:
                id = str(OWNER_USER_ID)
            author = Author()
            async def send(self, msg, **kwargs):
                pass # Suppress output

        await event_manager.PROFILE_CONFIG[profile]["add_event"](DummyCtx(), event_data)
        return web.json_response({"success": True, "message": "Event added"})
    except Exception as e:
        api_logger.error(f"Error adding event: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_update_event(request):
    is_valid, error_msg, _ = validate_api_key(request)
    if not is_valid:
        return web.json_response({"success": False, "error": error_msg}, status=401)

    profile = request.match_info["profile"].upper()
    event_id = request.match_info["event_id"]
    
    if profile not in event_manager.PROFILE_CONFIG:
        return web.json_response({"success": False, "error": "Invalid profile"}, status=404)

    try:
        data = await request.json()
        await event_manager.update_event(
            profile,
            event_id,
            data["title"], 
            data["category"], 
            str(data["start_unix"]), 
            str(data["end_unix"]), 
            data.get("image")
        )
        return web.json_response({"success": True, "message": "Event updated"})
    except Exception as e:
        api_logger.error(f"Error updating event: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_remove_event(request):
    is_valid, error_msg, _ = validate_api_key(request)
    if not is_valid:
        return web.json_response({"success": False, "error": error_msg}, status=401)

    profile = request.match_info["profile"].upper()
    event_id = request.match_info["event_id"]
    
    if profile not in event_manager.PROFILE_CONFIG:
        return web.json_response({"success": False, "error": "Invalid profile"}, status=404)

    try:
        success = await event_manager.remove_event_by_id(profile, event_id)
        if success:
            return web.json_response({"success": True, "message": "Event removed"})
        else:
            return web.json_response({"success": False, "error": "Event not found"}, status=404)
    except Exception as e:
        api_logger.error(f"Error removing event: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_list_notifications(request):
    is_valid, error_msg, _ = validate_api_key(request)
    if not is_valid:
        return web.json_response({"success": False, "error": error_msg}, status=401)

    profile = request.match_info["profile"].upper()
    event_id = request.match_info["event_id"]
    
    if profile not in event_manager.PROFILE_CONFIG:
        return web.json_response({"success": False, "error": "Invalid profile"}, status=404)

    try:
        notifs = await event_manager.get_pending_notifications_for_event(profile, event_id)
        return web.json_response({"success": True, "notifications": notifs})
    except Exception as e:
        api_logger.error(f"Error listing notifications: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_remove_notification(request):
    is_valid, error_msg, _ = validate_api_key(request)
    if not is_valid:
        return web.json_response({"success": False, "error": error_msg}, status=401)

    notif_id = request.match_info["notif_id"]
    try:
        await event_manager.remove_pending_notification(int(notif_id))
        return web.json_response({"success": True, "message": "Notification removed"})
    except Exception as e:
        api_logger.error(f"Error removing notification: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_update_notification(request):
    is_valid, error_msg, _ = validate_api_key(request)
    if not is_valid:
        return web.json_response({"success": False, "error": error_msg}, status=401)

    notif_id = request.match_info["notif_id"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid JSON body"}, status=400)

    try:
        if "custom_message" in data:
            await event_manager.update_notification_message(int(notif_id), data["custom_message"] or None)
        return web.json_response({"success": True, "message": "Notification updated"})
    except Exception as e:
        api_logger.error(f"Error updating notification: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_refresh_notifications(request):
    is_valid, error_msg, _ = validate_api_key(request)
    if not is_valid:
        return web.json_response({"success": False, "error": error_msg}, status=401)

    profile = request.match_info["profile"].upper()
    event_id = request.match_info["event_id"]
    
    if profile not in event_manager.PROFILE_CONFIG:
        return web.json_response({"success": False, "error": "Invalid profile"}, status=404)

    try:
        await event_manager.refresh_pending_notifications_for_event(profile, event_id)
        return web.json_response({"success": True, "message": "Notifications refreshed"})
    except Exception as e:
        api_logger.error(f"Error refreshing notifications: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_refresh_dashboard(request):
    is_valid, error_msg, _ = validate_api_key(request)
    if not is_valid:
        return web.json_response({"success": False, "error": error_msg}, status=401)

    profile = request.match_info["profile"].upper()
    if profile not in event_manager.PROFILE_CONFIG:
        return web.json_response({"success": False, "error": "Invalid profile"}, status=404)

    try:
        await event_manager.PROFILE_CONFIG[profile]["update_timers"]()
        return web.json_response({"success": True, "message": "Dashboard refreshed"})
    except Exception as e:
        api_logger.error(f"Error refreshing dashboard: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

def create_app():
    """
    Creates and configures the aiohttp web application.
    """
    app = web.Application()

    # Configure CORS if available
    if aiohttp_cors:
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            )
        })
    else:
        cors = None

    # Add routes
    app.router.add_post('/api/shadowverse/log_match', handle_log_match)
    app.router.add_post('/api/shadowverse/log_batch', handle_log_batch)
    app.router.add_delete('/api/shadowverse/match/{match_id}', handle_remove_match)
    app.router.add_get('/api/shadowverse/matches', handle_list_matches)
    app.router.add_get('/api/health', handle_health_check)
    app.router.add_get('/api/validate_key', handle_validate_key)
    
    # Plan C Routes
    app.router.add_get('/api/events/{profile}', handle_list_events)
    app.router.add_get('/api/events/{profile}/{event_id}', handle_get_event)
    app.router.add_post('/api/events/{profile}', handle_add_event)
    app.router.add_put('/api/events/{profile}/{event_id}', handle_update_event)
    app.router.add_delete('/api/events/{profile}/{event_id}', handle_remove_event)
    
    app.router.add_get('/api/events/{profile}/{event_id}/notifications', handle_list_notifications)
    app.router.add_delete('/api/notifications/{notif_id}', handle_remove_notification)
    app.router.add_patch('/api/notifications/{notif_id}', handle_update_notification)
    app.router.add_post('/api/events/{profile}/{event_id}/notifications/refresh', handle_refresh_notifications)
    
    app.router.add_post('/api/dashboard/{profile}/refresh', handle_refresh_dashboard)

    # Serve local event images (combined banners etc.)
    _data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    if os.path.isdir(_data_dir):
        app.router.add_static('/data', _data_dir)

    # Add CORS to all routes
    if cors:
        for route in list(app.router.routes()):
            cors.add(route)

    return app

async def start_api_server(host='0.0.0.0', port=8080):
    """
    Starts the API server.
    
    Args:
        host: Host to bind to (0.0.0.0 for all interfaces)
        port: Port to listen on (default: 8080)
    """
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    api_logger.info(f"API Server started on http://{host}:{port}")
    api_logger.info(f"Endpoints available:")
    api_logger.info(f"  POST   http://{host}:{port}/api/shadowverse/log_match")
    api_logger.info(f"  DELETE http://{host}:{port}/api/shadowverse/match/{{match_id}}")
    api_logger.info(f"  GET    http://{host}:{port}/api/shadowverse/matches")
    api_logger.info(f"  GET    http://{host}:{port}/api/health")
    api_logger.info(f"  GET    http://{host}:{port}/api/validate_key")
    api_logger.info(f"API keys loaded from {API_KEYS_FILE}")
    
    return runner

# For standalone testing
if __name__ == "__main__":
    import asyncio
    
    async def main():
        await start_api_server()
        # Keep running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            print("Shutting down API server...")
    
    asyncio.run(main())
