from twitter_handler import *
import sqlite3

PROFILE_KEYWORDS = {
    "HSR": {
        "required": ["update", "maintenance", "event", "warp", "period"],
        "ignored": [
            "special program", "trailer", "winner announcement", "strategy guide",
            "developer radio", "gallery", "manuscript", "radio"
        ]
    },
    "ZZZ": {
        "required": [
            "event", "channel", "banner", "update", "duration", "maintenance", "details"
        ],
        "ignored": [
            "trailer", "teaser", "demo", "collab", "birthday", "prize", "winner", "strategy",
            "behind-the-scenes", "mechanics intro", "agent record", "cutscene", "news", "discord",
            "check-in", "twitch", "store", "an outstanding partner", "for display only",
            "collaboration", "renovation talk", "benefits express", "overview", "hoyolab"
        ]
    },
    "AK": {
        "required": [
            "event", "maintenance", "update", "operators", "operator", "rate",
            "will be available soon", "will be live", "rerun"
        ],
        "ignored": [
            "trailer", "animation", "pv", "collection", "ep", "artwork", "compensation",
            "has ended", "issue", "artist", "hd", "mechanisms", "enemies", "introduction",
            "details", "emoji", "prize", "good luck", "new operators"
        ]
    },
    "STRI": {
        "required": ["event", "banner", "update"],
        "ignored": ["retweet", "maintenance complete"]
    },
    "WUWA": {
        "required": ["event", "banner", "update"],
        "ignored": ["retweet", "maintenance complete"]
    }
}

async def get_announce_channel(guild):
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT announce_channel_id FROM announce_config WHERE server_id=?", (str(guild.id),))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return guild.get_channel(int(row[0]))
    return None

async def tweet_listener_on_message(message):
    if message.author.bot:
        return False

    if not message.guild or not hasattr(message.channel, "id"):
        return False

    # Query the database for this channel in this server
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute(
        "SELECT profile, required_keywords, ignored_keywords FROM listener_channels WHERE server_id=? AND channel_id=?",
        (str(message.guild.id), str(message.channel.id))
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return False  # Not a listener channel

    profile, required_keywords, ignored_keywords = row
    profile = profile.upper()

    # Use DB keywords if set, otherwise fallback to PROFILE_KEYWORDS
    if required_keywords:
        required_keywords = [kw.strip() for kw in required_keywords.split(",") if kw.strip()]
    else:
        required_keywords = PROFILE_KEYWORDS.get(profile, {}).get("required", [])
    if ignored_keywords:
        ignored_keywords = [kw.strip() for kw in ignored_keywords.split(",") if kw.strip()]
    else:
        ignored_keywords = PROFILE_KEYWORDS.get(profile, {}).get("ignored", [])

    # Look for a Twitter/X link in the message
    twitter_link = None
    for word in message.content.split():
        if "twitter.com" in word or "x.com" in word:
            twitter_link = word
            break
    if not twitter_link:
        await message.add_reaction("❌")
        return True

    tweet_text, tweet_image, username = await fetch_tweet_content(twitter_link)
    if not tweet_text:
        await message.add_reaction("❌")
        return True

    # DEBUG PRINTS
    print("=== DEBUG: TWEET TEXT ===")
    print(repr(tweet_text))
    print("=== DEBUG: REQUIRED KEYWORDS ===")
    print(required_keywords)

    # Ignore if any ignored keyword is present
    if any(kw.lower() in tweet_text.lower() for kw in ignored_keywords):
        await message.add_reaction("❌")
        return True

    # Flatten text for keyword check
    flat_text = tweet_text.replace("\n", " ").replace("\r", " ").lower()
    if required_keywords and not any(kw.lower() in flat_text for kw in required_keywords):
        await message.add_reaction("❌")
        return True

    # If passed, process like the read command (call the function directly)
    await message.add_reaction("✅")

    # Use the announcement channel for all follow-up prompts
    announce_channel = await get_announce_channel(message.guild)
    if not announce_channel:
        # Fallback: use the listener channel if no announce channel is set
        announce_channel = message.channel

    # Create a fake context with the announcement channel for the read function
    ctx = await bot.get_context(message)
    ctx.channel = announce_channel

    await announce_channel.send("Detected a valid tweet, parsing...")
    await read(ctx, twitter_link)
    return True


@bot.event
async def on_reaction_add(reaction, user):
    # Only respond to ❌ reactions from users (not the bot itself)
    if user.bot:
        return
    if str(reaction.emoji) != "❌":
        return

    message = reaction.message

    # Only proceed if the bot has already reacted with ❌ to this message
    if not any(r.me and str(r.emoji) == "❌" for r in message.reactions):
        return

    # Only process Twitter/X links
    twitter_link = None
    for word in message.content.split():
        if "twitter.com" in word or "x.com" in word:
            twitter_link = word
            break
    if not twitter_link:
        return

    # Use the announcement channel for all follow-up prompts
    announce_channel = await get_announce_channel(message.guild)
    if not announce_channel:
        announce_channel = message.channel

    ctx = await bot.get_context(message)
    ctx.channel = announce_channel

    await announce_channel.send(
        f"{user.mention} forced a read on a previously ignored tweet. Parsing now..."
    )
    await read(ctx, twitter_link)