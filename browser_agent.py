'''    
# ============================================================
#  browser_agent.py  —  Agentic scraper
#  Supports: Amazon (amazon.in) and Flipkart (flipkart.com)
# ============================================================
import json, re, urllib.parse
from llm_client import call_llm
from config import REQUEST_TIMEOUT


NEXT_PAGE_SELECTORS = [
    "a[aria-label='Next']",
    "a[aria-label='next page' i]",
    "a:has-text('Next')",
    "a:has-text('›')",
    "a:has-text('»')",
    "[class*='next' i][href]",
    ".pagination a:last-child",
]


# ──────────────────────────────────────────────────────────
#  SITE DETECTION
# ──────────────────────────────────────────────────────────

def _detect_site(url: str) -> str:
    if "flipkart.com" in url: return "flipkart"
    if "amazon.in"   in url: return "amazon"
    return "unknown"


# ──────────────────────────────────────────────────────────
#  NAVIGATION PLANNER
# ──────────────────────────────────────────────────────────

FLIPKART_URL_GUIDE = """
Flipkart search URL structure:
  Base:  https://www.flipkart.com/search?q=KEYWORD
  Price: append &p%5B%5D=facets.price_range.from%3DMIN&p%5B%5D=facets.price_range.to%3DMAX

  Rules for price range:
  - "under X"         → MIN=500,  MAX=X
  - "above X"         → MIN=X,    MAX=500000
  - "between X and Y" → MIN=X,    MAX=Y
  - no price          → omit price params entirely
  - MIN must always be less than MAX

  Rules for keyword:
  - Use product terms only — no price words
  - e.g. "smartphones under 20000" → keyword = "smartphone"

Return ONLY JSON: {"keyword": "...", "url": "https://..."}
"""

AMAZON_URL_GUIDE = """
Amazon India search URL structure:
  Base:  https://www.amazon.in/s?k=KEYWORD&i=electronics
  Price: append &low-price=MIN&high-price=MAX  (plain rupees)
  Sort:  append &s=price-asc-rank

  Rules for price range:
  - "under X"         → low-price=100, high-price=X
    IMPORTANT: low-price must ALWAYS be less than high-price
    e.g. "under 500"  → low-price=100, high-price=500
    e.g. "under 2000" → low-price=100, high-price=2000
  - "above X"         → low-price=X,   high-price=500000
  - "between X and Y" → low-price=X,   high-price=Y
  - no price          → omit price params, just use base URL

  Rules for keyword:
  - Product terms only — no price words in keyword
  - e.g. "wireless earphones under 2000" → keyword = "wireless earphones"

Return ONLY JSON: {"keyword": "...", "url": "https://..."}
"""


def _plan_navigation(user_request: str, site: str) -> str | None:
    guide = FLIPKART_URL_GUIDE if site == "flipkart" else AMAZON_URL_GUIDE
    result = call_llm(f'User wants: "{user_request}"\n\n{guide}')
    if result and "url" in result:
        print(f"  [nav] planned URL: {result['url']}")
        return result["url"]
    return None


# ──────────────────────────────────────────────────────────
#  PAGE READER  —  targets product cards specifically
# ──────────────────────────────────────────────────────────

def _read_page(page) -> tuple[str, str]:
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except:
        pass
    try:
        # Amazon: target product card elements directly
        text = page.evaluate(
            "() => { var cards = document.querySelectorAll('[data-component-type=\\'s-search-result\\']');"
            " if (cards.length > 0) { return Array.from(cards).map(function(c){return c.innerText;}).join(' --- '); }"
            " return null; }"
        )
        if not text or len(text.strip()) < 200:
            # Flipkart: target product card divs
            text = page.evaluate(
                "() => { var cards = document.querySelectorAll('div[data-id]');"
                " if (cards.length > 5) { return Array.from(cards).map(function(c){return c.innerText;}).join(' --- '); }"
                " return null; }"
            )
        if not text or len(text.strip()) < 200:
            # Fallback: full body text minus noise
            text = page.evaluate(
                "() => { var noise = document.querySelectorAll('script,style,noscript,iframe,nav,header,footer');"
                " noise.forEach(function(e){e.remove();});"
                " return document.body.innerText; }"
            )
        text = (text or "").strip()
        print(f"  [page] {len(text)} chars | {text[:120].strip()!r}")
        return text[:10000], page.url
    except Exception as e:
        print(f"  [page] ERROR: {e}")
        return "", page.url


# ──────────────────────────────────────────────────────────
#  PAGE QUALITY CHECK
# ──────────────────────────────────────────────────────────

def _is_results_page(text: str, site: str) -> tuple[bool, str]:
    t = text.lower()
    char_count = len(text.strip())

    if char_count < 500:
        return False, f"too short ({char_count} chars) — page blocked or empty"

    # Genuine no-results (ignore keyboard shortcut "Results" text on Amazon)
    if ("no results for" in t or "didn't match any products" in t) \
            and "keyboard shortcuts" not in t[:500]:
        return False, "no results found for this query"

    if site == "flipkart":
        signals = ["add to cart", "buy now", "₹", "rating", "off", "sponsored"]
        found = [s for s in signals if s in t]
        if len(found) >= 2:
            return True, f"flipkart listings detected {found[:3]}"

    if site == "amazon":
        signals = ["add to cart", "sponsored", "₹", "out of stock", "results for", "delivery"]
        found = [s for s in signals if s in t]
        if len(found) >= 2:
            return True, f"amazon listings detected {found[:3]}"

    if char_count > 3000:
        return True, f"substantial page ({char_count} chars) — attempting extract"

    return False, f"unclear page ({char_count} chars)"


# ──────────────────────────────────────────────────────────
#  EXTRACTOR
# ──────────────────────────────────────────────────────────

def _extract(page_text: str, user_request: str, url: str) -> list:
    if len(page_text.strip()) < 200:
        print("  [extract] page too short, skipping")
        return []

    num_cards = page_text.count("---") + 1
    print(f"  [extract] reading ~{num_cards} product cards")

    # Tell LLM expected price range from URL so it doesn't confuse filter params with prices
    url_low  = re.search(r'low-price=(\d+)',  url)
    url_high = re.search(r'high-price=(\d+)', url)
    url_low_val  = int(url_low.group(1))  if url_low  else 0
    url_high_val = int(url_high.group(1)) if url_high else 999999

    price_hint = ""
    if url_low and url_high:
        price_hint = (
            f"NOTE: Products on this page are priced between "
            f"₹{url_low_val} and ₹{url_high_val}. "
            f"Extract the ACTUAL price shown on each card — "
            f"NOT the URL filter values ({url_low_val} and {url_high_val} are filters, not prices)."
        )

    result = call_llm(f"""
Extract ALL product listings from this page matching: "{user_request}"

{price_hint}

Return ONLY this JSON — no explanation, no markdown:
{{"records":[{{
  "name": "full product name",
  "brand": "brand name from product name",
  "price": "actual selling price as integer e.g. 1299",
  "original_price": "MRP/crossed-out price if shown, else empty",
  "discount_pct": "discount % if shown e.g. 25, else empty",
  "rating": "star rating e.g. 4.3, else empty",
  "review_count": "number of reviews e.g. 1243, else empty",
  "sponsored": "yes if Sponsored label shown, else no",
  "in_stock": "yes if Add to Cart visible, no if Out of Stock, else yes",
  "delivery_days": "delivery days if shown, else empty",
  "specs": "all visible specs: connectivity, playtime, RAM, battery etc.",
  "category": "product category"
}}]}}

RULES:
- price = ACTUAL price on the card (e.g. ₹1,299 → 1299). Never use URL filter values as price.
- brand = first recognizable word from product name (boAt, JBL, Sony, Samsung etc.)
- Prices like 149900 are paise → divide by 100 → 1499
- Empty string "" for any missing field
- Extract ALL {num_cards} product cards
- {{"records":[]}} only if truly no products visible

PAGE URL: {url}
PAGE CONTENT:
{page_text[:8000]}
""")

    records = (result or {}).get("records", [])

    # ── Post-processing: fix prices, brand, paise ──────────
    cleaned = []
    for r in records:
        # Fix price
        try:
            p = int(str(r.get("price","0")).replace(",","").replace("₹","").strip())
            if p > 100000:           # paise → rupees
                p = p // 100
            if p == url_low_val:     # price equals filter param = wrong, skip record
                continue
            r["price"] = str(p) if p > 0 else ""
        except:
            r["price"] = ""

        # Fix original_price paise
        try:
            op = int(str(r.get("original_price","0")).replace(",","").replace("₹","").strip())
            if op > 100000:
                r["original_price"] = str(op // 100)
        except:
            pass

        # Recalculate discount_pct if missing
        try:
            if not r.get("discount_pct") and r.get("price") and r.get("original_price"):
                p  = float(r["price"])
                op = float(r["original_price"])
                if op > p > 0:
                    r["discount_pct"] = str(round((op - p) / op * 100, 1))
        except:
            pass

        # Auto-extract brand from name if missing
        if not r.get("brand") and r.get("name"):
            words = str(r["name"]).split()
            if words and len(words[0]) > 1 and words[0][0].isupper():
                r["brand"] = words[0]

        # Only keep records with a valid price
        if r.get("price","").strip() not in ("", "0"):
            cleaned.append(r)

    print(f"  [extract] {len(cleaned)} records")
    return cleaned


# ──────────────────────────────────────────────────────────
#  PAGINATION
# ──────────────────────────────────────────────────────────

def _next_page(page) -> bool:
    url_before = page.url

    # Amazon: append &page=N directly — more reliable than clicking Next
    if "amazon.in" in url_before:
        match = re.search(r'[?&]page=(\d+)', url_before)
        current = int(match.group(1)) if match else 1
        next_num = current + 1
        if match:
            next_url = url_before.replace(f"page={current}", f"page={next_num}")
        else:
            sep = "&" if "?" in url_before else "?"
            next_url = url_before + sep + f"page={next_num}"
        print(f"  [next] amazon page {next_num}")
        page.goto(next_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
        page.wait_for_timeout(3000)
        return page.url != url_before

    # Flipkart: click Next button
    for sel in NEXT_PAGE_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(3000)
                if page.url != url_before:
                    print(f"  [next] {sel}")
                    return True
                else:
                    print("  [next] URL unchanged — no more pages")
                    return False
        except:
            continue
    return False


# ──────────────────────────────────────────────────────────
#  CACHE CLEANUP
# ──────────────────────────────────────────────────────────

def _clear_stale_cache():
    from llm_client import _cache, _save_cache
    stale = [k for k, v in _cache.items()
             if isinstance(json.loads(v).get("records"), list)
             and len(json.loads(v)["records"]) == 0]
    for k in stale: del _cache[k]
    if stale:
        _save_cache(_cache)
        print(f"[agent] cleared {len(stale)} stale cache entries")


# ──────────────────────────────────────────────────────────
#  MAIN AGENT LOOP
# ──────────────────────────────────────────────────────────

def run_agent(start_url: str, user_request: str, max_pages: int = 10) -> dict:
    from playwright.sync_api import sync_playwright

    _clear_stale_cache()

    site = _detect_site(start_url)
    if site == "unknown":
        print("[agent] Unsupported site. Use amazon.in or flipkart.com.")
        return {"records": [], "pages_visited": 0, "summary": "Unsupported site."}

    print(f"\n[agent] Site:    {site}")
    print(f"[agent] Request: {user_request}")
    print(f"[agent] Pages:   {max_pages}\n")

    search_url = _plan_navigation(user_request, site)
    if not search_url:
        return {"records": [], "pages_visited": 0, "summary": "Navigation planning failed."}

    all_records  = []
    pages_visited = 0
    last_text    = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
        )
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.new_page()

        print(f"[agent] Navigating to: {search_url}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
        page.wait_for_timeout(3000)

        for pg in range(max_pages):
            text, url = _read_page(page)
            is_results, reason = _is_results_page(text, site)
            print(f"[agent] Page {pg+1}/{max_pages} | {reason}")

            if not is_results:
                print("[agent] Not a results page — stopping")
                break

            # Scroll to trigger lazy-loaded product cards
            for _ in range(3):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(600)
            text, url = _read_page(page)

            # Detect stuck pagination
            if text == last_text:
                print("[agent] Page content identical to previous — stopping")
                break
            last_text = text

            records = _extract(text, user_request, url)
            if records:
                all_records.extend(records)
                pages_visited += 1
                print(f"[agent] Page {pages_visited}: {len(records)} records (total: {len(all_records)})")
            else:
                print(f"[agent] No records on page {pg+1} — stopping")
                break

            if pg < max_pages - 1:
                if not _next_page(page):
                    print("[agent] No next page")
                    break
                page.wait_for_timeout(2500)

        browser.close()

    # Deduplicate by name + price
    seen, unique = set(), []
    for r in all_records:
        k = f"{r.get('name','')}-{r.get('price','')}"
        if k not in seen:
            seen.add(k); unique.append(r)

    print(f"\n[agent] Done: {len(unique)} unique records from {pages_visited} pages")
    return {
        "records":       unique,
        "pages_visited": pages_visited,
        "summary":       f"Collected {len(unique)} records from {pages_visited} page(s) — {site}",
    }
'''

