'''
import sys, io
# Fix Windows charmap error for ₹ and other special characters
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
# ============================================================
#  main.py  —  Run from terminal. Three modes:
#
#  1. python main.py medical
#     Reads .txt files from data/ocr/, extracts clinical data → CSV
#
#  2. python main.py web "https://books.toscrape.com" "get book titles and prices"
#     Scrapes a SPECIFIC URL you provide → CSV
#
#  3. python main.py agent "https://www.flipkart.com" "find laptops under 50000"
#     Starts from homepage, AI navigates automatically → CSV
# ============================================================
import os, argparse
import pandas as pd

from config import OCR_FOLDER, OUTPUT_FILE
from utils import load_cache, save_cache, get_hash
from rules import apply_rules
from validator import validate
from medical_extractor import extract_medical
from web_scraper import scrape
from browser_agent import run_agent


def run_medical():
    cache, rows = load_cache(), []
    files = [f for f in os.listdir(OCR_FOLDER) if f.endswith(".txt")]
    if not files:
        print(f"No .txt files found in {OCR_FOLDER}/"); return

    for file in files:
        path = os.path.join(OCR_FOLDER, file)
        with open(path, encoding="utf-8") as f: text = f.read()
        key = get_hash(text)

        if key in cache:
            print(f"[CACHE]      {file}"); data = cache[key]
        else:
            print(f"[PROCESSING] {file}"); data = extract_medical(text)
            if data is None: print(f"[FAILED]     {file}"); continue
            cache[key] = data; save_cache(cache)

        rows.append(validate(apply_rules(data)))
    _save(rows)


def run_web(url, request, fmt):
    result = scrape(url, request)
    if not result: print("Scraping failed."); return
    if result.get("summary"): print(f"\nSummary: {result['summary']}\n")
    _save(result.get("records", []), fmt)


def run_agent_mode(url, request, fmt, max_steps):
    # Simple: one prompt → scrape many pages → one CSV
    # Default max_steps=10 pages × ~20 records = ~200 records per run
    result = run_agent(url, request, max_pages=max_steps)
    if result.get("summary"): print(f"\nSummary: {result['summary']}\n")
    _save(result.get("records", []), fmt)


def _save(rows, fmt="csv"):
    if not rows: print("No records to save."); return
    df = pd.DataFrame(rows)
    base = os.path.splitext(OUTPUT_FILE)[0]
    paths = {"json": base+".json", "xlsx": base+".xlsx", "csv": OUTPUT_FILE}
    path = paths.get(fmt, OUTPUT_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # If file is locked (e.g. open in Excel), save with timestamp instead
    try:
        if fmt == "json":   df.to_json(path, orient="records", indent=2)
        elif fmt == "xlsx": df.to_excel(path, index=False)
        else:               df.to_csv(path, index=False)
    except (PermissionError, OSError):
        from datetime import datetime
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"{base}_{ts}.{fmt}"
        print(f"⚠️  File locked — saving to {path} instead")
        if fmt == "json":   df.to_json(path, orient="records", indent=2)
        elif fmt == "xlsx": df.to_excel(path, index=False)
        else:               df.to_csv(path, index=False)

    print(f"\n✅ {len(rows)} records saved → {path}")
    print(df.head(3).to_string())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="AI Data Extraction — 3 modes")
    s = p.add_subparsers(dest="mode", required=True)

    s.add_parser("medical", help="Extract from OCR .txt files in data/ocr/")

    wp = s.add_parser("web", help="Scrape a specific URL")
    wp.add_argument("url");    wp.add_argument("request")
    wp.add_argument("--format", default="csv", choices=["csv","json","xlsx"])

    ap = s.add_parser("agent", help="Scrape Amazon or Flipkart with AI")
    ap.add_argument("url",     help="https://www.flipkart.com or https://www.amazon.in")
    ap.add_argument("request", help="What to scrape e.g. 'wireless earphones under 2000'")
    ap.add_argument("--pages",  default=10, type=int, help="Number of pages to scrape (default: 10, each page ~20 records)")
    ap.add_argument("--format", default="csv", choices=["csv","json","xlsx"])

    args = p.parse_args()
    if args.mode == "medical": run_medical()
    elif args.mode == "web":   run_web(args.url, args.request, args.format)
    elif args.mode == "agent": run_agent_mode(args.url, args.request, args.format, args.pages)
'''

