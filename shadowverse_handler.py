import aiosqlite
import asyncio
from discord.ext import commands
from discord import ui, ButtonStyle, Embed, Interaction
from bot import bot
import json
import discord
import io
import logging

CRAFTS = [
    "Forestcraft",
    "Swordcraft",
    "Runecraft",
    "Dragoncraft",
    "Abysscraft",
    "Havencraft",
    "Portalcraft"
]

CRAFT_EMOJIS = {
    "Forestcraft": "<:forestcraft:1396066529849770065>",
    "Swordcraft": "<:swordcraft:1396066540075352094>",
    "Runecraft": "<:runecraft:1396066519644901458>",     
    "Dragoncraft": "<:filenefeet:1396066558819696691>",      
    "Abysscraft": "<:abysscraft:1396066508815208600>",       
    "Havencraft": "<:havencraft:1396066548375879720>",       
    "Portalcraft": "<:portalcraft:1396066495490166874>",      
}

# Abbreviation mapping for crafts
CRAFT_ALIASES = {
    "forest": "Forestcraft", "f": "Forestcraft",
    "sword": "Swordcraft", "s": "Swordcraft",
    "rune": "Runecraft", "r": "Runecraft",
    "dragon": "Dragoncraft", "d": "Dragoncraft",
    "abyss": "Abysscraft", "a": "Abysscraft",
    "haven": "Havencraft", "h": "Havencraft",
    "portal": "Portalcraft", "p": "Portalcraft"
}

async def init_sv_db():
    """
    Initializes the Shadowverse database with tables for channel assignment and winrate tracking.
    Adds 'bricks' column if missing.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS channel_assignments (
                server_id TEXT PRIMARY KEY,
                channel_id TEXT
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS winrates (
                user_id TEXT,
                server_id TEXT,
                played_craft TEXT,
                opponent_craft TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                bricks INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, server_id, played_craft, opponent_craft)
            )
        ''')
        # Try to add bricks column if missing (for upgrades)
        try:
            await conn.execute('ALTER TABLE winrates ADD COLUMN bricks INTEGER DEFAULT 0')
        except Exception:
            pass  # Already exists
        await conn.commit()

BRICK_EMOJI = "<a:golden_brick:1397960479971741747>"

async def record_match(user_id: str, server_id: str, played_craft: str, opponent_craft: str, win: bool, brick: bool = False):
    """
    Records a match result for a user.
    :param brick: True if the match was a brick, False otherwise
    """
    if played_craft not in CRAFTS or opponent_craft not in CRAFTS:
        raise ValueError("Invalid craft name.")
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # Ensure row exists
        await conn.execute('''
            INSERT OR IGNORE INTO winrates (user_id, server_id, played_craft, opponent_craft, wins, losses, bricks)
            VALUES (?, ?, ?, ?, 0, 0, 0)
        ''', (user_id, server_id, played_craft, opponent_craft))
        # Update win/loss/brick
        if win:
            await conn.execute('''
                UPDATE winrates SET wins = wins + 1
                WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
            ''', (user_id, server_id, played_craft, opponent_craft))
        else:
            await conn.execute('''
                UPDATE winrates SET losses = losses + 1
                WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
            ''', (user_id, server_id, played_craft, opponent_craft))
        if brick:
            await conn.execute('''
                UPDATE winrates SET bricks = bricks + 1
                WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
            ''', (user_id, server_id, played_craft, opponent_craft))
        await conn.commit()

def parse_sv_input(text):
    parts = text.strip().lower().split()
    # Only treat r/b as flags if they are after the first 3 parts
    if len(parts) < 3:
        return None
    core = parts[:3]
    flags = [p for p in parts[3:] if p in ("r", "b")]
    played, enemy, result = core
    played_craft = CRAFT_ALIASES.get(played[:6], None) or CRAFT_ALIASES.get(played[0], None)
    enemy_craft = CRAFT_ALIASES.get(enemy[:6], None) or CRAFT_ALIASES.get(enemy[0], None)
    win = None
    if result.startswith("w"):
        win = True
    elif result.startswith("l"):
        win = False
    brick = "b" in flags
    remove = "r" in flags
    if played_craft and enemy_craft and win is not None:
        return played_craft, enemy_craft, win, brick, remove
    return None

async def get_sv_channel_id(server_id):
    """
    Returns the channel ID assigned for Shadowverse logging in this server, or None if not set.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        async with conn.execute('SELECT channel_id FROM channel_assignments WHERE server_id=?', (str(server_id),)) as cursor:
            row = await cursor.fetchone()
    return int(row[0]) if row else None

