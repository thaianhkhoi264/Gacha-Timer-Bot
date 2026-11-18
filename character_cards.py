"""Character-card data from the source site's static JSON data files.

The site renders its pages from static JSON files listed in a manifest
(``/data/manifests/<game>.json`` maps a file name to a content hash; the files live at
``/data/<game>/<name>.<hash>.json``).  Reading those is far sturdier than scraping the
rendered DOM, whose CSS class names are hashed and change on every redeploy.

This module resolves the ``character-cards`` file (manifest -> page-bundle scan ->
network sniffing), keeps a raw local copy under ``data/cards/`` for other projects,
and converts cards into rows for the ``characters`` table.  It has no bot, Discord or
database dependency.
"""

import asyncio
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple

import aiohttp

logger = logging.getLogger("character_cards")
logger.setLevel(logging.INFO)

GAME = "umamusume"
BASE_URL = "https://gametora.com"  # the only place the source host is named
CHARACTERS_PAGE_URL = f"{BASE_URL}/umamusume/characters"
DEFAULT_MANIFEST_PREFIX = "/data/manifests/"
DEFAULT_DATA_PREFIX = "/data/"
CARDS_KEY = "character-cards"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT_S = 30
HTTP_ATTEMPTS = 3
HTTP_BACKOFF_S = 1.0          # waits 1x, 2x between attempts
BUNDLE_CHUNK_DELAY_S = 0.2    # pause between page-bundle chunk fetches
MAX_BUNDLE_CHUNKS = 60
NETWORK_WAIT_S = 25           # last-resort browser: how long to wait for the data request
MIN_CARDS = 100               # the source lists ~270; far fewer means a broken response

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cards")
CARDS_FILE = "character-cards.json"
META_FILE = "character-cards.meta.json"
MANIFEST_FILE = "manifest.json"

# The site's own display names for the ``version`` field, taken from the ``strings.en``
# table in the characters page's JS bundle and cross-checked against the names the old
# DOM scraper stored.  The JP banner scraper matches banner item names against
# ``characters.name`` exactly, so these must equal what the site displays.
VERSION_DISPLAY_NAMES = {
    "alt": "Alt Version",
    "summer": "Summer",
    "anime_collab": "Anime Collab",
    "fantasy": "Fantasy",
    "fairytale": "Fairytale",
    "wedding": "Wedding",
    "full_armor": "Full Armor",
    "halloween": "Halloween",
    "fall_festival": "Festival",
    "christmas": "Christmas",
    "new_year": "New Year",
    "valentine": "Valentine",
    "ballroom": "Ballroom",
    "cheerleader": "Cheerleader",
    "camping": "Camping",
    "commander": "Commander",
    "grand_live": "Grand Concert",
    "steampunk": "Steampunk",
    "blaze": "BLAZE",
    "sports_fest": "Sports Festival",
    "summer_trip": "Summer Trip",
    "warfare": "Warfare",
    "autumn": "Autumn",
    "larc": "Project L'Arc",
    "uaf": "U.A.F.",
    "gff": "Great Food Festival",
    "mecha": "Mecha",
    "twinkle": "The Twinkle Legends",
    "island": "Deserted Island",
    "parade": "Parade",
    "onsen": "Onsen",
    "beyond_dreams": "Beyond Dreams",
    "tracen_ken": "Tracen-ken",
    "shuntaisai": "Shuntaisai",
    "five_point_five_anni": "5.5th Anni",
}


# ── Cards -> characters rows ─────────────────────────────────────────────────

def version_display_name(version: str) -> Tuple[str, bool]:
    """Return ``(display_name, is_mapped)``; unmapped versions are title-cased."""
    mapped = VERSION_DISPLAY_NAMES.get(version)
    if mapped is not None:
        return mapped, True
    return str(version).replace("_", " ").title(), False


def card_to_row(card: dict) -> Tuple[dict, Optional[str]]:
    """Convert one card to a ``characters`` row.

    Returns ``(row, unmapped_version)``; ``unmapped_version`` is None unless the card's
    version has no entry in VERSION_DISPLAY_NAMES.  Raises ValueError for unusable cards.
    """
    try:
        card_id = str(card["card_id"]).strip()
        name = str(card["name_en"]).strip()
        url_name = str(card["url_name"]).strip()
    except (KeyError, TypeError) as exc:
        raise ValueError(f"card is missing {exc}") from exc
    if not card_id.isdigit() or not name or not url_name:
        raise ValueError(f"card has empty/invalid id, name or url_name: {card_id!r}")

    unmapped = None
    version = card.get("version")
    if version:
        display, mapped = version_display_name(version)
        name = f"{name} ({display})"
        if not mapped:
            unmapped = str(version)
    return {
        "character_id": card_id,
        "name": name,
        "link": f"/umamusume/characters/{url_name}",
    }, unmapped


