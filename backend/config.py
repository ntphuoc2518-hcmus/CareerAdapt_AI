"""CareerAdapt AI v5.0 - System Configuration & Environment Settings."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
# Real environment variables win, and tests never read a developer's .env file.
if "pytest" not in sys.modules:
    load_dotenv(BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR / "frontend"

# Application Settings
APP_NAME = "CareerAdapt AI"
APP_VERSION = "5.59.2"
DEBUG = os.getenv("CAREERADAPT_DEBUG", "False").lower() == "true"
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "127.0.0.1")
# Public address used in links sent by email (for example https://careeradapt.example.vn). Required in production.
PUBLIC_URL = os.getenv("CAREERADAPT_PUBLIC_URL", "").strip().rstrip("/")
# Comma-separated host names the server answers to in production (empty = no Host check).
ALLOWED_HOSTS = [item.strip() for item in os.getenv("CAREERADAPT_ALLOWED_HOSTS", "").split(",") if item.strip()]
# Reverse proxies allowed to set X-Forwarded-For, so rate limits see the real client address.
TRUSTED_PROXIES = os.getenv("CAREERADAPT_TRUSTED_PROXIES", "127.0.0.1").strip() or "127.0.0.1"

# LLM Integration Settings
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")  # 'mock', 'openai', 'gemini'
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20.0"))
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
AI_EMBEDDING_MODEL = os.getenv("AI_EMBEDDING_MODEL", "")

# Assistant limits
AI_CHAT_PER_MINUTE = int(os.getenv("AI_CHAT_PER_MINUTE", "8"))
AI_DAILY_TOKENS_PER_USER = int(os.getenv("AI_DAILY_TOKENS_PER_USER", "60000"))
AI_DAILY_TOKENS_TOTAL = int(os.getenv("AI_DAILY_TOKENS_TOTAL", "1000000"))
AI_MAX_TOOL_ROUNDS = int(os.getenv("AI_MAX_TOOL_ROUNDS", "4"))
AI_REQUEST_DEADLINE_SECONDS = float(os.getenv("AI_REQUEST_DEADLINE_SECONDS", "45"))
AI_CONTEXT_MESSAGES = int(os.getenv("AI_CONTEXT_MESSAGES", "12"))

# Business Rules Constants
TARGET_CAREER_DEFAULT = "DATA_ANALYST"
MIN_COVERAGE_FOR_READINESS = 0.80
CORE_SKILLS_REQUIRED = {"SQL", "DATA_QUALITY"}
DEFAULT_WEEKLY_HOURS = 4.0
DEFAULT_TIMELINE_WEEKS = 8