# ============================================================
#  browser_agent.py  —  Agentic scraper
#  Supports: Amazon (amazon.in) and Flipkart (flipkart.com)
# ============================================================
import json, re, urllib.parse, sys
from llm_client import call_llm
from config import REQUEST_TIMEOUT

# Fix Windows charmap error for special characters like ₹
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


NEXT_PAGE_SELECTORS = [
    "a[aria-label='Next']",
    "a[aria-label='next page' i]",
    "a:has-text('Next')",
    "a:has-text('›')",
    "a:has-text('»')",
    "[class*='next' i][href]",
    ".pagination a:last-child",
]


# ──────────────────────────────────────────────────────────
#  SITE DETECTION
# ──────────────────────────────────────────────────────────

def _detect_site(url: str) -> str:
    if "flipkart.com" in url: return "flipkart"
    if "amazon.in"   in url: return "amazon"
    return "unknown"


# ──────────────────────────────────────────────────────────
#  NAVIGATION PLANNER
# ──────────────────────────────────────────────────────────

FLIPKART_URL_GUIDE = """
Flipkart search URL structure:
  Base:  https://www.flipkart.com/search?q=KEYWORD
  Price: append &p%5B%5D=facets.price_range.from%3DMIN&p%5B%5D=facets.price_range.to%3DMAX

  Rules for price range:
  - "under X"         → MIN=500,  MAX=X
  - "above X"         → MIN=X,    MAX=500000
  - "between X and Y" → MIN=X,    MAX=Y
  - no price          → omit price params entirely
  - MIN must always be less than MAX

  Rules for keyword:
  - Use product terms only — no price words
  - e.g. "smartphones under 20000" → keyword = "smartphone"

Return ONLY JSON: {"keyword": "...", "url": "https://..."}
"""

