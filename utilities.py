from modules import *
from bot import *
import logging

from notification_handler import *
from datetime import datetime, timezone

@bot.command() # "hello" command
async def hello(ctx):
    """ Responds with a hello along with a truth. """
    await ctx.send("Hello! Kanami here! Alfa is into wearing maid cosplays!")

@bot.command() # "version" command
async def version(ctx):
    """ Returns the current version of the bot. """
    await ctx.send(f"Current version is {bot_version}!")

@bot.command(name="mmj") # "MMJ" command / AKA kill switch
async def mmj(ctx):
    """ Forces Kanami to shut down if you are worthy enough. """
    OWNER_ID = 680653908259110914
    if ctx.author.id != OWNER_ID:
        await ctx.send("You don't get to use this command!")
        return
    await ctx.send("Kanami is shutting down...")
    await bot.close()

@bot.command(name="help") # "help" command
async def help_command(ctx):
    """Shows help for Kanami bot commands, organized by category."""
    embed = discord.Embed(
        title="Kanami Bot Help",
        description="Here are all the available commands that Kanami can do!",
        color=discord.Color.blurple()
    )

    # General
    embed.add_field(
        name="General",
        value=(
            "`Kanami help` — Show this help message\n"
            "`Kanami hello` — Say hello to Kanami\n"
            "`Kanami version` — Show bot version\n"
            "`Kanami timer` — Show all events for this server\n"
            "`Kanami checkchannels` — Show assigned channels\n"
        ),
        inline=False
    )

    # Event Management
    embed.add_field(
        name="Event Management",
        value=(
            "`Kanami add <title> <start> <end> [image] [profile] [category] [timezone]` — Add a new event\n"
            "`Kanami remove <title>` — Remove an event by title\n"
            "`Kanami edit <title> <item> <value>` — Edit an event (start, end, category, profile, image)\n"
            "`Kanami add_custom_category <category>` — Add a custom event category\n"
        ),
        inline=False
    )

    # Notification Management
    embed.add_field(
        name="Notification Management",
        value=(
            "`Kanami set_notification_channel #channel` — Set the notification channel\n"
            "`Kanami set_pending_notifications_channel #channel` — Set the pending notifications channel\n"
            "`Kanami set_notification_timing_channel #channel` — Set the notification timing channel\n"
            "`Kanami add_notification_timing <category> <start|end> <minutes>` — Add notification timing\n"
            "`Kanami clear_notification_timing <category> <start|end>` — Clear notification timing\n"
            "`Kanami refresh_notifications` — Refresh all notifications for ongoing events\n"
            "`Kanami refresh_pending_notifications` — Clear and recreate all pending notifications\n"
            "`Kanami clear_pending_notifications` — Clear all pending notifications\n"
        ),
        inline=False
    )

    # Role & Channel Management
    embed.add_field(
        name="Role & Channel Management",
        value=(
            "`Kanami assign` — Assign this channel for bot announcements\n"
            "`Kanami set_timer_channel #channel [profile]` — Set timer channel for a profile\n"
            "`Kanami assign_profile_role <profile> @Role` — Assign a role to a profile\n"
            "`Kanami assign_region_role <region> @Role` — Assign a role to a region\n"
            "`Kanami create_role_reaction` — Create role reaction messages\n"
            "`Kanami update_role_reaction` — Update role reaction messages\n"
            "`Kanami create_combined_roles` — Create combined region+game roles\n"
            "`Kanami update_all_combined_roles` — Update all members' combined roles\n"
            "`Kanami delete_role <role name>` — Delete a role\n"
        ),
        inline=False
    )

    # Utility
    embed.add_field(
        name="Utility",
        value=(
            "`Kanami purge [amount]` — Delete the last X messages (default 50, requires Manage Messages)\n"
            "`Kanami convert <time> [date]` — Convert date/time to Unix timestamp\n"
            "`Kanami converttz <time> [date] [timezone]` — Convert date/time with timezone\n"
            "`Kanami update` — Manually update all timer channels\n"
        ),
        inline=False
    )

    # Admin/Owner
    embed.add_field(
        name="Bloosh only",
        value=(
            "`Kanami mmj` — Tells Kanami to More More Jump off a cliff... <:KanamiScream:1374712543704256594>\n"
        ),
        inline=False
    )

    await ctx.send(embed=embed)