async def set_dashboard_message_id(server_id, user_id, message_id):
    """
    Sets or removes the dashboard message ID for a user in a server.
    If message_id is None, removes the entry.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        if message_id is not None:
            await conn.execute('''
                INSERT OR REPLACE INTO dashboard_messages (server_id, user_id, message_id)
                VALUES (?, ?, ?)
            ''', (str(server_id), str(user_id), str(message_id)))
        else:
            await conn.execute('DELETE FROM dashboard_messages WHERE server_id=? AND user_id=?', (str(server_id), str(user_id)))
        await conn.commit()

async def get_dashboard_message_id(server_id, user_id):
    """
    Returns the dashboard message ID for a user in a server, or None if not set.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS dashboard_messages (
                server_id TEXT,
                user_id TEXT,
                message_id TEXT,
                PRIMARY KEY (server_id, user_id)
            )
        ''')
        async with conn.execute('SELECT message_id FROM dashboard_messages WHERE server_id=? AND user_id=?', (str(server_id), str(user_id))) as cursor:
            row = await cursor.fetchone()
    if row and row[0] and row[0].isdigit():
        return int(row[0])
    return None

async def update_dashboard_message(member, channel):
    crafts = await get_user_played_crafts(str(member.id), str(channel.guild.id))
    if not crafts:
        return
    craft = crafts[0]
    winrate_dict = await get_winrate(str(member.id), str(channel.guild.id), craft)
    title, desc = craft_winrate_summary(member, craft, winrate_dict)
    embed = Embed(title=title, description=desc, color=0x3498db)
    view = CraftDashboardView(member, channel.guild.id, crafts)
    msg_id = await get_dashboard_message_id(channel.guild.id, member.id)
    if msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed, view=view)
            return
        except Exception:
            pass
    msg = await channel.send(embed=embed, view=view)
    await set_dashboard_message_id(channel.guild.id, member.id, msg.id)

async def get_user_played_crafts(user_id, server_id):
    """
    Returns a list of crafts the user has recorded matches for (as played_craft).
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        async with conn.execute('''
            SELECT DISTINCT played_craft FROM winrates
            WHERE user_id=? AND server_id=? AND (wins > 0 OR losses > 0)
        ''', (str(user_id), str(server_id))) as cursor:
            crafts = [row[0] async for row in cursor]
    return crafts

async def get_winrate(user_id, server_id, played_craft):
    """
    Returns a dict of win/loss/brick stats for the user's played_craft against each opponent craft.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        async with conn.execute('''
            SELECT opponent_craft, wins, losses, bricks FROM winrates
            WHERE user_id=? AND server_id=? AND played_craft=?
        ''', (str(user_id), str(server_id), played_craft)) as cursor:
            results = {craft: {"wins": 0, "losses": 0, "bricks": 0} for craft in CRAFTS}
            async for opponent_craft, wins, losses, bricks in cursor:
                results[opponent_craft] = {"wins": wins, "losses": losses, "bricks": bricks}
    return results

def craft_winrate_summary(user, played_craft, winrate_dict):
    total_wins = sum(v["wins"] for v in winrate_dict.values())
    total_losses = sum(v["losses"] for v in winrate_dict.values())
    total_bricks = sum(v["bricks"] for v in winrate_dict.values())
    total_games = total_wins + total_losses
    winrate = (total_wins / total_games * 100) if total_games > 0 else 0
    title = f"{user.display_name}\n**{played_craft} {CRAFT_EMOJIS.get(played_craft, '')} Win Rate**"
    desc = f"**Total:** {total_wins}W / {total_losses}L / Win rate: {winrate:.1f}% / {BRICK_EMOJI}: {total_bricks}\n"
    desc += "---\n"
    for craft in CRAFTS:
        v = winrate_dict[craft]
        games = v["wins"] + v["losses"]
        wr = (v["wins"] / games * 100) if games > 0 else 0
        desc += (
            f"{craft} {CRAFT_EMOJIS.get(craft, '')}: "
            f"win: {v['wins']} / loss: {v['losses']} / Win rate: {wr:.1f}% / {BRICK_EMOJI}: {v['bricks']}\n"
        )
    return title, desc

# --- Streak DB helpers ---
async def get_streak_state(user_id, server_id):
    """
    Returns the streak data for a user in a server, or None if not set.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS streaks (
                user_id TEXT,
                server_id TEXT,
                streak_data TEXT,
                PRIMARY KEY (user_id, server_id)
            )
        ''')
        async with conn.execute('SELECT streak_data FROM streaks WHERE user_id=? AND server_id=?', (str(user_id), str(server_id))) as cursor:
            row = await cursor.fetchone()
    if row:
        return json.loads(row[0])
    return None