AMAZON_URL_GUIDE = """
Amazon India search URL structure:
  Base:  https://www.amazon.in/s?k=KEYWORD&i=electronics
  Price: append &low-price=MIN&high-price=MAX  (plain rupees)
  Sort:  append &s=price-asc-rank

  Rules for price range:
  - "under X"         → low-price=100, high-price=X
    IMPORTANT: low-price must ALWAYS be less than high-price
    e.g. "under 500"  → low-price=100, high-price=500
    e.g. "under 2000" → low-price=100, high-price=2000
  - "above X"         → low-price=X,   high-price=500000
  - "between X and Y" → low-price=X,   high-price=Y
  - no price          → omit price params, just use base URL

  Rules for keyword:
  - Product terms only — no price words in keyword
  - e.g. "wireless earphones under 2000" → keyword = "wireless earphones"

Return ONLY JSON: {"keyword": "...", "url": "https://..."}
"""


def _plan_navigation(user_request: str, site: str) -> str | None:
    guide = FLIPKART_URL_GUIDE if site == "flipkart" else AMAZON_URL_GUIDE
    result = call_llm(f'User wants: "{user_request}"\n\n{guide}')
    if result and "url" in result:
        print(f"  [nav] planned URL: {result['url']}")
        return result["url"]
    return None


