"""
Abstract scraper interface for the Gacha Timer Bot.

This module defines the abstract base class for game event scrapers,
following the Open/Closed Principle (OCP) from SOLID.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.core.models import Event


class EventScraper(ABC):
    """
    Abstract base class for game event scrapers.

    Each game module can implement this interface to provide
    automated event extraction from various sources (websites, APIs, etc.).
    """

    def __init__(self, profile: str):
        """
        Initialize the scraper.

        Args:
            profile: Game profile code (HSR/ZZZ/AK/etc.)
        """
        self.profile = profile

    @abstractmethod
    async def scrape_events(self) -> List[Event]:
        """
        Scrape events from the data source.

        Returns:
            List of Event entities extracted from the source

        Raises:
            ScraperError: If scraping fails
        """
        pass

    @abstractmethod
    async def validate_source(self) -> bool:
        """
        Validate that the data source is accessible.

        Returns:
            True if source is accessible, False otherwise
        """
        pass

    async def get_new_events(self, existing_events: List[Event]) -> List[Event]:
        """
        Get events that are new (not in existing_events).

        This is a helper method that compares scraped events with existing ones.

        Args:
            existing_events: List of events already in the database

        Returns:
            List of new Event entities
        """
        scraped = await self.scrape_events()
        existing_titles = {(e.title, e.start_date) for e in existing_events}

        new_events = []
        for event in scraped:
            if (event.title, event.start_date) not in existing_titles:
                new_events.append(event)

        return new_events

    async def get_updated_events(self, existing_events: List[Event]) -> List[Event]:
        """
        Get events that have been updated (title matches but data changed).

        Args:
            existing_events: List of events already in the database

        Returns:
            List of updated Event entities
        """
        scraped = await self.scrape_events()
        existing_map = {e.title: e for e in existing_events}

        updated_events = []
        for event in scraped:
            if event.title in existing_map:
                existing = existing_map[event.title]
                # Check if any data changed
                if (existing.start_date != event.start_date or
                    existing.end_date != event.end_date or
                    existing.image != event.image or
                    existing.category != event.category):
                    # Copy the ID from existing event
                    event.id = existing.id
                    updated_events.append(event)

        return updated_events


class WebScraper(EventScraper):
    """
    Abstract base class for web-based scrapers (Playwright, BeautifulSoup, etc.).
    """

    @abstractmethod
    async def initialize_browser(self):
        """Initialize the browser/web client."""
        pass

    @abstractmethod
    async def close_browser(self):
        """Close the browser/web client and cleanup resources."""
        pass


class APIScrap (EventScraper):
    """
    Abstract base class for API-based scrapers.
    """

    @abstractmethod
    async def fetch_data(self) -> dict:
        """
        Fetch raw data from the API.

        Returns:
            Raw API response data
        """
        pass

    @abstractmethod
    async def parse_response(self, data: dict) -> List[Event]:
        """
        Parse API response into Event entities.

        Args:
            data: Raw API response data

        Returns:
            List of Event entities
        """
        pass

    async def scrape_events(self) -> List[Event]:
        """
        Scrape events from the API.

        Returns:
            List of Event entities
        """
        data = await self.fetch_data()
        return await self.parse_response(data)


class LLMScraper(EventScraper):
    """
    Abstract base class for LLM-based event extraction
    (e.g., from Twitter posts, images, announcements).
    """

    @abstractmethod
    async def extract_from_text(self, text: str) -> Optional[Event]:
        """
        Extract event data from text using LLM.

        Args:
            text: Text content to extract from

        Returns:
            Event entity or None if extraction fails
        """
        pass

    @abstractmethod
    async def extract_from_image(self, image_url: str) -> Optional[Event]:
        """
        Extract event data from an image using vision-capable LLM.

        Args:
            image_url: URL to the image

        Returns:
            Event entity or None if extraction fails
        """
        pass


class ScraperError(Exception):
    """Base exception for scraper errors."""
    pass


class ScraperConnectionError(ScraperError):
    """Raised when scraper cannot connect to the data source."""
    pass


class ScraperParseError(ScraperError):
    """Raised when scraper cannot parse the data."""
    pass
