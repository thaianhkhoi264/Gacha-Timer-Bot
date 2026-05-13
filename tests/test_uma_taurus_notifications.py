"""
Temporary script to inspect notification schedule for Champions Meeting: Taurus Cup (CM0003).

Run with: python tests/test_uma_taurus_notifications.py
Delete after use.
"""

import sys
import os
import datetime

repo_root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, 'src'))

from core.services.uma_scheduler import UmaScheduler

# CM0003 from pifiles/uma_musume_data.db
EVENT_TITLE = "Champions Meeting: Taurus Cup"
EVENT_START = 1778450400
EVENT_END   = 1779141540

UTC = datetime.timezone.utc
EST = datetime.timezone(datetime.timedelta(hours=-5))

def fmt(unix: int) -> str:
    dt_utc = datetime.datetime.fromtimestamp(unix, tz=UTC)
    dt_est = datetime.datetime.fromtimestamp(unix, tz=EST)
    return f"{dt_utc.strftime('%Y-%m-%d %H:%M')} UTC  /  {dt_est.strftime('%Y-%m-%d %H:%M')} EST"


scheduler = UmaScheduler()

print("=" * 70)
print(f"Event: {EVENT_TITLE}")
print(f"Start : {fmt(EVENT_START)}")
print(f"End   : {fmt(EVENT_END)}")
print(f"Duration: {(EVENT_END - EVENT_START) / 86400:.2f} days")
print("=" * 70)

# --- Phases ---
print("\nPHASES (chronological):")
phases = scheduler.calculate_champions_meeting_phases(EVENT_START, EVENT_END)
for p in phases:
    print(f"  {p.name:<22} {fmt(p.start_unix)}  to  {fmt(p.end_unix)}  ({p.duration_days}d)")

# --- Notifications ---
print("\nNOTIFICATIONS (all, including past):")
notifs = scheduler.create_champions_meeting_notifications(
    EVENT_TITLE, EVENT_START, EVENT_END, current_time=0
)
for n in notifs:
    phase_str = f"phase={n.phase}" if n.phase else "         "
    print(f"  [{n.timing_type:<35}] {fmt(n.notify_unix)}  |  {phase_str}  |  {n.message_template}")

print()