@bot.command(name="purge") # "purge" command
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int = 50):
    """
    Deletes the past X messages in the channel. Default is 50.
    Usage: Kanami purge [amount]
    """
    if amount < 1 or amount > 100:
        await ctx.send("Please specify an amount between 1 and 100.")
        return

    confirm_msg = await ctx.send(
        f"Are you absolutely sure about that? Kanami won't take responsibility if she deletes anything wrong... React with ✅ to confirm or ❌ to cancel."
    )
    await confirm_msg.add_reaction("✅")
    await confirm_msg.add_reaction("❌")

    def check(reaction, user):
        return (
            user == ctx.author
            and reaction.message.id == confirm_msg.id
            and str(reaction.emoji) in ["✅", "❌"]
        )

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=30.0, check=check)
    except Exception:
        await confirm_msg.edit(content="Purge cancelled (no response).")
        await confirm_msg.delete(delay=3)
        return

    if str(reaction.emoji) == "✅":
        deleted = await ctx.channel.purge(limit=amount)
        result_msg = await ctx.send(f"Deleted {len(deleted)} messages.", delete_after=5)
        await confirm_msg.delete()
        try:
            await ctx.message.delete()
        except Exception:
            pass
    else:
        await confirm_msg.edit(content="Purge cancelled.")
        await confirm_msg.delete(delay=2)
        try:
            await ctx.message.delete()
        except Exception:
            pass

def send_log(server_id, message):
    """Logs a message to both the console and the discord.log file, including the server ID."""
    log_entry = f"[Server {server_id}] {message}"
    print(log_entry)
    try:
        with open("discord.log", "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def test_notif(ctx):
    """
    Creates 5 test events in a new category, sets up notification timing, and cleans up after notifications are sent.
    """
    import random
    import string
    import sqlite3
    import asyncio
    from datetime import datetime, timezone, timedelta

    # Generate a unique category name
    rand_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    test_category = f"TEST_CATEGORY_{rand_suffix}"

    # Add custom category
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS custom_categories (
        server_id TEXT,
        category TEXT,
        PRIMARY KEY (server_id, category)
    )''')
    c.execute("INSERT OR IGNORE INTO custom_categories (server_id, category) VALUES (?, ?)", (str(ctx.guild.id), test_category))
    conn.commit()

    # Add notification timing: 1 minute before end
    c.execute('''INSERT OR IGNORE INTO notification_timings (server_id, category, timing_type, timing_minutes)
                 VALUES (?, ?, ?, ?)''', (str(ctx.guild.id), test_category, "end", 1))
    conn.commit()
    conn.close()

    # Update notification timing channel
    await update_notification_timing_message(ctx.guild)

    # Create 5 events: start 5 min before now, end 4 min after now (to ensure notification is in the future)
    now = int(datetime.now(timezone.utc).timestamp())
    start_unix = now  # Start now
    end_unix = now + 2 * 60  # End 2-3 minutes from now
    event_ids = []
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    for i in range(5):
        title = f"Test Event {i+1} ({rand_suffix})"
        c.execute(
            '''INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image, category, is_hyv, profile)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)''',
            (str(ctx.author.id), str(ctx.guild.id), title, str(start_unix), str(end_unix), None, test_category, "ALL")
        )
        event_ids.append(title)
    conn.commit()
    conn.close()

    await ctx.send(f"Created 5 test events in category `{test_category}`. Notification will be sent in ~3 minutes.")

    # Schedule notifications for each event
    for title in event_ids:
        event = {
            'server_id': str(ctx.guild.id),
            'category': test_category,
            'profile': "ALL",
            'title': title,
            'start_date': str(start_unix),
            'end_date': str(end_unix)
        }
        await schedule_notifications_for_event(event)

    # Update pending notifications embed
    await update_all_pending_notifications_embeds(ctx.guild)

    # Show how many pending notifications were created
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM pending_notifications WHERE server_id=? AND category=?", (str(ctx.guild.id), test_category))
    count = c.fetchone()[0]
    conn.close()
    await ctx.send(f"{count} pending notifications scheduled for `{test_category}`.")

    # Wait for notifications to be sent (give a buffer, e.g., 240 seconds)
    await asyncio.sleep(240)

    # Cleanup: delete events, category, and timing
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    # Delete events
    c.execute("DELETE FROM user_data WHERE server_id=? AND category=?", (str(ctx.guild.id), test_category))
    # Delete pending notifications for these events
    c.execute("DELETE FROM pending_notifications WHERE server_id=? AND category=?", (str(ctx.guild.id), test_category))
    # Delete notification timing
    c.execute("DELETE FROM notification_timings WHERE server_id=? AND category=?", (str(ctx.guild.id), test_category))
    # Delete custom category
    c.execute("DELETE FROM custom_categories WHERE server_id=? AND category=?", (str(ctx.guild.id), test_category))
    conn.commit()
    conn.close()

    await update_all_pending_notifications_embeds(ctx.guild)
    await update_notification_timing_message(ctx.guild)
    await ctx.send(f"Cleaned up test events, category, and notification timing for `{test_category}`.")