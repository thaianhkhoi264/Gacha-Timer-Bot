from modules import *
from bot import bot, bot_version

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