def cards_to_rows(cards: List[dict]) -> Tuple[List[dict], Set[str], int]:
    """Convert cards to rows.  Returns ``(rows, unmapped_versions, skipped_count)``.

    Every card is kept regardless of ``release_en`` (JP-only cards are included, as the
    old DOM scraper did).  Duplicate card ids keep the first occurrence.
    """
    rows, seen, unmapped_versions, skipped = [], set(), set(), 0
    for card in cards:
        try:
            row, unmapped = card_to_row(card)
        except ValueError as exc:
            skipped += 1
            logger.warning(f"[Cards] Skipping unusable character card: {exc}")
            continue
        if row["character_id"] in seen:
            continue
        seen.add(row["character_id"])
        rows.append(row)
        if unmapped:
            unmapped_versions.add(unmapped)
    return rows, unmapped_versions, skipped


def parse_cards(body: bytes) -> List[dict]:
    """Decode a character-cards file; raises ValueError if it doesn't look like one."""
    try:
        data = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON list, got {type(data).__name__}")
    usable = sum(
        1 for c in data
        if isinstance(c, dict) and "card_id" in c and "name_en" in c and "url_name" in c
    )
    if len(data) < MIN_CARDS or usable < 0.9 * len(data):
        raise ValueError(f"only {usable}/{len(data)} usable cards (minimum {MIN_CARDS})")
    return data


# ── HTTP ─────────────────────────────────────────────────────────────────────

class FetchError(Exception):
    """An HTTP request failed (``status`` is set when the server answered)."""

    def __init__(self, url: str, status: Optional[int] = None, reason: str = ""):
        detail = f"HTTP {status}" if status else reason
        super().__init__(f"{url}: {detail}")
        self.url = url
        self.status = status


class DiscoveryError(Exception):
    """A discovery step could not locate the character-cards file."""


