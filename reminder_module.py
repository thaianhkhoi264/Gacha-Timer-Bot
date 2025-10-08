import asyncio
import pytz
from datetime import datetime, timedelta
from bot import bot
from global_config import *

USER_ID = 443416461457883136  # Naito's User ID
MESSAGE = "It's time to sleep little boy <:KanamiAnger:1406653154111524924>"

async def daily_reminder_task():
    await bot.wait_until_ready()
    print("[Reminder] Task started and bot is ready.")
    tz = pytz.timezone("US/Eastern")
    
    while not bot.is_closed():
        now = datetime.now(tz)
        print(f"[Reminder] Current time (EST): {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Calculate next 7 PM EST
        next_run = now.replace(hour=19, minute=0, second=0, microsecond=0)
        if now >= next_run:
            # If it's already past 7 PM today, schedule for tomorrow
            next_run += timedelta(days=1)
        
        print(f"[Reminder] Next reminder scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')} EST")
        
        # Calculate time to wait until 5 minutes before 7 PM (for pre-notification)
        pre_notification_time = next_run - timedelta(minutes=5)
        wait_for_pre_notification = (pre_notification_time - now).total_seconds()
        
        print(f"[Reminder] Time until pre-notification: {wait_for_pre_notification} seconds ({wait_for_pre_notification/3600:.2f} hours)")
        
        # If there's time for a pre-notification, send it
        if wait_for_pre_notification > 0:
            print(f"[Reminder] Sleeping until pre-notification time...")
            await asyncio.sleep(wait_for_pre_notification)
            print("[Reminder] Sending pre-notification to owner...")
            try:
                owner = await bot.fetch_user(OWNER_USER_ID)
                await owner.send("The daily reminder will be sent to Naito in 5 minutes.")
                print("[Reminder] Pre-notification sent successfully.")
            except Exception as e:
                print(f"[Reminder] Failed to send pre-notification to owner: {e}")
            
            # Now sleep the remaining 5 minutes until 7 PM
            print("[Reminder] Sleeping remaining 5 minutes until 7 PM...")
            await asyncio.sleep(300)
        else:
            # If we're already past the pre-notification time, just wait until 7 PM
            wait_for_reminder = (next_run - datetime.now(tz)).total_seconds()
            print(f"[Reminder] Already past pre-notification time. Waiting {wait_for_reminder} seconds until 7 PM...")
            if wait_for_reminder > 0:
                await asyncio.sleep(wait_for_reminder)
        
        # Send the actual reminder at 7 PM
        print("[Reminder] Sending reminder now...")
        try:
            user = await bot.fetch_user(USER_ID)
            await user.send(MESSAGE)
            print(f"[Reminder] Reminder sent to user {USER_ID}")
            
            owner = await bot.fetch_user(OWNER_USER_ID)
            await owner.send(f"Kanami reminded Naito to go to sleep. <:KanamiHeart:1374409597628186624>")
            print(f"[Reminder] Confirmation sent to owner {OWNER_USER_ID}")
            
            reminderer = await bot.fetch_user(264758014198808577)  # Alfa
            await reminderer.send(f"Kanami reminded Naito to go to sleep. You should too <:KanamiHeart:1374409597628186624>")
            print("[Reminder] Confirmation sent to Alfa")
        except Exception as e:
            print(f"[Reminder] Failed to send DM: {e}")
        
        # After sending, sleep for 1 minute to prevent double-sending if the loop runs again immediately
        print("[Reminder] Sleeping 60 seconds before next calculation...")
        await asyncio.sleep(60)