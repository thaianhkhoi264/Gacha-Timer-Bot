from modules import *
from twitter_handler import *
from database_handler import *
from utilities import *
from bot import *

@bot.event # Bot announces when its ready
async def on_ready():
    print(f"Kanami is ready to go!")
    # Announce in all assigned announcement channels
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT server_id, announce_channel_id FROM announce_config")
    rows = c.fetchall()
    conn.close()
    for server_id, channel_id in rows:
        guild = bot.get_guild(int(server_id))
        if guild:
            channel = guild.get_channel(int(channel_id))
            if channel:
                try:
                    await channel.send(f"Kanami is ready to go! (version {bot_version})")
                except Exception:
                    pass

@bot.event # Checks for "good girl" and "good boy" in messages
async def on_message(message):
    if message.author == bot.user:
        return  # Ignore messages from the bot itself

    if "good girl" in message.content.lower():
        emoji = "<:KanamiHeart:1374409597628186624>"  # Custom emoji with the given ID
        await message.channel.send(emoji)

    if "good boy" in message.content.lower():
        await message.channel.send(f"Go more more jump off a bridge")

    await bot.process_commands(message)  # Ensure other commands still work

@bot.command() # "assign" command to assign the bot to announce its readiness in this channel
@commands.has_permissions(manage_channels=True)
async def assign(ctx):
    """
    Assigns the bot to announce its readiness in this channel on startup.
    Usage: Kanami assign
    """
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("REPLACE INTO announce_config (server_id, announce_channel_id) VALUES (?, ?)", (str(ctx.guild.id), str(ctx.channel.id)))
    conn.commit()
    conn.close()
    await ctx.send("This channel has been assigned for bot announcements.")

@bot.command()  # "checkchannels" command to show assigned announcement and timer channels
async def checkchannels(ctx):
    """
    Shows which channels are set for announcements and timer updates in this server.
    Usage: Kanami checkchannels
    """
    guild_id = str(ctx.guild.id)
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()

    # Get announcement channel
    c.execute("SELECT announce_channel_id FROM announce_config WHERE server_id=?", (guild_id,))
    announce_row = c.fetchone()
    announce_channel = None
    if announce_row and announce_row[0]:
        announce_channel = ctx.guild.get_channel(int(announce_row[0]))

    # Get timer channel
    c.execute("SELECT timer_channel_id FROM config WHERE server_id=?", (guild_id,))
    timer_row = c.fetchone()
    timer_channel = None
    if timer_row and timer_row[0]:
        timer_channel = ctx.guild.get_channel(int(timer_row[0]))

    conn.close()

    msg = "**Assigned Channels:**\n"
    msg += f"**Announcement Channel:** {announce_channel.mention if announce_channel else 'Not set'}\n"
    msg += f"**Timer Channel:** {timer_channel.mention if timer_channel else 'Not set'}"

    await ctx.send(msg)

@bot.command() # "convert" command to convert date and time to Unix timestamp
async def convert(ctx, time: str, date: str = None):
    """
    Command to convert a given date and time into a Unix timestamp.
    If no date is provided, it assumes today's date.
    """
    try:
        # Use today's date if no date is provided
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        unix_timestamp = convert_to_unix(date, time)
        await ctx.send(f"The Unix timestamp for {date} {time} is: `{unix_timestamp}`")
        await ctx.send(f"Which is <t:{unix_timestamp}:F> your time or <t:{unix_timestamp}:R>")
    except ValueError:
        await ctx.send("Invalid date or time format. Please use `YYYY-MM-DD` for the date and `HH:MM` (24-hour) for the time.")

@bot.command() # "converttz" command to convert date and time to Unix timestamp with timezone
async def converttz(ctx, time: str, date: str = None, timezone_str: str = "UTC"):
    """
    Converts a given date and time in a specified timezone or offset into a Unix timestamp.
    Supports IANA tz names (e.g., 'Asia/Tokyo') and offsets like 'UTC-8', 'GMT+5', etc.
    """
    try:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        unix_timestamp = convert_to_unix_tz(date, time, timezone_str)
        await ctx.send(
            f"The Unix timestamp for {date} {time} in `{timezone_str}` is: `{unix_timestamp}`"
        )
        await ctx.send(
            f"Which is <t:{unix_timestamp}:F> your time or <t:{unix_timestamp}:R>"
        )
    except ValueError as e:
        await ctx.send(
            str(e) if "Unknown timezone" in str(e) else
            "Invalid date or time format. Please use `YYYY-MM-DD` for the date and `HH:MM` (24-hour) for the time."
        )       


@bot.command() # "update" command to manually update the timer channel
async def update(ctx):
    """Manually update the timer channel with the latest events."""
    await update_timer_channel(ctx.guild, bot)
    await ctx.send("Timer channel updated with the latest events.")

@bot.command() # settimerchannel command to set the current channel as the timer display channel
@commands.has_permissions(manage_channels=True)
async def settimerchannel(ctx):
    """Set the current channel as the timer display channel."""
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("REPLACE INTO config (server_id, timer_channel_id) VALUES (?, ?)",
              (str(ctx.guild.id), str(ctx.channel.id)))
    conn.commit()
    conn.close()
    await ctx.send("This channel is now set for timer updates.")

bot.run(token,log_handler=handler, log_level=logging.DEBUG)