"""
REST API module for Gacha Timer Bot.

This module provides a modular REST API using aiohttp:
- Health check endpoint
- API key authentication
- Shadowverse match logging endpoints

Usage:
    from src.api import create_api_server, start_api_server

    # Create and start the API server
    app, runner = await create_api_server(
        host='0.0.0.0',
        port=8080,
        bot_instance=bot,
    )

    # Later, to stop:
    await runner.cleanup()
"""

import asyncio
import logging
from typing import Optional, Any, Tuple

from aiohttp import web

from src.api.middleware import (
    APIKeyAuth,
    create_auth_middleware,
    create_logging_middleware,
    create_error_middleware,
)
from src.api.routes import (
    setup_routes,
    ShadowverseRoutes,
    NotificationRoutes,
)
from src.api.models import (
    ShadowverseCraft,
    MatchResult,
    LogMatchRequest,
    LogBatchRequest,
    LogMatchResponse,
    LogBatchResponse,
    HealthResponse,
    ValidateKeyResponse,
    APIResponse,
)

logger = logging.getLogger("api")

# Module version
__version__ = "3.0.0"


async def create_api_server(
    host: str = '0.0.0.0',
    port: int = 8080,
    bot_instance: Any = None,
    api_keys_file: str = None,
    sv_channel_id: int = None,
    record_match_func=None,
    remove_match_func=None,
    get_matches_func=None,
    update_dashboard_func=None,
    enable_auth: bool = True,
) -> Tuple[web.Application, web.AppRunner]:
    """
    Create and configure the API server.

    Args:
        host: Host to bind to
        port: Port to bind to
        bot_instance: Discord bot instance (for notifications)
        api_keys_file: Path to API keys JSON file
        sv_channel_id: Shadowverse channel ID for notifications
        record_match_func: Function to record matches
        remove_match_func: Function to remove matches
        get_matches_func: Function to get matches
        update_dashboard_func: Function to update dashboard
        enable_auth: Whether to enable API key authentication

    Returns:
        Tuple of (Application, AppRunner)
    """
    # Initialize middleware
    middlewares = [
        create_error_middleware(),
        create_logging_middleware(),
    ]

    auth = None
    if enable_auth:
        auth = APIKeyAuth(api_keys_file)
        middlewares.append(create_auth_middleware(auth))

    # Create application
    app = web.Application(middlewares=middlewares)

    # Store bot reference
    app['bot'] = bot_instance

    # Configure routes
    shadowverse_routes = None
    if any([record_match_func, remove_match_func, get_matches_func]):
        shadowverse_routes = ShadowverseRoutes(
            record_match_func=record_match_func,
            remove_match_func=remove_match_func,
            get_matches_func=get_matches_func,
            update_dashboard_func=update_dashboard_func,
            bot_instance=bot_instance,
            sv_channel_id=sv_channel_id,
        )

    setup_routes(app, auth=auth, shadowverse_routes=shadowverse_routes)

    # Create runner
    runner = web.AppRunner(app)
    await runner.setup()

    # Create site
    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info(f"API server started on http://{host}:{port}")

    return app, runner


async def start_api_server(
    host: str = '0.0.0.0',
    port: int = 8080,
    **kwargs,
) -> Tuple[web.Application, web.AppRunner]:
    """
    Start the API server (alias for create_api_server).

    This function exists for backwards compatibility.
    """
    return await create_api_server(host, port, **kwargs)


async def stop_api_server(runner: web.AppRunner):
    """
    Stop the API server.

    Args:
        runner: The AppRunner returned from create_api_server
    """
    if runner:
        await runner.cleanup()
        logger.info("API server stopped")


class APIServer:
    """
    API Server manager class.

    Provides a context manager interface for the API server.

    Usage:
        async with APIServer(port=8080, bot_instance=bot) as server:
            # Server is running
            await asyncio.sleep(3600)
        # Server is stopped
    """

    def __init__(
        self,
        host: str = '0.0.0.0',
        port: int = 8080,
        **kwargs,
    ):
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None

    async def start(self):
        """Start the API server."""
        self.app, self.runner = await create_api_server(
            self.host,
            self.port,
            **self.kwargs,
        )

    async def stop(self):
        """Stop the API server."""
        await stop_api_server(self.runner)
        self.app = None
        self.runner = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self.runner is not None


__all__ = [
    # Server functions
    'create_api_server',
    'start_api_server',
    'stop_api_server',
    'APIServer',
    # Middleware
    'APIKeyAuth',
    'create_auth_middleware',
    'create_logging_middleware',
    'create_error_middleware',
    # Routes
    'setup_routes',
    'ShadowverseRoutes',
    'NotificationRoutes',
    # Models
    'ShadowverseCraft',
    'MatchResult',
    'LogMatchRequest',
    'LogBatchRequest',
    'LogMatchResponse',
    'LogBatchResponse',
    'HealthResponse',
    'ValidateKeyResponse',
    'APIResponse',
]