# ──────────────────────────────────────────────────────────
#  PAGE READER  —  targets product cards specifically
# ──────────────────────────────────────────────────────────

def _read_page(page) -> tuple[str, str]:
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except:
        pass
    try:
        # Amazon: target product card elements directly
        text = page.evaluate(
            "() => { var cards = document.querySelectorAll('[data-component-type=\\'s-search-result\\']');"
            " if (cards.length > 0) { return Array.from(cards).map(function(c){return c.innerText;}).join(' --- '); }"
            " return null; }"
        )
        if not text or len(text.strip()) < 200:
            # Flipkart: target product card divs
            text = page.evaluate(
                "() => { var cards = document.querySelectorAll('div[data-id]');"
                " if (cards.length > 5) { return Array.from(cards).map(function(c){return c.innerText;}).join(' --- '); }"
                " return null; }"
            )
        if not text or len(text.strip()) < 200:
            # Fallback: full body text minus noise
            text = page.evaluate(
                "() => { var noise = document.querySelectorAll('script,style,noscript,iframe,nav,header,footer');"
                " noise.forEach(function(e){e.remove();});"
                " return document.body.innerText; }"
            )
        text = (text or "").strip()
        print(f"  [page] {len(text)} chars | {text[:120].strip()!r}")
        return text[:8000], page.url
    except Exception as e:
        print(f"  [page] ERROR: {e}")
        return "", page.url


