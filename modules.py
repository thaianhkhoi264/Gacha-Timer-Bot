import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import subprocess

import aiosqlite

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import re
import asyncio
from playwright.async_api import async_playwright
import dateparser

import pytz