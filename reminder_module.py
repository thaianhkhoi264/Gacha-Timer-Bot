import asyncio
import pytz
import discord
import random
from datetime import datetime, timedelta
from bot import bot
from global_config import *

USER_ID = 443416461457883136  # Naito's User ID
MESSAGE = "It's time to sleep little boy <:KanamiAnger:1406653154111524924>. Kanami will keep reminding you until you go to sleep or reply!"

# Randomized follow-up messages
FOLLOW_UP_MESSAGES = [
    "Kanami is reminding you again! Go to sleep now! <:KanamiAnger:1406653154111524924>",
    "Are you still awake?! Little boy needs his sleep! <:KanamiAnger:1406653154111524924>",
    "Gweheh~ Kanami won't stop until you go to bed! <:KanamiAnger:1406653154111524924>",
    "Sleep time is NOW! Don't make Kanami angrier! <:KanamiAnger:1406653154111524924>",
    "Naito! Bed! NOW! Kanami is getting impatient! <:KanamiAnger:1406653154111524924>",
    "Why are you still awake?! Kanami demands you sleep! <:KanamiAnger:1406653154111524924>",
    "Little boy... Kanami is watching you... Go to sleep! <:KanamiAnger:1406653154111524924>",
    "This is your health we're talking about! Sleep! <:KanamiAnger:1406653154111524924>",
    "Kanami will keep pestering you until you rest! <:KanamiAnger:1406653154111524924>",
    "GO TO SLEEP! Kanami is not joking around! <:KanamiAnger:1406653154111524924>",
    "Sleep deprived Naito makes Kanami sad... and angry! <:KanamiAnger:1406653154111524924>",
    "Your bed is calling! Answer it! Now! <:KanamiAnger:1406653154111524924>",
    "Kanami's patience is running thin... SLEEP! <:KanamiAnger:1406653154111524924>",
    "Do you want Kanami to keep nagging? Sleep already! <:KanamiAnger:1406653154111524924>",
    "Little boy needs rest! Kanami insists! <:KanamiAnger:1406653154111524924>"
]

REMINDER_INTERVAL = 300  # 5 minutes in seconds (configurable)
REMINDER_DURATION = 1800  # Keep reminding for 30 minutes total (configurable)
FOLLOW_UP_ENABLED = True  # Toggle for follow-up messages (configurable)

print("[Reminder] Module loaded.")

async def get_user_status(user_id):
    """
    Get the user's current Discord status.
    Returns: 'offline', 'online', 'idle', 'dnd', or None if not found
    """
    try:
        # Check if user is in any mutual servers to get their status
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                status = member.status
                print(f"[Reminder] User {user_id} status: {status}")
                return status
        
        # If user not found in any mutual servers
        print(f"[Reminder] User {user_id} not found in mutual servers")
        return None
        
    except Exception as e:
        print(f"[Reminder] Error checking user status: {e}")
        return None

