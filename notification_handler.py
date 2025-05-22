from modules import *
from bot import *
from database_handler import *
from twitter_handler import *

# function to get the notification timing for a server
async def update_notification_timing_message(guild):
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT channel_id FROM notification_timing_channel WHERE server_id=?", (str(guild.id),))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    channel_id = int(row[0])
    channel = guild.get_channel(channel_id)
    if not channel:
        conn.close()
        return

    c.execute("SELECT category, timing_type, timing_minutes FROM notification_timings WHERE server_id=?", (str(guild.id),))
    timings = c.fetchall()
    conn.close()

    embed = discord.Embed(
        title="Notification Timings",
        description="Current notification timings for each category.",
        color=discord.Color.blue()
    )

    if not timings:
        embed.description = "No notification timings set."
    else:
        # Group by category
        timing_dict = {}
        for cat, ttype, mins in timings:
            if cat not in timing_dict:
                timing_dict[cat] = {}
            timing_dict[cat][ttype] = mins
        for cat, types in timing_dict.items():
            start = types.get("start", "Not set")
            end = types.get("end", "Not set")
            embed.add_field(
                name=f"{cat}",
                value=f"**Start:** {start} min\n**End:** {end} min",
                inline=False
            )

    # Try to edit the existing message, or send a new one
    try:
        c = sqlite3.connect('kanami_data.db').cursor()
        c.execute("SELECT message_id FROM notification_timing_channel WHERE server_id=?", (str(guild.id),))
        msg_row = c.fetchone()
        if msg_row and msg_row[0]:
            message_id = int(msg_row[0])
            try:
                msg = await channel.fetch_message(message_id)
                await msg.edit(content=None, embed=embed)
                return
            except Exception:
                pass
        msg = await channel.send(embed=embed)
        c.execute("UPDATE notification_timing_channel SET message_id=? WHERE server_id=?", (str(msg.id), str(guild.id)))
        c.connection.commit()
    except Exception:
        pass

# Listeners for reaction roles
@bot.event
async def on_raw_reaction_add(payload):
    if payload.member is None or payload.member.bot:
        return
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT role_id FROM role_reactions WHERE server_id=? AND message_id=? AND emoji=?",
              (str(payload.guild_id), str(payload.message_id), str(payload.emoji)))
    row = c.fetchone()
    conn.close()
    if row:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(int(row[0]))
        if role:
            member = guild.get_member(payload.user_id)
            if member:
                await member.add_roles(role, reason="Role reaction add")
                # Send a confirmation message in the channel
                channel = guild.get_channel(payload.channel_id)
                if channel:
                    try:
                        confirm_msg = await channel.send(f"{member.mention}, Kanami will notify you about `{role.name}` news!")
                        await asyncio.sleep(5)
                        await confirm_msg.delete()
                    except Exception:
                        pass

@bot.event
async def on_raw_reaction_remove(payload):
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT role_id FROM role_reactions WHERE server_id=? AND message_id=? AND emoji=?",
              (str(payload.guild_id), str(payload.message_id), str(payload.emoji)))
    row = c.fetchone()
    conn.close()
    if row:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(int(row[0]))
        if role:
            member = guild.get_member(payload.user_id)
            if member:
                await member.remove_roles(role, reason="Role reaction remove")
                # Send a confirmation message in the channel
                channel = guild.get_channel(payload.channel_id)
                if channel:
                    try:
                        confirm_msg = await channel.send(f"{member.mention}, Kanami won't notify you about `{role.name}` anymore...")
                        await asyncio.sleep(5)
                        await confirm_msg.delete()
                    except Exception:
                        pass


