"""
dump_uma_db.py — Standalone script to dump Uma Musume DB to data/uma_db_dump.txt
Run: python dump_uma_db.py
"""
import asyncio
import aiosqlite
import os
from datetime import datetime, timezone

UMA_DB_PATH = os.path.join("data", "uma_musume_data.db")
NOTIF_DB_PATH = os.path.join("data", "notification_data.db")
GAMETORA_DB_PATH = os.path.join("data", "JP_Data", "uma_jp_data.db")
OUT_PATH = os.path.join("data", "uma_db_dump.txt")


async def main():
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(f"=== UMA MUSUME DB DUMP ===\n")
        f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n")

        # ── events ──────────────────────────────────────────────
        f.write("=" * 80 + "\n")
        f.write("TABLE: events  (uma_musume_data.db)\n")
        f.write("=" * 80 + "\n\n")

        async with aiosqlite.connect(UMA_DB_PATH) as conn:
            async with conn.execute(
                "SELECT id, title, category, profile, start_date, end_date, image, description, user_id "
                "FROM events ORDER BY start_date ASC"
            ) as cursor:
                rows = await cursor.fetchall()

            f.write(f"Total events: {len(rows)}\n\n")
            for row in rows:
                event_id, title, category, profile, start, end, image, desc, user_id = row
                try:
                    start_dt = datetime.fromtimestamp(int(start), tz=timezone.utc).isoformat()
                except Exception:
                    start_dt = str(start)
                try:
                    end_dt = datetime.fromtimestamp(int(end), tz=timezone.utc).isoformat()
                except Exception:
                    end_dt = str(end)

                f.write(f"--- ID: {event_id} ---\n")
                f.write(f"  Title:    {title}\n")
                f.write(f"  Category: {category}\n")
                f.write(f"  Profile:  {profile}\n")
                f.write(f"  Start:    {start_dt}  (unix: {start})\n")
                f.write(f"  End:      {end_dt}  (unix: {end})\n")
                f.write(f"  Image:    {(image or 'None')[:120]}\n")
                f.write(f"  Desc:     {(desc or 'None')[:200]}\n")
                f.write(f"  User ID:  {user_id}\n\n")

            # ── event_messages ───────────────────────────────────
            f.write("=" * 80 + "\n")
            f.write("TABLE: event_messages\n")
            f.write("=" * 80 + "\n\n")
            async with conn.execute(
                "SELECT event_id, channel_id, message_id FROM event_messages ORDER BY event_id"
            ) as cursor:
                msg_rows = await cursor.fetchall()
            f.write(f"Total mappings: {len(msg_rows)}\n\n")
            for event_id, channel_id, message_id in msg_rows:
                f.write(f"  Event {event_id} -> channel {channel_id}, message {message_id}\n")

        # ── pending_notifications ────────────────────────────────
        f.write("\n\n" + "=" * 80 + "\n")
        f.write("TABLE: pending_notifications  (notification_data.db)\n")
        f.write("=" * 80 + "\n\n")

        async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
            async with conn.execute(
                "SELECT id, title, profile, category, notify_unix, timing_type, sent "
                "FROM pending_notifications WHERE profile='UMA' ORDER BY notify_unix ASC"
            ) as cursor:
                notif_rows = await cursor.fetchall()

            f.write(f"Total UMA notifications: {len(notif_rows)}\n\n")
            for row in notif_rows:
                notif_id, title, profile, category, notify_unix, timing_type, sent = row
                try:
                    notify_dt = datetime.fromtimestamp(int(notify_unix), tz=timezone.utc).isoformat()
                except Exception:
                    notify_dt = str(notify_unix)
                sent_label = "SENT" if sent else "pending"
                f.write(f"  [{notif_id}] {title[:60]}  |  {timing_type}  |  {notify_dt}  |  {sent_label}\n")

        # ── GameTora DB ──────────────────────────────────────────
        f.write("\n\n" + "=" * 80 + "\n")
        f.write("GAMETORA DB  (data/JP_Data/uma_jp_data.db)\n")
        f.write("=" * 80 + "\n\n")

        if not os.path.exists(GAMETORA_DB_PATH):
            f.write("  ⚠ GameTora DB not found.\n")
        else:
            async with aiosqlite.connect(GAMETORA_DB_PATH) as gt:
                # characters
                f.write("── TABLE: characters ──\n")
                async with gt.execute("SELECT character_id, name, link FROM characters ORDER BY name") as cur:
                    rows = await cur.fetchall()
                f.write(f"Total: {len(rows)}\n")
                for char_id, name, link in rows:
                    f.write(f"  {char_id}  {name}  {link or ''}\n")

                # support_cards
                f.write("\n── TABLE: support_cards ──\n")
                async with gt.execute("SELECT card_id, name, link FROM support_cards ORDER BY name") as cur:
                    rows = await cur.fetchall()
                f.write(f"Total: {len(rows)}\n")
                for card_id, name, link in rows:
                    f.write(f"  {card_id}  {name}  {link or ''}\n")

                # banners
                f.write("\n── TABLE: banners ──\n")
                async with gt.execute(
                    "SELECT banner_id, banner_type, description, server FROM banners ORDER BY ROWID DESC"
                ) as cur:
                    rows = await cur.fetchall()
                f.write(f"Total: {len(rows)}\n")
                for banner_id, btype, desc, server in rows:
                    f.write(f"  [{banner_id}] {btype} ({server})  {(desc or '')[:80]}\n")

                # banner_items
                f.write("\n── TABLE: banner_items ──\n")
                async with gt.execute(
                    "SELECT banner_id, item_id, item_type FROM banner_items ORDER BY banner_id"
                ) as cur:
                    rows = await cur.fetchall()
                f.write(f"Total: {len(rows)}\n")
                for banner_id, item_id, item_type in rows:
                    f.write(f"  banner={banner_id}  {item_type}={item_id}\n")

                # global_banner_images
                f.write("\n── TABLE: global_banner_images ──\n")
                async with gt.execute(
                    "SELECT banner_id, image_filename FROM global_banner_images ORDER BY banner_id"
                ) as cur:
                    rows = await cur.fetchall()
                f.write(f"Total: {len(rows)}\n")
                for banner_id, filename in rows:
                    f.write(f"  banner={banner_id}  {filename}\n")

                # metadata
                f.write("\n── TABLE: metadata ──\n")
                async with gt.execute("SELECT key, value FROM metadata") as cur:
                    rows = await cur.fetchall()
                for key, val in rows:
                    f.write(f"  {key}: {val}\n")

    print(f"Dump written to: {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
