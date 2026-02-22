"""
API route handlers.

This module provides route handlers for the REST API:
- Health check endpoint
- Shadowverse match logging endpoints
- Key validation endpoint
"""

import logging
from typing import Optional, Callable, Any
from aiohttp import web

from src.api.models import (
    LogMatchRequest,
    LogBatchRequest,
    LogMatchResponse,
    LogBatchResponse,
    HealthResponse,
    ValidateKeyResponse,
    APIResponse,
)

logger = logging.getLogger("api.routes")


# =============================================================================
# Health Routes
# =============================================================================

async def handle_health_check(request: web.Request) -> web.Response:
    """
    Health check endpoint.

    GET /api/health

    Returns:
        {"status": "healthy", "version": "3.0.0"}
    """
    response = HealthResponse()
    return web.json_response(response.to_dict())


# =============================================================================
# Validation Routes
# =============================================================================

def create_validate_key_handler(auth):
    """
    Create the validate key handler with auth dependency.

    Args:
        auth: APIKeyAuth instance

    Returns:
        Route handler function
    """
    async def handle_validate_key(request: web.Request) -> web.Response:
        """
        Validate an API key.

        GET /api/validate_key
        Headers: X-API-Key

        Returns:
            {"valid": true/false, "description": "..."}
        """
        api_key = request.get('api_key')

        if api_key:
            description = auth.get_description(api_key)
            response = ValidateKeyResponse(
                success=True,
                valid=True,
                description=description or "Unknown",
            )
        else:
            response = ValidateKeyResponse(
                success=False,
                valid=False,
                description="",
            )

        return web.json_response(response.to_dict())

    return handle_validate_key


# =============================================================================
# Shadowverse Routes
# =============================================================================

class ShadowverseRoutes:
    """
    Route handlers for Shadowverse match logging.

    These handlers can be used standalone or with an injected
    Shadowverse handler for database operations.
    """

    def __init__(
        self,
        record_match_func: Optional[Callable] = None,
        remove_match_func: Optional[Callable] = None,
        get_matches_func: Optional[Callable] = None,
        update_dashboard_func: Optional[Callable] = None,
        bot_instance: Any = None,
        sv_channel_id: int = None,
    ):
        """
        Initialize Shadowverse routes.

        Args:
            record_match_func: Function to record a match to database
            remove_match_func: Function to remove a match by ID
            get_matches_func: Function to get recent matches
            update_dashboard_func: Function to update the dashboard
            bot_instance: Discord bot instance for notifications
            sv_channel_id: Shadowverse channel ID for notifications
        """
        self.record_match = record_match_func
        self.remove_match = remove_match_func
        self.get_matches = get_matches_func
        self.update_dashboard = update_dashboard_func
        self.bot = bot_instance
        self.sv_channel_id = sv_channel_id

    async def handle_log_match(self, request: web.Request) -> web.Response:
        """
        Log a single Shadowverse match.

        POST /api/shadowverse/log_match
        Headers: X-API-Key
        Body: {
            "player_craft": "Forestcraft",
            "opponent_craft": "Swordcraft",
            "result": "win",
            "bricked": false,
            "notes": "optional notes"
        }

        Returns:
            {
                "success": true,
                "match_id": 123,
                "player_craft": "Forestcraft",
                "opponent_craft": "Swordcraft",
                "result": "win",
                "message": "Match logged successfully"
            }
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                APIResponse(success=False, error="Invalid JSON body").to_dict(),
                status=400
            )

        match_request = LogMatchRequest.from_dict(data)
        validation_error = match_request.validate()

        if validation_error:
            return web.json_response(
                APIResponse(success=False, error=validation_error).to_dict(),
                status=400
            )

        # Get user ID from request (set by auth middleware)
        user_id = request.get('user_id', '0')

        # Record the match
        if self.record_match:
            try:
                match_id = await self.record_match(
                    user_id=user_id,
                    player_craft=match_request.player_craft,
                    opponent_craft=match_request.opponent_craft,
                    result=match_request.result,
                    bricked=match_request.bricked,
                )

                # Update dashboard if available
                if self.update_dashboard and self.bot:
                    try:
                        await self.update_dashboard(self.bot)
                    except Exception as e:
                        logger.warning(f"Failed to update dashboard: {e}")

                response = LogMatchResponse(
                    success=True,
                    message="Match logged successfully",
                    match_id=match_id,
                    player_craft=match_request.player_craft,
                    opponent_craft=match_request.opponent_craft,
                    result=match_request.result,
                )
                return web.json_response(response.to_dict())

            except Exception as e:
                logger.error(f"Failed to record match: {e}")
                return web.json_response(
                    APIResponse(success=False, error=str(e)).to_dict(),
                    status=500
                )
        else:
            # No record function available (stub mode)
            response = LogMatchResponse(
                success=True,
                message="Match logged (stub mode - no database)",
                match_id=0,
                player_craft=match_request.player_craft,
                opponent_craft=match_request.opponent_craft,
                result=match_request.result,
            )
            return web.json_response(response.to_dict())

    async def handle_log_batch(self, request: web.Request) -> web.Response:
        """
        Log multiple Shadowverse matches in a batch.

        POST /api/shadowverse/log_batch
        Headers: X-API-Key
        Body: {
            "matches": [
                {"player_craft": "...", "opponent_craft": "...", "result": "..."},
                ...
            ]
        }

        Returns:
            {
                "success": true,
                "processed": 10,
                "failed": 0,
                "match_ids": [1, 2, 3, ...]
            }
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                APIResponse(success=False, error="Invalid JSON body").to_dict(),
                status=400
            )

        batch_request = LogBatchRequest.from_dict(data)
        validation_error = batch_request.validate()

        if validation_error:
            return web.json_response(
                APIResponse(success=False, error=validation_error).to_dict(),
                status=400
            )

        user_id = request.get('user_id', '0')
        match_ids = []
        failed = 0

        for match in batch_request.matches:
            if self.record_match:
                try:
                    match_id = await self.record_match(
                        user_id=user_id,
                        player_craft=match.player_craft,
                        opponent_craft=match.opponent_craft,
                        result=match.result,
                        bricked=match.bricked,
                    )
                    match_ids.append(match_id)
                except Exception as e:
                    logger.warning(f"Failed to record match in batch: {e}")
                    failed += 1
            else:
                match_ids.append(0)  # Stub mode

        # Update dashboard once after batch
        if self.update_dashboard and self.bot and match_ids:
            try:
                await self.update_dashboard(self.bot)
            except Exception as e:
                logger.warning(f"Failed to update dashboard: {e}")

        response = LogBatchResponse(
            success=True,
            message=f"Processed {len(match_ids)} matches",
            processed=len(match_ids),
            failed=failed,
            match_ids=match_ids,
        )
        return web.json_response(response.to_dict())

    async def handle_remove_match(self, request: web.Request) -> web.Response:
        """
        Remove a match by ID.

        DELETE /api/shadowverse/match/{match_id}
        Headers: X-API-Key

        Returns:
            {"success": true, "message": "Match removed"}
        """
        match_id_str = request.match_info.get('match_id', '')

        try:
            match_id = int(match_id_str)
        except ValueError:
            return web.json_response(
                APIResponse(success=False, error="Invalid match ID").to_dict(),
                status=400
            )

        user_id = request.get('user_id', '0')

        if self.remove_match:
            try:
                success = await self.remove_match(match_id, user_id)
                if success:
                    # Update dashboard
                    if self.update_dashboard and self.bot:
                        await self.update_dashboard(self.bot)

                    return web.json_response(
                        APIResponse(
                            success=True,
                            message=f"Match {match_id} removed"
                        ).to_dict()
                    )
                else:
                    return web.json_response(
                        APIResponse(
                            success=False,
                            error="Match not found or not owned by you"
                        ).to_dict(),
                        status=404
                    )
            except Exception as e:
                logger.error(f"Failed to remove match: {e}")
                return web.json_response(
                    APIResponse(success=False, error=str(e)).to_dict(),
                    status=500
                )
        else:
            return web.json_response(
                APIResponse(
                    success=True,
                    message="Match removed (stub mode)"
                ).to_dict()
            )

    async def handle_list_matches(self, request: web.Request) -> web.Response:
        """
        List recent matches.

        GET /api/shadowverse/matches?limit=10&offset=0
        Headers: X-API-Key

        Returns:
            {
                "success": true,
                "matches": [...],
                "total": 100
            }
        """
        try:
            limit = int(request.query.get('limit', '10'))
            offset = int(request.query.get('offset', '0'))
        except ValueError:
            return web.json_response(
                APIResponse(success=False, error="Invalid limit or offset").to_dict(),
                status=400
            )

        limit = min(limit, 100)  # Cap at 100
        user_id = request.get('user_id', '0')

        if self.get_matches:
            try:
                matches = await self.get_matches(user_id, limit, offset)
                return web.json_response({
                    "success": True,
                    "matches": matches,
                    "limit": limit,
                    "offset": offset,
                })
            except Exception as e:
                logger.error(f"Failed to get matches: {e}")
                return web.json_response(
                    APIResponse(success=False, error=str(e)).to_dict(),
                    status=500
                )
        else:
            return web.json_response({
                "success": True,
                "matches": [],
                "limit": limit,
                "offset": offset,
                "message": "Stub mode - no database",
            })


