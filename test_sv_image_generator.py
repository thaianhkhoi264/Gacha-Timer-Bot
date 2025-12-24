"""
Shadowverse Win Rate Dashboard Image Generator - Test Script

This standalone script generates sample dashboard images for visual verification
before integrating into the main bot code.

Usage:
    python test_sv_image_generator.py

Output:
    test_output/dashboard_test.png
"""

import os
import time
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# Test data (from user's database dump)
TEST_DATA = {
    "user_name": "Test User",
    "played_craft": "Dragoncraft",
    "winrate_dict": {
        "Forestcraft": {"wins": 1, "losses": 1, "bricks": 0},
        "Swordcraft": {"wins": 1, "losses": 1, "bricks": 0},
        "Runecraft": {"wins": 4, "losses": 3, "bricks": 1},
        "Dragoncraft": {"wins": 0, "losses": 6, "bricks": 2},
        "Abysscraft": {"wins": 4, "losses": 3, "bricks": 0},
        "Havencraft": {"wins": 3, "losses": 3, "bricks": 1},
        "Portalcraft": {"wins": 3, "losses": 3, "bricks": 0}
    }
}

# Craft list (same as in shadowverse_handler.py)
CRAFTS = [
    "Forestcraft",
    "Swordcraft",
    "Runecraft",
    "Dragoncraft",
    "Abysscraft",
    "Havencraft",
    "Portalcraft"
]

# Color specifications
COLORS = {
    "bg_top": (26, 95, 122),        # #1a5f7a - Cyan top
    "bg_bottom": (13, 47, 63),      # #0d2f3f - Dark blue bottom
    "gold": (212, 175, 55),         # #d4af37 - Gold border/dividers
    "white": (255, 255, 255),       # #ffffff - Text
    "green": (0, 255, 0),           # #00ff00 - Win count
    "red": (255, 68, 68),           # #ff4444 - Loss count
    "bar_red": (255, 68, 68),       # #ff4444 - 0-45%
    "bar_yellow": (255, 170, 0),    # #ffaa00 - 45-55%
    "bar_green": (0, 255, 0),       # #00ff00 - 55-100%
    "bar_bg": (51, 51, 51),         # #333333 - Bar background
    "bar_outline": (102, 102, 102)  # #666666 - Bar outline
}


class IconCache:
    """Cache for loaded and resized icons to improve performance."""

    def __init__(self):
        self.cache = {}

    def get_class_icon(self, craft_name, size=(50, 56)):
        """
        Load and resize a class icon.

        Args:
            craft_name: Full craft name (e.g., "Dragoncraft")
            size: Target size tuple (width, height)

        Returns:
            PIL Image in RGBA mode
        """
        key = f"class_{craft_name}_{size}"
        if key not in self.cache:
            # Convert craft name to filename (e.g., "Dragoncraft" -> "class_dragon.png")
            craft_short = craft_name.lower().replace("craft", "")
            filename = f"class_{craft_short}.png"
            path = os.path.join("images", "Class", filename)

            try:
                img = Image.open(path).convert("RGBA")
                img = img.resize(size, Image.Resampling.LANCZOS)
                self.cache[key] = img
            except Exception as e:
                print(f"Warning: Failed to load icon {path}: {e}")
                # Create placeholder
                img = Image.new("RGBA", size, (100, 100, 100, 255))
                self.cache[key] = img

        return self.cache[key]

    def get_brick_icon(self, size=(24, 24)):
        """
        Load and resize the brick icon.

        Args:
            size: Target size tuple (width, height)

        Returns:
            PIL Image in RGBA mode
        """
        key = f"brick_{size}"
        if key not in self.cache:
            path = os.path.join("images", "golden_brick.png")

            try:
                img = Image.open(path).convert("RGBA")
                img = img.resize(size, Image.Resampling.LANCZOS)
                self.cache[key] = img
            except Exception as e:
                print(f"Warning: Failed to load brick icon {path}: {e}")
                # Create placeholder
                img = Image.new("RGBA", size, (255, 215, 0, 255))
                self.cache[key] = img

        return self.cache[key]


def load_font(size, bold=False):
    """
    Load Noto Sans font with fallback to system fonts.

    Args:
        size: Font size in pixels
        bold: Whether to use bold variant (note: variable fonts don't distinguish, same file used)

    Returns:
        PIL ImageFont object
    """
    # Try Noto Sans variable font first
    font_name = "NotoSans-VariableFont_wdth,wght.ttf"
    font_path = os.path.join("fonts", font_name)

    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        # Try common system fonts as fallback
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

        # If all else fails, use default (but warn user)
        print(f"Warning: Could not load any scalable font, text will be small")
        return ImageFont.load_default()


