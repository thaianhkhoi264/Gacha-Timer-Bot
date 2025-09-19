import asyncio
import pytz
from datetime import datetime, timedelta
from bot import bot
from global_config import *

USER_ID = 443416461457883136  # Naito's User ID
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

        # Notify owner 5 minutes before the reminder
        if wait_seconds > 300:
            await asyncio.sleep(wait_seconds - 300)
            try:
                owner = await bot.fetch_user(OWNER_USER_ID)
                await owner.send("The daily reminder will be sent to Naito in 5 minutes.")
            except Exception as e:
                print(f"[Reminder] Failed to send pre-notification to owner: {e}")
            await asyncio.sleep(300)
        else:
            await asyncio.sleep(wait_seconds)

        try:
            user = await bot.fetch_user(USER_ID)
            await user.send(MESSAGE)
            owner = await bot.fetch_user(OWNER_USER_ID)
            await owner.send(f"Kanami reminded Naito to go to sleep. <:KanamiHeart:1374409597628186624>")
            reminderer = await bot.fetch_user(264758014198808577)  # Alfa
            await reminderer.send(f"Kanami reminded Naito to go to sleep. <:KanamiHeart:1374409597628186624>")
        except Exception as e:
            print(f"[Reminder] Failed to send DM: {e}")
        await asyncio.sleep(1)  # Prevents double sending if the loop runs too quickly