# ──────────────────────────────────────────────────────────
#  PAGE QUALITY CHECK
# ──────────────────────────────────────────────────────────

def _is_results_page(text: str, site: str) -> tuple[bool, str]:
    t = text.lower()
    char_count = len(text.strip())

    if char_count < 500:
        return False, f"too short ({char_count} chars) — page blocked or empty"

    # Genuine no-results (ignore keyboard shortcut "Results" text on Amazon)
    if ("no results for" in t or "didn't match any products" in t) \
            and "keyboard shortcuts" not in t[:500]:
        return False, "no results found for this query"

    if site == "flipkart":
        signals = ["add to cart", "buy now", "₹", "rating", "off", "sponsored"]
        found = [s for s in signals if s in t]
        if len(found) >= 2:
            return True, f"flipkart listings detected {found[:3]}"

    if site == "amazon":
        signals = ["add to cart", "sponsored", "₹", "out of stock", "results for", "delivery"]
        found = [s for s in signals if s in t]
        if len(found) >= 2:
            return True, f"amazon listings detected {found[:3]}"

    if char_count > 3000:
        return True, f"substantial page ({char_count} chars) — attempting extract"

    return False, f"unclear page ({char_count} chars)"


# ──────────────────────────────────────────────────────────
#  EXTRACTOR
# ──────────────────────────────────────────────────────────

