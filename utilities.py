from modules import *
from bot import *
import logging

@bot.command() # "hello" command
async def hello(ctx):
    """ Responds with a hello along with a truth. """
    await ctx.send("Hello! Kanami here! Alfa is into wearing maid cosplays!")

@bot.command() # "version" command
async def version(ctx):
    """ Returns the current version of the bot. """
    await ctx.send(f"Current version is {bot_version}!")

@bot.command(name="mmj") # "MMJ" command
async def mmj(ctx):
    """ Forces Kanami to shut down if you are worthy enough. """
    OWNER_ID = 680653908259110914
    if ctx.author.id != OWNER_ID:
        await ctx.send("You don't get to use this command!")
        return
    await ctx.send("Kanami is shutting down...")
    await bot.close()

@bot.command(name="purge")
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