async def send_reminder_to_user(owner_triggered=False):
    """
    Send reminder to user based on their current status.
    This can be called by the daily task or manually by owner.
    Returns True if reminder was sent, False otherwise.
    """
    global REMINDER_INTERVAL, REMINDER_DURATION, FOLLOW_UP_ENABLED
    
    tz = pytz.timezone("US/Eastern")
    
    # Get user's current status
    user_status = await get_user_status(USER_ID)
    
    # Decision logic based on status:
    # - online/idle: Send reminder with full loop (multiple reminders)
    # - dnd: Send ONE reminder only (no loop)
    # - offline: Skip reminder completely (user can't respond anyway)
    # - None/unknown: Skip reminder (safe fallback)
    
    owner = await bot.fetch_user(OWNER_USER_ID)
    trigger_msg = " (MANUALLY TRIGGERED)" if owner_triggered else ""
    
    if user_status == discord.Status.offline or user_status is None:
        print(f"[Reminder] User {USER_ID} is OFFLINE or not found. NOT sending reminder (user can't respond).")
        await owner.send(f"Skipped sleep reminder{trigger_msg} - Naito is offline/unavailable 💤")
        print("[Reminder] Skipped reminder notification sent to owner")
        return False
        
    elif user_status == discord.Status.do_not_disturb:
        print(f"[Reminder] User {USER_ID} is in DND mode. Sending ONE reminder only (no follow-ups).")
        try:
            user = await bot.fetch_user(USER_ID)
            await user.send(MESSAGE)
            print(f"[Reminder] Single DND reminder sent to user {USER_ID}")
            
            await owner.send(f"Kanami sent ONE sleep reminder to Naito{trigger_msg} (DND mode - no follow-ups). <:KanamiHeart:1374409597628186624>")
            print(f"[Reminder] DND confirmation sent to owner {OWNER_USER_ID}")
            
            reminderer = await bot.fetch_user(264758014198808577)  # Alfa
            await reminderer.send(f"Kanami reminded Naito to go to sleep (DND - single message). You should too <:KanamiHeart:1374409597628186624>")
            print("[Reminder] DND confirmation sent to Alfa")
            return True
                    
        except Exception as e:
            print(f"[Reminder] Failed to send DND reminder: {e}")
            return False
            
    elif user_status in [discord.Status.online, discord.Status.idle]:
        status_name = "ONLINE" if user_status == discord.Status.online else "IDLE/AWAY"
        print(f"[Reminder] User {USER_ID} is {status_name}. Sending reminder with full follow-up loop...")
        try:
            user = await bot.fetch_user(USER_ID)
            await user.send(MESSAGE)
            print(f"[Reminder] Reminder sent to user {USER_ID}")
            
            await owner.send(f"Kanami reminded Naito to go to sleep{trigger_msg} (Status: {status_name}). <:KanamiHeart:1374409597628186624>")
            print(f"[Reminder] Confirmation sent to owner {OWNER_USER_ID}")
            
            reminderer = await bot.fetch_user(264758014198808577)  # Alfa
            await reminderer.send(f"Kanami reminded Naito to go to sleep. You should too <:KanamiHeart:1374409597628186624>")
            print("[Reminder] Confirmation sent to Alfa")
            
            # Keep reminding the main user every 5 minutes for 30 minutes total (max 6 reminders)
            reminder_count = 1
            reminder_start_time = datetime.now(tz)
            max_reminders = REMINDER_DURATION // REMINDER_INTERVAL
            
            # Check if follow-up is enabled or if we trigger the 5% chance random spam
            use_random_spam = False
            if not FOLLOW_UP_ENABLED:
                # 5% chance to trigger random spam mode when follow-up is disabled
                if random.random() < 0.05:
                    use_random_spam = True
                    print("[Reminder] Random spam mode ACTIVATED (5% chance)!")
                    await owner.send("🎲 Random spam mode activated for this reminder! (5% chance)")
            
            if use_random_spam:
                # Special mode: Send messages every 5 seconds for 30 seconds
                print("[Reminder] Starting random spam mode: 5 second intervals for 30 seconds")
                spam_duration = 30  # 30 seconds total
                spam_interval = 5  # 5 seconds between messages
                spam_count = spam_duration // spam_interval  # 6 messages
                
                for i in range(spam_count):
                    await asyncio.sleep(spam_interval)
                    spam_msg = random.choice(FOLLOW_UP_MESSAGES)
                    await user.send(spam_msg)
                    print(f"[Reminder] Spam message {i+1}/{spam_count} sent")
                
                await owner.send(f"Random spam mode completed - sent {spam_count} messages in {spam_duration} seconds!")
                print("[Reminder] Random spam mode completed")
                return True
            
            elif FOLLOW_UP_ENABLED:
                # Normal follow-up mode
                while reminder_count < max_reminders:
                    print(f"[Reminder] Waiting for user response (5 minutes) - Reminder #{reminder_count}/{max_reminders}")
                    
                    # Check if user went offline during the loop
                    current_status = await get_user_status(USER_ID)
                    if current_status == discord.Status.offline:
                        print(f"[Reminder] User went OFFLINE during reminder loop. Stopping reminders.")
                        await owner.send(f"Naito went offline after {reminder_count} reminder(s). Stopping follow-ups. 💤")
                        break
                    
                    try:
                        # Wait for a DM from the user for 5 minutes
                        def check(m):
                            return m.author.id == USER_ID and isinstance(m.channel, bot.dm_channel.__class__)
                        
                        msg = await bot.wait_for('message', check=check, timeout=REMINDER_INTERVAL)
                        print(f"[Reminder] User responded: '{msg.content}' - Stopping reminders.")
                        
                        # Send confirmation to owner that user responded
                        await owner.send(f"Naito responded to the reminder after {reminder_count} message(s): '{msg.content[:50]}'")
                        print("[Reminder] Response confirmation sent to owner")
                        break  # Exit the reminder loop
                        
                    except asyncio.TimeoutError:
                        # User didn't respond in 5 minutes, send another reminder
                        reminder_count += 1
                        elapsed_time = (datetime.now(tz) - reminder_start_time).total_seconds() / 60
                        print(f"[Reminder] No response after 5 minutes ({elapsed_time:.1f} min elapsed). Sending reminder #{reminder_count}...")
                        
                        # Send a random follow-up message
                        follow_up_msg = random.choice(FOLLOW_UP_MESSAGES)
                        await user.send(follow_up_msg)
                        print(f"[Reminder] Follow-up reminder #{reminder_count}/{max_reminders} sent to user {USER_ID}")
                
                # If we exhausted all reminders without a response
                if reminder_count >= max_reminders:
                    print(f"[Reminder] Maximum reminder duration (30 minutes) reached. Stopping reminders.")
                    await owner.send(f"Naito did not respond after {max_reminders} reminders over 30 minutes. 💤")
                    print("[Reminder] Non-response notification sent to owner")
            
            else:
                # Follow-up disabled and no random spam triggered
                print("[Reminder] Follow-up messages disabled, only initial message sent")
                await owner.send(f"Reminder sent (follow-ups disabled, no spam triggered)")
            
            return True
                    
        except Exception as e:
            print(f"[Reminder] Failed to send DM: {e}")
            return False
    
    else:
        # Unknown status, skip to be safe
        print(f"[Reminder] Unknown user status: {user_status}. Skipping reminder.")
        await owner.send(f"Skipped sleep reminder{trigger_msg} - unknown status: {user_status}")
        print("[Reminder] Unknown status notification sent to owner")
        return False

