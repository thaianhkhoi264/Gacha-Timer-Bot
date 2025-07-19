import sqlite3
from discord.ext import commands
from discord import ui, ButtonStyle, Embed, Interaction
from bot import bot

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

def init_sv_db():
    """
    Initializes the Shadowverse database with tables for channel assignment and winrate tracking.
    """
    conn = sqlite3.connect('shadowverse_data.db')
    c = conn.cursor()
    # Channel assignment table
    c.execute('''
        CREATE TABLE IF NOT EXISTS channel_assignments (
            server_id TEXT PRIMARY KEY,
            channel_id TEXT
        )
    ''')
    # Winrate tracking table
    c.execute('''
        CREATE TABLE IF NOT EXISTS winrates (
            user_id TEXT,
            server_id TEXT,
            played_craft TEXT,
            opponent_craft TEXT,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, server_id, played_craft, opponent_craft)
        )
    ''')
    conn.commit()
    conn.close()

def record_match(user_id: str, server_id: str, played_craft: str, opponent_craft: str, win: bool):
    """
    Records a match result for a user.
    :param user_id: Discord user ID
    :param server_id: Discord server ID
    :param played_craft: The craft the user played
    :param opponent_craft: The craft the opponent played
    :param win: True if user won, False if lost
    """
    if played_craft not in CRAFTS or opponent_craft not in CRAFTS:
        raise ValueError("Invalid craft name.")
    conn = sqlite3.connect('shadowverse_data.db')
    c = conn.cursor()
    # Ensure row exists
    c.execute('''
        INSERT OR IGNORE INTO winrates (user_id, server_id, played_craft, opponent_craft, wins, losses)
        VALUES (?, ?, ?, ?, 0, 0)
    ''', (user_id, server_id, played_craft, opponent_craft))
    # Update win/loss
    if win:
        c.execute('''
            UPDATE winrates SET wins = wins + 1
            WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
        ''', (user_id, server_id, played_craft, opponent_craft))
    else:
        c.execute('''
            UPDATE winrates SET losses = losses + 1
            WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
        ''', (user_id, server_id, played_craft, opponent_craft))
    conn.commit()
    conn.close()

def parse_sv_input(text):
    # Accepts formats like "Sword Dragon Win", "S D W", "Swordcraft Dragon W", etc.
    parts = text.strip().lower().split()
    if len(parts) != 3:
        return None
    played, enemy, result = parts
    played_craft = CRAFT_ALIASES.get(played[:6], None) or CRAFT_ALIASES.get(played[0], None)
    enemy_craft = CRAFT_ALIASES.get(enemy[:6], None) or CRAFT_ALIASES.get(enemy[0], None)
    win = None
    if result.startswith("w"):
        win = True
    elif result.startswith("l"):
        win = False
    if played_craft and enemy_craft and win is not None:
        return played_craft, enemy_craft, win
    return None

def get_sv_channel_id(server_id):
    conn = sqlite3.connect('shadowverse_data.db')
    c = conn.cursor()
    c.execute('SELECT channel_id FROM channel_assignments WHERE server_id=?', (str(server_id),))
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else None

def set_dashboard_message_id(server_id, user_id, message_id):
    conn = sqlite3.connect('shadowverse_data.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO dashboard_messages (server_id, user_id, message_id)
        VALUES (?, ?, ?)
    ''', (str(server_id), str(user_id), str(message_id)))
    conn.commit()
    conn.close()

def get_dashboard_message_id(server_id, user_id):
    conn = sqlite3.connect('shadowverse_data.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS dashboard_messages (
            server_id TEXT,
            user_id TEXT,
            message_id TEXT,
            PRIMARY KEY (server_id, user_id)
        )
    ''')
    c.execute('SELECT message_id FROM dashboard_messages WHERE server_id=? AND user_id=?', (str(server_id), str(user_id)))
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else None

