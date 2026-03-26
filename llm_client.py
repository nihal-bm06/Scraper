# ============================================================
#  llm_client.py  —  Calls OpenRouter free models with caching
#  Rotates through free models automatically on rate limit.
#  Caches responses by prompt hash — never wastes a request.
#  FIX: empty results are NOT cached (prevents cache poisoning)
# ============================================================
import json, time, hashlib, os, requests, re
from config import OPENROUTER_API_KEY, OPENROUTER_FREE_MODELS

_PROMPT_CACHE_FILE = "data/prompt_cache.json"

def _load_cache():
    if os.path.exists(_PROMPT_CACHE_FILE):
        try:
            with open(_PROMPT_CACHE_FILE) as f: return json.load(f)
        except: pass
    return {}

def _save_cache(c):
    os.makedirs("data", exist_ok=True)
    with open(_PROMPT_CACHE_FILE, "w") as f: json.dump(c, f)

_cache = _load_cache()


def _call_openrouter(prompt: str) -> str | None:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "AI Web Scraper",
    }
    for model in OPENROUTER_FREE_MODELS:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={"model": model, "messages": [{"role":"user","content":prompt}], "temperature":0.1},
                headers=headers, timeout=120  # increased — large extraction prompts need more time
            )
            if r.status_code == 429:
                print(f"  [OR] rate limit on {model}, waiting 5s…"); time.sleep(5); continue
            if r.status_code in (400, 404):
                print(f"  [OR] {r.status_code} on {model} — model unavailable, trying next…"); continue
            r.raise_for_status()
            print(f"  [LLM] ok: {model}")
            return r.json()["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            print(f"  [OR] timeout on {model}, trying next…"); continue
        except Exception as e:
            print(f"  [LLM] {model}: {e}"); continue
    return None


def call_llm(prompt: str) -> dict | None:
    """Call LLM with prompt cache + model rotation. Returns parsed JSON dict."""
    key = hashlib.md5(prompt.encode()).hexdigest()

    # Cache hit — skip API call
    if key in _cache:
        print("  [LLM] cache hit")
        try: return json.loads(_cache[key])
        except: pass

    raw = _call_openrouter(prompt)
    if not raw:
        print("[LLM] all models failed"); return None

    # Strip markdown fences
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if not cleaned.startswith(("{","[")):
        m = re.search(r'(\{.*\}|\[.*\])', cleaned, re.DOTALL)
        if m: cleaned = m.group(1)

    try:
        parsed = json.loads(cleaned)

        # ── FIX: Never cache empty records — prevents cache poisoning ──
        # If records key exists but is empty, it means the page had no data.
        # Caching this would make every future call return empty too.
        records = parsed.get("records", None)
        if isinstance(records, list) and len(records) == 0:
            print("  [LLM] empty result — not caching")
            return parsed

        _cache[key] = json.dumps(parsed)
        _save_cache(_cache)
        return parsed
    except Exception as e:
        print(f"[LLM] JSON parse error: {e}\nRaw: {cleaned[:200]}")
        return None
'''
import hashlib
import json
import os
import time
from typing import Any

import requests

from config import (
    BASE_BACKOFF_SECONDS,
    CACHE_FILE,
    GLOBAL_COOLDOWN_SECONDS,
    MAX_BACKOFF_SECONDS,
    MAX_RETRIES_PER_MODEL,
    MISSING_VALUE,
    OPENROUTER_API_KEY,
    OPENROUTER_MODELS,
    REQUEST_TIMEOUT,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_session = requests.Session()
_last_call_ts = 0.0


def _ensure_data_dir() -> None:
    os.makedirs(os.path.dirname(CACHE_FILE) or ".", exist_ok=True)


def _load_cache() -> dict[str, Any]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    _ensure_data_dir()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


_cache = _load_cache()


def _cooldown() -> None:
    global _last_call_ts
    elapsed = time.time() - _last_call_ts
    if elapsed < GLOBAL_COOLDOWN_SECONDS:
        time.sleep(GLOBAL_COOLDOWN_SECONDS - elapsed)
    _last_call_ts = time.time()


def _extract_first_json_blob(text: str) -> Any | None:
    if not text:
        return None

    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(cleaned):
        if ch not in "[{":
            continue
        try:
            obj, _ = decoder.raw_decode(cleaned[idx:])
            return obj
        except json.JSONDecodeError:
            continue
    return None


def _normalize_payload(obj: Any, expected_keys: list[str] | None) -> dict[str, Any] | None:
    if obj is None:
        return None

    if isinstance(obj, dict):
        data = dict(obj)
    else:
        return None

    if expected_keys:
        normalized = {}
        for key in expected_keys:
            val = data.get(key, MISSING_VALUE)
            normalized[key] = val if val not in (None, "", [], {}) else MISSING_VALUE
        return normalized

    return data


def _request_model(model: str, prompt: str, max_tokens: int = 1400) -> str | None:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is missing. Set it in your environment or config.py first."
        )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "Medical OCR Extractor",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict medical OCR data extraction assistant. "
                    "Return JSON only. Never guess. If missing, use 'Not documented'."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }

    _cooldown()
    response = _session.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code in (429, 500, 502, 503, 504):
        raise requests.HTTPError(f"retryable_status:{response.status_code}", response=response)
    if response.status_code in (400, 401, 402, 403, 404):
        raise RuntimeError(f"non_retryable_status:{response.status_code} body={response.text[:400]}")

    response.raise_for_status()
    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"Unexpected API payload: {str(data)[:500]}") from exc


def call_llm_json(prompt: str, expected_keys: list[str] | None = None) -> dict[str, Any] | None:
    """
    Calls OpenRouter with cache + retries + model rotation.
    Returns a dict or None.
    """
    cache_key = hashlib.sha256(
        json.dumps({"prompt": prompt, "expected_keys": expected_keys}, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    cached = _cache.get(cache_key)
    if cached is not None:
        parsed = _normalize_payload(cached, expected_keys)
        if parsed is not None:
            print("  [LLM] cache hit")
            return parsed

    for model in OPENROUTER_MODELS:
        for attempt in range(1, MAX_RETRIES_PER_MODEL + 1):
            try:
                raw = _request_model(model, prompt)
                parsed = _normalize_payload(_extract_first_json_blob(raw or ""), expected_keys)
                if parsed is None:
                    print(f"  [LLM] {model} returned non-JSON content")
                    continue

                _cache[cache_key] = parsed
                _save_cache(_cache)
                print(f"  [LLM] ok: {model}")
                return parsed
            except requests.HTTPError as exc:
                msg = str(exc)
                if "retryable_status:" in msg:
                    code = msg.split(":", 1)[1]
                    sleep_s = min(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)
                    print(f"  [LLM] {model} hit {code}; retry {attempt}/{MAX_RETRIES_PER_MODEL} after {sleep_s}s")
                    time.sleep(sleep_s)
                    continue
                print(f"  [LLM] {model} http error: {exc}")
                break
            except requests.Timeout:
                sleep_s = min(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)
                print(f"  [LLM] {model} timeout; retry {attempt}/{MAX_RETRIES_PER_MODEL} after {sleep_s}s")
                time.sleep(sleep_s)
            except Exception as exc:
                print(f"  [LLM] {model} failed: {exc}")
                break

    print("  [LLM] all models failed")
    return None
'''
'''
# ============================================================
#  llm_client.py  —  OpenRouter API with multi-key + multi-model rotation
#
#  Strategy to avoid rate limits:
#  1. Rotate through multiple API keys (add more keys to config.py)
#  2. Rotate through multiple free models per key
#  3. Cache every response — same prompt = zero API calls
#  4. Wait intelligently on 429 before retrying
# ============================================================
import json, time, hashlib, os, requests, re, sys, io

# Fix Windows charmap error for special characters like Rs symbol
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import OPENROUTER_API_KEYS, OPENROUTER_FREE_MODELS

_PROMPT_CACHE_FILE = "data/prompt_cache.json"

def _load_cache():
    if os.path.exists(_PROMPT_CACHE_FILE):
        try:
            with open(_PROMPT_CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def _save_cache(c):
    os.makedirs("data", exist_ok=True)
    with open(_PROMPT_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)

_cache = _load_cache()


def _call_openrouter(prompt: str) -> str | None:
    """
    Try every (key, model) combination until one works.
    Rotates keys first, then models — maximizes chance of success.
    """
    # Round-robin rotation: spread across keys AND models evenly
    # (key1,model1), (key2,model2), (key3,model3),
    # (key1,model2), (key2,model3), (key3,model1), ...
    # This means if key1+model1 rate-limits, next try is key2+model2 (different key AND model)
    attempts = []
    n_keys   = len(OPENROUTER_API_KEYS)
    n_models = len(OPENROUTER_FREE_MODELS)
    seen = set()
    for offset in range(n_models):
        for ki in range(n_keys):
            key   = OPENROUTER_API_KEYS[ki]
            model = OPENROUTER_FREE_MODELS[(ki + offset) % n_models]
            if (key, model) not in seen:
                attempts.append((key, model))
                seen.add((key, model))

    for key, model in attempts:
        key_short = key[-8:]  # show last 8 chars for identification
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a precise data extraction assistant. "
                                "Always return valid JSON only. "
                                "Never hallucinate or invent data. "
                                "If information is not present in the source text, use empty string."
                            )
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0,
                    "max_tokens": 4096,
                },
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "X-Title": "AI Medical Scraper",
                },
                timeout=90
            )

            if r.status_code == 429:
                wait = int(r.headers.get("retry-after", 5))
                wait = max(wait, 3)  # minimum 3s wait
                print(f"  [OR] rate limit [{key_short}] {model} — waiting {wait}s…")
                time.sleep(wait)
                continue

            if r.status_code == 402:
                print(f"  [OR] daily limit [{key_short}] — trying next key…")
                continue

            if r.status_code == 401:
                print(f"  [OR] invalid key [{key_short}] — check config.py")
                continue

            if r.status_code in (400, 404):
                print(f"  [OR] {r.status_code} [{key_short}] {model} — model unavailable")
                continue

            r.raise_for_status()

            data = r.json()
            if "choices" not in data or not data["choices"]:
                print(f"  [OR] empty response [{key_short}] {model}")
                continue

            content = data["choices"][0].get("message", {}).get("content", "")
            if not content:
                print(f"  [OR] empty content [{key_short}] {model}")
                continue

            print(f"  [LLM] ok: {model} [{key_short}]")
            return content

        except (requests.exceptions.Timeout, TimeoutError):
            print(f"  [OR] timeout [{key_short}] {model} — trying next…")
            continue
        except requests.exceptions.ConnectionError as e:
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                print(f"  [OR] connection timeout [{key_short}] {model} — trying next…")
            else:
                print(f"  [OR] connection error [{key_short}] {model}: {str(e)[:80]}")
            continue
        except Exception as e:
            print(f"  [LLM] {model}: {str(e)[:100]}")
            continue

    print("[LLM] all keys and models failed")
    return None


def call_llm(prompt: str) -> dict | None:
    """Call LLM with caching + key/model rotation. Returns parsed JSON dict."""
    key = hashlib.md5(prompt.encode()).hexdigest()

    # Cache hit — zero API call
    if key in _cache:
        print("  [LLM] cache hit")
        try: return json.loads(_cache[key])
        except: pass

    raw = _call_openrouter(prompt)
    if not raw:
        return None

    # Strip markdown fences
    cleaned = raw.strip()
    cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    cleaned = cleaned.strip()

    # Extract JSON if buried in text
    if not cleaned.startswith(("{", "[")):
        m = re.search(r'(\{.*\}|\[.*\])', cleaned, re.DOTALL)
        if m: cleaned = m.group(1)

    try:
        parsed = json.loads(cleaned)

        # Never cache empty records — prevents cache poisoning
        records = parsed.get("records", None)
        if isinstance(records, list) and len(records) == 0:
            print("  [LLM] empty result — not caching")
            return parsed

        _cache[key] = json.dumps(parsed, ensure_ascii=False)
        _save_cache(_cache)
        return parsed

    except Exception as e:
        print(f"[LLM] JSON parse error: {e}\nRaw: {cleaned[:300]}")
        return None
'''
'''
# ============================================================
#  llm_client.py  —  Groq API with caching + model rotation
#  Groq free tier: 100 requests/min, 14400 req/day
#  Much higher limits than OpenRouter free tier
# ============================================================
import json, time, hashlib, os, requests, re
from config import GROQ_API_KEY, GROQ_MODELS

_PROMPT_CACHE_FILE = "data/prompt_cache.json"

def _load_cache():
    if os.path.exists(_PROMPT_CACHE_FILE):
        try:
            with open(_PROMPT_CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def _save_cache(c):
    os.makedirs("data", exist_ok=True)
    with open(_PROMPT_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)

_cache = _load_cache()


def _call_groq(prompt: str) -> str | None:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    for model in GROQ_MODELS:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a precise data extraction assistant. Always return valid JSON only. Never hallucinate or invent data. If information is not present in the source text, use empty string."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.0,
                    "max_tokens": 4096,
                },
                headers=headers,
                timeout=60
            )

            if r.status_code == 429:
                # Groq rate limit — check retry-after header
                retry_after = int(r.headers.get("retry-after", 10))
                print(f"  [Groq] rate limit on {model}, waiting {retry_after}s…")
                time.sleep(retry_after)
                continue

            if r.status_code == 400:
                err = r.json().get("error", {}).get("message", "")
                print(f"  [Groq] 400 on {model}: {err[:80]} — trying next…")
                continue

            if r.status_code == 401:
                print(f"  [Groq] 401 Unauthorized — check your GROQ_API_KEY in config.py")
                return None

            r.raise_for_status()

            data = r.json()
            if "choices" not in data or not data["choices"]:
                print(f"  [Groq] {model}: empty response"); continue

            content = data["choices"][0].get("message", {}).get("content", "")
            if not content:
                print(f"  [Groq] {model}: empty content"); continue

            print(f"  [LLM] ok: {model}")
            return content

        except requests.exceptions.Timeout:
            print(f"  [Groq] timeout on {model}, trying next…"); continue
        except Exception as e:
            print(f"  [LLM] {model}: {e}"); continue

    print("[LLM] all models failed")
    return None


def call_llm(prompt: str) -> dict | None:
    """Call Groq LLM with caching + model rotation. Returns parsed JSON dict."""
    key = hashlib.md5(prompt.encode()).hexdigest()

    # Cache hit — skip API call
    if key in _cache:
        print("  [LLM] cache hit")
        try: return json.loads(_cache[key])
        except: pass

    raw = _call_groq(prompt)
    if not raw:
        return None

    # Strip markdown fences
    cleaned = raw.strip()
    cleaned = re.sub(r'^```json\s*', '', cleaned)
    cleaned = re.sub(r'^```\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    cleaned = cleaned.strip()

    if not cleaned.startswith(("{", "[")):
        m = re.search(r'(\{.*\}|\[.*\])', cleaned, re.DOTALL)
        if m: cleaned = m.group(1)

    try:
        parsed = json.loads(cleaned)

        # Don't cache empty records
        records = parsed.get("records", None)
        if isinstance(records, list) and len(records) == 0:
            print("  [LLM] empty result — not caching")
            return parsed

        _cache[key] = json.dumps(parsed, ensure_ascii=False)
        _save_cache(_cache)
        return parsed

    except Exception as e:
        print(f"[LLM] JSON parse error: {e}\nRaw: {cleaned[:200]}")
        return None

'''
'''
# ============================================================
#  llm_client.py  —  Groq API with caching + smart rate limit handling
#  Groq free tier: 100 req/min, 14,400 req/day — much better than OpenRouter
# ============================================================
import json, time, hashlib, os, requests, re, random
from config import GROQ_API_KEY, GROQ_MODELS

_PROMPT_CACHE_FILE = "data/prompt_cache.json"

def _load_cache():
    if os.path.exists(_PROMPT_CACHE_FILE):
        try:
            with open(_PROMPT_CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def _save_cache(c):
    os.makedirs("data", exist_ok=True)
    with open(_PROMPT_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)

_cache = _load_cache()


def _call_groq(prompt: str, system: str = None, max_tokens: int = 4096) -> str | None:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    system_msg = system or (
        "You are a precise data extraction assistant. "
        "Always return valid JSON only. "
        "Never hallucinate or invent data. "
        "If information is not present in the source text, use empty string."
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user",   "content": prompt}
    ]

    for model in GROQ_MODELS:
        # Each model gets up to 3 attempts before moving to the next
        for attempt in range(3):
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json={
                        "model":       model,
                        "messages":    messages,
                        "temperature": 0.0,
                        "max_tokens":  max_tokens,
                    },
                    headers=headers,
                    timeout=120
                )

                # ── Rate limit: respect the retry-after header ──────────────
                if r.status_code == 429:
                    retry_after = int(r.headers.get("retry-after", 15))
                    # Add small jitter so parallel calls don't all retry at once
                    wait = retry_after + random.randint(1, 5)
                    print(f"  [Groq] rate limit on {model} — waiting {wait}s…")
                    time.sleep(wait)
                    continue   # retry SAME model after waiting

                # ── Model not available ──────────────────────────────────────
                if r.status_code in (400, 404):
                    err = ""
                    try:
                        err = r.json().get("error", {}).get("message", "")[:80]
                    except:
                        pass
                    print(f"  [Groq] {r.status_code} on {model}: {err} — trying next model…")
                    break   # move to next model

                # ── Auth error ───────────────────────────────────────────────
                if r.status_code == 401:
                    print("  [Groq] 401 Unauthorized — check GROQ_API_KEY in config.py")
                    return None

                r.raise_for_status()

                data = r.json()
                if not data.get("choices"):
                    print(f"  [Groq] {model}: empty response — trying next model…")
                    break

                content = data["choices"][0].get("message", {}).get("content", "").strip()
                if not content:
                    print(f"  [Groq] {model}: empty content — trying next model…")
                    break

                print(f"  [LLM] ok: {model}")
                return content

            except requests.exceptions.Timeout:
                print(f"  [Groq] timeout on {model} (attempt {attempt+1}) — retrying…")
                time.sleep(5)
                continue
            except requests.exceptions.ConnectionError:
                print(f"  [Groq] connection error on {model} — waiting 10s…")
                time.sleep(10)
                continue
            except Exception as e:
                print(f"  [LLM] {model}: {e}")
                break

    print("[LLM] all models failed")
    return None


def _clean_json(raw: str) -> str:
    """Strip markdown fences and extract JSON from raw LLM output."""
    cleaned = raw.strip()
    cleaned = re.sub(r'^```json\s*', '', cleaned)
    cleaned = re.sub(r'^```\s*',     '', cleaned)
    cleaned = re.sub(r'\s*```$',     '', cleaned)
    cleaned = cleaned.strip()

    # If response has text before the JSON, extract the JSON block
    if not cleaned.startswith(("{", "[")):
        m = re.search(r'(\{.*\}|\[.*\])', cleaned, re.DOTALL)
        if m:
            cleaned = m.group(1)

    return cleaned


def call_llm(prompt: str, system: str = None, max_tokens: int = 4096) -> dict | list | None:
    """
    Call Groq LLM with prompt caching + model rotation.
    Returns parsed JSON (dict or list), or None on failure.
    """
    key = hashlib.md5(prompt.encode()).hexdigest()

    # ── Cache hit ────────────────────────────────────────────────────────────
    if key in _cache:
        print("  [LLM] cache hit")
        try:
            return json.loads(_cache[key])
        except:
            pass

    raw = _call_groq(prompt, system=system, max_tokens=max_tokens)
    if not raw:
        return None

    cleaned = _clean_json(raw)

    try:
        parsed = json.loads(cleaned)

        # Don't cache empty record lists (scraping result, not medical)
        records = parsed.get("records", None) if isinstance(parsed, dict) else None
        if isinstance(records, list) and len(records) == 0:
            print("  [LLM] empty result — not caching")
            return parsed

        _cache[key] = json.dumps(parsed, ensure_ascii=False)
        _save_cache(_cache)
        return parsed

    except json.JSONDecodeError as e:
        print(f"[LLM] JSON parse error: {e}\nRaw: {cleaned[:300]}")
        return None


def call_llm_raw(prompt: str, system: str = None) -> str | None:
    """
    Call Groq and return raw text (not JSON).
    Used when you don't need structured output.
    No caching.
    """
    return _call_groq(prompt, system=system, max_tokens=2048)
'''