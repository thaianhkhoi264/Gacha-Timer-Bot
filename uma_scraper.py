"""
uma_scraper.py — Standalone Uma Musume timeline scraper.

Runs independently of the Discord bot.  Call via cron:
    0 */4 * * *  /path/to/venv/bin/python /path/to/bot/uma_scraper.py

On success, writes the current UTC timestamp to data/scraper_last_run.txt
so the bot's file-watcher task knows to refresh Discord embeds.
"""
import asyncio
import os
import logging
from datetime import datetime, timezone

# ── Logging ──────────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join("logs", "scraper.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("uma_scraper")

LAST_RUN_FILE = os.path.join("data", "scraper_last_run.txt")


async def main():
    logger.info("=== Uma Musume scraper starting ===")
    try:
        from uma_handler import scrape_and_save_events
        await scrape_and_save_events()

        # Signal to the bot that new data is available
        os.makedirs("data", exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
            f.write(timestamp)
        logger.info(f"Scrape complete. Wrote timestamp: {timestamp}")

    except Exception as e:
        import traceback
        logger.error(f"Scraper failed: {e}")
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    asyncio.run(main())
