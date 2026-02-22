"""
Validation Service for Gacha Timer Bot.

Handles data validation and cleanup operations for events and notifications.
"""

import re
import time
from typing import List, Optional, Set, Tuple
from dataclasses import dataclass

from ..models import Event, Notification, GameProfile, EventCategory


@dataclass
class ValidationError:
    """Represents a validation error."""
    field: str
    message: str
    value: any = None


@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    errors: List[ValidationError]

    @classmethod
    def success(cls) -> 'ValidationResult':
        return cls(is_valid=True, errors=[])

    @classmethod
    def failure(cls, errors: List[ValidationError]) -> 'ValidationResult':
        return cls(is_valid=False, errors=errors)


class ValidationService:
    """
    Service for validating and cleaning event/notification data.

    Responsibilities:
    - Validate event data before saving
    - Clean up invalid or inconsistent data
    - Check for duplicates
    """

    # Valid categories by profile
    VALID_CATEGORIES = {
        "HSR": ["Banner", "Event", "Maintenance", "Offer"],
        "ZZZ": ["Banner", "Event", "Maintenance", "Offer"],
        "WUWA": ["Banner", "Event", "Maintenance", "Offer"],
        "AK": ["Banner", "Event", "Maintenance"],
        "STRI": ["Banner", "Event", "Maintenance"],
        "UMA": [
            "Character Banner", "Support Banner", "Paid Banner",
            "Story Event", "Champions Meeting", "Legend Race",
            "Selection Gacha", "Event"
        ],
    }

    # Minimum event duration (1 hour)
    MIN_DURATION_SECONDS = 3600

    # Maximum event duration (365 days)
    MAX_DURATION_SECONDS = 365 * 86400

    # Maximum future time (2 years ahead)
    MAX_FUTURE_SECONDS = 2 * 365 * 86400

    def validate_event(self, event: Event) -> ValidationResult:
        """
        Validate an event's data.

        Args:
            event: The event to validate

        Returns:
            ValidationResult with any errors found
        """
        errors = []

        # Title validation
        if not event.title or not event.title.strip():
            errors.append(ValidationError("title", "Title is required"))
        elif len(event.title) > 200:
            errors.append(ValidationError("title", "Title too long (max 200 chars)", event.title))

        # Profile validation
        if not event.profile:
            errors.append(ValidationError("profile", "Profile is required"))
        elif event.profile.upper() not in self.VALID_CATEGORIES:
            errors.append(ValidationError(
                "profile",
                f"Invalid profile. Must be one of: {list(self.VALID_CATEGORIES.keys())}",
                event.profile
            ))

        # Category validation
        if not event.category:
            errors.append(ValidationError("category", "Category is required"))
        elif event.profile and event.profile.upper() in self.VALID_CATEGORIES:
            valid_cats = self.VALID_CATEGORIES[event.profile.upper()]
            if event.category not in valid_cats:
                errors.append(ValidationError(
                    "category",
                    f"Invalid category for {event.profile}. Must be one of: {valid_cats}",
                    event.category
                ))

        # Date validation
        current_time = int(time.time())

        if not event.start_date:
            errors.append(ValidationError("start_date", "Start date is required"))
        elif event.start_date > current_time + self.MAX_FUTURE_SECONDS:
            errors.append(ValidationError(
                "start_date",
                "Start date too far in the future (max 2 years)",
                event.start_date
            ))

        if not event.end_date:
            errors.append(ValidationError("end_date", "End date is required"))
        elif event.start_date and event.end_date:
            duration = event.end_date - event.start_date

            if event.end_date <= event.start_date:
                errors.append(ValidationError(
                    "end_date",
                    "End date must be after start date",
                    event.end_date
                ))
            elif duration < self.MIN_DURATION_SECONDS:
                errors.append(ValidationError(
                    "duration",
                    "Event duration too short (min 1 hour)",
                    duration
                ))
            elif duration > self.MAX_DURATION_SECONDS:
                errors.append(ValidationError(
                    "duration",
                    "Event duration too long (max 365 days)",
                    duration
                ))

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def validate_notification(self, notification: Notification) -> ValidationResult:
        """
        Validate a notification's data.

        Args:
            notification: The notification to validate

        Returns:
            ValidationResult with any errors found
        """
        errors = []

        # Required fields
        if not notification.title:
            errors.append(ValidationError("title", "Title is required"))

        if not notification.profile:
            errors.append(ValidationError("profile", "Profile is required"))

        if not notification.category:
            errors.append(ValidationError("category", "Category is required"))

        if not notification.timing_type:
            errors.append(ValidationError("timing_type", "Timing type is required"))

        if not notification.notify_unix:
            errors.append(ValidationError("notify_unix", "Notify time is required"))

        if not notification.event_time_unix:
            errors.append(ValidationError("event_time_unix", "Event time is required"))

        # Timing validation
        if notification.notify_unix and notification.event_time_unix:
            if notification.notify_unix > notification.event_time_unix:
                # Notification should be before or at event time
                errors.append(ValidationError(
                    "notify_unix",
                    "Notification time should be before event time",
                    notification.notify_unix
                ))

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def clean_title(self, title: str) -> str:
        """
        Clean and normalize an event title.

        Args:
            title: Raw title string

        Returns:
            Cleaned title
        """
        if not title:
            return ""

        # Strip whitespace
        title = title.strip()

        # Remove excessive whitespace
        title = re.sub(r'\s+', ' ', title)

        # Remove problematic characters
        title = re.sub(r'[<>]', '', title)

        return title

    def normalize_profile(self, profile: str) -> str:
        """
        Normalize a profile name to standard format.

        Args:
            profile: Profile name

        Returns:
            Normalized profile (uppercase)
        """
        if not profile:
            return ""

        profile = profile.strip().upper()

        # Handle aliases
        aliases = {
            "HONKAI": "HSR",
            "STARRAIL": "HSR",
            "HONKAI STAR RAIL": "HSR",
            "ZENLESS": "ZZZ",
            "ZENLESS ZONE ZERO": "ZZZ",
            "WUTHERING": "WUWA",
            "WUTHERING WAVES": "WUWA",
            "ARKNIGHTS": "AK",
            "STRINOVA": "STRI",
            "UMA MUSUME": "UMA",
            "UMAMUSUME": "UMA",
        }

        return aliases.get(profile, profile)

    def normalize_category(self, category: str, profile: str) -> str:
        """
        Normalize a category name.

        Args:
            category: Category name
            profile: Profile for context

        Returns:
            Normalized category
        """
        if not category:
            return ""

        category = category.strip()

        # Common category mappings
        lower = category.lower()

        if "banner" in lower:
            if profile.upper() == "UMA":
                if "character" in lower:
                    return "Character Banner"
                elif "support" in lower:
                    return "Support Banner"
                elif "paid" in lower:
                    return "Paid Banner"
            return "Banner"

        if "event" in lower:
            if profile.upper() == "UMA" and "story" in lower:
                return "Story Event"
            return "Event"

        if "maintenance" in lower or "maint" in lower:
            return "Maintenance"

        if "offer" in lower or "shop" in lower or "pack" in lower:
            return "Offer"

        if "champion" in lower or "cm" in lower:
            return "Champions Meeting"

        if "legend" in lower or "lr" in lower:
            return "Legend Race"

        # Return as-is with title case
        return category.title()

    def is_duplicate_event(
        self,
        event: Event,
        existing_events: List[Event],
        tolerance_seconds: int = 3600
    ) -> bool:
        """
        Check if an event is a duplicate of an existing one.

        Args:
            event: Event to check
            existing_events: List of existing events
            tolerance_seconds: Time tolerance for matching (default 1 hour)

        Returns:
            True if event appears to be a duplicate
        """
        for existing in existing_events:
            # Same profile and category
            if existing.profile != event.profile:
                continue
            if existing.category != event.category:
                continue

            # Similar title (ignore case and whitespace)
            if self._normalize_for_comparison(existing.title) != self._normalize_for_comparison(event.title):
                continue

            # Similar times (within tolerance)
            if abs(existing.start_date - event.start_date) <= tolerance_seconds:
                return True

        return False

    def _normalize_for_comparison(self, text: str) -> str:
        """Normalize text for duplicate comparison."""
        if not text:
            return ""
        # Lowercase, remove extra whitespace, remove special chars
        text = text.lower().strip()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s]', '', text)
        return text

    def get_valid_categories(self, profile: str) -> List[str]:
        """
        Get valid categories for a profile.

        Args:
            profile: Game profile

        Returns:
            List of valid category names
        """
        profile = profile.upper()
        return self.VALID_CATEGORIES.get(profile, ["Banner", "Event", "Maintenance"])

    def is_valid_profile(self, profile: str) -> bool:
        """Check if a profile is valid."""
        return profile.upper() in self.VALID_CATEGORIES

    def is_valid_category(self, category: str, profile: str) -> bool:
        """Check if a category is valid for a profile."""
        valid = self.get_valid_categories(profile)
        return category in valid
