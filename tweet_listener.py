from twitter_handler import *
from ml_handler import run_llm_inference
import aiosqlite
import re

PROFILE_KEYWORDS = {
    "HSR": {
        "required": ["update", "maintenance", "event", "warp", "period"],
        "ignored": [
            "special program", "trailer", "winner announcement", "strategy guide",
            "developer radio", "gallery", "manuscript", "radio", "novaflare", "outfit", "pack", "packs",
            "outfits", "adjustments", "improvements", "ep", "trailblaze mission", "trailblaze missions",
            "hoyo fest", "hoyofest", "sales", "sale"
        ]
    },
    "ZZZ": {
        "required": [
            "event", "channel", "banner", "update", "duration", "maintenance", "details"
        ],
        "ignored": [
            "trailer", "teaser", "demo", "collab", "birthday", "prize", "winner", "strategy",
            "behind-the-scenes", "mechanics intro", "agent record", "cutscene", "news", "discord",
            "check-in", "twitch", "store", "an outstanding partner", "for display only", "ep",
            "collaboration", "renovation talk", "benefits express", "overview", "hoyolab",
            "pop-up", "pop up", "offline", "cosplayer", "cosplayers", "fanart", "fanarts",
            "anniversary countdown", "countdown event", "agent mechanics", "observation log"
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
            "details", "emoji", "prize", "good luck", "new operators", "winner", "winners"
        ]
    },
    "STRI": {
        "required": [
            "event", "preview", "offer", "maintenance", "availability", "duration", "date", "update"
        ],
        "ignored": [
            "giveaway", "prize", "winner", "winners", "fanart", "workshop", "showcase", "wallpaper",
            "birthday", "trailer", "teaser", "collab", "collaboration", "profile puzzle", "snap & share",
            "meme", "hotfix", "patch notes", "cd-key", "cdk code", "reward", "prizes", "congratulations",
            "thank you", "launch", "official website", "comic", "episode", "record your", "share your",
            "show us", "capture", "artist", "artwork", "template", "entry", "entries", "dm",
            "winner announcement", "strategy", "join the", "join us", "premiering",
            "premiere", "premieres", "premiered", "maintenance complete", "retweet",
            "rt", "like this post", "how to enter", "to enter", "first look",
            "agent preview", "agent reveal", "map preview", 
            "four-panel comics", "panel comic", "panel comics", "panel episode", "panel episodes"
        ]
    },
    "WUWA": {
        "required": ["event", "banner", "update"],
        "ignored": ["retweet", "maintenance complete"]
    }
}

async def get_announce_channel(guild):
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute(
            "SELECT announce_channel_id FROM announce_config WHERE server_id=?",
            (str(guild.id),)
        ) as cursor:
            row = await cursor.fetchone()
    if row and row[0]:
        return guild.get_channel(int(row[0]))
    return None