def create_gradient(width, height, color_top, color_bottom):
    """
    Create a vertical gradient background.

    Args:
        width: Image width
        height: Image height
        color_top: RGB tuple for top color
        color_bottom: RGB tuple for bottom color

    Returns:
        PIL Image
    """
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
    """
    Draw an octagonal border with cut corners.

    Args:
        draw: PIL ImageDraw object
        width: Image width
        height: Image height
        inset: Distance from edge to border
        corner_cut: Length of diagonal cuts at corners
        color: RGB tuple
        thickness: Line thickness in pixels
    """
    # Define 8 points for octagon (clockwise from top-left)
    points = [
        (inset + corner_cut, inset),                          # Top-left horizontal
        (width - inset - corner_cut, inset),                  # Top-right horizontal
        (width - inset, inset + corner_cut),                  # Right-top vertical
        (width - inset, height - inset - corner_cut),         # Right-bottom vertical
        (width - inset - corner_cut, height - inset),         # Bottom-right horizontal
        (inset + corner_cut, height - inset),                 # Bottom-left horizontal
        (inset, height - inset - corner_cut),                 # Left-bottom vertical
        (inset, inset + corner_cut),                          # Left-top vertical
    ]

    # Draw lines connecting points
    for i in range(len(points)):
        start = points[i]
        end = points[(i + 1) % len(points)]
        draw.line([start, end], fill=color, width=thickness)


def add_stroked_icon(base_img, icon, x, y, outer_black=3, gold=3, inner_black=3):
    """
    Add a class icon with a triple-layer stroke/outline effect following the icon's shape.

    Args:
        base_img: Base PIL Image to paste onto
        icon: Icon PIL Image (RGBA)
        x, y: Position to paste at
        outer_black: Width of outer black stroke (default 3)
        gold: Width of gold stroke (default 3)
        inner_black: Width of inner black stroke (default 3)
    """
    icon_w, icon_h = icon.size

    # Calculate total stroke width
    total_stroke = outer_black + gold + inner_black
    padding = total_stroke + 2
    stroked_w = icon_w + padding * 2
    stroked_h = icon_h + padding * 2

    # Create canvas for stroked icon
    stroked = Image.new('RGBA', (stroked_w, stroked_h), (0, 0, 0, 0))

    # Helper function to create offsets for a given radius
    def get_offsets(radius):
        offsets = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx*dx + dy*dy <= radius*radius:  # Circular stroke
                    offsets.append((dx, dy))
        return offsets

    alpha = icon.split()[3]  # Get alpha channel

    # Layer 1: Outer black stroke (widest)
    outer_offsets = get_offsets(total_stroke)
    for dx, dy in outer_offsets:
        black_icon = Image.new('RGBA', (icon_w, icon_h), (0, 0, 0, 255))
        black_icon.putalpha(alpha)
        stroked.paste(black_icon, (padding + dx, padding + dy), black_icon)

    # Layer 2: Gold stroke (medium)
    gold_offsets = get_offsets(gold + inner_black)
    for dx, dy in gold_offsets:
        gold_icon = Image.new('RGBA', (icon_w, icon_h), COLORS["gold"] + (255,))
        gold_icon.putalpha(alpha)
        stroked.paste(gold_icon, (padding + dx, padding + dy), gold_icon)

    # Layer 3: Inner black stroke (smallest)
    inner_offsets = get_offsets(inner_black)
    for dx, dy in inner_offsets:
        black_icon = Image.new('RGBA', (icon_w, icon_h), (0, 0, 0, 255))
        black_icon.putalpha(alpha)
        stroked.paste(black_icon, (padding + dx, padding + dy), black_icon)

    # Paste the original icon on top
    stroked.paste(icon, (padding, padding), icon)

    # Paste the final stroked icon onto the base image
    base_img.paste(stroked, (x - padding, y - padding), stroked)


def draw_winrate_bar(draw, x, y, width, height, winrate):
    """
    Draw a colored win rate bar (clean design without background).

    Args:
        draw: PIL ImageDraw object
        x, y: Top-left position
        width: Bar width
        height: Bar height
        winrate: Win rate percentage (0-100)
    """
    # Determine color based on win rate
    if winrate < 45:
        color = COLORS["bar_red"]
    elif winrate < 55:
        color = COLORS["bar_yellow"]
    else:
        color = COLORS["bar_green"]

    # For 0% winrate, show 1% to display a small speck of red
    display_winrate = max(winrate, 1.0) if winrate > 0 else 1.0

    # Fill bar proportionally (minimum 1% if there are games played)
    fill_width = int(width * (display_winrate / 100))
    if fill_width > 0:
        draw.rectangle(
            [x, y, x + fill_width, y + height],
            fill=color
        )


