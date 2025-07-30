import discord
from discord.ext import commands
from discord import app_commands
import modules
import sqlite3
import bot

WISHLIST_USER_ID = 1008040282501152869
OWNER_ID = 680653908259110914
DB_PATH = "wishlist_data.db"

def init_wishlist_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS wishlist (item TEXT PRIMARY KEY)")
    c.execute("CREATE TABLE IF NOT EXISTS wishlist_msg (user_id TEXT PRIMARY KEY, message_id TEXT)")
    conn.commit()
    conn.close()

def get_wishlist():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS wishlist (item TEXT PRIMARY KEY)")
    c.execute("SELECT item FROM wishlist ORDER BY item ASC")
    items = [row[0] for row in c.fetchall()]
    conn.close()
    return items

def add_wishlist_item(item):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS wishlist (item TEXT PRIMARY KEY)")
    try:
        c.execute("INSERT INTO wishlist (item) VALUES (?)", (item,))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def remove_wishlist_item(item):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS wishlist (item TEXT PRIMARY KEY)")
    c.execute("DELETE FROM wishlist WHERE item=?", (item,))
    conn.commit()
    conn.close()

async def send_wishlist_dashboard(bot):
    items = get_wishlist()
    embed = discord.Embed(
        title="Wishlist",
        description="\n".join([f"• {item}" for item in items]) if items else "No items in the wishlist.",
        color=0x2ecc71
    )
    user = await bot.fetch_user(WISHLIST_USER_ID)
    # Try to find the last wishlist message id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS wishlist_msg (user_id TEXT PRIMARY KEY, message_id TEXT)")
    c.execute("SELECT message_id FROM wishlist_msg WHERE user_id=?", (str(WISHLIST_USER_ID),))
    row = c.fetchone()
    msg_id = int(row[0]) if row and row[0] else None
    conn.close()
    try:
        if msg_id:
            msg = await user.fetch_message(msg_id)
            await msg.edit(embed=embed)
        else:
            msg = await user.send(embed=embed)
            # Save the message id for future edits
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("REPLACE INTO wishlist_msg (user_id, message_id) VALUES (?, ?)", (str(WISHLIST_USER_ID), str(msg.id)))
            conn.commit()
            conn.close()
    except Exception:
        # If edit fails, send a new message and update the id
        msg = await user.send(embed=embed)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("REPLACE INTO wishlist_msg (user_id, message_id) VALUES (?, ?)", (str(WISHLIST_USER_ID), str(msg.id)))
        conn.commit()
        conn.close()
    # Always send a copy to the owner (new message)
    owner = await bot.fetch_user(OWNER_ID)
    await owner.send(embed=embed)

init_wishlist_db()


@bot.command()
@commands.is_owner()
async def wishlist_add(ctx, *, item: str):
    """Owner: Add an item to the wishlist."""
    success = add_wishlist_item(item)
    if success:
        await ctx.send(f"Added `{item}` to the wishlist.")
        await send_wishlist_dashboard(ctx.bot)
    else:
        await ctx.send(f"`{item}` is already in the wishlist.")

@bot.command()
@commands.is_owner()
async def wishlist_remove(ctx, *, item: str):
    """Owner: Remove an item from the wishlist."""
    remove_wishlist_item(item)
    await ctx.send(f"Removed `{item}` from the wishlist.")
    await send_wishlist_dashboard(ctx.bot)

@bot.command()
@commands.is_owner()
async def wishlist_show(ctx):
    """Owner: Show the current wishlist."""
    items = get_wishlist()
    if items:
        msg = "**Current Wishlist:**\n" + "\n".join([f"• {item}" for item in items])
    else:
        msg = "The wishlist is empty."
    await ctx.send(msg)
