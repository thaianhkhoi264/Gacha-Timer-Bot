import modules
from bot import *
import aiosqlite
import onnxruntime as ort
import numpy as np
from transformers import AutoTokenizer

onnx_model_path = "./phi-2-onnx/model.onnx"
session = ort.InferenceSession(onnx_model_path)

tokenizer = AutoTokenizer.from_pretrained("microsoft/phi-2")

def tokenize(text):
    # Tokenize and convert to numpy array for ONNX Runtime
    tokens = tokenizer(text, return_tensors="np", padding="max_length", max_length=128, truncation=True)
    return tokens["input_ids"]

async def run_phi2_inference(text):
    input_ids = tokenize(text)
    # Run inference
    outputs = session.run(None, {"input_ids": input_ids})
    # Assume the output is token IDs (adjust if your model outputs logits)
    # outputs[0] is usually the output token IDs
    output_ids = outputs[0]
    # Decode output tokens to text
    response = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    return response

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

# Message handler to be called from main.py's on_message
async def ml_on_message(message):
    if message.author == bot.user:
        return
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute(
            "SELECT channel_id FROM llm_hub_channel WHERE server_id=?",
            (str(message.guild.id),)
        ) as cursor:
            row = await cursor.fetchone()
    if row and str(message.channel.id) == row[0]:
        response = await run_phi2_inference(message.content)
        await message.channel.send(response)
        return True
    return False

@bot.command()
@commands.has_permissions(manage_channels=True)
async def set_llm_channel(ctx, channel: discord.TextChannel):
    """Set the LLM chat hub channel for this server."""
    async with aiosqlite.connect('kanami_data.db') as conn:
        await conn.execute(
            "REPLACE INTO llm_hub_channel (server_id, channel_id) VALUES (?, ?)",
            (str(ctx.guild.id), str(channel.id))
        )
        await conn.commit()
    await ctx.send(f"{channel.mention} is now set as the LLM chat hub channel.")