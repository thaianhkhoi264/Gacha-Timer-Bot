"""
One-time cleanup script: remove duplicate UMA event rows created by the
date-shift bug (LR/CM events that got re-inserted instead of updated).

Deduplication logic:
  - Groups events by (title, category) for profile='UMA'
  - Within each group, only considers pairs whose start_dates are within
    60 days of each other (genuine date-shift duplicates, not the same
    cup/race running again months later)
  - Keeps the row with the LATEST start_date (= the current correct dates)
  - Deletes the rest from both `events` and `event_messages`

Usage (dry-run, no changes):
    python scripts/uma_dedup.py

Usage (apply deletions):
    python scripts/uma_dedup.py --apply
"""

import sqlite3
import sys
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uma_musume_data.db")
TWO_MONTHS = 60 * 24 * 3600  # 60 days in seconds
DRY_RUN = "--apply" not in sys.argv


def main():
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, title, start_date, end_date, category FROM events "
        "WHERE profile='UMA' ORDER BY title, category, CAST(start_date AS INTEGER) ASC"
    ).fetchall()

    # Group by (title, category)
    groups: dict[tuple, list] = {}
    for row in rows:
        key = (row["title"], row["category"])
        groups.setdefault(key, []).append(row)

    to_delete: list[str] = []

    for (title, category), group in groups.items():
        if len(group) < 2:
            continue

        # Within this group, find pairs that are close enough to be date-shift
        # duplicates (start_dates within 60 days). Keep the one with the latest
        # start_date; mark the rest for deletion.
        #
        # Sort descending by start_date so group[0] is always the keeper.
        group_sorted = sorted(group, key=lambda r: int(r["start_date"]), reverse=True)
        keeper = group_sorted[0]

        for other in group_sorted[1:]:
            gap = abs(int(keeper["start_date"]) - int(other["start_date"]))
            if gap <= TWO_MONTHS:
                to_delete.append(other["id"])
                keeper_dt = datetime.fromtimestamp(int(keeper["start_date"]), tz=timezone.utc)
                other_dt  = datetime.fromtimestamp(int(other["start_date"]), tz=timezone.utc)
                print(
                    f"[DUPE] '{title}' ({category})\n"
                    f"       KEEP  {keeper['id']:>10}  start={keeper_dt.strftime('%Y-%m-%d')}\n"
                    f"       DELETE {other['id']:>9}  start={other_dt.strftime('%Y-%m-%d')}"
                )
            else:
                # Too far apart — likely genuinely different occurrences (same cup, different year)
                print(
                    f"[SKIP] '{title}' ({category})\n"
                    f"       {keeper['id']} and {other['id']} are {gap//86400}d apart — treating as distinct events"
                )

    if not to_delete:
        print("\nNo duplicates found.")
        conn.close()
        return

    print(f"\n{'[DRY RUN] Would delete' if DRY_RUN else 'Deleting'} {len(to_delete)} duplicate row(s): {to_delete}")

    if not DRY_RUN:
        for eid in to_delete:
            conn.execute("DELETE FROM events WHERE id=?", (eid,))
            conn.execute("DELETE FROM event_messages WHERE event_id=?", (eid,))
        conn.commit()
        print("Done. Run !uma_refresh in Discord to clean up the stale embeds.")
    else:
        print("\nRe-run with --apply to delete these rows.")

    conn.close()


if __name__ == "__main__":
    main()
