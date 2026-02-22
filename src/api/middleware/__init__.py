"""
API middleware for request processing.

This module provides middleware components:
- API key authentication
- Request logging
- Error handling
"""

import os
import json
import logging
from typing import Dict, Optional, Tuple, Callable
from aiohttp import web

logger = logging.getLogger("api.middleware")


# =============================================================================
# API Key Authentication
# =============================================================================

class APIKeyAuth:
    """
    API key authentication middleware.

    Validates requests using X-API-Key header or api_key in JSON body.
    """

    DEFAULT_KEYS_FILE = "api_keys.json"

    # Map user descriptions to Discord user IDs
    USER_DESCRIPTION_TO_ID = {
        "Narisurii": "680653908259110914",
        "Alfabem": "264758014198808577",
        "Naito": "443416461457883136",
        "SteveGHShadow": "220457675475910656",
    }

    def __init__(self, keys_file: str = None):
        """
        Initialize the auth middleware.

        Args:
            keys_file: Path to API keys JSON file
        """
        self.keys_file = keys_file or self.DEFAULT_KEYS_FILE
        self.valid_keys: Dict[str, str] = {}
        self._load_keys()

    def _load_keys(self):
        """Load API keys from file."""
        if os.path.exists(self.keys_file):
            try:
                with open(self.keys_file, 'r') as f:
                    self.valid_keys = json.load(f)
                logger.info(f"Loaded {len(self.valid_keys)} API keys")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load API keys: {e}")
                self.valid_keys = {}
        else:
            self._create_default_keys()

    def _create_default_keys(self):
        """Create default API keys file."""
        default_keys = {
            "CHANGE_ME_secret_key_123": "Example API Key - REPLACE THIS"
        }
        try:
            with open(self.keys_file, 'w') as f:
                json.dump(default_keys, f, indent=2)
            logger.warning(
                f"Created default {self.keys_file}. "
                "Please update with your own API keys!"
            )
            self.valid_keys = default_keys
        except IOError as e:
            logger.error(f"Failed to create default API keys file: {e}")
            self.valid_keys = {}

    def reload_keys(self):
        """Reload API keys from file."""
        self._load_keys()

    def validate(self, request: web.Request) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate the API key from a request.

        Args:
            request: The aiohttp request object

        Returns:
            Tuple of (is_valid, error_message, api_key)
        """
        api_key = request.headers.get('X-API-Key')

        if not api_key:
            return False, "Missing API key. Provide via 'X-API-Key' header.", None

        if api_key not in self.valid_keys:
            logger.warning(f"Invalid API key attempt: {api_key[:10]}...")
            return False, "Invalid API key.", None

        return True, None, api_key

    def get_user_id(self, api_key: str) -> Optional[str]:
        """
        Get the Discord user ID associated with an API key.

        Args:
            api_key: The validated API key

        Returns:
            Discord user ID or None
        """
        if api_key not in self.valid_keys:
            return None

        description = self.valid_keys[api_key]
        return self.USER_DESCRIPTION_TO_ID.get(description)

    def get_description(self, api_key: str) -> Optional[str]:
        """Get the description for an API key."""
        return self.valid_keys.get(api_key)


def create_auth_middleware(auth: APIKeyAuth):
    """
    Create an aiohttp middleware for API key authentication.

    Args:
        auth: APIKeyAuth instance

    Returns:
        aiohttp middleware function
    """
    @web.middleware
    async def auth_middleware(request: web.Request, handler: Callable):
        # Skip auth for health check
        if request.path == '/api/health':
            return await handler(request)

        is_valid, error, api_key = auth.validate(request)

        if not is_valid:
            return web.json_response(
                {"error": error, "success": False},
                status=401
            )

        # Store validated key in request for route handlers
        request['api_key'] = api_key
        request['user_id'] = auth.get_user_id(api_key)

        return await handler(request)

    return auth_middleware


# =============================================================================
# Request Logging Middleware
# =============================================================================

def create_logging_middleware():
    """Create an aiohttp middleware for request logging."""
    @web.middleware
    async def logging_middleware(request: web.Request, handler: Callable):
        logger.info(f"{request.method} {request.path}")

        try:
            response = await handler(request)
            logger.info(f"{request.method} {request.path} -> {response.status}")
            return response
        except web.HTTPException as e:
            logger.warning(f"{request.method} {request.path} -> {e.status}")
            raise
        except Exception as e:
            logger.error(f"{request.method} {request.path} -> Error: {e}")
            raise

    return logging_middleware


# =============================================================================
# Error Handling Middleware
# =============================================================================

def create_error_middleware():
    """Create an aiohttp middleware for error handling."""
    @web.middleware
    async def error_middleware(request: web.Request, handler: Callable):
        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON in request body", "success": False},
                status=400
            )
        except Exception as e:
            logger.exception(f"Unhandled error in {request.path}")
            return web.json_response(
                {"error": "Internal server error", "success": False},
                status=500
            )

    return error_middleware


__all__ = [
    'APIKeyAuth',
    'create_auth_middleware',
    'create_logging_middleware',
    'create_error_middleware',
]