async def _http_get(url: str) -> bytes:
    """GET with a timeout, retries and backoff.  4xx (except 429) is final: no retry."""
    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html, */*"}
    last: Optional[FetchError] = None
    for attempt in range(1, HTTP_ATTEMPTS + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    last = FetchError(url, status=resp.status)
                    if resp.status < 500 and resp.status != 429:
                        raise last
        except FetchError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last = FetchError(url, reason=f"{type(exc).__name__}: {exc}")
        if attempt < HTTP_ATTEMPTS:
            await asyncio.sleep(HTTP_BACKOFF_S * attempt)
    raise last


# ── Discovery ────────────────────────────────────────────────────────────────

@dataclass
class Resolution:
    """Where the character-cards file lives, and how it was found."""
    data_url: str
    hash: Optional[str]
    discovered_via: str
    manifest_url: Optional[str] = None
    manifest_body: Optional[bytes] = None


@dataclass
class BundleHints:
    manifest_prefixes: List[str] = field(default_factory=list)
    data_prefixes: List[str] = field(default_factory=list)
    keys: List[str] = field(default_factory=list)


async def _load_manifest(prefix: str) -> Tuple[str, bytes, dict]:
    url = f"{BASE_URL}{prefix}{GAME}.json"
    body = await _http_get(url)
    try:
        manifest = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise DiscoveryError(f"{url} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise DiscoveryError(f"{url} is not a JSON object")
    return url, body, manifest


def _resolution_from_manifest(url, body, manifest, data_prefix, key, via) -> Resolution:
    file_hash = manifest.get(key)
    if not file_hash or not isinstance(file_hash, str):
        raise DiscoveryError(f"manifest {url} has no '{key}' entry")
    return Resolution(
        data_url=f"{BASE_URL}{data_prefix}{GAME}/{key}.{file_hash}.json",
        hash=file_hash,
        discovered_via=via,
        manifest_url=url,
        manifest_body=body,
    )


async def _resolve_via_manifest() -> Resolution:
    """Step 1: the manifest at its known path."""
    url, body, manifest = await _load_manifest(DEFAULT_MANIFEST_PREFIX)
    return _resolution_from_manifest(
        url, body, manifest, DEFAULT_DATA_PREFIX, CARDS_KEY, "manifest")


_SCRIPT_SRC_RE = re.compile(
    r'<script[^>]+src=["\'](?:' + re.escape(BASE_URL) + r')?(/_next/static/[^"\']+\.js)["\']')
_MANIFEST_PREFIX_RE = re.compile(r'["\'`](/[A-Za-z0-9_\-/]*manifests/)["\'`]')
_DATA_PREFIX_RE = re.compile(
    r'["\'`](/[A-Za-z0-9_\-/]*data/)(?=["\'`]\s*\.concat\(|\$\{)')
_KEY_RE = re.compile(
    r'\(\s*["\']' + GAME + r'["\']\s*,\s*["\']([A-Za-z0-9_\-/]*card[A-Za-z0-9_\-/]*)["\']')


def _add_unique(target: List[str], values) -> None:
    for value in values:
        if value not in target:
            target.append(value)


async def _scan_bundle() -> BundleHints:
    """Read the characters page's script chunks for the manifest path, data path and key."""
    html = (await _http_get(CHARACTERS_PAGE_URL)).decode("utf-8", "replace")
    srcs = list(dict.fromkeys(_SCRIPT_SRC_RE.findall(html)))[:MAX_BUNDLE_CHUNKS]
    if not srcs:
        raise DiscoveryError("the characters page lists no /_next/static script chunks")

    hints = BundleHints()
    for index, src in enumerate(srcs):
        try:
            js = (await _http_get(BASE_URL + src)).decode("utf-8", "replace")
        except FetchError as exc:
            logger.debug(f"[Cards] Skipping bundle chunk {src}: {exc}")
            continue
        _add_unique(hints.manifest_prefixes, _MANIFEST_PREFIX_RE.findall(js))
        _add_unique(hints.data_prefixes, _DATA_PREFIX_RE.findall(js))
        _add_unique(hints.keys, [
            k for k in _KEY_RE.findall(js)
            if "character" in k and "card" in k and "source" not in k
        ])
        if hints.manifest_prefixes and hints.data_prefixes and hints.keys:
            break
        if BUNDLE_CHUNK_DELAY_S and index < len(srcs) - 1:
            await asyncio.sleep(BUNDLE_CHUNK_DELAY_S)

    if not (hints.manifest_prefixes or hints.data_prefixes or hints.keys):
        raise DiscoveryError(f"nothing useful found in {len(srcs)} bundle chunk(s)")
    logger.info(f"[Cards] Bundle scan hints: {hints}")
    return hints


async def _resolve_via_bundle() -> Resolution:
    """Step 2: rediscover the manifest path / data path / key from the page's JS bundle."""
    hints = await _scan_bundle()
    manifest_prefixes: List[str] = []
    _add_unique(manifest_prefixes, hints.manifest_prefixes + [DEFAULT_MANIFEST_PREFIX])
    data_prefix = (hints.data_prefixes or [DEFAULT_DATA_PREFIX])[0]
    keys: List[str] = []
    _add_unique(keys, hints.keys + [CARDS_KEY])

    errors = []
    for prefix in manifest_prefixes:
        try:
            url, body, manifest = await _load_manifest(prefix)
        except (FetchError, DiscoveryError) as exc:
            errors.append(str(exc))
            continue
        for key in keys:
            try:
                return _resolution_from_manifest(
                    url, body, manifest, data_prefix, key, "bundle-scan")
            except DiscoveryError as exc:
                errors.append(str(exc))
    raise DiscoveryError("bundle hints did not resolve: " + "; ".join(errors[-3:]))


_CARDS_URL_RE = re.compile(r"/data/(?:[^/?#]+/)*character-cards\.([0-9A-Za-z]+)\.json")
_MANIFEST_URL_RE = re.compile(r"/data/manifests/[^/?#]+\.json")
_ANY_DATA_JSON_RE = re.compile(r"/data/.*\.json")


async def _resolve_via_network() -> Resolution:
    """Step 3 (last resort): load the page in a browser and watch which data files it requests."""
    from playwright.async_api import async_playwright

    seen: List[Tuple[str, int]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=USER_AGENT)
            page.on("response", lambda response: seen.append((response.url, response.status)))
            await page.goto(CHARACTERS_PAGE_URL, wait_until="domcontentloaded", timeout=60000)
            for _ in range(NETWORK_WAIT_S * 2):
                if any(_CARDS_URL_RE.search(url) for url, _ in seen):
                    break
                await asyncio.sleep(0.5)
        finally:
            await browser.close()

    data_urls = [url for url, status in seen if status == 200 and _ANY_DATA_JSON_RE.search(url)]
    manifest_url = next((u for u in data_urls if _MANIFEST_URL_RE.search(u)), None)

    for url in data_urls:
        match = _CARDS_URL_RE.search(url)
        if match:
            return Resolution(url, match.group(1), "network", manifest_url)

    # The file may have been renamed: pick a data file that actually looks like card data.
    for url in [u for u in data_urls if not _MANIFEST_URL_RE.search(u)][:15]:
        try:
            parse_cards(await _http_get(url))
        except (FetchError, ValueError):
            continue
        hash_match = re.search(r"\.([0-9a-f]{6,})\.json$", url)
        return Resolution(url, hash_match.group(1) if hash_match else None, "network", manifest_url)

    raise DiscoveryError(f"no character-cards request seen among {len(seen)} network responses")


# ── Local copy ───────────────────────────────────────────────────────────────

def _atomic_write_bytes(path: str, data: bytes) -> None:
    """Write via a temp file in the same folder, then rename over the target."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _load_saved(data_dir: str) -> Optional[Tuple[dict, List[dict]]]:
    """Return ``(meta, cards)`` from the saved copy, or None if absent/corrupt."""
    try:
        with open(os.path.join(data_dir, META_FILE), "rb") as handle:
            meta = json.loads(handle.read().decode("utf-8"))
        with open(os.path.join(data_dir, CARDS_FILE), "rb") as handle:
            cards = parse_cards(handle.read())
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or not meta.get("hash"):
        return None
    return meta, cards


def _save_copy(data_dir: str, body: bytes, cards: List[dict], res: Resolution) -> None:
    """Persist the raw data file, then the manifest, then the meta file (the commit marker)."""
    _atomic_write_bytes(os.path.join(data_dir, CARDS_FILE), body)
    if res.manifest_body:
        _atomic_write_bytes(os.path.join(data_dir, MANIFEST_FILE), res.manifest_body)
    meta = {
        "source_url": res.data_url,
        "manifest_url": res.manifest_url,
        "hash": res.hash,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(cards),
        "discovered_via": res.discovered_via,
    }
    _atomic_write_bytes(
        os.path.join(data_dir, META_FILE),
        (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )


# ── Public entry point ───────────────────────────────────────────────────────

@dataclass
class CharacterCards:
    cards: List[dict]
    hash: Optional[str]
    discovered_via: str
    downloaded: bool
    source_url: str


async def fetch_character_cards(data_dir: str = DATA_DIR) -> Optional[CharacterCards]:
    """Get the current character cards, or None if every discovery method failed.

    The data file is only downloaded when its hash differs from the saved copy's.  On
    total failure nothing is written, so the previous copy (and the caller's database
    rows) stay exactly as they were.
    """
    saved = _load_saved(data_dir)
    steps = (
        ("manifest", _resolve_via_manifest),
        ("bundle-scan", _resolve_via_bundle),
        ("network", _resolve_via_network),
    )

    errors = []
    for via, resolver in steps:
        try:
            res = await resolver()
            if saved and res.hash and saved[0].get("hash") == res.hash:
                logger.info(
                    f"[Cards] character-cards unchanged (hash {res.hash}, found via {via}); "
                    f"using saved copy")
                return CharacterCards(saved[1], res.hash, via, False, res.data_url)
            body = await _http_get(res.data_url)
            cards = parse_cards(body)
        except Exception as exc:  # any failure falls through to the next method
            errors.append(f"{via}: {exc}")
            logger.warning(f"[Cards] character-cards discovery via {via} failed: {exc}")
            continue

        logger.info(
            f"[Cards] character-cards downloaded via {via}: {len(cards)} cards, "
            f"hash {res.hash}")
        try:
            _save_copy(data_dir, body, cards, res)
        except OSError as exc:
            logger.error(f"[Cards] Could not save the local character-cards copy: {exc}")
        return CharacterCards(cards, res.hash, via, True, res.data_url)

    logger.error(
        "[Cards] Could not fetch character-cards by any method "
        f"({'; '.join(errors)}); keeping the previous copy and database rows untouched")
    return None