async def daily_reminder_task():
    print("[Reminder] Task function called, waiting for bot to be ready...")
    await bot.wait_until_ready()
    print("[Reminder] Bot is ready, starting reminder loop.")
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
        
        # Send the actual reminder at 7 PM using the shared function
        print("[Reminder] Time for scheduled reminder! Calling send_reminder_to_user()...")
        await send_reminder_to_user(owner_triggered=False)
        
        # After sending, sleep for 1 minute to prevent double-sending if the loop runs again immediately
        print("[Reminder] Sleeping 60 seconds before next calculation...")
        await asyncio.sleep(60)

@bot.command(name='remind_naito')
async def manual_reminder_command(ctx):
    """
    Owner command to manually trigger the reminder process immediately.
    Usage: !remind_naito
    """
    # Check if the user is the owner
    if ctx.author.id != OWNER_USER_ID:
        await ctx.send("Only the owner can use this command.")
        print(f"[Reminder] Unauthorized manual reminder attempt by user {ctx.author.id}")
        return
    
    print(f"[Reminder] Manual reminder triggered by owner {ctx.author.id}")
    await ctx.send("Starting manual reminder process for Naito... <:KanamiAnger:1406653154111524924>")
    
    # Call the same function that the daily task uses
    result = await send_reminder_to_user(owner_triggered=True)
    
    if result:
        await ctx.send("Manual reminder process completed successfully!")
    else:
        await ctx.send("Reminder was skipped (user offline or error occurred).")
    
    print(f"[Reminder] Manual reminder completed with result: {result}")