def generate_winrate_image(user_name, played_craft, winrate_dict, output_path=None, width=1600, height=900):
    """
    Generate a Shadowverse win rate dashboard image.

    Args:
        user_name: Display name of the user
        played_craft: The craft being played (e.g., "Dragoncraft")
        winrate_dict: Dict mapping opponent crafts to stats
                     Format: {"Forestcraft": {"wins": 1, "losses": 1, "bricks": 0}, ...}
        output_path: Path to save image (if None, returns BytesIO)
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        BytesIO object if output_path is None, otherwise None
    """
    # Create gradient background
    img = create_gradient(width, height, COLORS["bg_top"], COLORS["bg_bottom"])
    draw = ImageDraw.Draw(img)

    # Draw octagonal border
    draw_octagonal_border(draw, width, height, inset=10, corner_cut=30, color=COLORS["gold"], thickness=3)

    # Load fonts (optimized sizes to prevent overlap)
    font_header = load_font(56, bold=True)
    font_title = load_font(48, bold=True)
    font_normal = load_font(36, bold=False)
    font_stats = load_font(32, bold=False)

    # Initialize icon cache
    icon_cache = IconCache()

    # Calculate totals
    total_wins = sum(v["wins"] for v in winrate_dict.values())
    total_losses = sum(v["losses"] for v in winrate_dict.values())
    total_bricks = sum(v["bricks"] for v in winrate_dict.values())
    total_games = total_wins + total_losses
    total_winrate = (total_wins / total_games * 100) if total_games > 0 else 0

    # Layout constants (optimized for 16:9 and minimal whitespace)
    content_x = 60  # Left padding
    y = 30  # Current Y position (moved up)

    # Draw header: User Name
    draw.text((content_x, y - 5), user_name, fill=COLORS["white"], font=font_header)
    y += 80  # Gap after user name (increased gap)

    # Draw title: [icon] Craft Name Win Rate
    class_icon = icon_cache.get_class_icon(played_craft, size=(60, 67))
    title_icon_height = 67
    add_stroked_icon(img, class_icon, content_x, y)

    title_text = f"{played_craft} Win Rate"
    # Center text vertically with icon using text bbox
    title_center = y + title_icon_height // 2
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    text_height = bbox[3] - bbox[1]
    title_y = title_center - text_height // 2 - 10
    draw.text((content_x + 80, title_y), title_text, fill=COLORS["white"], font=font_title)
    y += 85  # Gap after title

    # Draw first divider
    divider_left = content_x
    divider_right = width - 60
    draw.line([(divider_left, y), (divider_right, y)], fill=COLORS["gold"], width=3)
    y += 30

    # Draw matchup rows (7 crafts) - fill more of the screen
    bar_width = 650  # Much longer bars (horizontal scaling)
    bar_height = 28  # Keep height reasonable
    row_height = 78  # Adequate spacing for 36px font

    # Draw brick icon header (above the brick column)
    brick_icon = icon_cache.get_brick_icon(size=(48, 48))
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
        craft_icon = icon_cache.get_class_icon(craft, size=(50, 56))
        icon_height = 56
        add_stroked_icon(img, craft_icon, content_x, y)

        # Calculate vertical center of the row based on icon
        row_center = y + icon_height // 2 - 10

        # Draw craft name - vertically centered using text bbox
        craft_x = content_x + 70
        bbox = draw.textbbox((0, 0), craft, font=font_normal)
        text_height = bbox[3] - bbox[1]
        craft_y = row_center - text_height // 2 
        draw.text((craft_x, craft_y), craft, fill=COLORS["white"], font=font_normal)

        # Draw win rate bar - vertically centered with row
        bar_x = craft_x + 320
        bar_y = row_center - bar_height // 2 + 12
        draw_winrate_bar(draw, bar_x, bar_y, bar_width, bar_height, winrate)

        # Draw percentage - vertically centered using text bbox
        percent_x = bar_x + bar_width + 20
        percent_text = f"{winrate:.1f}%"
        bbox = draw.textbbox((0, 0), percent_text, font=font_stats)
        text_height = bbox[3] - bbox[1]
        percent_y = row_center - text_height // 2
        draw.text((percent_x, percent_y), percent_text, fill=COLORS["white"], font=font_stats)

        # Draw win/loss counts - vertically centered using text bbox
        wl_x = percent_x + 140
        win_text = f"{wins}W"
        loss_text = f"{losses}L"
        bbox = draw.textbbox((0, 0), win_text, font=font_stats)
        text_height = bbox[3] - bbox[1]
        wl_y = row_center - text_height // 2
        draw.text((wl_x, wl_y), win_text, fill=COLORS["green"], font=font_stats)
        draw.text((wl_x + 85, wl_y), "/", fill=COLORS["white"], font=font_stats)
        draw.text((wl_x + 105, wl_y), loss_text, fill=COLORS["red"], font=font_stats)

        # Draw brick count - vertically centered using text bbox
        brick_text = str(bricks)
        bbox = draw.textbbox((0, 0), brick_text, font=font_stats)
        text_height = bbox[3] - bbox[1]
        brick_y = row_center - text_height // 2
        draw.text((brick_column_x + 20, brick_y), brick_text, fill=COLORS["white"], font=font_stats)

        y += row_height

    # Draw second divider
    y += 10
    draw.line([(divider_left, y), (divider_right, y)], fill=COLORS["gold"], width=3)
    y += 30

    # Draw total row - aligned with craft rows (use same row height as craft rows)
    total_row_center = y + 56 // 2 - 10 # Same centering logic as craft rows

    # Draw total label - vertically centered using text bbox
    total_label = "Total Win Rate"
    bbox = draw.textbbox((0, 0), total_label, font=font_normal)
    text_height = bbox[3] - bbox[1]
    total_label_y = total_row_center - text_height // 2
    draw.text((content_x, total_label_y), total_label, fill=COLORS["white"], font=font_normal)

    # Draw total win rate bar - vertically centered
    total_bar_x = content_x + 390  # Same as craft_x + 320 where craft_x = content_x + 70
    total_bar_y = total_row_center - bar_height // 2 + 10
    draw_winrate_bar(draw, total_bar_x, total_bar_y, bar_width, bar_height, total_winrate)

    # Draw total percentage - vertically centered using text bbox
    total_percent_x = total_bar_x + bar_width + 20
    total_percent_text = f"{total_winrate:.1f}%"
    bbox = draw.textbbox((0, 0), total_percent_text, font=font_stats)
    text_height = bbox[3] - bbox[1]
    total_percent_y = total_row_center - text_height // 2
    draw.text((total_percent_x, total_percent_y), total_percent_text, fill=COLORS["white"], font=font_stats)

    # Draw total win/loss counts - vertically centered using text bbox
    total_wl_x = total_percent_x + 140
    total_win_text = f"{total_wins}W"
    total_loss_text = f"{total_losses}L"
    bbox = draw.textbbox((0, 0), total_win_text, font=font_stats)
    text_height = bbox[3] - bbox[1]
    total_wl_y = total_row_center - text_height // 2
    draw.text((total_wl_x, total_wl_y), total_win_text, fill=COLORS["green"], font=font_stats)
    draw.text((total_wl_x + 85, total_wl_y), "/", fill=COLORS["white"], font=font_stats)
    draw.text((total_wl_x + 105, total_wl_y), total_loss_text, fill=COLORS["red"], font=font_stats)

    # Draw total brick count - vertically centered using text bbox
    total_brick_text = str(total_bricks)
    bbox = draw.textbbox((0, 0), total_brick_text, font=font_stats)
    text_height = bbox[3] - bbox[1]
    total_brick_y = total_row_center - text_height // 2
    draw.text((brick_column_x + 20, total_brick_y), total_brick_text, fill=COLORS["white"], font=font_stats)

    # Save or return BytesIO
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, 'PNG')
        return None
    else:
        buffer = BytesIO()
        img.save(buffer, 'PNG')
        buffer.seek(0)
        return buffer


def main():
    """Run test image generation."""
    print("=" * 60)
    print("Shadowverse Dashboard Image Generator - Test")
    print("=" * 60)
    print()

    print(f"User: {TEST_DATA['user_name']}")
    print(f"Played Craft: {TEST_DATA['played_craft']}")
    print(f"Matchups: {len(TEST_DATA['winrate_dict'])}")
    print()

    print("Generating image...")
    start_time = time.time()

    output_path = os.path.join("test_output", "dashboard_test.png")
    generate_winrate_image(
        TEST_DATA["user_name"],
        TEST_DATA["played_craft"],
        TEST_DATA["winrate_dict"],
        output_path=output_path
    )

    elapsed = time.time() - start_time

    print(f"[OK] Image generated in {elapsed:.3f}s")
    print(f"[OK] Saved to: {output_path}")

    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        print(f"[OK] File size: {file_size / 1024:.1f} KB")

    print()
    print("=" * 60)
    print("Test complete! Check test_output/dashboard_test.png")
    print("=" * 60)


if __name__ == "__main__":
    main()