async def set_streak_state(user_id, server_id, streak_data):
    """
    Sets the streak data for a user in a server.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        await conn.execute('''
            INSERT OR REPLACE INTO streaks (user_id, server_id, streak_data)
            VALUES (?, ?, ?)
        ''', (str(user_id), str(server_id), json.dumps(streak_data)))
        await conn.commit()

async def clear_streak_state(user_id, server_id):
    """
    Removes the streak data for a user in a server.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        await conn.execute('DELETE FROM streaks WHERE user_id=? AND server_id=?', (str(user_id), str(server_id)))
        await conn.commit()

async def update_streak_dashboard(member, channel, streak_data):
    # streak_data: list of dicts: [{"played":..., "enemy":..., "win":..., "brick":...}, ...]
    total = len(streak_data)
    wins = sum(1 for m in streak_data if m["win"])
    losses = total - wins
    bricks = sum(1 for m in streak_data if m.get("brick"))
    winrate = (wins / total * 100) if total > 0 else 0
    desc = f"**Streak:** {wins}W / {losses}L / Win rate: {winrate:.1f}% / {BRICK_EMOJI}: {bricks}\n"
    desc += "---\n"
    for i, match in enumerate(streak_data, 1):
        desc += (
            f"{i}. {match['played']} vs {match['enemy']} — {'Win' if match['win'] else 'Loss'}"
            + (f" {BRICK_EMOJI}" if match.get("brick") else "") + "\n"
        )
    embed = Embed(title=f"{member.display_name}'s Streak", description=desc, color=0xf1c40f)
    # Send or update streak dashboard message
    msg = await channel.send(embed=embed)
    return msg.id

async def delete_streak_dashboard(channel, message_id):
    try:
        msg = await channel.fetch_message(message_id)
        await msg.delete()
    except Exception:
        pass

