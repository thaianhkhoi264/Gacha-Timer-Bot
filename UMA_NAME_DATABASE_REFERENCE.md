There are a few pages on a website that I need data to be parsed from. You will need to go to the website yourself to understand the structure of that website.

The databases should be in /data/JP_Data/

The first one is from this website:
https://gametora.com/umamusume/gacha/history?server=ja&type=all&year=all (JP)
https://gametora.com/umamusume/gacha/history?server=en&type=all&year=all (Global)

**IMPORTANT:** Use `server=ja` for Japanese server, NOT `server=jp` (which redirects to Global)

Near the top of the website, there should be 3 selectable categories:

Server: Global, JP (use `ja` parameter), KR, TW
Year: All, 2021-2025 (JP ONLY)/2025 (GLOBAL ONLY)/2022-2025(KR/TW ONLY)
Type: Characters, Support, All

This website contains the Event Images and Event banner images for both the Global version and the Japanese version of the game. IGNORE THE KR/TW SERVERS.

---

## STEP 1: JP Server Banner Data (server=ja, type=all, year=all)

### Website Structure (HTML/CSS)

The page uses **lazy loading** - you MUST scroll down to load all banners. Without scrolling, you'll only see the first ~48 banners.

**Lazy Loading Strategy:**
1. Load page with `wait_until="domcontentloaded"` (NOT networkidle)
2. Use timeout of 90 seconds (Raspberry Pi is slow)
3. Scroll down: `window.scrollBy(0, document.body.scrollHeight)`
4. Wait 3 seconds for items to load
5. Check container count
6. Repeat until no new containers appear for 5 consecutive iterations (max 50 iterations)

**CSS Selectors:**

```
Banner Container (card): .sc-37bc0b3c-0
Character/Support List: ul.sc-37bc0b3c-3 (inside container)
List Item: li (inside ul)
Name/Link: .gacha_link_alt__mZW_P or span.sc-37bc0b3c-5 (inside li)
Banner Image: img[src*="img_bnr_gacha_"] (inside container)
```

**Example DOM Structure:**
```html
<div class="sc-37bc0b3c-0">  <!-- Banner container -->
  <img src="https://gametora.com/images/umamusume/gacha/img_bnr_gacha_30380.png" />
  
  <ul class="sc-37bc0b3c-3">  <!-- Characters/Supports list -->
    <li>
      <a href="/umamusume/characters/109001-verxina">
        <span class="gacha_link_alt__mZW_P">Verxina</span>
      </a>
    </li>
    <li>
      <a href="/umamusume/characters/103001-rice-shower">
        <span class="gacha_link_alt__mZW_P">Rice Shower New, 0.75%</span>  <!-- Rate-up info must be cleaned -->
      </a>
    </li>
  </ul>
</div>
```

### Data Extraction

**Banner Type Detection:**
- Check container text for "Support Card" (English) or "サポートカード" (Japanese) → Type = "Support"
- Check container text for "Character" (English) or "キャラクター" (Japanese) → Type = "Character"
- Fallback: Check if any names contain "New" or "Rerun" → Type = "Character"
- Otherwise → Type = "Unknown"

**Banner ID:**
- Extract from image src: `img_bnr_gacha_XXXXX.png` → ID = XXXXX
- Use regex: `r'img_bnr_gacha_(\d+)\.png'`
- DO NOT save the image itself in Step 1

**Character/Support Names:**
- Extract all text from `.gacha_link_alt__mZW_P` spans
- **IMPORTANT:** Clean names by removing rate-up info from the END
- Regex pattern: `r'\s+(New|Rerun)(?:,?\s*[\d.]+%)?\s*$'`
  - Removes: " New", " New, 0.75%", " Rerun", " Rerun 0.75%", etc. at END only
  - This handles edge case: if char named "X New" appears on rate-up as "X New New", only removes one instance
- Strip whitespace after cleaning
- Store ALL names (not just first 5)

