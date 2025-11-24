from modules import *
from discord.ext import commands
import discord
import logging
import sys
import os
from dotenv import load_dotenv

bot_version = "2.6.0"
assigned_channels = {}

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True  # Required to see user online/offline/idle/dnd status

bot = commands.Bot(command_prefix='Kanami ', intents=intents, help_command=None)

# Create a logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File handler (keeps discord.log)
file_handler = logging.FileHandler("discord.log", mode="a")
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logger.addHandler(file_handler)

# Stream handler (prints to stdout, visible in journalctl)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logger.addHandler(stream_handler)

# Silence discord.py internal debug logs
logging.getLogger("discord.http").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.client").setLevel(logging.WARNING)
logging.getLogger("discord").setLevel(logging.INFO)