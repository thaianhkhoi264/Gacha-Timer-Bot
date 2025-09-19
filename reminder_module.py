import asyncio
import pytz
from datetime import datetime, timedelta
from bot import bot

USER_ID = 443416461457883136
MESSAGE = "It's time to sleep little boy <:KanamiAnger:1406653154111524924>"

async def daily_reminder_task():
    await bot.wait_until_ready()
    tz = pytz.timezone("US/Eastern")
    while not bot.is_closed():
        now = datetime.now(tz)
        next_run = now.replace(hour=19, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        try:
            user = await bot.fetch_user(USER_ID)
            await user.send(MESSAGE)
        except Exception as e:
            print(f"[Reminder] Failed to send DM: {e}")
        await asyncio.sleep(1)  # Prevents double sending if the loop runs too quickly