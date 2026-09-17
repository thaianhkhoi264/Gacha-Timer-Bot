"""
test_legend_race.py

Fetches upcoming legend race events from the uma.moe API,
builds the full embed (character links + stand images) the same way
process_api_events() should, and sends them to the test webhook.

Compares CURRENT (broken) output vs FIXED output side by side.
"""

import asyncio
import gzip
import json
import os
import sqlite3
import re
import time
import aiohttp
from io import BytesIO

# ── Config ──────────────────────────────────────────────────────────────────
# API_KEY and WEBHOOK_URL are secrets — set them via environment variables,
# never hardcode them here. (The previous hardcoded webhook/key were dead:
# the webhook's channel is deleted and the key is stale.)
API_KEY       = os.getenv("UMA_TEST_API_KEY", "")
API_URL       = "https://uma.moe/resources/current/banner_timeline.json.gz"
BASE_URL      = "https://uma.moe/"
STAND_URL_TPL = "https://uma.moe/assets/images/character_stand/chara_stand_{id}.webp"
GAMETORA_DB   = os.path.join("data", "JP_Data", "uma_jp_data.db")

WEBHOOK_URL = os.getenv("UMA_TEST_WEBHOOK_URL", "")

EMBED_COLOR_LEGEND = 0xFFD700   # gold

# ── PIL ──────────────────────────────────────────────────────────────────────
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[WARN] PIL not available - images won't be combined")


# ── Helpers ──────────────────────────────────────────────────────────────────

async def fetch_timeline():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, headers={"X-API-Key": API_KEY},
                               timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"API returned {resp.status}")
            raw = await resp.read()
    try:
        data = json.loads(gzip.decompress(raw))
    except Exception:
        data = json.loads(raw)
    return data.get("events", [])


def lookup_characters_by_ids(char_ids):
    """
    Given a list of character IDs (ints or strings like 101401),
    look them up in the GameTora characters table via the character_id column.

    Returns list of (name, link) tuples.
    """
    if not os.path.exists(GAMETORA_DB):
        print(f"[WARN] GameTora DB not found at {GAMETORA_DB}")
        return []
    results = []
    conn = sqlite3.connect(GAMETORA_DB)
    for cid in char_ids:
        cid_str = str(cid)
        row = conn.execute(
            "SELECT name, link FROM characters WHERE character_id = ?",
            (cid_str,)
        ).fetchone()
        if row:
            results.append((row[0], row[1]))
            print(f"  [GT] {cid_str} -> {row[0]}")
        else:
            print(f"  [GT] {cid_str} -> NOT FOUND in DB")
    conn.close()
    return results


