import modules
from bot import *
import aiosqlite

# Use llama-cpp-python for GGUF model inference
from llama_cpp import Llama

# Load the quantized model once (thread-safe, low RAM usage)
llm = Llama(model_path="./phi-2.Q4_K_M.gguf", n_ctx=512, n_threads=4)  # Adjust n_ctx and n_threads as needed

async def run_phi2_inference(text):
    print("[DEBUG] run_phi2_inference: called with text:", repr(text)[:100])
    try:
        # Generate response using the quantized model
        output = llm(text, max_tokens=128, stop=["<|endoftext|>"])
        response = output["choices"][0]["text"].strip()
        print("[DEBUG] run_phi2_inference: decoded response:", repr(response)[:100])
        return response
    except Exception as e:
        print("[ERROR] run_phi2_inference exception:", e)
        return f"[ERROR] LLM inference failed: {e}"

# Check if llm_hub_channel table exists
async def check_llm_table():
    async with aiosqlite.connect('kanami_data.db') as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS llm_hub_channel (
                server_id TEXT PRIMARY KEY,
                channel_id TEXT
            )
        ''')
        await conn.commit()

# Ctrl + / to un-comment the code block

# # Message handler to be called from main.py's on_message
# async def ml_on_message(message):
#     if message.author == bot.user:
#         return
#     async with aiosqlite.connect('kanami_data.db') as conn:
#         async with conn.execute(
#             "SELECT channel_id FROM llm_hub_channel WHERE server_id=?",
#             (str(message.guild.id),)
#         ) as cursor:
#             row = await cursor.fetchone()
#     if row and str(message.channel.id) == row[0]:
#         response = await run_phi2_inference(message.content)
#         await message.channel.send(response)
#         return True
#     return False

# @bot.command()
# @commands.has_permissions(manage_channels=True)
# async def set_llm_channel(ctx, channel: discord.TextChannel):
#     """Set the LLM chat hub channel for this server."""
#     async with aiosqlite.connect('kanami_data.db') as conn:
#         await conn.execute(
#             "REPLACE INTO llm_hub_channel (server_id, channel_id) VALUES (?, ?)",
#             (str(ctx.guild.id), str(channel.id))
#         )
#         await conn.commit()
#     await ctx.send(f"{channel.mention} is now set as the