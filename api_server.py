"""
REST API Server for Gacha Timer Bot
Allows external programs to log Shadowverse matches programmatically.
"""

from aiohttp import web
import aiosqlite
import json
import os
from shadowverse_handler import (
    record_match,
    update_dashboard_message,
    get_sv_channel_id,
    CRAFTS
)
from global_config import DEV_SERVER_ID
import logging

# Configure logging
api_logger = logging.getLogger("api_server")
api_logger.setLevel(logging.INFO)

# Bot instance will be set by main.py to avoid circular imports
bot_instance = None

# Load API keys from environment or config file
API_KEYS_FILE = "api_keys.json"

# Map user descriptions (from api_keys.json) to Discord user IDs
# When an API key is used, we look up its description and map it to a Discord ID
USER_DESCRIPTION_TO_ID = {
    "Narisurii": "680653908259110914",  # Owner
    "Alfabem": "264758014198808577",
    "Naito": "443416461457883136",
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
        await record_match(
            user_id, server_id, played_craft, opponent_craft, win, brick,
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
        
        # Return success response
        response_data = {
            "success": True,
            "message": "Match logged successfully and dashboard updated",
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

def create_app():
    """
    Creates and configures the aiohttp web application.
    """
    app = web.Application()
    
    # Add routes
    app.router.add_post('/api/shadowverse/log_match', handle_log_match)
    app.router.add_get('/api/health', handle_health_check)
    app.router.add_get('/api/validate_key', handle_validate_key)
    
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
    api_logger.info(f"  POST http://{host}:{port}/api/shadowverse/log_match")
    api_logger.info(f"  GET  http://{host}:{port}/api/health")
    api_logger.info(f"  GET  http://{host}:{port}/api/validate_key")
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
