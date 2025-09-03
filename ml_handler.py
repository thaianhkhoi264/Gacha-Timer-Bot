import modules
from bot import *
import aiosqlite
import numpy as np

def get_model_and_tokenizer():
    print("[DEBUG] get_model_and_tokenizer: called")
    import onnxruntime as ort
    from transformers import AutoTokenizer
    print("[DEBUG] get_model_and_tokenizer: importing done")
    onnx_model_path = "./phi-2-onnx/model.onnx"
    print("[DEBUG] get_model_and_tokenizer: loading session")
    session = ort.InferenceSession(onnx_model_path)
    print("[DEBUG] get_model_and_tokenizer: loading tokenizer")
    tokenizer = AutoTokenizer.from_pretrained("./phi-2")
    print("[DEBUG] get_model_and_tokenizer: loaded")
    return session, tokenizer

def tokenize(tokenizer, text):
    tokens = tokenizer(text, return_tensors="np", padding="max_length", max_length=128, truncation=True)
    return tokens["input_ids"]

async def run_phi2_inference(text):
    print("[DEBUG] run_phi2_inference: called with text:", repr(text)[:100])
    try:
        session, tokenizer = get_model_and_tokenizer()
        print("[DEBUG] run_phi2_inference: model and tokenizer loaded")
        input_ids = tokenize(tokenizer, text)
        print("[DEBUG] run_phi2_inference: input_ids shape:", input_ids.shape)
        outputs = session.run(None, {"input_ids": input_ids})
        print("[DEBUG] run_phi2_inference: outputs received")
        output_ids = outputs[0]
        print("[DEBUG] run_phi2_inference: output_ids shape:", output_ids.shape)
        response = tokenizer.decode(output_ids[0], skip_special_tokens=True)
        print("[DEBUG] run_phi2_inference: decoded response:", repr(response)[:100])
        # Optionally, free memory
        del session
        del tokenizer
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
#     await ctx.send(f"{channel.mention} is now set as the LLM chat hub channel.")