async def export_sv_db_command(message):
    """
    Exports the current Shadowverse database to a readable .txt file and sends it to the user.
    Usage: Type 'exportdb' in the Shadowverse channel.
    Only server admins can export.
    """
    sv_channel_id = await get_sv_channel_id(message.guild.id)
    if sv_channel_id and message.channel.id == sv_channel_id:
        if message.author.bot:
            return
        # Only allow server admins to export
        if not message.author.guild_permissions.administrator:
            await message.channel.send(f"{message.author.mention} You need administrator permissions to export the database.", delete_after=5)
            return

        async with aiosqlite.connect('shadowverse_data.db') as conn:
            output = io.StringIO()
            # Export channel assignments
            output.write("# channel_assignments\n")
            async with conn.execute('SELECT server_id, channel_id FROM channel_assignments') as cursor:
                async for row in cursor:
                    output.write(f"{row[0]}\t{row[1]}\n")
            # Export winrates
            output.write("\n# winrates\n")
            async with conn.execute('SELECT user_id, server_id, played_craft, opponent_craft, wins, losses, bricks FROM winrates') as cursor:
                async for row in cursor:
                    output.write("\t".join(map(str, row)) + "\n")
            # Export dashboard messages
            output.write("\n# dashboard_messages\n")
            async with conn.execute('SELECT server_id, user_id, message_id FROM dashboard_messages') as cursor:
                async for row in cursor:
                    output.write("\t".join(map(str, row)) + "\n")
            # Export streaks
            output.write("\n# streaks\n")
            async with conn.execute('SELECT user_id, server_id, streak_data FROM streaks') as cursor:
                async for row in cursor:
                    output.write("\t".join(map(str, row)) + "\n")
            output.seek(0)
            file = discord.File(fp=io.BytesIO(output.getvalue().encode()), filename="shadowverse_export.txt")
            await message.author.send("Here is your exported Shadowverse database:", file=file)
            await message.channel.send(f"{message.author.mention} Exported database sent via DM.", delete_after=5)

class CraftDashboardView(ui.View):
    def __init__(self, user, server_id, crafts, page=0):
        super().__init__(timeout=180)
        self.user = user
        self.server_id = server_id
        self.crafts = crafts
        self.page = page
        self.max_per_page = 5

        start = page * self.max_per_page
        end = start + self.max_per_page
        crafts_page = crafts[start:end]
        for craft in crafts_page:
            button = ui.Button(
                label=craft,
                emoji=CRAFT_EMOJIS.get(craft, None),
                style=ButtonStyle.primary,
                custom_id=f"craft_{craft}"
            )
            button.callback = self.make_craft_callback(craft)
            self.add_item(button)
        if end < len(crafts):
            next_button = ui.Button(
                label="→",
                style=ButtonStyle.secondary,
                custom_id="next_page"
            )
            next_button.callback = self.next_page_callback
            self.add_item(next_button)
        if page > 0:
            prev_button = ui.Button(
                label="←",
                style=ButtonStyle.secondary,
                custom_id="prev_page"
            )
            prev_button.callback = self.prev_page_callback
            self.add_item(prev_button)

    def make_craft_callback(self, craft):
        async def callback(interaction: Interaction):
            try:
                if interaction.user.id != self.user.id:
                    kanami_anger = "<:KanamiAnger:1406653154111524924>"
                    await interaction.response.send_message(f"This is not your dashboard! {kanami_anger}", ephemeral=True)
                    return
                winrate_dict = await get_winrate(str(self.user.id), str(self.server_id), craft)
                title, desc = craft_winrate_summary(self.user, craft, winrate_dict)
                embed = Embed(title=title, description=desc, color=0x3498db)
                await interaction.response.edit_message(embed=embed, view=CraftDashboardView(self.user, self.server_id, self.crafts, self.page))
            except discord.errors.HTTPException as e:
                if e.status == 429:
                    await interaction.response.send_message("Bot is being rate limited. Please try again in a few seconds.", ephemeral=True)
                else:
                    logging.error(f"[CraftDashboardView] Error in craft callback for {craft}: {e}", exc_info=True)
                    try:
                        await interaction.response.send_message("An error occurred while updating the dashboard.", ephemeral=True)
                    except Exception:
                        pass
            except Exception as e:
                logging.error(f"[CraftDashboardView] Error in craft callback for {craft}: {e}", exc_info=True)
                try:
                    await interaction.response.send_message("An error occurred while updating the dashboard.", ephemeral=True)
                except Exception:
                    pass
        return callback

    async def next_page_callback(self, interaction: Interaction):
        try:
            if interaction.user.id != self.user.id:
                kanami_anger = "<:KanamiAnger:1406653154111524924>"
                await interaction.response.send_message(f"This is not your dashboard! {kanami_anger}", ephemeral=True)
                return
            await interaction.response.edit_message(view=CraftDashboardView(self.user, self.server_id, self.crafts, self.page + 1))
        except Exception as e:
            logging.error(f"[CraftDashboardView] Error in next_page_callback: {e}", exc_info=True)
            try:
                await interaction.response.send_message("An error occurred while changing pages.", ephemeral=True)
            except Exception:
                pass

    async def prev_page_callback(self, interaction: Interaction):
        try:
            if interaction.user.id != self.user.id:
                kanami_anger = "<:KanamiAnger:1406653154111524924>"
                await interaction.response.send_message(f"This is not your dashboard! {kanami_anger}", ephemeral=True)
                return
            await interaction.response.edit_message(view=CraftDashboardView(self.user, self.server_id, self.crafts, self.page - 1))
        except Exception as e:
            logging.error(f"[CraftDashboardView] Error in prev_page_callback: {e}", exc_info=True)
            try:
                await interaction.response.send_message("An error occurred while changing pages.", ephemeral=True)
            except Exception:
                pass

    async def on_error(self, interaction: Interaction, error: Exception, item, /):
        # Log the error with details
        logging.error(f"[CraftDashboardView] Unhandled error in interaction: {error}", exc_info=True)
        try:
            await interaction.response.send_message("An error occurred.", ephemeral=True)
        except Exception:
            pass

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