@bot.command(name='reminder_config')
async def reminder_config_command(ctx, setting: str = None, value: str = None):
    """
    Owner command to configure reminder settings.
    Usage: 
        !reminder_config interval <minutes> - Set reminder interval in minutes
        !reminder_config duration <minutes> - Set reminder duration in minutes
        !reminder_config followup <on/off> - Enable or disable follow-up messages
        !reminder_config status - Show current settings
    """
    global REMINDER_INTERVAL, REMINDER_DURATION, FOLLOW_UP_ENABLED
    
    # Check if the user is the owner
    if ctx.author.id != OWNER_USER_ID:
        await ctx.send("Only the owner can use this command.")
        print(f"[Reminder] Unauthorized config attempt by user {ctx.author.id}")
        return
    
    # Show current status if no arguments
    if setting is None or setting.lower() == 'status':
        interval_min = REMINDER_INTERVAL // 60
        duration_min = REMINDER_DURATION // 60
        followup_status = "ENABLED" if FOLLOW_UP_ENABLED else "DISABLED"
        max_reminders = REMINDER_DURATION // REMINDER_INTERVAL if REMINDER_INTERVAL > 0 else 0
        
        status_msg = f"""**Current Reminder Settings:**
📊 Interval: `{interval_min} minutes` ({REMINDER_INTERVAL} seconds)
⏱️ Duration: `{duration_min} minutes` ({REMINDER_DURATION} seconds)
📨 Follow-up Messages: `{followup_status}`
🔢 Max Reminders per cycle: `{max_reminders}`
🎲 Random spam chance (when off): `5%` (every 5s for 30s)"""
        await ctx.send(status_msg)
        return
    
    # Handle setting changes
    if value is None:
        await ctx.send("Please provide a value. Usage: `!reminder_config <setting> <value>`")
        return
    
    setting = setting.lower()
    
    if setting == 'interval':
        try:
            minutes = int(value)
            if minutes < 1:
                await ctx.send("Interval must be at least 1 minute.")
                return
            
            old_interval = REMINDER_INTERVAL // 60
            REMINDER_INTERVAL = minutes * 60
            await ctx.send(f"✅ Reminder interval changed from `{old_interval} minutes` to `{minutes} minutes`")
            print(f"[Reminder] Interval changed to {minutes} minutes ({REMINDER_INTERVAL} seconds)")
            
        except ValueError:
            await ctx.send("Invalid value. Please provide a number of minutes.")
    
    elif setting == 'duration':
        try:
            minutes = int(value)
            if minutes < 1:
                await ctx.send("Duration must be at least 1 minute.")
                return
            
            old_duration = REMINDER_DURATION // 60
            REMINDER_DURATION = minutes * 60
            max_reminders = REMINDER_DURATION // REMINDER_INTERVAL if REMINDER_INTERVAL > 0 else 0
            await ctx.send(f"✅ Reminder duration changed from `{old_duration} minutes` to `{minutes} minutes` (max {max_reminders} reminders)")
            print(f"[Reminder] Duration changed to {minutes} minutes ({REMINDER_DURATION} seconds)")
            
        except ValueError:
            await ctx.send("Invalid value. Please provide a number of minutes.")
    
    elif setting == 'followup':
        value_lower = value.lower()
        if value_lower in ['on', 'enabled', 'true', '1', 'yes']:
            FOLLOW_UP_ENABLED = True
            await ctx.send("✅ Follow-up messages **ENABLED**. Normal reminder loop will be used.")
            print("[Reminder] Follow-up messages enabled")
        elif value_lower in ['off', 'disabled', 'false', '0', 'no']:
            FOLLOW_UP_ENABLED = False
            await ctx.send("✅ Follow-up messages **DISABLED**. Only initial message will be sent (with 5% chance of random spam mode).")
            print("[Reminder] Follow-up messages disabled")
        else:
            await ctx.send("Invalid value. Use: on/off, enabled/disabled, true/false, yes/no, or 1/0")
    
    else:
        await ctx.send(f"Unknown setting: `{setting}`. Valid settings: interval, duration, followup, status")
