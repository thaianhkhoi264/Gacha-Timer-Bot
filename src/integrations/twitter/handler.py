"""
Twitter Handler - Main orchestrator for Twitter-based event extraction.

This module handles:
- Detecting Twitter links in Discord messages
- Scraping tweet content
- Routing tweets to game-specific extractors
- Injecting extracted events into game modules
"""

import logging
import re
from typing import Dict, Optional, List
from discord import Message

from src.integrations.ml import MLService
from src.integrations.twitter.extractors.base import BaseTweetExtractor

logger = logging.getLogger("twitter_handler")


class TwitterHandler:
    """
    Main Twitter listener and event dispatcher.

    This class coordinates the Twitter integration workflow:
    1. Detects Twitter links in Discord messages
    2. Determines which game the tweet is for
    3. Scrapes tweet content using Playwright
    4. Passes to appropriate game-specific extractor
    5. Injects extracted events into game modules

    Example:
        ```python
        twitter_handler = TwitterHandler(
            game_modules={
                "HSR": hsr_module,
                "ZZZ": zzz_module,
                "AK": arknights_module,
            },
            ml_service=MLService()
        )

        @bot.event
        async def on_message(message):
            await twitter_handler.on_message(message)
            await bot.process_commands(message)
        ```
    """

    # Twitter/X URL patterns
    TWITTER_PATTERNS = [
        r'https?://(?:www\.)?twitter\.com/\w+/status/\d+',
        r'https?://(?:www\.)?x\.com/\w+/status/\d+',
    ]

    def __init__(
        self,
        game_modules: Dict[str, any],
        ml_service: MLService,
        scraper = None,
        profile_mapper = None,
    ):
        """
        Initialize the Twitter handler.

        Args:
            game_modules: Dictionary mapping profiles to game modules
                         e.g., {"HSR": hsr_module, "ZZZ": zzz_module}
            ml_service: MLService instance for LLM-based extraction
            scraper: Optional TweetScraper instance (will be created if not provided)
            profile_mapper: Optional ProfileMapper instance
        """
        self.game_modules = game_modules
        self.ml_service = ml_service

        # Lazy-load scraper and mapper to avoid circular imports
        self.scraper = scraper
        self.profile_mapper = profile_mapper

        # Extractors will be registered by game modules
        self.extractors: Dict[str, BaseTweetExtractor] = {}

        logger.info(
            f"TwitterHandler initialized with {len(game_modules)} game modules"
        )

    def register_extractor(self, profile: str, extractor: BaseTweetExtractor):
        """
        Register a game-specific tweet extractor.

        Args:
            profile: Game profile (HSR, ZZZ, AK, etc.)
            extractor: Extractor instance for this game
        """
        self.extractors[profile] = extractor
        logger.info(f"Registered tweet extractor for {profile}")

    async def on_message(self, message: Message) -> bool:
        """
        Handle Discord message - check for Twitter links and process.

        Args:
            message: Discord message object

        Returns:
            True if message contained Twitter link and was processed,
            False otherwise
        """
        # Ignore bot's own messages
        if message.author.bot:
            return False

        # Check if message contains Twitter link
        if not self._is_twitter_link(message.content):
            return False

        logger.info(f"Twitter link detected from {message.author}")

        try:
            # Extract Twitter URL
            url = self._extract_twitter_url(message.content)
            if not url:
                return False

            # Determine game profile from URL
            profile = self._get_profile_from_url(url)
            if not profile:
                logger.warning(f"Could not determine game profile from URL: {url}")
                return False

            # Check if we have this game module and extractor
            if profile not in self.game_modules:
                logger.warning(f"No game module registered for profile: {profile}")
                return False

            if profile not in self.extractors:
                logger.warning(f"No extractor registered for profile: {profile}")
                return False

            # Scrape tweet content
            await message.add_reaction("⏳")  # Processing indicator
            tweet_data = await self._scrape_tweet(url)

            if not tweet_data:
                await message.remove_reaction("⏳", message.guild.me)
                await message.add_reaction("❌")  # Failed
                return False

            # Extract events using game-specific extractor
            extractor = self.extractors[profile]
            events = await extractor.extract_events(tweet_data)

            if not events:
                logger.warning(f"No events extracted from tweet: {url}")
                await message.remove_reaction("⏳", message.guild.me)
                await message.add_reaction("❓")  # No events found
                return False

            # Inject events into game module
            game_module = self.game_modules[profile]
            success_count = 0

            for event_data in events:
                try:
                    await game_module.add_event(ctx=message, event_data=event_data)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to add event: {e}", exc_info=True)

            # Update reaction based on success
            await message.remove_reaction("⏳", message.guild.me)
            if success_count > 0:
                await message.add_reaction("✅")  # Success
                logger.info(
                    f"Successfully extracted and added {success_count} events from tweet"
                )
            else:
                await message.add_reaction("❌")  # Failed

            return True

        except Exception as e:
            logger.error(f"Error processing Twitter link: {e}", exc_info=True)
            try:
                await message.remove_reaction("⏳", message.guild.me)
                await message.add_reaction("❌")
            except:
                pass
            return False

    def _is_twitter_link(self, text: str) -> bool:
        """Check if text contains a Twitter/X link."""
        for pattern in self.TWITTER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _extract_twitter_url(self, text: str) -> Optional[str]:
        """Extract the first Twitter URL from text."""
        for pattern in self.TWITTER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    def _get_profile_from_url(self, url: str) -> Optional[str]:
        """
        Determine game profile from Twitter URL.

        Uses profile_mapper if available, otherwise extracts username
        and does basic mapping.

        Args:
            url: Twitter URL

        Returns:
            Profile string (HSR, ZZZ, etc.) or None
        """
        if self.profile_mapper:
            return self.profile_mapper.get_profile(url)

        # Fallback: extract username and do basic mapping
        # Format: https://twitter.com/USERNAME/status/1234567890
        match = re.search(r'twitter\.com/(\w+)/status', url)
        if not match:
            match = re.search(r'x\.com/(\w+)/status', url)

        if not match:
            return None

        username = match.group(1).lower()

        # Basic username → profile mapping
        username_map = {
            "honkaistarrail": "HSR",
            "zenlesszero": "ZZZ",
            "arknightsen": "AK",
            "strinovaglobal": "STRI",
            "wutheringwaves": "WUWA",
        }

        return username_map.get(username)

    async def _scrape_tweet(self, url: str) -> Optional[Dict]:
        """
        Scrape tweet content using Playwright.

        Args:
            url: Twitter URL

        Returns:
            Dictionary with tweet data:
                - text: Tweet text
                - image: Optional image URL
                - author: Tweet author
                - url: Tweet URL
                - timestamp: Tweet timestamp
        """
        if not self.scraper:
            # Lazy-load scraper
            try:
                from src.integrations.twitter.scraper import TweetScraper
                self.scraper = TweetScraper()
            except ImportError:
                logger.error("TweetScraper not yet implemented")
                return None

        try:
            return await self.scraper.scrape_tweet(url)
        except Exception as e:
            logger.error(f"Failed to scrape tweet: {e}", exc_info=True)
            return None


__all__ = ['TwitterHandler']
