import aiosqlite
import asyncio
from discord.ext import commands
from discord import ui, ButtonStyle, Embed, Interaction
from bot import bot
import json
import discord
import io
import logging
import os
from io import BytesIO

# Try to import PIL for image generation
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("PIL not available, dashboard will use embeds")

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

# Color specifications for image generation
DASHBOARD_COLORS = {
    "bg_top": (26, 95, 122),        # #1a5f7a - Cyan top
    "bg_bottom": (13, 47, 63),      # #0d2f3f - Dark blue bottom
    "gold": (212, 175, 55),         # #d4af37 - Gold border/dividers
    "white": (255, 255, 255),       # #ffffff - Text
    "green": (0, 255, 0),           # #00ff00 - Win count
    "red": (255, 68, 68),           # #ff4444 - Loss count
    "bar_red": (255, 68, 68),       # #ff4444 - 0-45%
    "bar_yellow": (255, 170, 0),    # #ffaa00 - 45-55%
    "bar_green": (0, 255, 0),       # #00ff00 - 55-100%
}

# Global icon cache for image generation
_icon_cache = None

class IconCache:
    """Cache for loaded and resized icons to improve performance."""

    def __init__(self):
        self.cache = {}

    def get_class_icon(self, craft_name, size=(50, 56)):
        """Load and resize a class icon."""
        key = f"class_{craft_name}_{size}"
        if key not in self.cache:
            craft_short = craft_name.lower().replace("craft", "")
            filename = f"class_{craft_short}.png"
            path = os.path.join("images", "Class", filename)

            try:
                img = Image.open(path).convert("RGBA")
                img = img.resize(size, Image.Resampling.LANCZOS)
                self.cache[key] = img
            except Exception as e:
                logging.warning(f"Failed to load icon {path}: {e}")
                img = Image.new("RGBA", size, (100, 100, 100, 255))
                self.cache[key] = img

        return self.cache[key]

    def get_brick_icon(self, size=(24, 24)):
        """Load and resize the brick icon."""
        key = f"brick_{size}"
        if key not in self.cache:
            path = os.path.join("images", "golden_brick.png")

            try:
                img = Image.open(path).convert("RGBA")
                img = img.resize(size, Image.Resampling.LANCZOS)
                self.cache[key] = img
            except Exception as e:
                logging.warning(f"Failed to load brick icon {path}: {e}")
                img = Image.new("RGBA", size, (255, 215, 0, 255))
                self.cache[key] = img

        return self.cache[key]


def load_dashboard_font(size, bold=False):
    """Load Noto Sans font with fallback to system fonts."""
    if not PIL_AVAILABLE:
        return None

    font_name = "NotoSans-VariableFont_wdth,wght.ttf"
    font_path = os.path.join("fonts", font_name)

    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        system_fonts = [
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]

        for system_font in system_fonts:
            try:
                return ImageFont.truetype(system_font, size)
            except Exception:
                continue

        logging.warning("Could not load any scalable font, text will be small")
        return ImageFont.load_default()