**Examples of name cleaning:**
```
"Nakayama Festa (Christmas) New, 0.75%" → "Nakayama Festa (Christmas)"
"Jungle Pocket Rerun" → "Jungle Pocket"
"Verxina" → "Verxina" (unchanged)
"Character New New" (hypothetical char named "X New" on rate-up) → "Character New"
```

**Description:**
- Join all cleaned character/support names with ", "
- Store full list (not truncated)
- Example: "Verxina, Rice Shower, Tokai Teio, Maruzenskyy, Special Week"

### Database Schema

**banners table:**
```sql
id INTEGER PRIMARY KEY
banner_id TEXT UNIQUE NOT NULL
banner_type TEXT NOT NULL  -- Character, Support, or Unknown
description TEXT  -- Comma-separated list of all items
server TEXT NOT NULL DEFAULT 'JA'  -- 'JA' for Japanese
```

**characters table:**
```sql
character_id TEXT PRIMARY KEY  -- From URL: /characters/109001-verxina
name TEXT
link TEXT  -- Full URL: https://gametora.com/umamusume/characters/109001-verxina
```

**support_cards table:**
```sql
support_id TEXT PRIMARY KEY
name TEXT
link TEXT
```

**banner_items table (junction):**
```sql
banner_id TEXT
item_id TEXT  -- character_id or support_id
item_type TEXT  -- 'character' or 'support'
PRIMARY KEY (banner_id, item_id, item_type)
```

### Parsing Example

Event ID 30332 with 17 characters:
1. Container `.sc-37bc0b3c-0` has image `img_bnr_gacha_30332.png` → banner_id = 30332
2. Container text contains "Character" → banner_type = "Character"
3. `ul.sc-37bc0b3c-3` has 17 `li` elements, each with a name
4. Extract all 17 names, clean them, join with ", "
5. Insert into banners: (30332, 'Character', 'name1, name2, ..., name17', 'JA')
6. For each name, extract character ID and link from the href
7. Insert into characters and banner_items tables

---

## STEP 2: Global Server Banner Images (server=en, type=all, year=all)

Same website structure as Step 1, but with server=en parameter.

**What to Do:**
1. Load page with same lazy-loading strategy as Step 1
2. For each banner, extract:
   - Banner ID from image src (same regex: `img_bnr_gacha_XXXXX.png`)
   - Image URL: Full URL to the PNG file

**Do NOT extract character/support data** - that's already from Step 1 JP data

**Download & Store:**
1. Download image to `data/JP_Data/banner_images/`
2. Filename: `img_bnr_gacha_XXXXX.png` (keep original name)
3. Store mapping in database

### Database Schema

**global_banner_images table:**
```sql
banner_id TEXT PRIMARY KEY
image_url TEXT  -- Full URL
image_path TEXT  -- Local file path: data/JP_Data/banner_images/img_bnr_gacha_XXXXX.png
downloaded BOOLEAN  -- Whether image was successfully saved
```

---

## Implementation Notes

### Timeout & Reliability
- Use `wait_until="domcontentloaded"` (NOT "networkidle")
- Set `timeout=90000` (90 seconds) for Raspberry Pi
- Implement 3-retry logic with exponential backoff:
  ```python
  for attempt in range(3):
      try:
          await page.goto(url, timeout=90000, wait_until="domcontentloaded")
          break
      except Exception as e:
          if attempt < 2:
              await asyncio.sleep(2 ** attempt)
          else:
              raise
  ```

### CSS Class Stability
- These classes are dynamically generated and may change
- Monitor for failed extractions
- If parsing breaks, check actual HTML on website
- All classes currently verified: `.sc-37bc0b3c-0`, `ul.sc-37bc0b3c-3`, `.gacha_link_alt__mZW_P`

### Data Validation
- Verify banner_id is numeric
- Verify character/support links follow pattern: `/umamusume/characters/XXXXX-name`
- Skip items with no name or ID
- Log extraction failures for debugging

### Current Results (as of Dec 8, 2025)
- JP Server: 317 banners successfully loading
- Global Server: 48 banners successfully loading
- Character name cleaning: Working (no "New, 0.75%" suffixes)
- Banner type detection: Working (proper Character vs Support classification)