# ============================================================
#  web_scraper.py  —  Scrape a specific URL (you provide the URL)
#  Used when user already knows the exact page to scrape.
#  For automatic navigation from homepage → use browser_agent.py
# ============================================================
import json
from config import MAX_RETRIES
from llm_client import call_llm


def fetch_page(url: str) -> str | None:
    """Fetch page with Playwright (handles JS) and clean with trafilatura."""
    try:
        from playwright.sync_api import sync_playwright
        import trafilatura
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            page.goto(url, wait_until="networkidle", timeout=30_000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            html = page.content()
            browser.close()
        return trafilatura.extract(html, include_tables=True) or html[:8000]
    except ImportError:
        print("Install: pip install playwright trafilatura && playwright install chromium")
        return None
    except Exception as e:
        print(f"[fetch] {e}"); return None


def scrape(url: str, user_request: str) -> dict | None:
    """
    Full pipeline: fetch page → LLM plans columns → LLM extracts → validate → retry.
    Returns {"records": [...], "summary": "..."}
    """
    print(f"\n[scraper] {url}")
    page_text = fetch_page(url)
    if not page_text: return None

    # Step 1: plan what columns to extract
    plan = call_llm(f"""
You are a web data extraction planner.
Return ONLY a JSON object — no explanation:
{{"task_type":"structured","columns":["col1","col2"],"output_format":"csv"}}

User request: {user_request}
URL: {url}
Page snippet: {page_text[:1500]}
""")
    if not plan: print("[scraper] plan failed"); return None
    print(f"[scraper] plan: {plan}")

    # Step 2: extract with self-healing
    cols = plan.get("columns", [])
    template = ", ".join(f'"{c}":"value"' for c in cols)
    feedback = ""

    for attempt in range(1, MAX_RETRIES + 1):
        extra = f"\nPrevious attempt failed: {feedback}. Fix it." if feedback else ""
        result = call_llm(f"""
Extract ALL records from the page below.
Return ONLY JSON — no markdown:
{{"records":[{{{template}}}],"summary":"brief summary"}}

Rules: missing field → null | do NOT invent data
Columns: {", ".join(cols)}
PAGE TEXT:
{page_text[:6000]}{extra}
""")
        records = (result or {}).get("records", [])
        if records:
            print(f"[scraper] got {len(records)} records on attempt {attempt}")
            return result
        feedback = "empty records returned"
        print(f"[scraper] attempt {attempt} empty, retrying…")

    return None