def _extract(page_text: str, user_request: str, url: str) -> list:
    if len(page_text.strip()) < 200:
        print("  [extract] page too short, skipping")
        return []

    num_cards = page_text.count("---") + 1
    print(f"  [extract] reading ~{num_cards} product cards")

    # Tell LLM expected price range from URL so it doesn't confuse filter params with prices
    url_low  = re.search(r'low-price=(\d+)',  url)
    url_high = re.search(r'high-price=(\d+)', url)
    url_low_val  = int(url_low.group(1))  if url_low  else 0
    url_high_val = int(url_high.group(1)) if url_high else 999999

    price_hint = ""
    if url_low and url_high:
        price_hint = (
            f"NOTE: Products on this page are priced between "
            f"₹{url_low_val} and ₹{url_high_val}. "
            f"Extract the ACTUAL price shown on each card — "
            f"NOT the URL filter values ({url_low_val} and {url_high_val} are filters, not prices)."
        )

    result = call_llm(f"""
Extract ALL product listings from this page matching: "{user_request}"

{price_hint}

Return ONLY this JSON — no explanation, no markdown:
{{"records":[{{
  "name": "full product name",
  "brand": "brand name from product name",
  "price": "actual selling price as integer e.g. 1299",
  "original_price": "MRP/crossed-out price if shown, else empty",
  "discount_pct": "discount % if shown e.g. 25, else empty",
  "rating": "star rating e.g. 4.3, else empty",
  "review_count": "number of reviews e.g. 1243, else empty",
  "sponsored": "yes if Sponsored label shown, else no",
  "in_stock": "yes if Add to Cart visible, no if Out of Stock, else yes",
  "delivery_days": "delivery days if shown, else empty",
  "specs": "all visible specs: connectivity, playtime, RAM, battery etc.",
  "category": "product category"
}}]}}

RULES:
- price = ACTUAL price on the card (e.g. ₹1,299 → 1299). Never use URL filter values as price.
- brand = first recognizable word from product name (boAt, JBL, Sony, Samsung etc.)
- Prices like 149900 are paise → divide by 100 → 1499
- Empty string "" for any missing field
- Extract ALL {num_cards} product cards
- {{"records":[]}} only if truly no products visible

PAGE URL: {url}
PAGE CONTENT:
{page_text[:6000]}
""")

    records = (result or {}).get("records", [])

    # ── Post-processing: fix prices, brand, paise ──────────
    cleaned = []
    for r in records:
        # Fix price
        try:
            p = int(str(r.get("price","0")).replace(",","").replace("₹","").strip())
            if p > 100000:           # paise → rupees
                p = p // 100
            if p == url_low_val:     # price equals filter param = wrong, skip record
                continue
            r["price"] = str(p) if p > 0 else ""
        except:
            r["price"] = ""

        # Fix original_price paise
        try:
            op = int(str(r.get("original_price","0")).replace(",","").replace("₹","").strip())
            if op > 100000:
                r["original_price"] = str(op // 100)
        except:
            pass

        # Recalculate discount_pct if missing
        try:
            if not r.get("discount_pct") and r.get("price") and r.get("original_price"):
                p  = float(r["price"])
                op = float(r["original_price"])
                if op > p > 0:
                    r["discount_pct"] = str(round((op - p) / op * 100, 1))
        except:
            pass

        # Auto-extract brand from name if missing
        if not r.get("brand") and r.get("name"):
            words = str(r["name"]).split()
            if words and len(words[0]) > 1 and words[0][0].isupper():
                r["brand"] = words[0]

        # Only keep records with a valid price
        if r.get("price","").strip() not in ("", "0"):
            cleaned.append(r)

    print(f"  [extract] {len(cleaned)} records")
    return cleaned


# ──────────────────────────────────────────────────────────
#  PAGINATION
# ──────────────────────────────────────────────────────────

def _next_page(page) -> bool:
    url_before = page.url

    # Amazon: append &page=N directly — more reliable than clicking Next
    if "amazon.in" in url_before:
        match = re.search(r'[?&]page=(\d+)', url_before)
        current = int(match.group(1)) if match else 1
        next_num = current + 1
        if match:
            next_url = url_before.replace(f"page={current}", f"page={next_num}")
        else:
            sep = "&" if "?" in url_before else "?"
            next_url = url_before + sep + f"page={next_num}"
        print(f"  [next] amazon page {next_num}")
        page.goto(next_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
        page.wait_for_timeout(3000)
        return page.url != url_before

    # Flipkart: click Next button
    for sel in NEXT_PAGE_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(3000)
                if page.url != url_before:
                    print(f"  [next] {sel}")
                    return True
                else:
                    print("  [next] URL unchanged — no more pages")
                    return False
        except:
            continue
    return False


# ──────────────────────────────────────────────────────────
#  CACHE CLEANUP
# ──────────────────────────────────────────────────────────

def _clear_stale_cache():
    from llm_client import _cache, _save_cache
    stale = [k for k, v in _cache.items()
             if isinstance(json.loads(v).get("records"), list)
             and len(json.loads(v)["records"]) == 0]
    for k in stale: del _cache[k]
    if stale:
        _save_cache(_cache)
        print(f"[agent] cleared {len(stale)} stale cache entries")


# ──────────────────────────────────────────────────────────
#  MAIN AGENT LOOP
# ──────────────────────────────────────────────────────────

def run_agent(start_url: str, user_request: str, max_pages: int = 10) -> dict:
    from playwright.sync_api import sync_playwright

    _clear_stale_cache()

    site = _detect_site(start_url)
    if site == "unknown":
        print("[agent] Unsupported site. Use amazon.in or flipkart.com.")
        return {"records": [], "pages_visited": 0, "summary": "Unsupported site."}

    print(f"\n[agent] Site:    {site}")
    print(f"[agent] Request: {user_request}")
    print(f"[agent] Pages:   {max_pages}\n")

    search_url = _plan_navigation(user_request, site)
    if not search_url:
        return {"records": [], "pages_visited": 0, "summary": "Navigation planning failed."}

    all_records  = []
    pages_visited = 0
    last_text    = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
        )
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.new_page()

        print(f"[agent] Navigating to: {search_url}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
        page.wait_for_timeout(3000)

        for pg in range(max_pages):
            text, url = _read_page(page)
            is_results, reason = _is_results_page(text, site)
            print(f"[agent] Page {pg+1}/{max_pages} | {reason}")

            if not is_results:
                print("[agent] Not a results page — stopping")
                break

            # Scroll to trigger lazy-loaded product cards
            for _ in range(3):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(600)
            text, url = _read_page(page)

            # Detect stuck pagination
            if text == last_text:
                print("[agent] Page content identical to previous — stopping")
                break
            last_text = text

            records = _extract(text, user_request, url)
            if records:
                all_records.extend(records)
                pages_visited += 1
                print(f"[agent] Page {pages_visited}: {len(records)} records (total: {len(all_records)})")
            else:
                print(f"[agent] No records on page {pg+1} — stopping")
                break

            if pg < max_pages - 1:
                if not _next_page(page):
                    print("[agent] No next page")
                    break
                page.wait_for_timeout(2500)

        browser.close()

    # Deduplicate by name + price
    seen, unique = set(), []
    for r in all_records:
        k = f"{r.get('name','')}-{r.get('price','')}"
        if k not in seen:
            seen.add(k); unique.append(r)

    print(f"\n[agent] Done: {len(unique)} unique records from {pages_visited} pages")
    return {
        "records":       unique,
        "pages_visited": pages_visited,
        "summary":       f"Collected {len(unique)} records from {pages_visited} page(s) — {site}",
    }