async def update_dashboard_message(member, channel):
    crafts = get_user_played_crafts(str(member.id), str(channel.guild.id))
    if not crafts:
        return
    craft = crafts[0]
    winrate_dict = get_winrate(str(member.id), str(channel.guild.id), craft)
    title, desc = craft_winrate_summary(member, craft, winrate_dict)
    embed = Embed(title=title, description=desc, color=0x3498db)
    view = CraftDashboardView(member, channel.guild.id, crafts)
    msg_id = get_dashboard_message_id(channel.guild.id, member.id)
    if msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed, view=view)
            return
        except Exception:
            pass
    msg = await channel.send(embed=embed, view=view)
    set_dashboard_message_id(channel.guild.id, member.id, msg.id)


def get_user_played_crafts(user_id, server_id):
    """
    Returns a list of crafts the user has recorded matches for (as played_craft).
    """
    conn = sqlite3.connect('shadowverse_data.db')
    c = conn.cursor()
    c.execute('''
        SELECT DISTINCT played_craft FROM winrates
        WHERE user_id=? AND server_id=? AND (wins > 0 OR losses > 0)
    ''', (str(user_id), str(server_id)))
    crafts = [row[0] for row in c.fetchall()]
    conn.close()
    return crafts

def get_winrate(user_id, server_id, played_craft):
    """
    Returns a dict of win/loss stats for the user's played_craft against each opponent craft.
    """
    conn = sqlite3.connect('shadowverse_data.db')
    c = conn.cursor()
    c.execute('''
        SELECT opponent_craft, wins, losses FROM winrates
        WHERE user_id=? AND server_id=? AND played_craft=?
    ''', (str(user_id), str(server_id), played_craft))
    results = {craft: {"wins": 0, "losses": 0} for craft in CRAFTS}
    for opponent_craft, wins, losses in c.fetchall():
        results[opponent_craft] = {"wins": wins, "losses": losses}
    conn.close()
    return results

def craft_winrate_summary(user, played_craft, winrate_dict):
    total_wins = sum(v["wins"] for v in winrate_dict.values())
    total_losses = sum(v["losses"] for v in winrate_dict.values())
    total_games = total_wins + total_losses
    winrate = (total_wins / total_games * 100) if total_games > 0 else 0
    title = f"{user.display_name}\n**{played_craft} {CRAFT_EMOJIS.get(played_craft, '')} Win Rate**"
    desc = f"**Total:** {total_wins}W / {total_losses}L / Win rate: {winrate:.1f}%\n"
    desc += "---\n"
    for craft in CRAFTS:
        v = winrate_dict[craft]
        games = v["wins"] + v["losses"]
        wr = (v["wins"] / games * 100) if games > 0 else 0
        desc += f"{craft} {CRAFT_EMOJIS.get(craft, '')}: win: {v['wins']} / loss: {v['losses']} / Win rate: {wr:.1f}%\n"
    return title, desc