#Crete and delete role commands
@bot.command()
@commands.has_permissions(manage_roles=True)
async def create_role(ctx, *, role_name: str):
    """Creates a new role with the given name and assigns an emoji for reaction roles."""
    guild = ctx.guild
    existing_role = discord.utils.get(guild.roles, name=role_name)
    if existing_role:
        await ctx.send(f"Role `{role_name}` already exists.")
        return

    await ctx.send("Please reply with the emoji you want to use for this role (within 30 seconds).")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content

    try:
        msg = await bot.wait_for('message', check=check, timeout=30)
        emoji = msg.content.strip()
    except Exception:
        await ctx.send("No emoji received, cancelling role creation.")
        return

    try:
        role = await guild.create_role(name=role_name)
        await ctx.send(f"Role `{role_name}` created with emoji {emoji}!")
        # Save to DB (role will be added to the reaction message later)
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO role_reactions (server_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
                  (str(guild.id), None, emoji, str(role.id)))
        conn.commit()
        conn.close()
    except discord.Forbidden:
        await ctx.send("I don't have permission to create roles.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def delete_role(ctx, *, role_name: str):
    """Deletes a role with the given name."""
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        await ctx.send(f"Role `{role_name}` does not exist.")
        return

    try:
        await role.delete()
        await ctx.send(f"Role `{role_name}` deleted.")
        # Remove from DB
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        c.execute("DELETE FROM role_reactions WHERE server_id=? AND role_id=?", (str(guild.id), str(role.id)))
        conn.commit()
        conn.close()
    except discord.Forbidden:
        await ctx.send("I don't have permission to delete roles.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def create_role_reaction(ctx):
    """Creates a role reaction message."""
    guild = ctx.guild
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT emoji, role_id FROM role_reactions WHERE server_id=? AND role_id IS NOT NULL", (str(guild.id),))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await ctx.send("No roles with emojis found. Use the create_role command first.")
        return

    msg = await ctx.send("React to this message to get notification for each game.")
    # Save message_id for future reference
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    for emoji, role_id in rows:
        await msg.add_reaction(emoji)
        c.execute("UPDATE role_reactions SET message_id=? WHERE server_id=? AND emoji=?",
                  (str(msg.id), str(guild.id), emoji))
    conn.commit()
    conn.close()
    

@bot.command()
@commands.has_permissions(manage_roles=True)
async def update_role_reaction(ctx):
    """Deletes the current role reaction message and creates a new one."""
    guild = ctx.guild
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    # Get the current message_id (if any)
    c.execute("SELECT DISTINCT message_id FROM role_reactions WHERE server_id=? AND message_id IS NOT NULL", (str(guild.id),))
    row = c.fetchone()
    old_message_id = row[0] if row else None

    # Get all emoji-role pairs
    c.execute("SELECT emoji, role_id FROM role_reactions WHERE server_id=? AND role_id IS NOT NULL", (str(guild.id),))
    rows = c.fetchall()
    conn.close()

    # Delete the old message if it exists
    if old_message_id:
        for channel in guild.text_channels:
            try:
                old_msg = await channel.fetch_message(int(old_message_id))
                if old_msg.author == guild.me:
                    await old_msg.delete()
                    break
            except Exception:
                continue

    if not rows:
        await ctx.send("No roles with emojis found. Use the create_role command first.")
        return

    # Create new role reaction message
    msg = await ctx.send("React to this message to get notification for each game.")
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    for emoji, role_id in rows:
        await msg.add_reaction(emoji)
        c.execute("UPDATE role_reactions SET message_id=? WHERE server_id=? AND emoji=?",
                  (str(msg.id), str(guild.id), emoji))
    conn.commit()
    conn.close()
    await ctx.send("Role reaction message updated!")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def set_notification_channel(ctx, channel: discord.TextChannel):
    """Sets the notification channel for the server."""
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO notification_channel (server_id, channel_id) VALUES (?, ?)",
              (str(ctx.guild.id), str(channel.id)))
    conn.commit()
    conn.close()
    await ctx.send(f"Notification channel set to {channel.mention}.")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def set_notification_timing(ctx, category: str, timing_type: str, minutes: int):
    """
    Set notification timing (in minutes before event) for a category and type (start/end).
    Usage: Kanami set_notification_timing <category> <start|end> <minutes>
    """
    timing_type = timing_type.lower()
    if timing_type not in ("start", "end"):
        await ctx.send("timing_type must be 'start' or 'end'.")
        return
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO notification_timings (server_id, category, timing_type, timing_minutes) VALUES (?, ?, ?, ?)",
        (str(ctx.guild.id), category, timing_type, minutes)
    )
    conn.commit()
    conn.close()
    await ctx.send(f"Notification timing for `{category}` `{timing_type}` set to {minutes} minutes before event.")
    await update_notification_timing_message(ctx.guild)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def set_notification_timing_channel(ctx, channel: discord.TextChannel):
    """Sets the channel where notification timings are displayed and updated."""
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO notification_timing_channel (server_id, channel_id) VALUES (?, ?)",
              (str(ctx.guild.id), str(channel.id)))
    conn.commit()
    conn.close()
    await ctx.send(f"Notification timing status channel set to {channel.mention}.")
    await update_notification_timing_message(ctx.guild)
    