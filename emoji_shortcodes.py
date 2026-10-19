"""Emoji shortcodes for custom notification messages (e.g. ``:diapat:``)."""

import re

DIA_EMOJIS = {
    "diawave":   "<a:diawave:1558272299818426419>",
    "diapat":    "<a:diapat:1508665594013286400>",
    "dianod":    "<a:dianod:1508662343322697839>",
    "diashake":  "<a:diashake:1508662342060081253>",
    "diastare":  "<a:diastare:1508665580071161967>",
    "diascared": "<:diascared:1528840090451837088>",
    "diaread":   "<:diaread:1529673666370207884>",
    "diacheer":  "<:diacheer:1561791513464143984>",
}

# The first alternative swallows already-expanded emoji whole so the ":name:"
# inside "<a:name:id>" is never expanded a second time.  Only known names are
# matched, so unknown ":foo:" text is never consumed.
_SHORTCODE_RE = re.compile(
    r"<a?:\w+:\d+>"
    r"|(?<!<a)(?<!<):("
    + "|".join(re.escape(name) for name in sorted(DIA_EMOJIS, key=len, reverse=True))
    + r"):"
)


def expand_emoji_shortcodes(text):
    """Replace known ``:name:`` shortcodes with their raw Discord emoji strings."""
    if not text:
        return text
    return _SHORTCODE_RE.sub(
        lambda m: DIA_EMOJIS[m.group(1)] if m.group(1) else m.group(0), text
    )