class CraftDashboardView(ui.View):
    def __init__(self, user, server_id, crafts, page=0):
        super().__init__(timeout=180)
        self.user = user
        self.server_id = server_id
        self.crafts = crafts
        self.page = page
        self.max_per_page = 5

        # Only show up to 5 crafts per page, last button is "→" if more pages
        start = page * self.max_per_page
        end = start + self.max_per_page
        crafts_page = crafts[start:end]
        for i, craft in enumerate(crafts_page):
            self.add_item(ui.Button(
                label=craft,
                emoji=CRAFT_EMOJIS.get(craft, None),
                style=ButtonStyle.primary,
                custom_id=f"craft_{craft}"
            ))
        if end < len(crafts):
            self.add_item(ui.Button(
                label="→",
                style=ButtonStyle.secondary,
                custom_id="next_page"
            ))
        if page > 0:
            self.add_item(ui.Button(
                label="←",
                style=ButtonStyle.secondary,
                custom_id="prev_page"
            ))

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user.id

    @ui.button(label="dummy", style=ButtonStyle.secondary, disabled=True, row=4)
    async def dummy(self, interaction: Interaction, button: ui.Button):
        pass  # Placeholder to avoid empty row error

    async def on_error(self, interaction: Interaction, error: Exception, item, /):
        await interaction.response.send_message("An error occurred.", ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    @ui.button(label="dummy", style=ButtonStyle.secondary, disabled=True, row=4)
    async def dummy2(self, interaction: Interaction, button: ui.Button):
        pass

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user.id

    async def on_button_click(self, interaction: Interaction):
        custom_id = interaction.data["custom_id"]
        if custom_id.startswith("craft_"):
            craft = custom_id[6:]
            winrate_dict = get_winrate(str(self.user.id), str(self.server_id), craft)
            title, desc = craft_winrate_summary(self.user, craft, winrate_dict)
            embed = Embed(title=title, description=desc, color=0x3498db)
            await interaction.response.edit_message(embed=embed, view=CraftDashboardView(self.user, self.server_id, self.crafts, self.page))
        elif custom_id == "next_page":
            await interaction.response.edit_message(view=CraftDashboardView(self.user, self.server_id, self.crafts, self.page + 1))
        elif custom_id == "prev_page":
            await interaction.response.edit_message(view=CraftDashboardView(self.user, self.server_id, self.crafts, self.page - 1))

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user.id

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    try:
        sv_channel_id = get_sv_channel_id(message.guild.id)
        if sv_channel_id and message.channel.id == sv_channel_id:
            parsed = None
            try:
                parsed = parse_sv_input(message.content)
            except Exception as e:
                # Log parsing error for debugging
                print(f"[Shadowverse] Parse error: {e}")
            await message.delete()
            if parsed:
                try:
                    played_craft, enemy_craft, win = parsed
                    record_match(str(message.author.id), str(message.guild.id), played_craft, enemy_craft, win)
                    # Ephemeral confirmation (Discord doesn't support true ephemeral for normal messages, so DM the user)
                    try:
                        await message.author.send(
                            f"✅ Recorded: **{played_craft}** vs **{enemy_craft}** — {'Win' if win else 'Loss'}"
                        )
                    except Exception:
                        pass  # Ignore DM errors (user may have DMs closed)
                    await update_dashboard_message(message.author, message.channel)
                except Exception as e:
                    print(f"[Shadowverse] Record error: {e}")
                    try:
                        await message.channel.send(
                            f"{message.author.mention} An error occurred while recording your match. Please try again.",
                            delete_after=5
                        )
                    except Exception:
                        pass
            else:
                try:
                    await message.channel.send(
                        f"{message.author.mention} Invalid format. Use `[Your Deck] [Enemy Deck] [Win/Lose]` (e.g., `Sword Dragon Win` or `S D W`).",
                        delete_after=5
                    )
                except Exception:
                    pass
    except Exception as e:
        print(f"[Shadowverse] Unexpected error in on_message: {e}")

@bot.command(name="shadowverse")
@commands.has_permissions(manage_channels=True)
async def shadowverse(ctx, channel_id: int = None):
    """
    Sets the Shadowverse channel for this server.
    Usage: Kanami shadowverse [channel_id]
    If no channel_id is provided, uses the current channel.
    """
    init_sv_db()
    channel = ctx.guild.get_channel(channel_id) if channel_id else ctx.channel
    if not channel:
        await ctx.send("Invalid channel ID.")
        return
    conn = sqlite3.connect('shadowverse_data.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO channel_assignments (server_id, channel_id)
        VALUES (?, ?)
    ''', (str(ctx.guild.id), str(channel.id)))
    conn.commit()
    conn.close()
    # Instruction message at the top
    instruction = (
        "**Shadowverse Winrate Tracker**\n"
        "To record a match, type:\n"
        "`[Your Deck] [Enemy Deck] [Win/Lose]`\n"
        "Examples: `Sword Dragon Win`, `S D W`, `Swordcraft Dragon W`, `Abyss Haven Lose`, `A H L`\n"
        "Accepted abbreviations: `F`/`Forest`, `S`/`Sword`, `R`/`Rune`, `D`/`Dragon`, `A`/`Abyss`, `H`/`Haven`, `P`/`Portal`.\n"
        "Accepted results: `Win`/`W`, `Lose`/`L`.\n"
        "Your message will be deleted and your dashboard will be updated automatically."
    )
    await channel.send(instruction)
    await ctx.send(f"{channel.mention} has been set as the Shadowverse channel for this server.")
    # Optionally, update dashboards for all users with data
    for member in ctx.guild.members:
        if not member.bot:
            await update_dashboard_message(member, channel)

# Initialize the database
init_sv_db