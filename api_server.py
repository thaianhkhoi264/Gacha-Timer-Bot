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
from bot import bot
from global_config import DEV_SERVER_ID
import logging

# Configure logging
api_logger = logging.getLogger("api_server")
api_logger.setLevel(logging.INFO)

# Load API keys from environment or config file
API_KEYS_FILE = "api_keys.json"

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

def validate_api_key(request):
    """
    Validates the API key from the request.
    Checks both 'X-API-Key' header and 'api_key' in JSON body.
    Returns (is_valid, error_message)
    """
    # Check header first
    api_key = request.headers.get('X-API-Key')
    
    # If not in header, check body (will be checked later when parsing JSON)
    if not api_key:
        return False, "Missing API key. Provide via 'X-API-Key' header or 'api_key' in body."
    
    if api_key not in VALID_API_KEYS:
        api_logger.warning(f"Invalid API key attempt: {api_key[:10]}...")
        return False, "Invalid API key."
    
    return True, None

async def handle_log_match(request):
    """
    POST /api/shadowverse/log_match
    
    Logs a Shadowverse match and updates the user's dashboard.
    Automatically uses the development server (DEV_SERVER_ID from global_config.py).
    
    Request Body (JSON):
    {
        "api_key": "your_secret_key",  // Optional if using X-API-Key header
        "user_id": "123456789012345678",  // Discord user ID (string)
        "played_craft": "Dragoncraft",  // One of: Forestcraft, Swordcraft, Runecraft, Dragoncraft, Abysscraft, Havencraft, Portalcraft
        "opponent_craft": "Forestcraft",  // Same options as above
        "win": true,  // Boolean: true for win, false for loss
        "brick": false  // Boolean: true if bricked, false otherwise (optional, defaults to false)
    }
    
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
        is_valid, error_msg = validate_api_key(request)
        if not is_valid:
            # Try to get from body if header validation failed
            api_key_body = data.get('api_key')
            if api_key_body and api_key_body in VALID_API_KEYS:
                is_valid = True
            else:
                api_logger.warning(f"Unauthorized API request from {request.remote}")
                return web.json_response(
                    {"success": False, "error": error_msg},
                    status=401
                )
        
        # Validate required fields (server_id is now automatic)
        required_fields = ['user_id', 'played_craft', 'opponent_craft', 'win']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return web.json_response(
                {"success": False, "error": f"Missing required fields: {', '.join(missing_fields)}"},
                status=400
            )
        
        # Extract and validate data
        user_id = str(data['user_id'])
        server_id = str(DEV_SERVER_ID)  # Automatically use development server
        played_craft = data['played_craft']
        opponent_craft = data['opponent_craft']
        win = bool(data['win'])
        brick = bool(data.get('brick', False))
        
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
        await record_match(user_id, server_id, played_craft, opponent_craft, win, brick)
        
        # Get the guild and channel for dashboard update
        guild = bot.get_guild(DEV_SERVER_ID)
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
        "bot_connected": bot.is_ready(),
        "bot_user": str(bot.user) if bot.user else "Not connected"
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
        "description": "user_description"
    }
    """
    is_valid, error_msg = validate_api_key(request)
    
    if is_valid:
        api_key = request.headers.get('X-API-Key')
        return web.json_response({
            "valid": True,
            "description": VALID_API_KEYS.get(api_key, "Unknown")
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