def create_gradient(width, height, color_top, color_bottom):
    """Create a vertical gradient background."""
    base = Image.new('RGB', (width, height), color_top)
    draw = ImageDraw.Draw(base)

    for y in range(height):
        ratio = y / height
        r = int(color_top[0] * (1 - ratio) + color_bottom[0] * ratio)
        g = int(color_top[1] * (1 - ratio) + color_bottom[1] * ratio)
        b = int(color_top[2] * (1 - ratio) + color_bottom[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    return base


def draw_octagonal_border(draw, width, height, inset, corner_cut, color, thickness):
    """Draw an octagonal border with cut corners."""
    points = [
        (inset + corner_cut, inset),
        (width - inset - corner_cut, inset),
        (width - inset, inset + corner_cut),
        (width - inset, height - inset - corner_cut),
        (width - inset - corner_cut, height - inset),
        (inset + corner_cut, height - inset),
        (inset, height - inset - corner_cut),
        (inset, inset + corner_cut),
    ]

    for i in range(len(points)):
        start = points[i]
        end = points[(i + 1) % len(points)]
        draw.line([start, end], fill=color, width=thickness)


def add_stroked_icon(base_img, icon, x, y, outer_black=3, gold=3, inner_black=3):
    """Add a class icon with a triple-layer stroke/outline effect following the icon's shape."""
    icon_w, icon_h = icon.size

    total_stroke = outer_black + gold + inner_black
    padding = total_stroke + 2
    stroked_w = icon_w + padding * 2
    stroked_h = icon_h + padding * 2

    stroked = Image.new('RGBA', (stroked_w, stroked_h), (0, 0, 0, 0))

    def get_offsets(radius):
        offsets = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx*dx + dy*dy <= radius*radius:
                    offsets.append((dx, dy))
        return offsets

    alpha = icon.split()[3]

    # Layer 1: Outer black stroke
    outer_offsets = get_offsets(total_stroke)
    for dx, dy in outer_offsets:
        black_icon = Image.new('RGBA', (icon_w, icon_h), (0, 0, 0, 255))
        black_icon.putalpha(alpha)
        stroked.paste(black_icon, (padding + dx, padding + dy), black_icon)

    # Layer 2: Gold stroke
    gold_offsets = get_offsets(gold + inner_black)
    for dx, dy in gold_offsets:
        gold_icon = Image.new('RGBA', (icon_w, icon_h), DASHBOARD_COLORS["gold"] + (255,))
        gold_icon.putalpha(alpha)
        stroked.paste(gold_icon, (padding + dx, padding + dy), gold_icon)

    # Layer 3: Inner black stroke
    inner_offsets = get_offsets(inner_black)
    for dx, dy in inner_offsets:
        black_icon = Image.new('RGBA', (icon_w, icon_h), (0, 0, 0, 255))
        black_icon.putalpha(alpha)
        stroked.paste(black_icon, (padding + dx, padding + dy), black_icon)

    stroked.paste(icon, (padding, padding), icon)
    base_img.paste(stroked, (x - padding, y - padding), stroked)


def draw_winrate_bar(draw, x, y, width, height, winrate):
    """Draw a colored win rate bar (clean design without background)."""
    if winrate < 45:
        color = DASHBOARD_COLORS["bar_red"]
    elif winrate < 55:
        color = DASHBOARD_COLORS["bar_yellow"]
    else:
        color = DASHBOARD_COLORS["bar_green"]

    display_winrate = max(winrate, 1.0) if winrate > 0 else 1.0
    fill_width = int(width * (display_winrate / 100))
    if fill_width > 0:
        draw.rectangle([x, y, x + fill_width, y + height], fill=color)


def generate_dashboard_image(user_name, played_craft, winrate_dict):
    """
    Generate a Shadowverse win rate dashboard image.

    Returns BytesIO object containing PNG image, or None if PIL is not available.
    """
    if not PIL_AVAILABLE:
        return None

    global _icon_cache
    if _icon_cache is None:
        _icon_cache = IconCache()

    width, height = 1600, 900

    # Create gradient background
    img = create_gradient(width, height, DASHBOARD_COLORS["bg_top"], DASHBOARD_COLORS["bg_bottom"])
    draw = ImageDraw.Draw(img)

    # Draw octagonal border
    draw_octagonal_border(draw, width, height, inset=10, corner_cut=30, color=DASHBOARD_COLORS["gold"], thickness=3)

    # Load fonts
    font_header = load_dashboard_font(56, bold=True)
    font_title = load_dashboard_font(48, bold=True)
    font_normal = load_dashboard_font(36, bold=False)
    font_stats = load_dashboard_font(32, bold=False)

    # Calculate totals
    total_wins = sum(v["wins"] for v in winrate_dict.values())
    total_losses = sum(v["losses"] for v in winrate_dict.values())
    total_bricks = sum(v["bricks"] for v in winrate_dict.values())
    total_games = total_wins + total_losses
    total_winrate = (total_wins / total_games * 100) if total_games > 0 else 0

    # Layout constants
    content_x = 60
    y = 30

    # Draw header: User Name
    draw.text((content_x, y - 5), user_name, fill=DASHBOARD_COLORS["white"], font=font_header)
    y += 80

    # Draw title: [icon] Craft Name Win Rate
    class_icon = _icon_cache.get_class_icon(played_craft, size=(60, 67))
    title_icon_height = 67
    add_stroked_icon(img, class_icon, content_x, y)

    title_text = f"{played_craft} Win Rate"
    title_center = y + title_icon_height // 2
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    text_height = bbox[3] - bbox[1]
    title_y = title_center - text_height // 2 - 10
    draw.text((content_x + 80, title_y), title_text, fill=DASHBOARD_COLORS["white"], font=font_title)
    y += 85

    # Draw first divider
    divider_left = content_x
    divider_right = width - 60
    draw.line([(divider_left, y), (divider_right, y)], fill=DASHBOARD_COLORS["gold"], width=3)
    y += 30

    # Draw matchup rows
    bar_width = 650
    bar_height = 28
    row_height = 78

    # Draw brick icon header
    brick_icon = _icon_cache.get_brick_icon(size=(48, 48))
    brick_column_x = width - 180
    img.paste(brick_icon, (brick_column_x + 5, y - 90), brick_icon)

    for craft in CRAFTS:
        stats = winrate_dict.get(craft, {"wins": 0, "losses": 0, "bricks": 0})
        wins = stats["wins"]
        losses = stats["losses"]
        bricks = stats["bricks"]
        games = wins + losses
        winrate = (wins / games * 100) if games > 0 else 0

        # Draw class icon with stroke
        craft_icon = _icon_cache.get_class_icon(craft, size=(50, 56))
        icon_height = 56
        add_stroked_icon(img, craft_icon, content_x, y)

        # Calculate vertical center of the row
        row_center = y + icon_height // 2 - 10

        # Draw craft name
        craft_x = content_x + 70
        bbox = draw.textbbox((0, 0), craft, font=font_normal)
        text_height = bbox[3] - bbox[1]
        craft_y = row_center - text_height // 2
        draw.text((craft_x, craft_y), craft, fill=DASHBOARD_COLORS["white"], font=font_normal)

        # Draw win rate bar
        bar_x = craft_x + 320
        bar_y = row_center - bar_height // 2 + 12
        draw_winrate_bar(draw, bar_x, bar_y, bar_width, bar_height, winrate)

        # Draw percentage
        percent_x = bar_x + bar_width + 20
        percent_text = f"{winrate:.1f}%"
        bbox = draw.textbbox((0, 0), percent_text, font=font_stats)
        text_height = bbox[3] - bbox[1]
        percent_y = row_center - text_height // 2
        draw.text((percent_x, percent_y), percent_text, fill=DASHBOARD_COLORS["white"], font=font_stats)

        # Draw win/loss counts
        wl_x = percent_x + 140
        win_text = f"{wins}W"
        loss_text = f"{losses}L"
        bbox = draw.textbbox((0, 0), win_text, font=font_stats)
        text_height = bbox[3] - bbox[1]
        wl_y = row_center - text_height // 2
        draw.text((wl_x, wl_y), win_text, fill=DASHBOARD_COLORS["green"], font=font_stats)
        draw.text((wl_x + 85, wl_y), "/", fill=DASHBOARD_COLORS["white"], font=font_stats)
        draw.text((wl_x + 105, wl_y), loss_text, fill=DASHBOARD_COLORS["red"], font=font_stats)

        # Draw brick count
        brick_text = str(bricks)
        bbox = draw.textbbox((0, 0), brick_text, font=font_stats)
        text_height = bbox[3] - bbox[1]
        brick_y = row_center - text_height // 2
        draw.text((brick_column_x + 20, brick_y), brick_text, fill=DASHBOARD_COLORS["white"], font=font_stats)

        y += row_height

    # Draw second divider
    y += 10
    draw.line([(divider_left, y), (divider_right, y)], fill=DASHBOARD_COLORS["gold"], width=3)
    y += 30

    # Draw total row
    total_row_center = y + 56 // 2 - 10

    # Draw total label
    total_label = "Total Win Rate"
    bbox = draw.textbbox((0, 0), total_label, font=font_normal)
    text_height = bbox[3] - bbox[1]
    total_label_y = total_row_center - text_height // 2
    draw.text((content_x, total_label_y), total_label, fill=DASHBOARD_COLORS["white"], font=font_normal)

    # Draw total win rate bar
    total_bar_x = content_x + 390
    total_bar_y = total_row_center - bar_height // 2 + 10
    draw_winrate_bar(draw, total_bar_x, total_bar_y, bar_width, bar_height, total_winrate)

    # Draw total percentage
    total_percent_x = total_bar_x + bar_width + 20
    total_percent_text = f"{total_winrate:.1f}%"
    bbox = draw.textbbox((0, 0), total_percent_text, font=font_stats)
    text_height = bbox[3] - bbox[1]
    total_percent_y = total_row_center - text_height // 2
    draw.text((total_percent_x, total_percent_y), total_percent_text, fill=DASHBOARD_COLORS["white"], font=font_stats)

    # Draw total win/loss counts
    total_wl_x = total_percent_x + 140
    total_win_text = f"{total_wins}W"
    total_loss_text = f"{total_losses}L"
    bbox = draw.textbbox((0, 0), total_win_text, font=font_stats)
    text_height = bbox[3] - bbox[1]
    total_wl_y = total_row_center - text_height // 2
    draw.text((total_wl_x, total_wl_y), total_win_text, fill=DASHBOARD_COLORS["green"], font=font_stats)
    draw.text((total_wl_x + 85, total_wl_y), "/", fill=DASHBOARD_COLORS["white"], font=font_stats)
    draw.text((total_wl_x + 105, total_wl_y), total_loss_text, fill=DASHBOARD_COLORS["red"], font=font_stats)

    # Draw total brick count
    total_brick_text = str(total_bricks)
    bbox = draw.textbbox((0, 0), total_brick_text, font=font_stats)
    text_height = bbox[3] - bbox[1]
    total_brick_y = total_row_center - text_height // 2
    draw.text((brick_column_x + 20, total_brick_y), total_brick_text, fill=DASHBOARD_COLORS["white"], font=font_stats)

    # Return BytesIO
    buffer = BytesIO()
    img.save(buffer, 'PNG')
    buffer.seek(0)
    return buffer


async def init_sv_db():
    """
    Initializes the Shadowverse database with tables for channel assignment and winrate tracking.
    Adds 'bricks' column if missing. Adds season tracking.
    Adds detailed match history table for individual match records.
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
        # Season configuration table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS season_config (
                server_id TEXT PRIMARY KEY,
                current_season INTEGER DEFAULT 3
            )
        ''')
        # Archived season data table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS archived_winrates (
                season INTEGER,
                user_id TEXT,
                server_id TEXT,
                played_craft TEXT,
                opponent_craft TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                bricks INTEGER DEFAULT 0,
                PRIMARY KEY (season, user_id, server_id, played_craft, opponent_craft)
            )
        ''')
        # Detailed match history table (for individual matches with metadata)
        # NOTE: This table will be deprecated after migration to 3-table system
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                played_craft TEXT NOT NULL,
                opponent_craft TEXT NOT NULL,
                win INTEGER NOT NULL,
                brick INTEGER DEFAULT 0,
                timestamp TEXT,
                player_points INTEGER,
                player_point_type TEXT,
                player_rank TEXT,
                player_group TEXT,
                opponent_points INTEGER,
                opponent_point_type TEXT,
                opponent_rank TEXT,
                opponent_group TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        # NEW: 3-Table Architecture for clean source separation
        # Discord-logged matches (simple, no metadata)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS discord_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                played_craft TEXT NOT NULL,
                opponent_craft TEXT NOT NULL,
                win INTEGER NOT NULL,
                brick INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        # API-logged matches (detailed with metadata)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS api_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                played_craft TEXT NOT NULL,
                opponent_craft TEXT NOT NULL,
                win INTEGER NOT NULL,
                brick INTEGER DEFAULT 0,
                timestamp TEXT,
                player_points INTEGER,
                player_point_type TEXT,
                player_rank TEXT,
                player_group TEXT,
                opponent_points INTEGER,
                opponent_point_type TEXT,
                opponent_rank TEXT,
                opponent_group TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        # Combined winrates (aggregated from both discord_matches and api_matches)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS combined_winrates (
                user_id TEXT,
                server_id TEXT,
                played_craft TEXT,
                opponent_craft TEXT,
                discord_wins INTEGER DEFAULT 0,
                discord_losses INTEGER DEFAULT 0,
                discord_bricks INTEGER DEFAULT 0,
                api_wins INTEGER DEFAULT 0,
                api_losses INTEGER DEFAULT 0,
                api_bricks INTEGER DEFAULT 0,
                total_wins INTEGER DEFAULT 0,
                total_losses INTEGER DEFAULT 0,
                total_bricks INTEGER DEFAULT 0,
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

async def get_current_season(server_id):
    """
    Returns the current season number for a server. Defaults to 3 if not set.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        await conn.execute('''
            INSERT OR IGNORE INTO season_config (server_id, current_season)
            VALUES (?, 3)
        ''', (str(server_id),))
        await conn.commit()
        async with conn.execute('SELECT current_season FROM season_config WHERE server_id=?', (str(server_id),)) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else 3

async def archive_current_season(server_id):
    """
    Archives all current winrate data to the archived_winrates table with the current season number,
    then clears the current match tables (discord_matches, api_matches, combined_winrates) and increments the season.
    Returns the archived season number and count of records archived.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        current_season = await get_current_season(server_id)

        # NEW: 3-Table Architecture - Copy combined totals to archived_winrates
        await conn.execute('''
            INSERT INTO archived_winrates (season, user_id, server_id, played_craft, opponent_craft, wins, losses, bricks)
            SELECT ?, user_id, server_id, played_craft, opponent_craft, total_wins, total_losses, total_bricks
            FROM combined_winrates
            WHERE server_id = ?
        ''', (current_season, str(server_id)))

        # Count archived records
        async with conn.execute('SELECT COUNT(*) FROM combined_winrates WHERE server_id=?', (str(server_id),)) as cursor:
            row = await cursor.fetchone()
            archived_count = row[0] if row else 0

        # NEW: 3-Table Architecture - Clear all three tables for this server
        await conn.execute('DELETE FROM discord_matches WHERE server_id=?', (str(server_id),))
        await conn.execute('DELETE FROM api_matches WHERE server_id=?', (str(server_id),))
        await conn.execute('DELETE FROM combined_winrates WHERE server_id=?', (str(server_id),))

        # LEGACY: Also clear old tables for backward compatibility
        # TODO: Remove after migration is complete and verified
        await conn.execute('DELETE FROM winrates WHERE server_id=?', (str(server_id),))

        # Increment season
        new_season = current_season + 1
        await conn.execute('UPDATE season_config SET current_season=? WHERE server_id=?', (new_season, str(server_id)))

        await conn.commit()

    return current_season, archived_count, new_season

async def get_archived_winrate(user_id, server_id, played_craft, season):
    """
    Returns a dict of win/loss/brick stats for the user's played_craft against each opponent craft
    for a specific archived season.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        async with conn.execute('''
            SELECT opponent_craft, wins, losses, bricks FROM archived_winrates
            WHERE user_id=? AND server_id=? AND played_craft=? AND season=?
        ''', (str(user_id), str(server_id), played_craft, season)) as cursor:
            results = {craft: {"wins": 0, "losses": 0, "bricks": 0} for craft in CRAFTS}
            async for opponent_craft, wins, losses, bricks in cursor:
                results[opponent_craft] = {"wins": wins, "losses": losses, "bricks": bricks}
    return results

async def get_archived_user_crafts(user_id, server_id, season):
    """
    Returns a list of crafts the user has recorded matches for in a specific season.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        async with conn.execute('''
            SELECT DISTINCT played_craft FROM archived_winrates
            WHERE user_id=? AND server_id=? AND season=? AND (wins > 0 OR losses > 0)
        ''', (str(user_id), str(server_id), season)) as cursor:
            crafts = [row[0] async for row in cursor]
    return crafts

async def get_available_seasons(server_id):
    """
    Returns a list of season numbers that have archived data for this server.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        async with conn.execute('''
            SELECT DISTINCT season FROM archived_winrates WHERE server_id=? ORDER BY season DESC
        ''', (str(server_id),)) as cursor:
            seasons = [row[0] async for row in cursor]
    return seasons

async def _update_combined_winrates(conn, user_id, server_id, played_craft, opponent_craft,
                                     win, brick, source, increment=True):
    """
    Helper function to update combined_winrates table.

    Updates the appropriate source-specific columns (discord_* or api_*) and total columns.

    :param conn: Active aiosqlite connection
    :param user_id: Discord user ID
    :param server_id: Discord server ID
    :param played_craft: Craft played by user
    :param opponent_craft: Opponent's craft
    :param win: True if win, False if loss
    :param brick: True if bricked
    :param source: 'discord' or 'api'
    :param increment: True to add (+1), False to subtract (-1)
    """
    # Ensure row exists
    await conn.execute('''
        INSERT OR IGNORE INTO combined_winrates (
            user_id, server_id, played_craft, opponent_craft,
            discord_wins, discord_losses, discord_bricks,
            api_wins, api_losses, api_bricks,
            total_wins, total_losses, total_bricks
        ) VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    ''', (user_id, server_id, played_craft, opponent_craft))

    # Determine which columns to update based on source
    if source == "discord":
        win_col = "discord_wins"
        loss_col = "discord_losses"
        brick_col = "discord_bricks"
    elif source == "api":
        win_col = "api_wins"
        loss_col = "api_losses"
        brick_col = "api_bricks"
    else:
        raise ValueError(f"Invalid source: {source}. Must be 'discord' or 'api'.")

    delta = 1 if increment else -1

    # Update source-specific win/loss columns and totals
    if win:
        await conn.execute(f'''
            UPDATE combined_winrates
            SET {win_col} = MAX(0, {win_col} + ?), total_wins = MAX(0, total_wins + ?)
            WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
        ''', (delta, delta, user_id, server_id, played_craft, opponent_craft))
    else:
        await conn.execute(f'''
            UPDATE combined_winrates
            SET {loss_col} = MAX(0, {loss_col} + ?), total_losses = MAX(0, total_losses + ?)
            WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
        ''', (delta, delta, user_id, server_id, played_craft, opponent_craft))

    # Update brick columns if bricked
    if brick:
        await conn.execute(f'''
            UPDATE combined_winrates
            SET {brick_col} = MAX(0, {brick_col} + ?), total_bricks = MAX(0, total_bricks + ?)
            WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
        ''', (delta, delta, user_id, server_id, played_craft, opponent_craft))

async def record_match(user_id: str, server_id: str, played_craft: str, opponent_craft: str, win: bool, brick: bool = False,
                       source: str = "discord",
                       timestamp: str = None, player_points: int = None, player_point_type: str = None,
                       player_rank: str = None, player_group: str = None, opponent_points: int = None,
                       opponent_point_type: str = None, opponent_rank: str = None, opponent_group: str = None):
    """
    Records a match result for a user in the new 3-table architecture.

    :param user_id: Discord user ID
    :param server_id: Discord server ID
    :param played_craft: Craft played by the user
    :param opponent_craft: Craft played by the opponent
    :param win: True if win, False if loss
    :param brick: True if the match was a brick, False otherwise
    :param source: Match source - "discord" or "api" (default: "discord")
    :param timestamp: ISO format timestamp of the match (optional, required for API)
    :param player_points: Player's points (optional, API only)
    :param player_point_type: Type of points (e.g., 'RP', 'MP') (optional, API only)
    :param player_rank: Player's rank (e.g., 'A1', 'Master') (optional, API only)
    :param player_group: Player's group (e.g., 'Topaz', 'Diamond') (optional, API only)
    :param opponent_points: Opponent's points (optional, API only)
    :param opponent_point_type: Opponent's point type (optional, API only)
    :param opponent_rank: Opponent's rank (optional, API only)
    :param opponent_group: Opponent's group (optional, API only)
    :return: Match ID from the appropriate table
    """
    if played_craft not in CRAFTS or opponent_craft not in CRAFTS:
        raise ValueError("Invalid craft name.")

    if source not in ("discord", "api"):
        raise ValueError(f"Invalid source: {source}. Must be 'discord' or 'api'.")

    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # NEW: 3-Table Architecture - Route to appropriate table based on source
        if source == "discord":
            # Insert into discord_matches (simple, no metadata)
            cursor = await conn.execute('''
                INSERT INTO discord_matches (
                    user_id, server_id, played_craft, opponent_craft, win, brick
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, server_id, played_craft, opponent_craft, int(win), int(brick)))
            match_id = cursor.lastrowid

        elif source == "api":
            # Insert into api_matches (detailed with metadata)
            cursor = await conn.execute('''
                INSERT INTO api_matches (
                    user_id, server_id, played_craft, opponent_craft, win, brick,
                    timestamp, player_points, player_point_type, player_rank, player_group,
                    opponent_points, opponent_point_type, opponent_rank, opponent_group
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, server_id, played_craft, opponent_craft, int(win), int(brick),
                  timestamp, player_points, player_point_type, player_rank, player_group,
                  opponent_points, opponent_point_type, opponent_rank, opponent_group))
            match_id = cursor.lastrowid

        # Update combined_winrates table
        await _update_combined_winrates(conn, user_id, server_id, played_craft, opponent_craft,
                                        win, brick, source, increment=True)

        # LEGACY: Also update old tables for backward compatibility during migration
        # TODO: Remove after migration is complete and verified
        await conn.execute('''
            INSERT OR IGNORE INTO winrates (user_id, server_id, played_craft, opponent_craft, wins, losses, bricks)
            VALUES (?, ?, ?, ?, 0, 0, 0)
        ''', (user_id, server_id, played_craft, opponent_craft))

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

        # LEGACY: Also insert into old matches table
        await conn.execute('''
            INSERT INTO matches (
                user_id, server_id, played_craft, opponent_craft, win, brick,
                timestamp, player_points, player_point_type, player_rank, player_group,
                opponent_points, opponent_point_type, opponent_rank, opponent_group
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, server_id, played_craft, opponent_craft, int(win), int(brick),
              timestamp, player_points, player_point_type, player_rank, player_group,
              opponent_points, opponent_point_type, opponent_rank, opponent_group))

        await conn.commit()
        return match_id

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

async def refresh_all_dashboards():
    """
    Refresh all Shadowverse dashboards across all servers.
    Called on bot startup to update dashboard images.
    """
    from bot import bot
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # Get all servers with Shadowverse channels
        async with conn.execute('SELECT DISTINCT server_id FROM channel_assignment') as cursor:
            server_ids = [row[0] async for row in cursor]

    for server_id in server_ids:
        guild = bot.get_guild(int(server_id))
        if not guild:
            continue

        # Get the Shadowverse channel
        sv_channel_id = await get_sv_channel(server_id)
        if not sv_channel_id:
            continue

        sv_channel = guild.get_channel(int(sv_channel_id))
        if not sv_channel:
            continue

        # Refresh dashboards for all users in this server
        for member in guild.members:
            if not member.bot:
                try:
                    await update_dashboard_message(member, sv_channel)
                except Exception as e:
                    logging.error(f"[Refresh] Error updating dashboard for {member.name} in {guild.name}: {e}")

async def update_dashboard_message(member, channel):
    crafts = await get_user_played_crafts(str(member.id), str(channel.guild.id))
    if not crafts:
        return
    craft = crafts[0]
    winrate_dict = await get_winrate(str(member.id), str(channel.guild.id), craft)
    view = CraftDashboardView(member, channel.guild.id, crafts)
    msg_id = await get_dashboard_message_id(channel.guild.id, member.id)

    # Try to generate image, fall back to embed if PIL is not available
    image_buffer = generate_dashboard_image(member.display_name, craft, winrate_dict)

    if image_buffer:
        # Use image-based dashboard
        file = discord.File(fp=image_buffer, filename="dashboard.png")

        if msg_id:
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(attachments=[file], view=view)
                return
            except Exception:
                pass
        msg = await channel.send(file=file, view=view)
        await set_dashboard_message_id(channel.guild.id, member.id, msg.id)
    else:
        # Fall back to embed-based dashboard
        title, desc = craft_winrate_summary(member, craft, winrate_dict)
        embed = Embed(title=title, description=desc, color=0x3498db)

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
    Reads from combined_winrates table which aggregates both Discord and API matches.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # NEW: 3-Table Architecture - Read from combined_winrates
        async with conn.execute('''
            SELECT DISTINCT played_craft FROM combined_winrates
            WHERE user_id=? AND server_id=? AND (total_wins > 0 OR total_losses > 0)
        ''', (str(user_id), str(server_id))) as cursor:
            crafts = [row[0] async for row in cursor]
    return crafts

async def get_winrate(user_id, server_id, played_craft):
    """
    Returns a dict of win/loss/brick stats for the user's played_craft against each opponent craft.
    Reads from combined_winrates table which aggregates both Discord and API matches.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # NEW: 3-Table Architecture - Read from combined_winrates
        async with conn.execute('''
            SELECT opponent_craft, total_wins, total_losses, total_bricks FROM combined_winrates
            WHERE user_id=? AND server_id=? AND played_craft=?
        ''', (str(user_id), str(server_id), played_craft)) as cursor:
            results = {craft: {"wins": 0, "losses": 0, "bricks": 0} for craft in CRAFTS}
            async for opponent_craft, wins, losses, bricks in cursor:
                results[opponent_craft] = {"wins": wins, "losses": losses, "bricks": bricks}
    return results

def craft_winrate_summary(user, played_craft, winrate_dict):
    """
    Legacy embed format - FALLBACK ONLY (used when PIL is not available).
    New dashboards use image generation instead.
    """
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
    def __init__(self, user, server_id, crafts, page=0, season=None):
        super().__init__(timeout=180)
        self.user = user
        self.server_id = server_id
        self.crafts = crafts
        self.page = page
        self.season = season  # None = current season, int = archived season
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

                # Defer the interaction to prevent timeout
                await interaction.response.defer()

                # Get winrate data based on season
                if self.season is None:
                    winrate_dict = await get_winrate(str(self.user.id), str(self.server_id), craft)
                    current_season = await get_current_season(self.server_id)
                    season_text = f" (Season {current_season})"
                else:
                    winrate_dict = await get_archived_winrate(str(self.user.id), str(self.server_id), craft, self.season)
                    season_text = f" (Season {self.season} - Archived)"

                # Try to generate image, fall back to embed if PIL is not available
                user_name = self.user.display_name + season_text
                image_buffer = generate_dashboard_image(user_name, craft, winrate_dict)

                if image_buffer:
                    # Use image-based dashboard
                    file = discord.File(fp=image_buffer, filename="dashboard.png")
                    await interaction.edit_original_response(attachments=[file], view=CraftDashboardView(self.user, self.server_id, self.crafts, self.page, self.season))
                else:
                    # Fall back to embed-based dashboard
                    title, desc = craft_winrate_summary(self.user, craft, winrate_dict)
                    title += season_text
                    embed = Embed(title=title, description=desc, color=0x3498db)
                    await interaction.edit_original_response(embed=embed, view=CraftDashboardView(self.user, self.server_id, self.crafts, self.page, self.season))
            except discord.errors.HTTPException as e:
                if e.status == 429:
                    await interaction.followup.send("Bot is being rate limited. Please try again in a few seconds.", ephemeral=True)
                else:
                    logging.error(f"[CraftDashboardView] Error in craft callback for {craft}: {e}", exc_info=True)
                    try:
                        await interaction.followup.send("An error occurred while updating the dashboard.", ephemeral=True)
                    except Exception:
                        pass
            except Exception as e:
                logging.error(f"[CraftDashboardView] Error in craft callback for {craft}: {e}", exc_info=True)
                try:
                    await interaction.followup.send("An error occurred while updating the dashboard.", ephemeral=True)
                except Exception:
                    pass
        return callback

    async def next_page_callback(self, interaction: Interaction):
        try:
            if interaction.user.id != self.user.id:
                kanami_anger = "<:KanamiAnger:1406653154111524924>"
                await interaction.response.send_message(f"This is not your dashboard! {kanami_anger}", ephemeral=True)
                return
            await interaction.response.edit_message(view=CraftDashboardView(self.user, self.server_id, self.crafts, self.page + 1, self.season))
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
            await interaction.response.edit_message(view=CraftDashboardView(self.user, self.server_id, self.crafts, self.page - 1, self.season))
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
    Removes one Discord match record for a user if it exists.
    Only affects discord_matches table (NOT api_matches).
    Returns True if a record was removed, False otherwise.

    This is used by Discord 'r' flag removal (e.g., "dragon forest w r").
    """
    if played_craft not in CRAFTS or opponent_craft not in CRAFTS:
        raise ValueError("Invalid craft name.")

    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # NEW: 3-Table Architecture - Find most recent Discord match
        async with conn.execute('''
            SELECT id, brick FROM discord_matches
            WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=? AND win=?
            ORDER BY id DESC LIMIT 1
        ''', (user_id, server_id, played_craft, opponent_craft, int(win))) as cursor:
            row = await cursor.fetchone()

        if not row:
            return False

        match_id, match_brick = row

        # Delete from discord_matches
        await conn.execute('DELETE FROM discord_matches WHERE id=?', (match_id,))

        # Update combined_winrates (decrement Discord stats)
        await _update_combined_winrates(
            conn, user_id, server_id, played_craft, opponent_craft,
            win, bool(match_brick), source="discord", increment=False
        )

        # LEGACY: Also update old winrates table for backward compatibility
        # TODO: Remove after migration is complete and verified
        async with conn.execute('''
            SELECT wins, losses, bricks FROM winrates
            WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
        ''', (user_id, server_id, played_craft, opponent_craft)) as cursor:
            legacy_row = await cursor.fetchone()

        if legacy_row:
            wins, losses, bricks_count = legacy_row
            if win and wins > 0:
                await conn.execute('''
                    UPDATE winrates SET wins = wins - 1
                    WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
                ''', (user_id, server_id, played_craft, opponent_craft))
            elif not win and losses > 0:
                await conn.execute('''
                    UPDATE winrates SET losses = losses - 1
                    WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
                ''', (user_id, server_id, played_craft, opponent_craft))
            if match_brick and bricks_count > 0:
                await conn.execute('''
                    UPDATE winrates SET bricks = bricks - 1
                    WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=?
                ''', (user_id, server_id, played_craft, opponent_craft))

        await conn.commit()
        return True

async def remove_match_by_id(match_id: int, user_id: str):
    """
    Removes an API match by its ID and updates the combined_winrates table accordingly.
    Only affects api_matches table (NOT discord_matches).
    Only allows removal if the match belongs to the specified user (security check).

    This is used by the API endpoint for removing matches via DELETE /api/shadowverse/match/{id}.

    :param match_id: The ID of the match to remove
    :param user_id: The Discord user ID (for ownership verification)
    :return: Tuple (success: bool, message: str, match_data: dict or None)
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # NEW: 3-Table Architecture - Query from api_matches only
        async with conn.execute('''
            SELECT user_id, server_id, played_craft, opponent_craft, win, brick,
                   timestamp, player_points, player_point_type, player_rank, player_group,
                   opponent_points, opponent_point_type, opponent_rank, opponent_group
            FROM api_matches
            WHERE id = ?
        ''', (match_id,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            return False, "Match not found", None

        (match_user_id, server_id, played_craft, opponent_craft, win, brick,
         timestamp, player_points, player_point_type, player_rank, player_group,
         opponent_points, opponent_point_type, opponent_rank, opponent_group) = row

        # Security check: verify the match belongs to this user
        if match_user_id != user_id:
            return False, "You don't have permission to remove this match", None

        # Delete from api_matches
        await conn.execute('DELETE FROM api_matches WHERE id = ?', (match_id,))

        # Update combined_winrates (decrement API stats)
        await _update_combined_winrates(
            conn, match_user_id, server_id, played_craft, opponent_craft,
            bool(win), bool(brick), source="api", increment=False
        )

        # LEGACY: Also update old winrates table for backward compatibility
        # TODO: Remove after migration is complete and verified
        if win:
            await conn.execute('''
                UPDATE winrates SET wins = wins - 1
                WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=? AND wins > 0
            ''', (match_user_id, server_id, played_craft, opponent_craft))
        else:
            await conn.execute('''
                UPDATE winrates SET losses = losses - 1
                WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=? AND losses > 0
            ''', (match_user_id, server_id, played_craft, opponent_craft))

        if brick:
            await conn.execute('''
                UPDATE winrates SET bricks = bricks - 1
                WHERE user_id=? AND server_id=? AND played_craft=? AND opponent_craft=? AND bricks > 0
            ''', (match_user_id, server_id, played_craft, opponent_craft))

        await conn.commit()

        match_data = {
            "id": match_id,
            "played_craft": played_craft,
            "opponent_craft": opponent_craft,
            "win": bool(win),
            "brick": bool(brick),
            "timestamp": timestamp,
            "player_points": player_points,
            "player_point_type": player_point_type,
            "player_rank": player_rank,
            "player_group": player_group,
            "opponent_points": opponent_points,
            "opponent_point_type": opponent_point_type,
            "opponent_rank": opponent_rank,
            "opponent_group": opponent_group
        }

        return True, "Match removed successfully", match_data

async def get_recent_matches(user_id: str, server_id: str, limit: int = 10):
    """
    Gets the most recent matches for a user from both Discord and API sources.
    Merges results from discord_matches and api_matches tables.

    :param user_id: Discord user ID
    :param server_id: Discord server ID
    :param limit: Maximum number of matches to return (default 10)
    :return: List of match dictionaries with source indicator
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # NEW: 3-Table Architecture - Query from both tables

        # Get Discord matches (simple, no metadata)
        async with conn.execute('''
            SELECT id, played_craft, opponent_craft, win, brick, created_at
            FROM discord_matches
            WHERE user_id = ? AND server_id = ?
        ''', (user_id, server_id)) as cursor:
            discord_matches = []
            async for row in cursor:
                discord_matches.append({
                    "id": row[0],
                    "source": "discord",
                    "played_craft": row[1],
                    "opponent_craft": row[2],
                    "win": bool(row[3]),
                    "brick": bool(row[4]),
                    "timestamp": None,
                    "player": {
                        "points": None,
                        "point_type": None,
                        "rank": None,
                        "group": None
                    },
                    "opponent": {
                        "points": None,
                        "point_type": None,
                        "rank": None,
                        "group": None
                    },
                    "created_at": row[5]
                })

        # Get API matches (detailed with metadata)
        async with conn.execute('''
            SELECT id, played_craft, opponent_craft, win, brick, timestamp,
                   player_points, player_point_type, player_rank, player_group,
                   opponent_points, opponent_point_type, opponent_rank, opponent_group,
                   created_at
            FROM api_matches
            WHERE user_id = ? AND server_id = ?
        ''', (user_id, server_id)) as cursor:
            api_matches = []
            async for row in cursor:
                api_matches.append({
                    "id": row[0],
                    "source": "api",
                    "played_craft": row[1],
                    "opponent_craft": row[2],
                    "win": bool(row[3]),
                    "brick": bool(row[4]),
                    "timestamp": row[5],
                    "player": {
                        "points": row[6],
                        "point_type": row[7],
                        "rank": row[8],
                        "group": row[9]
                    },
                    "opponent": {
                        "points": row[10],
                        "point_type": row[11],
                        "rank": row[12],
                        "group": row[13]
                    },
                    "created_at": row[14]
                })

        # Merge and sort by ID descending (most recent first)
        all_matches = discord_matches + api_matches
        all_matches.sort(key=lambda x: x['id'], reverse=True)

        # Return up to limit matches
        return all_matches[:limit]

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
                current_season = await get_current_season(message.guild.id)
                instruction = (
                    f"**🎮 Shadowverse Winrate Tracker - Season {current_season} 🎮**\n\n"
                    f"**📝 How to Record Matches:**\n"
                    f"Type: `[Your Deck] [Enemy Deck] [Win/Loss]`\n\n"
                    f"**Examples:**\n"
                    f"• `Sword Dragon Win` or `S D W`\n"
                    f"• `Abyss Haven Loss` or `A H L`\n"
                    f"• `Forest Rune Win B` (B = bricked)\n"
                    f"• `Portal Sword Loss R` (R = remove/undo)\n\n"
                    f"**🃏 Craft Abbreviations:**\n"
                    f"F/Forest, S/Sword, R/Rune, D/Dragon, A/Abyss, H/Haven, P/Portal\n\n"
                    f"**📊 Additional Features:**\n"
                    f"• Add `B` to mark a match as bricked\n"
                    f"• Add `R` to remove/undo a match\n"
                    f"• Type `streak start` to begin tracking a win streak\n"
                    f"• Type `streak end` to finish and get your streak summary\n\n"
                    f"**📜 View Stats:**\n"
                    f"• Your stats will automatically appear below\n"
                    f"• Click craft buttons to view different matchups\n"
                    f"• Use `Kanami sv_seasons` to see all seasons\n\n"
                    f"Your messages will be automatically deleted and your dashboard will update! ✨"
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
                                await record_match(str(msg.author.id), str(message.guild.id), played_craft, enemy_craft, win, brick, source="discord")
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
                        await record_match(user_id, server_id, played_craft, enemy_craft, win, brick, source="discord")
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
    
    current_season = await get_current_season(ctx.guild.id)
    
    # Instruction message at the top
    instruction = (
        f"**🎮 Shadowverse Winrate Tracker - Season {current_season} 🎮**\n\n"
        f"**📝 How to Record Matches:**\n"
        f"Type: `[Your Deck] [Enemy Deck] [Win/Loss]`\n\n"
        f"**Examples:**\n"
        f"• `Sword Dragon Win` or `S D W`\n"
        f"• `Abyss Haven Loss` or `A H L`\n"
        f"• `Forest Rune Win B` (B = bricked)\n"
        f"• `Portal Sword Loss R` (R = remove/undo)\n\n"
        f"**🃏 Craft Abbreviations:**\n"
        f"F/Forest, S/Sword, R/Rune, D/Dragon, A/Abyss, H/Haven, P/Portal\n\n"
        f"**📊 Additional Features:**\n"
        f"• Add `B` to mark a match as bricked\n"
        f"• Add `R` to remove/undo a match\n"
        f"• Type `streak start` to begin tracking a win streak\n"
        f"• Type `streak end` to finish and get your streak summary\n\n"
        f"**📜 View Stats:**\n"
        f"• Your stats will automatically appear below\n"
        f"• Click craft buttons to view different matchups\n"
        f"• Use `Kanami sv_seasons` to see all seasons\n\n"
        f"Your messages will be automatically deleted and your dashboard will update! ✨"
    )
    await channel.send(instruction)
    await ctx.send(f"{channel.mention} has been set as the Shadowverse channel for this server.")
    # Optionally, update dashboards for all users with data
    for member in ctx.guild.members:
        if not member.bot:
            await update_dashboard_message(member, channel)

@bot.command(name="sv_newseason")
@commands.has_permissions(administrator=True)
async def sv_newseason(ctx):
    """
    Archives current season data and starts a new season.
    Usage: Kanami sv_newseason
    Requires administrator permissions.
    """
    await init_sv_db()
    
    # Confirm action
    current_season = await get_current_season(ctx.guild.id)
    confirm_msg = await ctx.send(
        f"⚠️ **Confirm Season Transition**\n"
        f"This will:\n"
        f"• Archive all Season {current_season} data to a new channel\n"
        f"• Clear and update the Shadowverse channel for Season {current_season + 1}\n"
        f"• Reset all current winrate data\n\n"
        f"React with ✅ to confirm or ❌ to cancel."
    )
    await confirm_msg.add_reaction("✅")
    await confirm_msg.add_reaction("❌")
    
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
    
    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
        
        if str(reaction.emoji) == "❌":
            await ctx.send("Season transition cancelled.")
            return
        
        # Proceed with archiving
        await ctx.send("📦 Archiving current season data...")
        archived_season, archived_count, new_season = await archive_current_season(ctx.guild.id)
        
        # Create archive channel
        await ctx.send("📁 Creating archive channel...")
        sv_channel_id = await get_sv_channel_id(ctx.guild.id)
        sv_channel = ctx.guild.get_channel(sv_channel_id) if sv_channel_id else None
        
        # Create channel in the same category as SV channel if possible
        category = sv_channel.category if sv_channel else None
        archive_channel = await ctx.guild.create_text_channel(
            f"shadowverse-season-{archived_season}",
            category=category,
            topic=f"Archived winrate data from Shadowverse Season {archived_season}"
        )
        
        # Post archive header
        await ctx.send("📊 Posting archived data to new channel...")
        header_embed = Embed(
            title=f"📜 Shadowverse Season {archived_season} Archive",
            description=(
                f"This channel contains all winrate data from **Season {archived_season}**.\n"
                f"Total records archived: **{archived_count}**\n\n"
                f"📅 Season ended: <t:{int(discord.utils.utcnow().timestamp())}:F>\n"
                f"🆕 Current season: **{new_season}**\n\n"
                f"Use `Kanami sv_season {archived_season}` to view your personal stats from this season."
            ),
            color=0x95a5a6
        )
        await archive_channel.send(embed=header_embed)
        
        # Post all users' season data to archive channel
        await ctx.send("💾 Generating user reports...")
        
        # Get all users who have data in this season
        async with aiosqlite.connect('shadowverse_data.db') as conn:
            async with conn.execute('''
                SELECT DISTINCT user_id FROM archived_winrates 
                WHERE server_id=? AND season=?
            ''', (str(ctx.guild.id), archived_season)) as cursor:
                user_ids = [row[0] async for row in cursor]
        
        # Post data for each user
        user_count = 0
        for user_id in user_ids:
            try:
                member = ctx.guild.get_member(int(user_id))
                if not member:
                    continue
                
                crafts = await get_archived_user_crafts(user_id, str(ctx.guild.id), archived_season)
                if not crafts:
                    continue
                
                user_count += 1
                
                # Create embed for each craft the user played
                for craft in crafts:
                    winrate_dict = await get_archived_winrate(user_id, str(ctx.guild.id), craft, archived_season)
                    title, desc = craft_winrate_summary(member, craft, winrate_dict)
                    embed = Embed(title=title, description=desc, color=0x95a5a6)
                    await archive_channel.send(embed=embed)
                
                # Add separator between users
                if user_count < len(user_ids):
                    await archive_channel.send("─" * 50)
                    
            except Exception as e:
                logging.error(f"Error archiving data for user {user_id}: {e}")
                continue
        
        # Clear and update SV channel
        if sv_channel:
            await ctx.send("🧹 Clearing Shadowverse channel...")
            
            # Delete all messages in SV channel (except pinned)
            try:
                deleted = 0
                async for message in sv_channel.history(limit=None):
                    if not message.pinned:
                        await message.delete()
                        deleted += 1
                        if deleted % 10 == 0:  # Rate limit safety
                            await asyncio.sleep(1)
            except Exception as e:
                logging.error(f"Error clearing SV channel: {e}")
            
            # Post new season instructions
            instruction = (
                f"**🎮 Shadowverse Winrate Tracker - Season {new_season} 🎮**\n\n"
                f"**📝 How to Record Matches:**\n"
                f"Type: `[Your Deck] [Enemy Deck] [Win/Loss]`\n\n"
                f"**Examples:**\n"
                f"• `Sword Dragon Win` or `S D W`\n"
                f"• `Abyss Haven Loss` or `A H L`\n"
                f"• `Forest Rune Win B` (B = bricked)\n"
                f"• `Portal Sword Loss R` (R = remove/undo)\n\n"
                f"**🃏 Craft Abbreviations:**\n"
                f"F/Forest, S/Sword, R/Rune, D/Dragon, A/Abyss, H/Haven, P/Portal\n\n"
                f"**📊 Additional Features:**\n"
                f"• Add `B` to mark a match as bricked\n"
                f"• Add `R` to remove/undo a match\n"
                f"• Type `streak start` to begin tracking a win streak\n"
                f"• Type `streak end` to finish and get your streak summary\n\n"
                f"**📜 Previous Seasons:**\n"
                f"• Season {archived_season} archived in {archive_channel.mention}\n"
                f"• View your Season {archived_season} stats: `Kanami sv_season {archived_season}`\n"
                f"• List all seasons: `Kanami sv_seasons`\n\n"
                f"Your messages will be automatically deleted and your dashboard will update! ✨"
            )
            await sv_channel.send(instruction)
            
            # Update dashboards for all users
            await ctx.send("🔄 Refreshing user dashboards...")
            for member in ctx.guild.members:
                if not member.bot:
                    try:
                        await update_dashboard_message(member, sv_channel)
                    except Exception as e:
                        logging.error(f"Error updating dashboard for {member.name}: {e}")
        
        # Final confirmation
        await ctx.send(
            f"✅ **Season transition complete!**\n"
            f"📦 Season {archived_season}: {archived_count} records archived\n"
            f"📁 Archive channel: {archive_channel.mention}\n"
            f"👥 Users archived: {user_count}\n"
            f"🆕 Current season: **{new_season}**\n"
            f"🎮 Shadowverse channel cleared and updated\n\n"
            f"Good luck in Season {new_season}! 🎉"
        )
        
    except asyncio.TimeoutError:
        await ctx.send("Season transition timed out (no response).")

@bot.command(name="sv_season")
async def sv_season(ctx, season: int = None, user: discord.Member = None):
    """
    View winrate data for a specific season (archived or current).
    Usage: 
        Kanami sv_season [season_number] [@user]
        Kanami sv_season (shows current season)
    If no user is mentioned, shows your own data.
    """
    await init_sv_db()
    
    target_user = user if user else ctx.author
    current_season = await get_current_season(ctx.guild.id)
    
    if season is None:
        # Show current season
        season = current_season
        is_current = True
    else:
        is_current = (season == current_season)
    
    # Get crafts and winrate data
    if is_current:
        crafts = await get_user_played_crafts(str(target_user.id), str(ctx.guild.id))
        season_text = f"Season {season} (Current)"
    else:
        # Check if season exists
        available_seasons = await get_available_seasons(ctx.guild.id)
        if season not in available_seasons:
            await ctx.send(
                f"❌ Season {season} not found.\n"
                f"Available archived seasons: {', '.join(map(str, available_seasons)) if available_seasons else 'None'}\n"
                f"Current season: {current_season}"
            )
            return
        crafts = await get_archived_user_crafts(str(target_user.id), str(ctx.guild.id), season)
        season_text = f"Season {season} (Archived)"
    
    if not crafts:
        await ctx.send(f"{target_user.display_name} has no recorded matches in {season_text}.")
        return
    
    # Show first craft's data
    craft = crafts[0]
    if is_current:
        winrate_dict = await get_winrate(str(target_user.id), str(ctx.guild.id), craft)
    else:
        winrate_dict = await get_archived_winrate(str(target_user.id), str(ctx.guild.id), craft, season)
    
    title, desc = craft_winrate_summary(target_user, craft, winrate_dict)
    title += f" ({season_text})"
    embed = Embed(title=title, description=desc, color=0x3498db if is_current else 0x95a5a6)
    
    view = CraftDashboardView(target_user, ctx.guild.id, crafts, season=None if is_current else season)
    await ctx.send(embed=embed, view=view)

@bot.command(name="sv_seasons")
async def sv_seasons(ctx):
    """
    List all available seasons (current and archived).
    Usage: Kanami sv_seasons
    """
    await init_sv_db()
    
    current_season = await get_current_season(ctx.guild.id)
    available_seasons = await get_available_seasons(ctx.guild.id)
    
    embed = Embed(title="📅 Shadowverse Seasons", color=0x3498db)
    embed.add_field(
        name="Current Season",
        value=f"**Season {current_season}** 🟢",
        inline=False
    )
    
    if available_seasons:
        archived_text = "\n".join([f"Season {s} - View with `Kanami sv_season {s}`" for s in available_seasons])
        embed.add_field(
            name=f"Archived Seasons ({len(available_seasons)})",
            value=archived_text,
            inline=False
        )
    else:
        embed.add_field(
            name="Archived Seasons",
            value="No archived seasons yet.",
            inline=False
        )
    
    embed.set_footer(text="Use 'Kanami sv_newseason' (admin only) to start a new season")
    await ctx.send(embed=embed)

@bot.command(name="sv_recreate_archive")
@commands.has_permissions(administrator=True)
async def sv_recreate_archive(ctx, season: int):
    """
    Recreates an archive channel for a specific season from existing database records.
    Usage: Kanami sv_recreate_archive [season_number]
    Requires administrator permissions.
    """
    await init_sv_db()
    
    # Check if season exists in database
    available_seasons = await get_available_seasons(ctx.guild.id)
    if season not in available_seasons:
        await ctx.send(
            f"❌ Season {season} not found in database.\n"
            f"Available archived seasons: {', '.join(map(str, available_seasons)) if available_seasons else 'None'}"
        )
        return
    
    # Check if channel already exists
    existing_channel = discord.utils.get(ctx.guild.channels, name=f"shadowverse-season-{season}")
    if existing_channel:
        await ctx.send(f"⚠️ Archive channel for Season {season} already exists: {existing_channel.mention}\nDelete it first if you want to recreate it.")
        return
    
    await ctx.send(f"📁 Creating archive channel for Season {season}...")
    
    # Get SV channel for category placement
    sv_channel_id = await get_sv_channel_id(ctx.guild.id)
    sv_channel = ctx.guild.get_channel(sv_channel_id) if sv_channel_id else None
    category = sv_channel.category if sv_channel else None
    
    # Create archive channel
    archive_channel = await ctx.guild.create_text_channel(
        f"shadowverse-season-{season}",
        category=category,
        topic=f"Archived winrate data from Shadowverse Season {season}"
    )
    
    # Count total records
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        async with conn.execute('''
            SELECT COUNT(*) FROM archived_winrates 
            WHERE server_id=? AND season=?
        ''', (str(ctx.guild.id), season)) as cursor:
            row = await cursor.fetchone()
            archived_count = row[0] if row else 0
    
    # Post archive header
    await ctx.send("📊 Posting archived data...")
    header_embed = Embed(
        title=f"📜 Shadowverse Season {season} Archive",
        description=(
            f"This channel contains all winrate data from **Season {season}**.\n"
            f"Total records archived: **{archived_count}**\n\n"
            f"📅 Archive recreated: <t:{int(discord.utils.utcnow().timestamp())}:F>\n\n"
            f"Use `Kanami sv_season {season}` to view your personal stats from this season."
        ),
        color=0x95a5a6
    )
    await archive_channel.send(embed=header_embed)
    
    # Get all users who have data in this season
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        async with conn.execute('''
            SELECT DISTINCT user_id FROM archived_winrates 
            WHERE server_id=? AND season=?
        ''', (str(ctx.guild.id), season)) as cursor:
            user_ids = [row[0] async for row in cursor]
    
    # Post data for each user
    user_count = 0
    for user_id in user_ids:
        try:
            member = ctx.guild.get_member(int(user_id))
            if not member:
                continue
            
            crafts = await get_archived_user_crafts(user_id, str(ctx.guild.id), season)
            if not crafts:
                continue
            
            user_count += 1
            
            # Create embed for each craft the user played
            for craft in crafts:
                winrate_dict = await get_archived_winrate(user_id, str(ctx.guild.id), craft, season)
                title, desc = craft_winrate_summary(member, craft, winrate_dict)
                embed = Embed(title=title, description=desc, color=0x95a5a6)
                await archive_channel.send(embed=embed)
            
            # Add separator between users
            if user_count < len(user_ids):
                await archive_channel.send("─" * 50)
                
        except Exception as e:
            logging.error(f"Error archiving data for user {user_id}: {e}")
            continue
    
    # Final confirmation
    await ctx.send(
        f"✅ **Archive channel recreated!**\n"
        f"📁 Channel: {archive_channel.mention}\n"
        f"📦 Season {season}: {archived_count} records\n"
        f"👥 Users: {user_count}"
    )