async def fetch_image_bytes(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                return await r.read()
    except Exception as e:
        print(f"  [IMG] Failed to fetch {url}: {e}")
    return None


async def combine_images_horizontally_bytes(session, urls):
    """Download images and combine horizontally, return PNG bytes."""
    if not PIL_AVAILABLE:
        return None
    imgs = []
    for url in urls:
        data = await fetch_image_bytes(session, url)
        if data:
            try:
                imgs.append(Image.open(BytesIO(data)).convert("RGBA"))
            except Exception as e:
                print(f"  [IMG] Could not open image from {url}: {e}")
    if not imgs:
        return None
    target_h = max(i.height for i in imgs)
    resized = []
    for img in imgs:
        if img.height != target_h:
            ratio = target_h / img.height
            img = img.resize((int(img.width * ratio), target_h), Image.LANCZOS)
        resized.append(img)
    total_w = sum(i.width for i in resized)
    combined = Image.new("RGBA", (total_w, target_h), (0, 0, 0, 0))
    x = 0
    for img in resized:
        combined.paste(img, (x, 0))
        x += img.width
    buf = BytesIO()
    combined.save(buf, format="PNG")
    return buf.getvalue()


async def send_embed(session, embed_dict, image_bytes=None, filename="image.png"):
    """Send an embed to the test webhook, with optional image attachment."""
    payload = {"embeds": [embed_dict]}
    form = aiohttp.FormData()
    form.add_field("payload_json", json.dumps(payload))
    if image_bytes:
        form.add_field("files[0]", image_bytes,
                       filename=filename, content_type="image/png")
    async with session.post(WEBHOOK_URL, data=form) as r:
        if r.status not in (200, 204):
            text = await r.text()
            print(f"  [WEBHOOK] Error {r.status}: {text[:200]}")
        else:
            print(f"  [WEBHOOK] Sent OK ({r.status})")


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    now_ts = int(time.time())

    print("Fetching timeline from uma.moe API...")
    events = await fetch_timeline()
    legend_races = [
        e for e in events
        if e["type"] == "legend_race"
    ]

    # Filter to upcoming/ongoing only (end > now)
    import datetime
    def parse_iso(s):
        if not s:
            return 0
        s = s.replace("Z", "+00:00")
        return int(datetime.datetime.fromisoformat(s).timestamp())

    upcoming = []
    for ev in legend_races:
        end_ts = parse_iso(ev.get("estimated_end_date"))
        if end_ts > now_ts:
            upcoming.append(ev)

    print(f"Found {len(legend_races)} total, {len(upcoming)} upcoming/ongoing legend races")
    print()

    # Pick first 2 upcoming for the test
    test_events = upcoming[:2]

    async with aiohttp.ClientSession() as session:
        for ev in test_events:
            title = ev.get("title", "Legend Race")
            start_ts = parse_iso(ev.get("global_release_date"))
            end_ts   = parse_iso(ev.get("estimated_end_date"))
            race_details = ev.get("description", "")
            pickup_ids   = ev.get("pickup_card_ids") or []
            related_chars = ev.get("related_characters") or []
            image_path   = ev.get("image_path", "")

            print(f"=== {title} ===")
            print(f"  pickup_card_ids: {pickup_ids}")
            print(f"  related_characters: {related_chars}")
            print(f"  description (API): {race_details!r}")
            print(f"  image_path: {image_path!r}")
            print()

            # ── CURRENT (broken) embed ────────────────────────────────────
            # Mirrors what process_api_events() does right now:
            #   stand_urls = [f"{BASE_URL}{p}" for p in related_characters if p.startswith("assets/")]
            #   → always empty because related_characters are now names
            stand_urls_broken = [
                f"{BASE_URL}{p}"
                for p in related_chars
                if isinstance(p, str) and p.startswith("assets/")
            ]
            fallback_img_url = f"{BASE_URL}{image_path}" if image_path else ""
            current_img_url  = stand_urls_broken[0] if stand_urls_broken else fallback_img_url
            current_desc     = race_details   # raw "2400m - Medium - Turf"

            print(f"  [CURRENT] stand_urls found: {len(stand_urls_broken)}  (expected 0 - bug)")
            print(f"  [CURRENT] image: {current_img_url}")
            print(f"  [CURRENT] description: {current_desc!r}")
            print()

            current_embed = {
                "title": f"[CURRENT/BROKEN] {title}",
                "description": current_desc or "(no description)",
                "color": EMBED_COLOR_LEGEND,
                "fields": [
                    {"name": "Start", "value": f"<t:{start_ts}:F>", "inline": True},
                    {"name": "End",   "value": f"<t:{end_ts}:F>",   "inline": True},
                ],
                "footer": {"text": "Current process_api_events() output - related_characters are names now, not asset paths"},
            }
            if current_img_url.startswith("http"):
                current_embed["image"] = {"url": current_img_url}

            # ── FIXED embed ───────────────────────────────────────────────
            # Use pickup_card_ids to look up GameTora characters
            print(f"  Looking up {len(pickup_ids)} character IDs in GameTora DB...")
            gt_chars = lookup_characters_by_ids(pickup_ids)

            if gt_chars:
                char_links = ", ".join(
                    f"[{name}](https://gametora.com{link})" for name, link in gt_chars
                )
            else:
                # Fallback: use related_characters names (plain text)
                char_links = ", ".join(related_chars) or "Unknown"

            fixed_desc = f"**Characters:** {char_links}"
            if race_details:
                fixed_desc += f"\n{race_details}"

            # Image: combine character stand webps; fall back to Akamai URL
            stand_urls_fixed = [STAND_URL_TPL.format(id=cid) for cid in pickup_ids]
            print(f"  Stand URLs: {stand_urls_fixed}")

            combined_bytes = None
            combined_filename = "combined_legend.png"
            lr_img_url = None

            if len(stand_urls_fixed) > 1:
                print(f"  Combining {len(stand_urls_fixed)} stand images...")
                combined_bytes = await combine_images_horizontally_bytes(session, stand_urls_fixed)
                if combined_bytes:
                    print(f"  Combined OK ({len(combined_bytes)} bytes)")
                    lr_img_url = f"attachment://{combined_filename}"
                else:
                    print("  Combine FAILED - falling back to Akamai URL")
            elif stand_urls_fixed:
                data = await fetch_image_bytes(session, stand_urls_fixed[0])
                if data:
                    combined_bytes = data
                    combined_filename = "stand.png"
                    lr_img_url = f"attachment://{combined_filename}"

            if not lr_img_url:
                lr_img_url = ev.get("image") or fallback_img_url
                combined_bytes = None
                print(f"  Using Akamai fallback: {lr_img_url}")

            print(f"  [FIXED] description: {fixed_desc!r}")
            print()

            fixed_embed = {
                "title": f"[FIXED] {title}",
                "description": fixed_desc,
                "color": EMBED_COLOR_LEGEND,
                "fields": [
                    {"name": "Start", "value": f"<t:{start_ts}:F>", "inline": True},
                    {"name": "End",   "value": f"<t:{end_ts}:F>",   "inline": True},
                ],
                "footer": {"text": f"pickup_card_ids={pickup_ids} | stand: character_stand/chara_stand_{{id}}.webp"},
            }
            if lr_img_url:
                fixed_embed["image"] = {"url": lr_img_url}

            # Send both embeds
            print(f"  Sending CURRENT embed...")
            await send_embed(session, current_embed)
            await asyncio.sleep(0.5)

            print(f"  Sending FIXED embed...")
            await send_embed(session, fixed_embed,
                             image_bytes=combined_bytes,
                             filename=combined_filename)
            print()
            await asyncio.sleep(1)

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
