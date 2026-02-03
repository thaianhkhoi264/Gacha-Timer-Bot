"""
API request and response models.

This module provides dataclasses for API payloads:
- Request models for input validation
- Response models for consistent output format
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from enum import Enum


# =============================================================================
# Shadowverse Models
# =============================================================================

class ShadowverseCraft(str, Enum):
    """Shadowverse craft/class types."""
    FORESTCRAFT = "Forestcraft"
    SWORDCRAFT = "Swordcraft"
    RUNECRAFT = "Runecraft"
    DRAGONCRAFT = "Dragoncraft"
    SHADOWCRAFT = "Shadowcraft"
    BLOODCRAFT = "Bloodcraft"
    HAVENCRAFT = "Havencraft"
    PORTALCRAFT = "Portalcraft"
    ABYSSCRAFT = "Abysscraft"

    @classmethod
    def from_string(cls, value: str) -> Optional['ShadowverseCraft']:
        """Get craft from string (case-insensitive)."""
        value_lower = value.lower()
        for craft in cls:
            if craft.value.lower() == value_lower:
                return craft
        return None

    @classmethod
    def all_crafts(cls) -> List[str]:
        """Get list of all craft names."""
        return [craft.value for craft in cls]


class MatchResult(str, Enum):
    """Match result types."""
    WIN = "win"
    LOSS = "loss"

    @classmethod
    def from_string(cls, value: str) -> Optional['MatchResult']:
        """Get result from string (case-insensitive)."""
        value_lower = value.lower()
        for result in cls:
            if result.value == value_lower:
                return result
        return None


@dataclass
class LogMatchRequest:
    """Request model for logging a single Shadowverse match."""
    player_craft: str
    opponent_craft: str
    result: str
    bricked: bool = False
    notes: str = ""
    api_key: Optional[str] = None  # Can be provided in body instead of header

    def validate(self) -> Optional[str]:
        """
        Validate the request data.

        Returns:
            Error message if invalid, None if valid
        """
        # Validate crafts
        player = ShadowverseCraft.from_string(self.player_craft)
        if not player:
            return f"Invalid player_craft: {self.player_craft}. Valid: {ShadowverseCraft.all_crafts()}"

        opponent = ShadowverseCraft.from_string(self.opponent_craft)
        if not opponent:
            return f"Invalid opponent_craft: {self.opponent_craft}. Valid: {ShadowverseCraft.all_crafts()}"

        # Validate result
        match_result = MatchResult.from_string(self.result)
        if not match_result:
            return f"Invalid result: {self.result}. Must be 'win' or 'loss'"

        return None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LogMatchRequest':
        """Create request from dictionary."""
        return cls(
            player_craft=data.get('player_craft', ''),
            opponent_craft=data.get('opponent_craft', ''),
            result=data.get('result', ''),
            bricked=data.get('bricked', False),
            notes=data.get('notes', ''),
            api_key=data.get('api_key'),
        )


@dataclass
class LogBatchRequest:
    """Request model for logging multiple Shadowverse matches."""
    matches: List[LogMatchRequest]
    api_key: Optional[str] = None

    def validate(self) -> Optional[str]:
        """Validate all matches in the batch."""
        if not self.matches:
            return "No matches provided in batch"

        if len(self.matches) > 100:
            return "Maximum 100 matches per batch"

        for i, match in enumerate(self.matches):
            error = match.validate()
            if error:
                return f"Match {i + 1}: {error}"

        return None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LogBatchRequest':
        """Create request from dictionary."""
        matches_data = data.get('matches', [])
        matches = [LogMatchRequest.from_dict(m) for m in matches_data]
        return cls(
            matches=matches,
            api_key=data.get('api_key'),
        )


@dataclass
class MatchRecord:
    """Model for a recorded match from the database."""
    id: int
    user_id: str
    player_craft: str
    opponent_craft: str
    result: str
    bricked: bool
    timestamp: int
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return asdict(self)


# =============================================================================
# Response Models
# =============================================================================

@dataclass
class APIResponse:
    """Base response model."""
    success: bool
    message: str = ""
    error: str = ""
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        result = {"success": self.success}
        if self.message:
            result["message"] = self.message
        if self.error:
            result["error"] = self.error
        if self.data:
            result.update(self.data)
        return result


@dataclass
class LogMatchResponse(APIResponse):
    """Response for logging a match."""
    match_id: int = 0
    player_craft: str = ""
    opponent_craft: str = ""
    result: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        result = super().to_dict()
        if self.success:
            result.update({
                "match_id": self.match_id,
                "player_craft": self.player_craft,
                "opponent_craft": self.opponent_craft,
                "result": self.result,
            })
        return result


@dataclass
class LogBatchResponse(APIResponse):
    """Response for logging a batch of matches."""
    processed: int = 0
    failed: int = 0
    match_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        result = super().to_dict()
        if self.success:
            result.update({
                "processed": self.processed,
                "failed": self.failed,
                "match_ids": self.match_ids,
            })
        return result


@dataclass
class HealthResponse:
    """Response for health check endpoint."""
    status: str = "healthy"
    version: str = "3.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return asdict(self)


@dataclass
class ValidateKeyResponse(APIResponse):
    """Response for key validation endpoint."""
    valid: bool = False
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "valid": self.valid,
            "description": self.description if self.valid else "",
            "success": self.success,
        }


__all__ = [
    # Enums
    'ShadowverseCraft',
    'MatchResult',
    # Request models
    'LogMatchRequest',
    'LogBatchRequest',
    'MatchRecord',
    # Response models
    'APIResponse',
    'LogMatchResponse',
    'LogBatchResponse',
    'HealthResponse',
    'ValidateKeyResponse',
]