async def tweet_listener_on_message(message):
    print(f"[DEBUG] Called tweet_listener_on_message")
    print(f"[DEBUG] message.author: {message.author} (bot: {message.author.bot})")
    print(f"[DEBUG] message.guild: {getattr(message.guild, 'id', None)}")
    print(f"[DEBUG] message.channel: {getattr(message.channel, 'id', None)}")
    print(f"[DEBUG] message.content: {message.content}")

    if message.webhook_id is not None:
        print("[DEBUG] Message is from a webhook, allowing.")

    if message.author.id == bot.user.id:
        print("[DEBUG] Message is from myself, ignoring.")
        return False

    if not message.guild or not hasattr(message.channel, "id"):
        print("[DEBUG] Message has no guild or channel id, ignoring.")
        return False

    # Query the database for this channel in this server
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute(
            "SELECT profile, required_keywords, ignored_keywords FROM listener_channels WHERE server_id=? AND channel_id=?",
            (str(message.guild.id), str(message.channel.id))
        ) as cursor:
            row = await cursor.fetchone()
    print(f"[DEBUG] listener_channels DB row: {row}")
    if not row:
        print("[DEBUG] Channel is not a listener channel, ignoring.")
        return False  # Not a listener channel

    profile, required_keywords, ignored_keywords = row
    print(f"[DEBUG] profile: {profile}, required_keywords: {required_keywords}, ignored_keywords: {ignored_keywords}")
    profile = profile.upper()

    # # Use DB keywords if set, otherwise fallback to PROFILE_KEYWORDS
    # if required_keywords:
    #     required_keywords = [kw.strip() for kw in required_keywords.split(",") if kw.strip()]
    #     print(f"[DEBUG] Using DB required_keywords: {required_keywords}")
    # else:
    #     required_keywords = PROFILE_KEYWORDS.get(profile, {}).get("required", [])
    #     print(f"[DEBUG] Using default required_keywords: {required_keywords}")
    # if ignored_keywords:
    #     ignored_keywords = [kw.strip() for kw in ignored_keywords.split(",") if kw.strip()]
    #     print(f"[DEBUG] Using DB ignored_keywords: {ignored_keywords}")
    # else:
    #     ignored_keywords = PROFILE_KEYWORDS.get(profile, {}).get("ignored", [])
    #     print(f"[DEBUG] Using default ignored_keywords: {ignored_keywords}")

    # Look for a Twitter/X link in the message
    twitter_link = None
    for word in message.content.split():
        if "twitter.com" in word or "x.com" in word:
            twitter_link = word
            break
    print(f"[DEBUG] twitter_link: {twitter_link}")
    if not twitter_link and message.embeds:
        for embed in message.embeds:
            # Check embed.url
            if hasattr(embed, "url") and embed.url and ("twitter.com" in embed.url or "x.com" in embed.url):
                twitter_link = embed.url
                print(f"[DEBUG] Found twitter link in embed.url: {twitter_link}")
                break
            # Check embed.description
            if hasattr(embed, "description") and embed.description:
                for word in embed.description.split():
                    if "twitter.com" in word or "x.com" in word:
                        twitter_link = word
                        print(f"[DEBUG] Found twitter link in embed.description: {twitter_link}")
                        break
            if twitter_link:
                break
    if not twitter_link:
        print("[DEBUG] No Twitter/X link found in message.")
        await message.add_reaction("❌")
        return True

    tweet_text, tweet_image, username = await fetch_tweet_content(twitter_link)
    print(f"[DEBUG] tweet_text: {repr(tweet_text)}")
    print(f"[DEBUG] tweet_image: {tweet_image}")
    print(f"[DEBUG] username: {username}")
    if not tweet_text:
        print("[DEBUG] No tweet text found.")
        await message.add_reaction("❌")
        return True

    # # Ignore if any ignored keyword is present (word-boundary match)
    # ignored_found = []
    # for kw in ignored_keywords:
    #     if re.search(rf'\b{re.escape(kw.lower())}\b', tweet_text.lower()):
    #         ignored_found.append(kw)
    # if ignored_found:
    #     print(f"[DEBUG] Ignored keywords found: {ignored_found}")
    #     await message.add_reaction("❌")
    #     return True

    # # Flatten text for keyword check
    # flat_text = tweet_text.replace("\n", " ").replace("\r", " ").lower()
    # print(f"[DEBUG] flat_text: {flat_text}")
    # if required_keywords:
    #     found = False
    #     for kw in required_keywords:
    #         if re.search(rf'\b{re.escape(kw.lower())}\b', flat_text):
    #             print(f"[DEBUG] Required keyword matched: {kw}")
    #             found = True
    #             break
    #     if not found:
    #         print("[DEBUG] No required keyword matched.")
    #         await message.add_reaction("❌")
    #         return True
    # else:
    #     print("[DEBUG] No required keywords set, skipping required keyword check.")

    # Use LLM to classify if this is an event/announcement tweet
    is_event = await is_event_tweet(tweet_text, profile)
    if not is_event:
        print("[DEBUG] LLM classified this tweet as Filler/Non-event.")
        await message.add_reaction("❌")
        return True

    # If passed, process like the read command (call the function directly)
    await message.add_reaction("✅")
    print("[DEBUG] Passed all checks, calling read()")

    # Use the announcement channel for all follow-up prompts
    announce_channel = await get_announce_channel(message.guild)
    print(f"[DEBUG] announce_channel: {getattr(announce_channel, 'id', None)}")
    if not announce_channel:
        # Fallback: use the listener channel if no announce channel is set
        announce_channel = message.channel
        print("[DEBUG] No announce channel set, using listener channel.")

    # Create a fake context with the announcement channel for the read function
    ctx = await bot.get_context(message)
    ctx.channel = announce_channel

    await announce_channel.send("Detected a svalid tweet, parsing...")
    await read_llm(ctx, twitter_link)
    print("[DEBUG] Finished processing tweet.")
    return True   

# Check if the tweet is an event/announcement using LLM
async def is_event_tweet(tweet_text, profile):
    """
    Uses the LLM to classify if a tweet is an event/announcement for the given profile.
    Returns True if it's an event, False otherwise.
    """
    prompt = (
        f"Classify the following tweet for the game profile '{profile}'. "
        "Reply only with 'Event' if it is an in-game event, banner, maintenance, or update announcement. "
        "The tweet is only classified as an 'Event' if it has both a starting time and an ending time, regardless of timezone. "
        "The starting and ending time can be vague, such as `After version X.X update` or `It will take about five hours to complete`."
        "Reply only with 'Filler' if it is a trailer, fanart, contest, winner announcement, or any non-event content.\n"
        f"Tweet:\n{tweet_text}"
    )
    response = await run_llm_inference(prompt)
    return response.strip().lower().startswith("event")

@bot.event
async def on_reaction_add(reaction, user):
    # Only respond to reactions from users (not the bot itself)
    if user.bot:
        return

    # Only process if the reaction is either ❌ or ✅
    if str(reaction.emoji) not in ("❌", "✅"):
        return

    message = reaction.message

    # Only process Twitter/X links
    twitter_link = None
    for word in message.content.split():
        if "twitter.com" in word or "x.com" in word:
            twitter_link = word
            break
    if not twitter_link:
        return

    # Only trigger if the user added the reaction (no need to check for both)
    announce_channel = await get_announce_channel(message.guild)
    if not announce_channel:
        announce_channel = message.channel

    ctx = await bot.get_context(message)
    ctx.channel = announce_channel

    await announce_channel.send(
        f"{user.mention} forced a read on this tweet (by reacting with {reaction.emoji}). Parsing now..."
    )
    await read_llm(ctx, twitter_link)