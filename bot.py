from modules import *
from discord.ext import commands
import discord
import logging
import os
from dotenv import load_dotenv

bot_version = "2.0.3"
assigned_channels = {}

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='Kanami ', intents=intents, help_command=None)

# Remove all handlers from the root logger
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Set up logging to file only
logging.basicConfig(
    level=logging.DEBUG,  # or INFO
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    filename="discord.log",
    filemode="a"
)