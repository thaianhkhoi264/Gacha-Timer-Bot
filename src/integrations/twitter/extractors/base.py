"""
Base Tweet Extractor - Abstract interface for game-specific tweet parsers.

This module defines the base class that all game-specific tweet extractors
must implement. Each game has unique event date formats and parsing logic.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging


class BaseTweetExtractor(ABC):
    """
    Abstract base class for game-specific tweet extractors.

    Each game needs a specialized extractor to handle:
    - Game-specific date formats
    - Version/patch systems
    - Regional server handling
    - Event naming conventions
    - LLM prompt engineering

    Example Implementation:
        ```python
        class HSRTweetExtractor(BaseTweetExtractor):
            async def extract_events(self, tweet_data: Dict) -> List[Dict]:
                # Build HSR-specific prompt
                prompt = self._build_extraction_prompt(tweet_data)

                # Use ML to extract
                llm_response = await self.ml.run_inference(
                    prompt,
                    image_url=tweet_data.get("image")
                )

                # Parse and convert to regional timezones
                events = self._parse_llm_response(llm_response)
                for event in events:
                    event.update(await self._convert_to_all_timezones(event["start"]))

                return events
        ```
    """

    def __init__(self, ml_service, profile: str):
        """
        Initialize the tweet extractor.

        Args:
            ml_service: MLService instance for LLM inference
            profile: Game profile identifier (HSR, ZZZ, AK, etc.)
        """
        self.ml = ml_service
        self.profile = profile
        self.logger = logging.getLogger(f"twitter.extractor.{profile.lower()}")

    @abstractmethod
    async def extract_events(self, tweet_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract events from tweet data.

        Args:
            tweet_data: Dictionary containing:
                - text: Tweet text content
                - image: Optional image URL
                - author: Tweet author
                - url: Tweet URL
                - timestamp: Tweet timestamp

        Returns:
            List of event dictionaries, each containing:
                - title: Event title
                - category: Event category (Banner, Event, etc.)
                - start_date: Unix timestamp for event start
                - end_date: Unix timestamp for event end
                - description: Optional description
                - image: Optional image URL
                - profile: Game profile

                For regional games (HSR, ZZZ):
                - asia_start, asia_end: Unix timestamps for Asia server
                - america_start, america_end: Unix timestamps for America server
                - europe_start, europe_end: Unix timestamps for Europe server

        Raises:
            ValueError: If tweet data is invalid or extraction fails
        """
        pass

    @abstractmethod
    async def parse_date(self, date_str: str) -> Optional[int]:
        """
        Parse game-specific date format to Unix timestamp.

        Args:
            date_str: Date string in game-specific format

        Returns:
            Unix timestamp, or None if parsing fails

        Examples:
            HSR: "2025/06/18 04:00 (UTC+8)" → 1750032000
            Arknights: "Jun 18, 2025 16:00 (UTC-7)" → 1750104000
            STRI: "18.06.2025 12:00 UTC" → 1750075200
        """
        pass

    def _validate_tweet_data(self, tweet_data: Dict[str, Any]) -> bool:
        """
        Validate tweet data structure.

        Args:
            tweet_data: Tweet data to validate

        Returns:
            True if valid, False otherwise
        """
        required_fields = ["text"]
        for field in required_fields:
            if field not in tweet_data:
                self.logger.error(f"Missing required field: {field}")
                return False
        return True

    def _build_extraction_prompt(
        self,
        tweet_data: Dict[str, Any],
        *,
        include_image: bool = True
    ) -> str:
        """
        Build LLM extraction prompt.

        This is a base implementation that can be overridden for game-specific
        prompts with more detailed instructions.

        Args:
            tweet_data: Tweet data
            include_image: Whether to mention image in prompt

        Returns:
            Prompt string for LLM
        """
        prompt = f"""Extract event information from this {self.profile} game announcement:

Tweet text:
{tweet_data.get('text', '')}
"""
        if include_image and tweet_data.get('image'):
            prompt += "\n[Image attached - analyze for event dates and details]\n"

        prompt += """
Extract the following information:
1. Event title/name
2. Event category (Banner, Event, Maintenance, etc.)
3. Start date and time
4. End date and time
5. Any additional details

Format your response as JSON with fields:
{
    "title": "event title",
    "category": "Banner/Event/etc",
    "start": "date time",
    "end": "date time",
    "description": "additional details"
}
"""
        return prompt

    async def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse LLM response into event structures.

        This is a basic implementation that extracts JSON from the response.
        Override for more sophisticated parsing.

        Args:
            response: LLM response text

        Returns:
            List of event dictionaries
        """
        import json
        import re

        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if not json_match:
            self.logger.warning("No JSON found in LLM response")
            return []

        try:
            event_data = json.loads(json_match.group(0))
            return [event_data]
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON from LLM response: {e}")
            return []


__all__ = ['BaseTweetExtractor']
