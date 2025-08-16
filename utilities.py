from modules import *
from bot import bot, bot_version

import aiohttp
from discord.ext import commands

import logging
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
            "`Kanami check_channels` — Show assigned channels\n"
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

@bot.command()
async def restart(ctx):
    """Calls the Cloud Run endpoint to restart the VM (and the bot)."""
    await ctx.send("Requesting VM restart...")

    OWNER_ID = 680653908259110914
    if ctx.author.id != OWNER_ID:
        await ctx.send("You don't get to use this command!")
        return

    url = "https://reboot-vm-218886309090.us-central1.run.app"
    headers = {
        # If your Cloud Run endpoint requires an API key or auth, add it here
        # "Authorization": "Bearer YOUR_TOKEN"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers) as resp:
                if resp.status == 200:
                    await ctx.send("VM restart requested! Kanami will go offline and auto-restart soon.")
                else:
                    await ctx.send(f"Kanami failed to request restart. Status: {resp.status}")
        except Exception as e:
            await ctx.send(f"Error contacting Cloud Run: {e}")

def convert_to_unix_tz(date: str, time: str, timezone_str: str = "UTC"):
    """
    Converts a date and time string in a given timezone to a Unix timestamp.
    Supports IANA tz names (e.g., 'Asia/Tokyo') and offsets like 'UTC-8', 'GMT+5', etc.
    """
    from datetime import datetime
    import pytz
    import dateparser
    # Combine date and time
    dt_str = f"{date} {time}"
    # Try to parse with dateparser and timezone
    dt = dateparser.parse(dt_str, settings={'TIMEZONE': timezone_str, 'RETURN_AS_TIMEZONE_AWARE': True})
    if not dt:
        raise ValueError(f"Could not parse date/time: {dt_str} {timezone_str}")
    return int(dt.timestamp())

# Export pending notifications function
async def export_pending_notifications_core(ctx):
    """
    Exports the pending notifications table as a DM to the user.
    Only the owner (ID: 680653908259110914) can use this command.
    """
    OWNER_ID = 680653908259110914
    if ctx.author.id != OWNER_ID:
        await ctx.send("You are not authorized to use this command.")
        return

    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("""
        SELECT id, server_id, category, profile, title, timing_type, notify_unix, event_time_unix, sent, region
        FROM pending_notifications
        ORDER BY profile, server_id, notify_unix ASC
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        await ctx.author.send("There are no pending notifications in the database.")
        await ctx.send("Exported: No pending notifications.")
        return

    from collections import defaultdict, OrderedDict

    # Group notifications by profile, then by (title, category)
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        notif_id, server_id, category, profile, title, timing_type, notify_unix, event_time_unix, sent, region = row
        key = (title, category)
        grouped[profile][key].append({
            "timing_type": timing_type,
            "notify_unix": notify_unix,
            "event_time_unix": event_time_unix,
            "region": region
        })

    # Sort profiles alphabetically, then events by title
    sorted_profiles = sorted(grouped.keys())
    lines = []
    lines.append(f"**Pending Notifications Export ({len(rows)} rows):**")
    for profile in sorted_profiles:
        lines.append(f"# {profile}")
        events_dict = grouped[profile]
        # Sort events by title
        for (title, category), events in sorted(events_dict.items(), key=lambda x: x[0][0].lower()):
            lines.append(f"**{title}**")
            lines.append(f"{category}")
            # Check if any event has a region
            has_region = any(e["region"] for e in events)
            if has_region:
                # Group by region
                region_map = defaultdict(list)
                for e in events:
                    region = e["region"] or "Unknown"
                    region_map[region].append(e)
                for region, region_events in region_map.items():
                    lines.append(f"Region: {region}")
                    start_times = [f"<t:{e['event_time_unix']}:R>" for e in region_events if e["timing_type"] == "start"]
                    end_times = [f"<t:{e['event_time_unix']}:R>" for e in region_events if e["timing_type"] == "end"]
                    if start_times:
                        lines.append(f"   Start: {', '.join(start_times)}")
                    if end_times:
                        lines.append(f"   End: {', '.join(end_times)}")
            else:
                start_times = [f"<t:{e['event_time_unix']}:F>" for e in events if e["timing_type"] == "start"]
                end_times = [f"<t:{e['event_time_unix']}:F>" for e in events if e["timing_type"] == "end"]
                if start_times:
                    lines.append(f"Start: {', '.join(start_times)}")
                if end_times:
                    lines.append(f"End: {', '.join(end_times)}")
            lines.append("")  # Blank line between events

    # Discord DMs have a 2000 character limit per message
    msg = ""
    for line in lines:
        if len(msg) + len(line) + 1 > 1990:
            await ctx.author.send(f"{msg}")
            msg = ""
        msg += line + "\n"
    if msg:
        await ctx.author.send(f"{msg}")

    await ctx.send("Pending notifications exported to your DMs.")

@bot.command(name="export_pending_notifications")
async def export_pending_notifications(ctx):
    """Exports the pending notifications table as a DM to the user (owner only)."""
    await export_pending_notifications_core(ctx)

@bot.command(name="epn")
async def epn(ctx):
    """Shortened command for exporting the pending notifications table as a DM to the user (owner only)."""
    await export_pending_notifications_core(ctx)

@bot.command()
async def getlog(ctx):
    """
    Owner-only: Sends the discord.log file to your DMs.
    Usage: Kanami getlog
    """
    OWNER_ID = 680653908259110914  # Found in your code
    if ctx.author.id != OWNER_ID:
        await ctx.send("Only the bot owner can use this command.")
        return
    try:
        file = discord.File("discord.log")
        await ctx.author.send("Here is the latest discord.log file:", file=file)
        await ctx.send("Log file sent to your DMs.")
    except Exception as e:
        await ctx.send(f"Failed to send log file: {e}")