# ============================================================
#  main.py  —  Run from terminal. Three modes:
#
#  1. python main.py medical
#     Reads .txt files from data/ocr/, extracts clinical data → CSV
#
#  2. python main.py web "https://books.toscrape.com" "get book titles and prices"
#     Scrapes a SPECIFIC URL you provide → CSV
#
#  3. python main.py agent "https://www.flipkart.com" "find laptops under 50000"
#     Starts from homepage, AI navigates automatically → CSV
# ============================================================
import os, argparse
import pandas as pd

from config import OCR_FOLDER, OUTPUT_FILE
from utils import load_cache, save_cache, get_hash
from rules import apply_rules
from validator import validate
from medical_extractor import extract_medical
from web_scraper import scrape
from browser_agent import run_agent


def run_medical():
    cache, rows = load_cache(), []
    files = [f for f in os.listdir(OCR_FOLDER) if f.endswith(".txt")]
    if not files:
        print(f"No .txt files found in {OCR_FOLDER}/"); return

    for file in files:
        path = os.path.join(OCR_FOLDER, file)
        with open(path, encoding="utf-8") as f: text = f.read()
        key = get_hash(text)

        if key in cache:
            print(f"[CACHE]      {file}"); data = cache[key]
        else:
            print(f"[PROCESSING] {file}"); data = extract_medical(text)
            if data is None: print(f"[FAILED]     {file}"); continue
            cache[key] = data; save_cache(cache)

        rows.append(validate(apply_rules(data)))
    _save(rows)


def run_web(url, request, fmt):
    result = scrape(url, request)
    if not result: print("Scraping failed."); return
    if result.get("summary"): print(f"\nSummary: {result['summary']}\n")
    _save(result.get("records", []), fmt)


def run_agent_mode(url, request, fmt, max_steps):
    # Simple: one prompt → scrape many pages → one CSV
    # Default max_steps=10 pages × ~20 records = ~200 records per run
    result = run_agent(url, request, max_pages=max_steps)
    if result.get("summary"): print(f"\nSummary: {result['summary']}\n")
    _save(result.get("records", []), fmt)


def _save(rows, fmt="csv"):
    if not rows: print("No records to save."); return
    df = pd.DataFrame(rows)
    base = os.path.splitext(OUTPUT_FILE)[0]
    paths = {"json": base+".json", "xlsx": base+".xlsx", "csv": OUTPUT_FILE}
    path = paths.get(fmt, OUTPUT_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # If file is locked (e.g. open in Excel), save with timestamp instead
    try:
        if fmt == "json":   df.to_json(path, orient="records", indent=2)
        elif fmt == "xlsx": df.to_excel(path, index=False)
        else:               df.to_csv(path, index=False)
    except (PermissionError, OSError):
        from datetime import datetime
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"{base}_{ts}.{fmt}"
        print(f"⚠️  File locked — saving to {path} instead")
        if fmt == "json":   df.to_json(path, orient="records", indent=2)
        elif fmt == "xlsx": df.to_excel(path, index=False)
        else:               df.to_csv(path, index=False)

    print(f"\n✅ {len(rows)} records saved → {path}")
    print(df.head(3).to_string())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="AI Data Extraction — 3 modes")
    s = p.add_subparsers(dest="mode", required=True)

    s.add_parser("medical", help="Extract from OCR .txt files in data/ocr/")

    wp = s.add_parser("web", help="Scrape a specific URL")
    wp.add_argument("url");    wp.add_argument("request")
    wp.add_argument("--format", default="csv", choices=["csv","json","xlsx"])

    ap = s.add_parser("agent", help="Scrape Amazon or Flipkart with AI")
    ap.add_argument("url",     help="https://www.flipkart.com or https://www.amazon.in")
    ap.add_argument("request", help="What to scrape e.g. 'wireless earphones under 2000'")
    ap.add_argument("--pages",  default=10, type=int, help="Number of pages to scrape (default: 10, each page ~20 records)")
    ap.add_argument("--format", default="csv", choices=["csv","json","xlsx"])

    args = p.parse_args()
    if args.mode == "medical": run_medical()
    elif args.mode == "web":   run_web(args.url, args.request, args.format)
    elif args.mode == "agent": run_agent_mode(args.url, args.request, args.format, args.pages)