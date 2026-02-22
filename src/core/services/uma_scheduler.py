"""
Uma Musume Scheduler Service for Gacha Timer Bot.

Handles special scheduling logic for Uma Musume events:
- Champions Meeting: Multi-phase competitive event with distinct periods
- Legend Race: Character rotation event where each character has a time window
"""

import re
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from ..models import Notification


# Seconds per day constant
SECONDS_PER_DAY = 86400


@dataclass
class ChampionsMeetingPhase:
    """Represents a phase in Champions Meeting."""
    name: str
    start_unix: int
    end_unix: int
    duration_days: int


@dataclass
class LegendRaceCharacter:
    """Represents a character period in Legend Race."""
    name: str
    start_unix: int
    end_unix: int


class UmaScheduler:
    """
    Service for scheduling Uma Musume special events.

    Champions Meeting phases are calculated BACKWARDS from the event end:
    - Finals: Last 1 day
    - Final Registration: 1 day before Finals
    - Round 2: 2 days before Final Registration
    - Round 1: 2 days before Round 2
    - League Selection: Remaining time from start

    Legend Race characters are calculated FORWARDS from event start:
    - Each character gets 3 days
    - Characters rotate sequentially
    """

    # Champions Meeting phase definitions (name, duration_days)
    # Listed in reverse order (from end to start)
    CM_PHASES_REVERSE = [
        ("Finals", 1),
        ("Final Registration", 1),
        ("Round 2", 2),
        ("Round 1", 2),
        ("League Selection", None),  # Takes remaining time
    ]

    # Message templates for notifications
    CM_TEMPLATES = {
        "reminder": "uma_champions_meeting_reminder",
        "League Selection": "uma_champions_meeting_registration_start",
        "Round 1": "uma_champions_meeting_round1_start",
        "Round 2": "uma_champions_meeting_round2_start",
        "Final Registration": "uma_champions_meeting_final_registration_start",
        "Finals": "uma_champions_meeting_finals_start",
        "end": "uma_champions_meeting_end",
    }

    LR_TEMPLATES = {
        "reminder": "uma_legend_race_reminder",
        "character": "uma_legend_race_character_start",
        "end": "uma_legend_race_end",
    }

    # Duration for each Legend Race character (3 days)
    LR_CHARACTER_DURATION = 3 * SECONDS_PER_DAY

    def calculate_champions_meeting_phases(
        self,
        event_start: int,
        event_end: int
    ) -> List[ChampionsMeetingPhase]:
        """
        Calculate Champions Meeting phases from event start/end times.

        Phases are calculated backwards from the event end.

        Args:
            event_start: Event start UNIX timestamp
            event_end: Event end UNIX timestamp

        Returns:
            List of ChampionsMeetingPhase objects, ordered from first to last
        """
        phases = []
        current_end = event_end

        # Calculate phases in reverse order (from end to start)
        for phase_name, duration in self.CM_PHASES_REVERSE:
            if duration is None:
                # League Selection takes the remaining time
                phase_start = event_start
                phase_end = current_end
            else:
                duration_seconds = duration * SECONDS_PER_DAY
                phase_start = current_end - duration_seconds
                phase_end = current_end
                current_end = phase_start

            # Calculate actual duration in days
            actual_duration = (phase_end - phase_start) // SECONDS_PER_DAY

            phases.append(ChampionsMeetingPhase(
                name=phase_name,
                start_unix=phase_start,
                end_unix=phase_end,
                duration_days=actual_duration
            ))

        # Reverse to get chronological order
        phases.reverse()
        return phases

    def create_champions_meeting_notifications(
        self,
        event_title: str,
        event_start: int,
        event_end: int,
        current_time: Optional[int] = None
    ) -> List[Notification]:
        """
        Create all notifications for a Champions Meeting event.

        Creates:
        - 1 reminder notification (1 day before start)
        - 5 phase start notifications (one for each phase)
        - 1 end notification

        Args:
            event_title: Event title
            event_start: Event start UNIX timestamp
            event_end: Event end UNIX timestamp
            current_time: Current time for filtering past notifications

        Returns:
            List of Notification objects
        """
        if current_time is None:
            current_time = int(time.time())

        notifications = []
        phases = self.calculate_champions_meeting_phases(event_start, event_end)

        # 1. Reminder: 1 day before event starts
        reminder_time = event_start - SECONDS_PER_DAY
        if reminder_time > current_time:
            notifications.append(Notification(
                category="Champions Meeting",
                profile="UMA",
                title=event_title,
                timing_type="reminder",
                notify_unix=reminder_time,
                event_time_unix=event_start,
                message_template=self.CM_TEMPLATES["reminder"],
            ))

        # 2-6. Phase start notifications
        for phase in phases:
            if phase.start_unix > current_time:
                template = self.CM_TEMPLATES.get(phase.name, "uma_champions_meeting_phase_start")
                notifications.append(Notification(
                    category="Champions Meeting",
                    profile="UMA",
                    title=event_title,
                    timing_type=f"phase_{phase.name.lower().replace(' ', '_')}",
                    notify_unix=phase.start_unix,
                    event_time_unix=phase.start_unix,
                    phase=phase.name,
                    message_template=template,
                ))

        # 7. Event end notification
        if event_end > current_time:
            notifications.append(Notification(
                category="Champions Meeting",
                profile="UMA",
                title=event_title,
                timing_type="end",
                notify_unix=event_end,
                event_time_unix=event_end,
                message_template=self.CM_TEMPLATES["end"],
            ))

        return notifications

    def parse_legend_race_characters(
        self,
        description: str
    ) -> List[str]:
        """
        Extract character names from Legend Race event description.

        Supports multiple formats:
        - "- Character Name (details)"
        - "**Characters:** [Name1](url) [Name2](url)"
        - "characters: Name1, Name2, Name3"

        Args:
            description: Event description text

        Returns:
            List of character names
        """
        characters = []

        # Format 1: "- Character Name (...)" or "- **Character Name** (...)"
        pattern1 = r'-\s*\*{0,2}([^*\(]+)\*{0,2}\s*\('
        matches1 = re.findall(pattern1, description)
        if matches1:
            characters.extend([m.strip() for m in matches1])
            return characters

        # Format 2: Markdown links "[Name](url)"
        pattern2 = r'\[([^\]]+)\]\([^)]+\)'
        matches2 = re.findall(pattern2, description)
        if matches2:
            # Filter out non-character links (usually "More Info" etc.)
            for m in matches2:
                name = m.strip()
                if name and not any(skip in name.lower() for skip in ["more", "info", "link", "details"]):
                    characters.append(name)
            if characters:
                return characters

        # Format 3: "characters: Name1, Name2, Name3"
        pattern3 = r'characters?:\s*(.+?)(?:\n|$)'
        match3 = re.search(pattern3, description, re.IGNORECASE)
        if match3:
            chars = match3.group(1).split(',')
            characters.extend([c.strip() for c in chars if c.strip()])
            return characters

        return characters

    def calculate_legend_race_characters(
        self,
        event_start: int,
        event_end: int,
        character_names: List[str]
    ) -> List[LegendRaceCharacter]:
        """
        Calculate character time windows for Legend Race.

        Each character gets 3 days, rotating sequentially.

        Args:
            event_start: Event start UNIX timestamp
            event_end: Event end UNIX timestamp
            character_names: List of character names

        Returns:
            List of LegendRaceCharacter objects
        """
        characters = []
        current_start = event_start

        for name in character_names:
            # Each character gets 3 days
            char_end = min(current_start + self.LR_CHARACTER_DURATION, event_end)

            characters.append(LegendRaceCharacter(
                name=name,
                start_unix=current_start,
                end_unix=char_end
            ))

            current_start = char_end

            # Stop if we've reached the event end
            if current_start >= event_end:
                break

        return characters

    def create_legend_race_notifications(
        self,
        event_title: str,
        event_start: int,
        event_end: int,
        character_names: List[str],
        current_time: Optional[int] = None
    ) -> List[Notification]:
        """
        Create all notifications for a Legend Race event.

        Creates:
        - 1 reminder notification (1 day before start)
        - N character start notifications (one per character)
        - 1 end notification

        Args:
            event_title: Event title
            event_start: Event start UNIX timestamp
            event_end: Event end UNIX timestamp
            character_names: List of character names
            current_time: Current time for filtering past notifications

        Returns:
            List of Notification objects
        """
        if current_time is None:
            current_time = int(time.time())

        notifications = []
        characters = self.calculate_legend_race_characters(
            event_start, event_end, character_names
        )

        # 1. Reminder: 1 day before event starts
        reminder_time = event_start - SECONDS_PER_DAY
        if reminder_time > current_time:
            notifications.append(Notification(
                category="Legend Race",
                profile="UMA",
                title=event_title,
                timing_type="reminder",
                notify_unix=reminder_time,
                event_time_unix=event_start,
                message_template=self.LR_TEMPLATES["reminder"],
            ))

        # 2-(N+1). Character start notifications
        for char in characters:
            if char.start_unix > current_time:
                notifications.append(Notification(
                    category="Legend Race",
                    profile="UMA",
                    title=event_title,
                    timing_type=f"character_{char.name.lower().replace(' ', '_')}",
                    notify_unix=char.start_unix,
                    event_time_unix=char.start_unix,
                    character_name=char.name,
                    message_template=self.LR_TEMPLATES["character"],
                ))

        # (N+2). Event end notification
        if event_end > current_time:
            notifications.append(Notification(
                category="Legend Race",
                profile="UMA",
                title=event_title,
                timing_type="end",
                notify_unix=event_end,
                event_time_unix=event_end,
                message_template=self.LR_TEMPLATES["end"],
            ))

        return notifications

    def get_phase_emoji(self, phase_name: str) -> str:
        """Get an emoji for a Champions Meeting phase."""
        emojis = {
            "League Selection": "\U0001F4DD",  # Memo
            "Round 1": "\U0001F947",           # 1st place medal
            "Round 2": "\U0001F948",           # 2nd place medal
            "Final Registration": "\U0001F4CB", # Clipboard
            "Finals": "\U0001F3C6",            # Trophy
        }
        return emojis.get(phase_name, "\U0001F3C7")  # Horse racing as default

    def get_character_emoji(self) -> str:
        """Get emoji for Legend Race character notifications."""
        return "\U0001F3C7"  # Horse racing