def setup_routes(
    app: web.Application,
    auth=None,
    shadowverse_routes: Optional[ShadowverseRoutes] = None,
):
    """
    Set up all API routes.

    Args:
        app: aiohttp Application
        auth: APIKeyAuth instance (optional)
        shadowverse_routes: ShadowverseRoutes instance (optional)
    """
    # Health check (no auth required)
    app.router.add_get('/api/health', handle_health_check)

    # Key validation
    if auth:
        app.router.add_get('/api/validate_key', create_validate_key_handler(auth))

    # Shadowverse routes
    if shadowverse_routes:
        app.router.add_post(
            '/api/shadowverse/log_match',
            shadowverse_routes.handle_log_match
        )
        app.router.add_post(
            '/api/shadowverse/log_batch',
            shadowverse_routes.handle_log_batch
        )
        app.router.add_delete(
            '/api/shadowverse/match/{match_id}',
            shadowverse_routes.handle_remove_match
        )
        app.router.add_get(
            '/api/shadowverse/matches',
            shadowverse_routes.handle_list_matches
        )
    else:
        # Set up stub routes
        stub_routes = ShadowverseRoutes()
        app.router.add_post(
            '/api/shadowverse/log_match',
            stub_routes.handle_log_match
        )
        app.router.add_post(
            '/api/shadowverse/log_batch',
            stub_routes.handle_log_batch
        )
        app.router.add_delete(
            '/api/shadowverse/match/{match_id}',
            stub_routes.handle_remove_match
        )
        app.router.add_get(
            '/api/shadowverse/matches',
            stub_routes.handle_list_matches
        )


__all__ = [
    'handle_health_check',
    'create_validate_key_handler',
    'ShadowverseRoutes',
    'setup_routes',
]
