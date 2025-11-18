import modules
from bot import *
import aiosqlite
import os
import asyncio
from typing import Optional

# ============================================
# CLAUDE API SUPPORT
# ============================================
# Set ANTHROPIC_API_KEY in .env or environment to use Claude API
# Otherwise falls back to local GGUF model

# Available Claude models with pricing (per 1M tokens)
CLAUDE_MODELS = {
    "Haiku": {
        "id": "claude-3-5-haiku-20241022",
        "input_cost": 0.80,   # $0.80 per 1M input tokens
        "output_cost": 4.00,  # $4.00 per 1M output tokens
        "description": "Fast, efficient model for simple tasks (RECOMMENDED for event classification)"
    },
    "Sonnet": {
        "id": "claude-3-5-sonnet-20241022",
        "input_cost": 3.00,   # $3.00 per 1M input tokens
        "output_cost": 15.00, # $15.00 per 1M output tokens
        "description": "Balanced model for complex reasoning and coding"
    },
    "Opus": {
        "id": "claude-3-opus-20240229",
        "input_cost": 15.00,  # $15.00 per 1M input tokens
        "output_cost": 75.00, # $75.00 per 1M output tokens
        "description": "Most powerful model for highly complex tasks"
    }
}

# ============================================
# CONFIGURATION: Change model here
# ============================================
SELECTED_MODEL = "Haiku"  # Options: "Haiku", "Sonnet", "Opus"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
USE_CLAUDE = bool(ANTHROPIC_API_KEY)

if USE_CLAUDE:
    try:
        import anthropic
        claude_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        model_info = CLAUDE_MODELS[SELECTED_MODEL]
        print(f"[ML_HANDLER] Claude API enabled")
        print(f"[ML_HANDLER] Using model: {SELECTED_MODEL} ({model_info['id']})")
        print(f"[ML_HANDLER] Cost: ${model_info['input_cost']}/1M input, ${model_info['output_cost']}/1M output")
        print(f"[ML_HANDLER] Description: {model_info['description']}")
    except ImportError:
        print("[ML_HANDLER] anthropic package not found. Install with: pip install anthropic")
        USE_CLAUDE = False
        claude_client = None
else:
    claude_client = None
    print("[ML_HANDLER] Claude API not configured, using local GGUF model")

# ============================================
# LOCAL GGUF MODEL (Fallback)
# ============================================
# Use llama-cpp-python for GGUF model inference
try:
    from llama_cpp import Llama
    llm = Llama(model_path="./qwen3-1.7b-q4_k_m.gguf", n_ctx=1024, n_threads=4, verbose=False)
    print("[ML_HANDLER] Local GGUF model loaded successfully")
except Exception as e:
    print(f"[ML_HANDLER] Failed to load local GGUF model: {e}")
    llm = None

# ============================================
# UNIFIED LLM INFERENCE
# ============================================

async def run_llm_inference(text: str, max_tokens: int = 512) -> Optional[str]:
    """
    Unified LLM inference function.
    Tries Claude API first (if configured), falls back to local GGUF model.
    
    Args:
        text: The prompt to send to the LLM
        max_tokens: Maximum tokens to generate (default 512, increased for event extraction)
    
    Returns:
        str: LLM response, or None if all methods fail
    """
    print(f"[ML_HANDLER] run_llm_inference called (max_tokens={max_tokens})")
    print(f"[ML_HANDLER] Prompt preview: {repr(text)[:200]}...")
    
    # Try Claude API first if available
    if USE_CLAUDE and claude_client:
        try:
            print("[ML_HANDLER] Attempting Claude API call...")
            model_id = CLAUDE_MODELS[SELECTED_MODEL]["id"]
            response = await claude_client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                messages=[
                    {"role": "user", "content": text}
                ]
            )
            result = response.content[0].text.strip()
            print(f"[ML_HANDLER] Claude response preview: {repr(result)[:200]}...")
            return result
        except Exception as e:
            print(f"[ML_HANDLER] Claude API failed: {e}")
            print("[ML_HANDLER] Falling back to local GGUF model...")
    
    # Fallback to local GGUF model
    if llm:
        try:
            print("[ML_HANDLER] Using local GGUF model...")
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(
                None,
                lambda: llm(text, max_tokens=max_tokens, stop=["<|endoftext|>", "\n\n\n"])
            )
            result = output["choices"][0]["text"].strip()
            print(f"[ML_HANDLER] Local model response preview: {repr(result)[:200]}...")
            return result
        except Exception as e:
            print(f"[ML_HANDLER] Local GGUF model failed: {e}")
            return None
    
    print("[ML_HANDLER] No LLM available!")
    return None

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