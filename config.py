# ============================================================
#  config.py  —  EDIT THIS FILE FIRST before running anything
# ============================================================

# ── Get your FREE OpenRouter key (no credit card needed)
#    Sign up at: https://openrouter.ai → Keys → Create Key
OPENROUTER_API_KEY = "#insert your api key here"

# ── Free models to rotate through (all $0.00 per token)
#    If one hits a rate limit, the next one is tried automatically
'''OPENROUTER_FREE_MODELS = [
    "openai/gpt-4o-mini"
    "openrouter/free"                              # primary — OpenRouter auto-picks best free model
   # "meta-llama/llama-3.3-70b-instruct:free"       # backup 1
   # "google/gemini-2.0-flash-exp:free"
   #"stepfun/step-3.5-flash:free" 
   #"arcee-ai/trinity-large-preview:free"
                # backup 2
]'''

OPENROUTER_FREE_MODELS = [
  "stepfun/step-3.5-flash:free"
   # "arcee-ai/trinity-large-preview:free",
    #"z-ai/glm-4.5-air:free",
    #"nvidia/nemotron-3-nano-30b-a3b:free",
    #"arcee-ai/trinity-mini:free",
    #"nvidia/nemotron-nano-9b-v2:free",
    #"openrouter/free"
   #"qwen/qwen3-next-80b-a3b-instruct:free"
]

# ── File paths (don't change these)
OCR_FOLDER  = "data/ocr"            # put your .txt OCR files here
OUTPUT_FILE = "data/output.csv"     # final ML-ready CSV
CACHE_FILE  = "data/cache.json"     # data-level cache
EXCEL_PATH  = "data/reference.xlsx" # column schema for medical mode

# ── Scraper settings
MAX_RETRIES     = 5    # self-healing retry attempts
REQUEST_TIMEOUT = 30   # seconds per page load
'''OPENROUTER_API_KEY = ""
OPENROUTER_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "arcee-ai/trinity-mini:free",
]
# Input / output
PATIENTS_DIR = "data/patients"
OUTPUT_CSV = "data/output_patients.csv"
OUTPUT_XLSX = "data/output_patients.xlsx"
CACHE_FILE = "data/prompt_cache.json"

# API behaviour
REQUEST_TIMEOUT = 90
MAX_RETRIES_PER_MODEL = 3
BASE_BACKOFF_SECONDS = 4
MAX_BACKOFF_SECONDS = 60
GLOBAL_COOLDOWN_SECONDS = 2
PATIENT_COOLDOWN_SECONDS = 5

# Extraction behaviour
# Keep chunks moderate. Bigger is not always better because long noisy OCR text
# increases hallucination and can exceed context limits.
CHUNK_SIZE = 18000

# If very large patient folders exist, stop after this many chars per chunk.
# We do keyword-focused second pass later for missing fields.
SECOND_PASS_SNIPPET_WINDOW = 220

# Resume rule
MIN_FILLED_FIELDS_TO_SKIP = 25

# Value used for missing information everywhere
MISSING_VALUE = "Not documented"
'''
'''
# ============================================================
#  config.py  —  EDIT THIS FILE FIRST before running anything
# ============================================================

# ── Get your FREE OpenRouter key (no credit card needed)
#    Sign up at: https://openrouter.ai → Keys → Create Key
OPENROUTER_API_KEY = ""

# ── Free models to rotate through (all $0.00 per token)
#    If one hits a rate limit, the next one is tried automatically
OPENROUTER_FREE_MODELS = [
   # "mistralai/mistral-7b-instruct:free",
    #"google/gemma-2-9b-it:free",
    #"meta-llama/llama-3.1-8b-instruct:free",
    #"openchat/openchat-7b:free",
    "openai/gpt-5.4-pro"
]
 
# ── File paths (don't change these)
OCR_FOLDER  = "data/ocr"            # put your .txt OCR files here
OUTPUT_FILE = "data/output.csv"     # final ML-ready CSV
CACHE_FILE  = "data/cache.json"     # data-level cache
EXCEL_PATH  = "data/reference.xlsx" # column schema for medical mode
 
# ── Scraper settings
MAX_RETRIES     = 5    # self-healing retry attempts
REQUEST_TIMEOUT = 30   # seconds per page load

'''
'''      
# ============================================================
#  config.py  —  EDIT THIS FILE FIRST before running anything
# ============================================================

# ── Groq API Key (free, no credit card, 100 req/min)
#    Sign up at: https://console.groq.com → API Keys → Create
GROQ_API_KEY = ""

# ── Groq models (best for structured JSON extraction)
#    These are free on Groq with very high rate limits
GROQ_MODELS = [
    "llama-3.3-70b-versatile",   # PRIMARY — best quality, 100 req/min
    "openai/gpt-oss-120b"           # backup 1 — slightly older but very stable
   # "mixtral-8x7b-32768",        # backup 2 — good at following JSON instructions - not found in groq
   # "gemma2-9b-it"              # backup 3 — fast and lightweight - not found in groq
]

# ── File paths (don't change these)
OCR_FOLDER  = "data/ocr"
OUTPUT_FILE = "data/output.csv"
CACHE_FILE  = "data/cache.json"
EXCEL_PATH  = "data/reference.xlsx"

# ── Scraper settings
MAX_RETRIES     = 5
REQUEST_TIMEOUT = 30
'''
'''
# ============================================================
#  config.py  —  EDIT THIS FILE FIRST before running anything
# ============================================================

# ── Groq API Key (free, no credit card, 100 req/min)
#    Sign up at: https://console.groq.com → API Keys → Create
GROQ_API_KEY = ""

# ── Groq free models — verified working as of March 2026
#    All free, no billing needed
GROQ_MODELS = [
    "groq/compound-mini"
    # "llama-3.3-70b-versatile" # PRIMARY — best quality, 128k context, 100 req/min
               # BACKUP 1 — very stable, 8k context       # BACKUP 2 — 32k context, great for long documents              # BACKUP 3 — fast, lightweight fallback
]

# ── File paths (don't change these)
OCR_FOLDER  = "data/ocr"
OUTPUT_FILE = "data/output.csv"
CACHE_FILE  = "data/cache.json"
EXCEL_PATH  = "data/reference.xlsx"

# ── Scraper settings
MAX_RETRIES     = 5
REQUEST_TIMEOUT = 30
'''