async def remove_match(user_id: str, server_id: str, played_craft: str, opponent_craft: str, win: bool, brick: bool = False):
    """
    Removes one win/loss/brick record for a user if it exists.
    Returns True if a record was removed, False otherwise.
    """
    if played_craft not in CRAFTS or opponent_craft not in CRAFTS:
        raise ValueError("Invalid craft name.")
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        async with conn.execute('''
            SELECT wins, losses, bricks FROM winrates
            WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
        ''', (user_id, server_id, played_craft, opponent_craft)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return False
        wins, losses, bricks = row
        updated = False
        if win and wins > 0:
            await conn.execute('''
                UPDATE winrates SET wins = wins - 1
                WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
            ''', (user_id, server_id, played_craft, opponent_craft))
            updated = True
        elif not win and losses > 0:
            await conn.execute('''
                UPDATE winrates SET losses = losses - 1
                WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
            ''', (user_id, server_id, played_craft, opponent_craft))
            updated = True
        if brick and bricks > 0:
            await conn.execute('''
                UPDATE winrates SET bricks = bricks - 1
                WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
            ''', (user_id, server_id, played_craft, opponent_craft))
            updated = True
        await conn.commit()
        return updated

async def shadowverse_on_message(message):
    kanami_emoji = "<:KanamiHeart:1374409597628186624>"
    if message.author.bot:
        return False
    try:
        sv_channel_id = await get_sv_channel_id(message.guild.id)
        if sv_channel_id and message.channel.id == sv_channel_id:
            content = message.content.strip().lower()
            user_id = str(message.author.id)
            server_id = str(message.guild.id)

            # --- Refresh command ---
            if message.author.id == 680653908259110914 and content == "refresh":
                await message.delete()
                instruction = (
                    "**Shadowverse Winrate Tracker**\n"
                    "To record a match, type:\n"
                    "`[Your Deck] [Enemy Deck] [Win/Lose]`\n"
                    "Examples: `Sword Dragon Win`, `S D W`, `Swordcraft Dragon W`, `Abyss Haven Lose`, `A H L`\n"
                    "Accepted abbreviations: `F`/`Forest`, `S`/`Sword`, `R`/`Rune`, `D`/`Dragon`, `A`/`Abyss`, `H`/`Haven`, `P`/`Portal`.\n"
                    "Accepted results: `Win`/`W`, `Lose`/`L`.\n"
                    "Add `B` for brick, `R` to remove, in any order.\n"
                    "If you want to start a streak, type `streak start`, and to end it, type `streak end`.\n"
                    "Your message will be deleted and your dashboard will be updated automatically."
                )
                await message.channel.send(instruction)
                for member in message.guild.members:
                    if not member.bot:
                        await update_dashboard_message(member, message.channel)
                return True

            # --- Backread command ---
            if content == "backread":
                owner_id = 680653908259110914
                if message.author.id != owner_id and not message.author.guild_permissions.administrator:
                    await message.reply("Only the bot owner or server admins can use this command.", mention_author=False, delete_after=5)
                    return True
                await message.reply("Starting backread scan...", mention_author=False, delete_after=5)
                # Run the scan for this channel only
                report_logged = []
                report_skipped = []
                try:
                    async for msg in message.channel.history(limit=500):
                        if msg.author.bot:
                            continue
                        parsed = None
                        try:
                            parsed = parse_sv_input(msg.content)
                        except Exception as e:
                            report_skipped.append(f"[{message.guild.name}] {msg.author.display_name}: {msg.content} (parse error: {e})")
                            continue
                        if parsed:
                            played_craft, enemy_craft, win, brick, remove = parsed
                            try:
                                await record_match(str(msg.author.id), str(message.guild.id), played_craft, enemy_craft, win, brick)
                                report_logged.append(f"[{message.guild.name}] {msg.author.display_name}: {msg.content} (logged)")
                            except Exception as e:
                                report_skipped.append(f"[{message.guild.name}] {msg.author.display_name}: {msg.content} (record error: {e})")
                        else:
                            report_skipped.append(f"[{message.guild.name}] {msg.author.display_name}: {msg.content} (skipped: invalid format)")
                except Exception as e:
                    report_skipped.append(f"[{message.guild.name}] Error fetching history: {e}")

                # Prepare report
                report = "**Shadowverse Backread Scan Report**\n\n"
                report += f"**Logged Matches ({len(report_logged)}):**\n" + "\n".join(report_logged) + "\n\n"
                report += f"**Skipped Messages ({len(report_skipped)}):**\n" + "\n".join(report_skipped)

                # Send report to the user who requested
                try:
                    if len(report_logged) > 0 or len(report_skipped) > 0:
                        await message.author.send(report if len(report) < 1900 else report[:1900] + "\n...(truncated)")
                except Exception:
                    pass
                return True


            # --- Streak start ---
            if content == "streak start":
                await message.delete()
                await set_streak_state(user_id, server_id, [])
                streak_msg_id = await update_streak_dashboard(message.author, message.channel, [])
                await set_dashboard_message_id(server_id, f"streak_{user_id}", streak_msg_id)
                await message.reply(
                    "Streak started! All matches will be tracked until you type `streak end`.\n(This dashboard is only for you.)",
                    mention_author=False,
                    delete_after=5
                )
                return True

            # --- Streak end ---
            if content == "streak end":
                await message.delete()
                streak_data = await get_streak_state(user_id, server_id)
                streak_msg_id = await get_dashboard_message_id(server_id, f"streak_{user_id}")
                if streak_data and streak_msg_id:
                    # Prepare streak summary
                    total = len(streak_data)
                    wins = sum(1 for m in streak_data if m["win"])
                    losses = total - wins
                    bricks = sum(1 for m in streak_data if m.get("brick"))
                    winrate = (wins / total * 100) if total > 0 else 0
                    desc = f"**Streak:** {wins}W / {losses}L / Win rate: {winrate:.1f}% / {BRICK_EMOJI}: {bricks}\n"
                    desc += "---\n"
                    for i, match in enumerate(streak_data, 1):
                        desc += (
                            f"{i}. {match['played']} vs {match['enemy']} — {'Win' if match['win'] else 'Loss'}"
                            + (f" {BRICK_EMOJI}" if match.get("brick") else "") + "\n"
                        )
                    embed = Embed(title=f"{message.author.display_name}'s Streak Summary", description=desc, color=0xf1c40f)
                    try:
                        await message.author.send(embed=embed)
                    except Exception:
                        pass
                    await delete_streak_dashboard(message.channel, streak_msg_id)
                    await clear_streak_state(user_id, server_id)
                    await set_dashboard_message_id(server_id, f"streak_{user_id}", None)
                    await message.reply(
                        "Streak ended! Summary sent via DM.\n(This dashboard is only for you.)",
                        mention_author=False,
                        delete_after=5
                    )
                else:
                    await message.reply(
                        "No active streak to end.\n(This dashboard is only for you.)",
                        mention_author=False,
                        delete_after=5
                    )
                return True

            # --- Export database command ---
            sv_channel_id = await get_sv_channel_id(message.guild.id)
            if sv_channel_id and message.channel.id == sv_channel_id:
                content = message.content.strip().lower()
                if content == "exportdb":
                    await export_sv_db_command(message)
                    return True

            # --- Normal match logging ---
            parsed = None
            try:
                parsed = parse_sv_input(message.content)
            except Exception as e:
                print(f"[Shadowverse] Parse error: {e}")

            if parsed:
                played_craft, enemy_craft, win, brick, remove = parsed
                try:
                    # If streak is active, log to streak
                    streak_data = await get_streak_state(user_id, server_id)
                    streak_msg_id = await get_dashboard_message_id(server_id, f"streak_{user_id}")
                    if streak_data is not None:
                        streak_data.append({
                            "played": played_craft,
                            "enemy": enemy_craft,
                            "win": win,
                            "brick": brick
                        })
                        await set_streak_state(user_id, server_id, streak_data)
                        # Update streak dashboard
                        if streak_msg_id:
                            try:
                                msg = await message.channel.fetch_message(streak_msg_id)
                                total = len(streak_data)
                                wins = sum(1 for m in streak_data if m["win"])
                                losses = total - wins
                                bricks = sum(1 for m in streak_data if m.get("brick"))
                                winrate = (wins / total * 100) if total > 0 else 0
                                desc = f"**Streak:** {wins}W / {losses}L / Win rate: {winrate:.1f}% / {BRICK_EMOJI}: {bricks}\n"
                                desc += "---\n"
                                for i, match in enumerate(streak_data, 1):
                                    desc += (
                                        f"{i}. {match['played']} vs {match['enemy']} — {'Win' if match['win'] else 'Loss'}"
                                        + (f" {BRICK_EMOJI}" if match.get("brick") else "") + "\n"
                                    )
                                embed = Embed(title=f"{message.author.display_name}'s Streak", description=desc, color=0xf1c40f)
                                await msg.edit(embed=embed)
                            except Exception as e:
                                logging.warning(f"Failed to edit dashboard message: {e}")
                        else:
                            streak_msg_id = await update_streak_dashboard(message.author, message.channel, streak_data)
                            await set_dashboard_message_id(server_id, f"streak_{user_id}", streak_msg_id)
                    # Continue with normal winrate logging
                    if not remove:
                        await record_match(user_id, server_id, played_craft, enemy_craft, win, brick)
                        LOSS_MESSAGES = {
                            "Forestcraft": "SVO Moment 😔",
                            "Swordcraft": "Zirconia on curve be like",
                            "Runecraft": "Rune... Rune never changes",
                            "Dragoncraft": "How did you lose to this? <:filenefeet:1396066558819696691>",
                            "Abysscraft": "You fell for the Sham 😔",
                            "Havencraft": "You lost to a NEET Deck 😔",
                            "Portalcraft": "I can still feel the eggs vibrating... 😔"
                        }
                        # Sends attachment images if played craft is Dragoncraft
                        files = []
                        if played_craft == "Dragoncraft":
                            if win:
                                files.append(discord.File("images/dragon_win.png"))
                            else:
                                files.append(discord.File("images/dragon_loss.png"))
                        if not win:
                            reply_text = LOSS_MESSAGES.get(enemy_craft)
                            if brick:
                                reply_text += ", and also you should've drawn better 😔"
                            reply_msg = await message.reply(
                                f"Kanami recorded your match {kanami_emoji}, {reply_text}",
                                mention_author=False,
                                files = files if files else None
                            )
                        else:
                            reply_msg = await message.reply(
                                f"Kanami recorded your match, nice win! {kanami_emoji}",
                                mention_author=False,
                                files = files if files else None
                            )
                    else:
                        removed = await remove_match(user_id, server_id, played_craft, enemy_craft, win, brick)
                        if removed:
                            reply_msg = await message.reply(
                                f"Kanami removed your match {kanami_emoji}",
                                mention_author=False
                            )
                        else:
                            reply_msg = await message.reply(
                                f"⚠️ No record found to remove for: **{played_craft}** vs **{enemy_craft}** — {'Win' if win else 'Loss'}{' (Brick)' if brick else ''}\n(This dashboard is only for you.)",
                                mention_author=False
                            )
                    await update_dashboard_message(message.author, message.channel)
                    # Delete both messages after 5 seconds
                    await asyncio.sleep(5)
                    try:
                        await reply_msg.delete()
                    except Exception:
                        pass
                    try:
                        await message.delete()
                    except Exception:
                        pass
                except Exception as e:
                    print(f"[Shadowverse] Record error: {e}")
                    try:
                        reply_msg = await message.reply(
                            "An error occurred while recording your match. Please try again.\n(This dashboard is only for you.)",
                            mention_author=False
                        )
                        await asyncio.sleep(5)
                        await reply_msg.delete()
                        await message.delete()
                    except Exception:
                        pass
            else:
                try:
                    reply_msg = await message.reply(
                        "Invalid format. Use `[Your Deck] [Enemy Deck] [Win/Lose]` (e.g., `Sword Dragon Win` or `S D W`). Add `B` for brick, `R` to remove, in any order.\n(This dashboard is only for you.)",
                        mention_author=False
                    )
                    await asyncio.sleep(5)
                    await reply_msg.delete()
                    await message.delete()
                except Exception:
                    pass
            return True  # handled
    except Exception as e:
        print(f"[Shadowverse] Unexpected error in on_message: {e}")
    return False  # not handled

@bot.command(name="shadowverse")
@commands.has_permissions(manage_channels=True)
async def shadowverse(ctx, channel_id: int = None):
    """
    Sets the Shadowverse channel for this server.
    Usage: Kanami shadowverse [channel_id]
    If no channel_id is provided, uses the current channel.
    """
    await init_sv_db()
    channel = ctx.guild.get_channel(channel_id) if channel_id else ctx.channel
    if not channel:
        await ctx.send("Invalid channel ID.")
        return
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        await conn.execute('''
            INSERT OR REPLACE INTO channel_assignments (server_id, channel_id)
            VALUES (?, ?)
        ''', (str(ctx.guild.id), str(channel.id)))
        await conn.commit()
    # Instruction message at the top
    instruction = (
        "**Shadowverse Winrate Tracker**\n"
        "To record a match, type:\n"
        "`[Your Deck] [Enemy Deck] [Win/Lose]`\n"
        "Examples: `Sword Dragon Win`, `S D W`, `Swordcraft Dragon W`, `Abyss Haven Lose`, `A H L`\n"
        "Accepted abbreviations: `F`/`Forest`, `S`/`Sword`, `R`/`Rune`, `D`/`Dragon`, `A`/`Abyss`, `H`/`Haven`, `P`/`Portal`.\n"
        "Accepted results: `Win`/`W`, `Lose`/`L`.\n"
        "Add `B` for brick, `R` to remove, in any order.\n"
        "If you want to start a streak, type `streak start`, and to end it, type 'streak end'.\n"
        "Your message will be deleted and your dashboard will be updated automatically."
    )
    await channel.send(instruction)
    await ctx.send(f"{channel.mention} has been set as the Shadowverse channel for this server.")
    # Optionally, update dashboards for all users with data
    for member in ctx.guild.members:
        if not member.bot:
            await update_dashboard_message(member, channel)