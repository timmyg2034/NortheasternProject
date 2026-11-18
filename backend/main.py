"""FastAPI backend for Northeastern Men's Hockey Stats Explorer."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .engine import HockeyDatasets, ResponseCache, answer_question, build_llm, classify_api_error, load_datasets

DATA_DIR = Path(os.getenv("NU_DATA_DIR", Path(__file__).resolve().parent.parent))
load_dotenv(DATA_DIR / ".env")
RATE_LIMIT_MAX = int(os.getenv("CHAT_RATE_LIMIT_PER_MIN", "6"))
RATE_LIMIT_HOUR_MAX = int(os.getenv("CHAT_RATE_LIMIT_PER_HOUR", "40"))
RATE_LIMIT_DAY_MAX = int(os.getenv("CHAT_RATE_LIMIT_PER_DAY", "180"))
MAX_DAILY_LLM_CALLS = int(os.getenv("MAX_DAILY_LLM_CALLS", "1000"))
BUG_REPORTS_PATH = DATA_DIR / "bug_reports.jsonl"
_bug_report_lock = threading.Lock()

_BOT_UA_PATTERNS = (
    "curl/",
    "wget/",
    "python-requests",
    "python-urllib",
    "httpx",
    "aiohttp",
    "scrapy",
    "go-http-client",
    "java/",
    "okhttp",
    "postmanruntime",
    "insomnia",
    "headlesschrome",
    "puppeteer",
    "playwright",
    "selenium",
    "phantomjs",
)

HOCKEY_EAST_TEAMS = {
    "Boston College",
    "Boston University",
    "Connecticut",
    "Maine",
    "Massachusetts",
    "Massachusetts Lowell",
    "Merrimack",
    "New Hampshire",
    "Providence",
    "Vermont",
}


class RateLimiter:
    """Bounded in-memory sliding-window rate limiter keyed by client IP."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 60, max_keys: int = 4096) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self._window
        with self._lock:
            if len(self._hits) > self._max_keys and key not in self._hits:
                stale_keys = [k for k, dq in self._hits.items() if not dq or dq[-1] < cutoff]
                for k in stale_keys:
                    self._hits.pop(k, None)
                if len(self._hits) > self._max_keys:
                    oldest_key = next(iter(self._hits))
                    self._hits.pop(oldest_key, None)

            q = self._hits[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self._max:
                return False
            q.append(now)
            return True


class DailyBudgetTracker:
    """Global daily circuit breaker for non-cached LLM calls."""

    def __init__(self, max_daily_calls: int = 1000) -> None:
        self._max = max_daily_calls
        self._day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._count = 0
        self._lock = threading.Lock()

    def allow_and_increment(self) -> bool:
        if self._max <= 0:
            return True
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            if today != self._day:
                self._day = today
                self._count = 0
            if self._count >= self._max:
                return False
            self._count += 1
            return True


class ChatTokenManager:
    """Issues and verifies short-lived single-use HMAC-signed chat tokens."""

    def __init__(self, secret: str | None = None, ttl_seconds: int = 900, max_used: int = 8192) -> None:
        self._secret = (secret or os.getenv("CHAT_TOKEN_SECRET") or secrets.token_hex(32)).encode("utf-8")
        self._ttl = ttl_seconds
        self._max_used = max_used
        self._used: dict[str, float] = {}
        self._lock = threading.Lock()

    def issue(self) -> str:
        exp = int(time.time()) + self._ttl
        nonce = secrets.token_urlsafe(12)
        payload = f"{exp}.{nonce}"
        sig = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        return f"{payload}.{sig}"

    def verify_and_consume(self, token: str | None) -> bool:
        if not token or not isinstance(token, str):
            return False
        parts = token.strip().split(".")
        if len(parts) != 3:
            return False
        exp_str, nonce, sig = parts
        try:
            exp = int(exp_str)
        except ValueError:
            return False
        now = time.time()
        if exp < now or exp > now + self._ttl + 60:
            return False
        payload = f"{exp_str}.{nonce}"
        expected_sig = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected_sig):
            return False
        with self._lock:
            if len(self._used) > self._max_used:
                stale = [k for k, expiry in self._used.items() if expiry < now]
                for k in stale:
                    self._used.pop(k, None)
                if len(self._used) > self._max_used:
                    self._used.clear()
            if nonce in self._used:
                return False
            self._used[nonce] = float(exp)
        return True

    def sign_history_turn(self, role: str, content: str) -> str:
        msg = f"{role}\n{content}".encode("utf-8")
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()[:32]

    def verify_history_turn(self, role: str, content: str, sig: str | None) -> bool:
        if not sig or not isinstance(sig, str):
            return False
        expected = self.sign_history_turn(role, content)
        return hmac.compare_digest(sig.strip(), expected)


class TurnstileSessionManager:
    """Issues and verifies short-lived IP-bound HMAC passes after Turnstile succeeds once."""

    def __init__(self, secret: str | None = None, ttl_seconds: int = 7200) -> None:
        self._secret = (secret or os.getenv("CHAT_TOKEN_SECRET") or secrets.token_hex(32)).encode("utf-8")
        self._ttl = ttl_seconds

    @staticmethod
    def _ip_hash(client_ip: str) -> str:
        return hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:16]

    def issue(self, client_ip: str) -> str:
        exp = int(time.time()) + self._ttl
        ip_hash = self._ip_hash(client_ip)
        payload = f"{exp}.{ip_hash}"
        sig = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        return f"{payload}.{sig}"

    def verify(self, pass_token: str | None, client_ip: str) -> bool:
        if not pass_token or not isinstance(pass_token, str):
            return False
        parts = pass_token.strip().split(".")
        if len(parts) != 3:
            return False
        exp_str, ip_hash, sig = parts
        try:
            exp = int(exp_str)
        except ValueError:
            return False
        now = time.time()
        if exp < now or exp > now + self._ttl + 60:
            return False
        expected_ip_hash = self._ip_hash(client_ip)
        if not hmac.compare_digest(ip_hash, expected_ip_hash):
            return False
        payload = f"{exp_str}.{ip_hash}"
        expected_sig = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        return hmac.compare_digest(sig, expected_sig)


def _get_client_ip(request: Request) -> str:
    """Extract client IP safely behind Cloudflare / Render reverse proxies."""
    for header in ("cf-connecting-ip", "true-client-ip", "x-forwarded-for"):
        val = request.headers.get(header)
        if val:
            first_ip = val.split(",")[0].strip()
            if first_ip:
                return first_ip[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _verify_browser_request(request: Request) -> None:
    """Reject obvious automated scripts/bots and mismatched cross-origin requests."""
    ua = (request.headers.get("user-agent") or "").strip().lower()
    if not ua or len(ua) < 10 or any(pat in ua for pat in _BOT_UA_PATTERNS):
        raise HTTPException(
            status_code=403,
            detail="Automated requests are not permitted.",
        )

    origin = (request.headers.get("origin") or "").strip()
    host = (request.headers.get("host") or "").strip().lower()
    if origin and origin != "null":
        parsed = urllib.parse.urlparse(origin)
        origin_host = parsed.netloc.lower()
        if host and origin_host != host and not origin_host.endswith("northeasternhockeystats.com"):
            if allow_origins != ["*"] and origin not in allow_origins:
                raise HTTPException(
                    status_code=403,
                    detail="Cross-origin requests are not permitted.",
                )


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=4000)
    sig: str | None = Field(default=None, max_length=64)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=16)
    context: str | None = Field(default=None, max_length=300)


class ChatResponse(BaseModel):
    answer: str
    cached: bool = False
    turnstile_pass: str | None = None
    answer_sig: str | None = None


class _AppState:
    datasets: HockeyDatasets | None = None
    llm: Any = None
    cache: ResponseCache = ResponseCache(ttl_seconds=None, max_entries=2000)
    limiter: RateLimiter = RateLimiter(max_requests=20, window_seconds=60)
    chat_min_limiter: RateLimiter = RateLimiter(max_requests=RATE_LIMIT_MAX, window_seconds=60)
    chat_hour_limiter: RateLimiter = RateLimiter(max_requests=RATE_LIMIT_HOUR_MAX, window_seconds=3600)
    chat_day_limiter: RateLimiter = RateLimiter(max_requests=RATE_LIMIT_DAY_MAX, window_seconds=86400)
    daily_budget: DailyBudgetTracker = DailyBudgetTracker(max_daily_calls=MAX_DAILY_LLM_CALLS)
    token_manager: ChatTokenManager = ChatTokenManager()
    turnstile_sessions: TurnstileSessionManager = TurnstileSessionManager()


state = _AppState()


def _compute_dataset_version(data_dir: Path) -> str:
    h = hashlib.sha256()
    for csv_path in sorted(data_dir.glob("northeastern_*.csv")):
        stat = csv_path.stat()
        h.update(f"{csv_path.name}:{stat.st_size}:{stat.st_mtime_ns}|".encode("utf-8"))
    return h.hexdigest()[:16]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    state.datasets = load_datasets(DATA_DIR)
    state.cache.sync_version(_compute_dataset_version(DATA_DIR))
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    has_any_llm = bool(
        api_key
        or os.getenv("GEMINI_API_KEYS", "").strip()
        or os.getenv("GROQ_API_KEY", "").strip()
        or os.getenv("AXFORGE_API_KEY", "").strip()
        or os.getenv("NVIDIA_API_KEY", "").strip()
        or os.getenv("KILO_API_KEY", "").strip()
        or os.getenv("ENABLE_KILO_FREE_FALLBACK", "").strip().lower() in ("1", "true", "yes")
    )
    if has_any_llm:
        state.llm = build_llm(api_key)
    yield


app = FastAPI(
    title="NU Hockey Stats Explorer API",
    version="1.0.0",
    lifespan=lifespan,
)

raw_origins = os.getenv("FRONTEND_ORIGINS", "*")
allow_origins = [o.strip() for o in raw_origins.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval' https://challenges.cloudflare.com https://static.cloudflareinsights.com; "
        "worker-src 'self' blob: https://challenges.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' https: data: blob:; "
        "frame-src https://challenges.cloudflare.com; "
        "connect-src 'self' data: https://challenges.cloudflare.com https://cloudflareinsights.com; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    return response


DEFAULT_TURNSTILE_SITE_KEY = "0x4AAAAAAF_2EIKQvwCX1Yx1"
TURNSTILE_EXPECTED_ACTION = "ask_paws"


def _turnstile_config() -> tuple[str, str]:
    site_key = (os.getenv("TURNSTILE_SITE_KEY", DEFAULT_TURNSTILE_SITE_KEY) or DEFAULT_TURNSTILE_SITE_KEY).strip()
    secret_key = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
    return site_key, secret_key


def _verify_turnstile_token(token: str | None, client_ip: str) -> bool:
    _, secret_key = _turnstile_config()
    if not secret_key:
        return True
    cleaned = (token or "").strip()
    if not cleaned or len(cleaned) > 2048:
        return False
    body = urllib.parse.urlencode({
        "secret": secret_key,
        "response": cleaned,
        "remoteip": client_ip,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False

    if not data.get("success"):
        return False
    action = data.get("action")
    if action and action != TURNSTILE_EXPECTED_ACTION:
        return False
    raw_hostnames = os.getenv("TURNSTILE_HOSTNAMES", "").strip()
    if raw_hostnames:
        expected_hostnames = {h.strip().lower() for h in raw_hostnames.split(",") if h.strip()}
        if (data.get("hostname") or "").strip().lower() not in expected_hostnames:
            return False
    return True


def _require_datasets() -> HockeyDatasets:
    if state.datasets is None:
        raise HTTPException(status_code=503, detail="Datasets are not loaded yet.")
    return state.datasets


def _records(df) -> list[dict[str, Any]]:
    return df.fillna("").to_dict(orient="records")


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health() -> dict[str, Any]:
    ds = _require_datasets()
    latest_game = str(ds.games["date"].iloc[-1]) if not ds.games.empty else None
    site_key, secret_key = _turnstile_config()
    return {
        "status": "ok",
        "llm_configured": state.llm is not None,
        "turnstile_site_key": site_key if (site_key and secret_key) else None,
        "games_count": int(len(ds.games)),
        "skater_logs_count": int(len(ds.skaters)),
        "seasons_count": len(ds.available_seasons),
        "latest_season": ds.available_seasons[0] if ds.available_seasons else None,
        "latest_game_date": latest_game,
    }


@app.get("/api/seasons")
def get_seasons() -> dict[str, Any]:
    ds = _require_datasets()
    return {
        "seasons": ds.available_seasons,
        "opponents": ds.all_opponents,
    }


@app.get("/api/roster")
def get_roster(season: str | None = Query(default=None)) -> dict[str, Any]:
    ds = _require_datasets()
    target_season = season or (ds.available_seasons[0] if ds.available_seasons else "")
    df = ds.rosters[ds.rosters["season"] == target_season].copy()
    if not df.empty and "jersey_number" in df.columns:
        df["_num_sort"] = df["jersey_number"].astype(str).str.extract(r"(\d+)")[0].astype(float).fillna(999)
        df = df.sort_values(["_num_sort", "player_name"]).drop(columns=["_num_sort"])
    head_coach = ""
    roster_url = ""
    if not df.empty:
        coaches = [c for c in df["head_coach"].unique() if c]
        head_coach = coaches[0] if coaches else ""
        urls = [u for u in df["roster_url"].unique() if u]
        roster_url = urls[0] if urls else ""
    return {
        "season": target_season,
        "head_coach": head_coach,
        "roster_url": roster_url,
        "players": _records(df),
    }


def _parse_minutes_to_float(val: Any) -> float:
    text = str(val or "").strip()
    if ":" in text:
        parts = text.split(":", 1)
        try:
            return float(parts[0]) + float(parts[1]) / 60.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _filter_games_by_criteria(
    games_df: pd.DataFrame,
    target_season: str,
    scope: str,
    target_opponent: str | None,
    location: str = "all",
) -> pd.DataFrame:
    df = games_df if target_season == "all" else games_df[games_df["season"] == target_season]
    if scope == "conference":
        df = df[df["opponent"].isin(HOCKEY_EAST_TEAMS) & (df.get("game_type", "Regular Season") == "Regular Season")]
    elif scope == "beanpot":
        df = df[df.get("game_type", "") == "Beanpot"]
    elif scope == "postseason":
        df = df[df.get("game_type", "") == "Hockey East Tournament"]
    elif scope == "ncaa":
        df = df[df.get("game_type", "") == "NCAA Tournament"]
    if location and location.lower() != "all":
        df = df[df["location"].str.lower() == location.lower()]
    if target_opponent:
        df = df[df["opponent"].str.lower() == target_opponent.lower()]
    return df


def _skater_log_extras(
    ds: HockeyDatasets,
    target_season: str,
    scope: str,
    target_opponent: str | None,
    location: str = "all",
) -> dict[str, Any]:
    """Return per-player maps and team totals for MGG, HTG, MPG, and Faceoffs from skater logs."""
    sk_df = ds.skaters if target_season == "all" else ds.skaters[ds.skaters["season"] == target_season]
    sk_df = sk_df[sk_df["position"] != "G"]
    if scope != "all" or (location and location.lower() != "all") or target_opponent:
        fg = _filter_games_by_criteria(ds.games, target_season, scope, target_opponent, location)
        valid_keys = set(zip(fg["date"].astype(str), fg["opponent"].astype(str)))
        if not valid_keys:
            sk_df = sk_df.iloc[0:0]
        else:
            mask = [(str(d), str(o)) in valid_keys for d, o in zip(sk_df["date"], sk_df["opponent"])]
            sk_df = sk_df[mask]
    if sk_df.empty:
        return {
            "mgg_map": {}, "htg_map": {}, "mpg_map": {}, "fow_map": {}, "fol_map": {},
            "total_mgg": 0, "total_htg": 0, "total_mpg": 0, "total_fow": 0, "total_fol": 0,
        }
    mgg_df = sk_df[sk_df["goals"] >= 2]
    htg_df = sk_df[sk_df["goals"] >= 3]
    mpg_df = sk_df[sk_df["points"] >= 2]
    mgg_map = mgg_df.groupby("player_name").size().to_dict() if not mgg_df.empty else {}
    htg_map = htg_df.groupby("player_name").size().to_dict() if not htg_df.empty else {}
    mpg_map = mpg_df.groupby("player_name").size().to_dict() if not mpg_df.empty else {}
    fo_grp = sk_df.groupby("player_name")[["faceoffs_won", "faceoffs_lost"]].sum()
    fow_map = fo_grp["faceoffs_won"].to_dict() if not fo_grp.empty else {}
    fol_map = fo_grp["faceoffs_lost"].to_dict() if not fo_grp.empty else {}
    return {
        "mgg_map": {str(k): int(v) for k, v in mgg_map.items()},
        "htg_map": {str(k): int(v) for k, v in htg_map.items()},
        "mpg_map": {str(k): int(v) for k, v in mpg_map.items()},
        "fow_map": {str(k): int(v) for k, v in fow_map.items()},
        "fol_map": {str(k): int(v) for k, v in fol_map.items()},
        "total_mgg": int(len(mgg_df)),
        "total_htg": int(len(htg_df)),
        "total_mpg": int(len(mpg_df)),
        "total_fow": int(sk_df["faceoffs_won"].sum()),
        "total_fol": int(sk_df["faceoffs_lost"].sum()),
    }


def _build_team_stats(
    ds: Any,
    target_season: str,
    scope: str,
    target_opponent: str | None,
    location: str = "all",
) -> dict[str, Any]:
    games_df = _filter_games_by_criteria(ds.games, target_season, scope, target_opponent, location)
    unfiltered_loc_games = _filter_games_by_criteria(ds.games, target_season, scope, target_opponent, "all")
    valid_keys = set(zip(games_df["date"].astype(str), games_df["opponent"].astype(str)))

    gp = int(len(games_df))
    wins = int((games_df["outcome"] == "W").sum()) if gp else 0
    losses = int((games_df["outcome"] == "L").sum()) if gp else 0
    ties = int((games_df["outcome"] == "T").sum()) if gp else 0
    win_pct = round((wins + 0.5 * ties) / gp, 3) if gp else 0.0
    ot_games = int((games_df["is_overtime"] == 1).sum()) if gp else 0
    shootout_wins = int(((games_df["is_shootout"] == 1) & (games_df["shootout_winner"] == "Northeastern")).sum()) if gp else 0
    goals_for = int(games_df["nu_goals"].sum()) if gp else 0
    goals_against = int(games_df["opp_goals"].sum()) if gp else 0
    goal_diff = goals_for - goals_against
    gf_per_game = round(goals_for / gp, 2) if gp else 0.0
    ga_per_game = round(goals_against / gp, 2) if gp else 0.0
    shutouts_for = int(((games_df["is_shutout"] == 1) & (games_df["shutout_team"] == "Northeastern")).sum()) if gp else 0
    shutouts_against = int(((games_df["is_shutout"] == 1) & (games_df["shutout_team"] != "Northeastern")).sum()) if gp else 0

    pp_goals = int(games_df["nu_pp_goals"].sum()) if (gp and "nu_pp_goals" in games_df.columns) else 0
    pp_opps = int(games_df["nu_pp_opps"].sum()) if (gp and "nu_pp_opps" in games_df.columns) else 0
    pp_pct = round((pp_goals / pp_opps) * 100.0, 1) if pp_opps > 0 else 0.0

    opp_pp_goals = int(games_df["opp_pp_goals"].sum()) if (gp and "opp_pp_goals" in games_df.columns) else 0
    opp_pp_opps = int(games_df["opp_pp_opps"].sum()) if (gp and "opp_pp_opps" in games_df.columns) else 0
    pk_kills = max(0, opp_pp_opps - opp_pp_goals)
    pk_pct = round((pk_kills / opp_pp_opps) * 100.0, 1) if opp_pp_opps > 0 else 0.0

    use_game_logs = (
        target_opponent is not None
        or (location and location.lower() != "all")
        or scope in ("beanpot", "postseason", "ncaa")
    )

    ppg: int | None = pp_goals
    shg: int | None = None
    if use_game_logs:
        sk_df = ds.skaters if target_season == "all" else ds.skaters[ds.skaters["season"] == target_season]
        sk_df = sk_df[sk_df["position"] != "G"]
        if valid_keys:
            sk_df = sk_df[[(str(d), str(o)) in valid_keys for d, o in zip(sk_df["date"], sk_df["opponent"])]]
        else:
            sk_df = sk_df.iloc[0:0]
        shots = int(sk_df["shots"].sum()) if not sk_df.empty else 0
        pim = int(sk_df["penalty_minutes"].sum()) if not sk_df.empty else 0
        blocked_shots = int(sk_df["blocked_shots"].sum()) if not sk_df.empty else 0

        gl_df = ds.goalies if target_season == "all" else ds.goalies[ds.goalies["season"] == target_season]
        if valid_keys:
            gl_df = gl_df[[(str(d), str(o)) in valid_keys for d, o in zip(gl_df["date"], gl_df["opponent"])]]
        else:
            gl_df = gl_df.iloc[0:0]
        saves = int(gl_df["saves"].sum()) if not gl_df.empty else 0
        ga = int(gl_df["goals_against"].sum()) if not gl_df.empty else 0

        g_sub = ds.goals if target_season == "all" else ds.goals[ds.goals["season"] == target_season]
        if valid_keys:
            g_sub = g_sub[[(str(d), str(o)) in valid_keys for d, o in zip(g_sub["date"], g_sub["opponent"])]]
        else:
            g_sub = g_sub.iloc[0:0]
        nu_g_sub = g_sub[g_sub["team"] == "Northeastern"] if not g_sub.empty else g_sub
        shg = int((nu_g_sub["strength"] == "SH").sum()) if not nu_g_sub.empty else 0
    else:
        prefix = "conf_" if scope == "conference" else ""
        season_rows = ds.season_stats if target_season == "all" else ds.season_stats[ds.season_stats["season"] == target_season]
        sk_rows = season_rows[season_rows["position"] != "G"]
        shots = int(sk_rows[f"{prefix}shots"].sum()) if not sk_rows.empty else 0
        ppg = int(sk_rows[f"{prefix}ppg"].sum()) if not sk_rows.empty else pp_goals
        shg = int(sk_rows[f"{prefix}shg"].sum()) if not sk_rows.empty else 0
        pim = int(sk_rows[f"{prefix}pim"].sum()) if not sk_rows.empty else 0
        blocked_shots = int(sk_rows[f"{prefix}blocked_shots"].sum()) if not sk_rows.empty else 0

        gl_rows = season_rows[season_rows[f"{prefix}goalie_gp"] > 0]
        saves = int(gl_rows[f"{prefix}saves"].sum()) if not gl_rows.empty else 0
        ga = int(gl_rows[f"{prefix}ga"].sum()) if not gl_rows.empty else 0

    shot_pct = round((goals_for / shots) * 100.0, 1) if shots > 0 else 0.0
    save_pct = round(saves / (saves + ga), 3) if (saves + ga) > 0 else 0.0

    season_breakdown: list[dict[str, Any]] = []
    if target_season == "all" and gp > 0:
        for s_name, grp in games_df.groupby("season"):
            s_gp = int(len(grp))
            s_w = int((grp["outcome"] == "W").sum())
            s_l = int((grp["outcome"] == "L").sum())
            s_t = int((grp["outcome"] == "T").sum())
            s_gf = int(grp["nu_goals"].sum())
            s_ga = int(grp["opp_goals"].sum())
            season_breakdown.append({
                "season": str(s_name),
                "gp": s_gp,
                "wins": s_w,
                "losses": s_l,
                "ties": s_t,
                "win_pct": round((s_w + 0.5 * s_t) / s_gp, 3) if s_gp else 0.0,
                "goals_for": s_gf,
                "goals_against": s_ga,
                "goal_diff": s_gf - s_ga,
            })
        season_breakdown.sort(key=lambda r: r["season"], reverse=True)

    recent_games = (
        _records(games_df.sort_values("date", ascending=False))
        if (target_season != "all" or scope in ("beanpot", "postseason", "ncaa")) and gp > 0
        else []
    )

    extras = _skater_log_extras(ds, target_season, scope, target_opponent, location)
    fow = extras["total_fow"]
    fol = extras["total_fol"]
    faceoff_pct = round((fow / (fow + fol)) * 100.0, 1) if (fow + fol) > 0 else None

    def _wlt(sub_df) -> str:
        if sub_df.empty:
            return "0-0-0"
        w = int((sub_df["outcome"] == "W").sum())
        l = int((sub_df["outcome"] == "L").sum())
        t = int((sub_df["outcome"] == "T").sum())
        return f"{w}-{l}-{t}"

    location_splits = {
        "home": _wlt(unfiltered_loc_games[unfiltered_loc_games["location"] == "Home"]) if not unfiltered_loc_games.empty else "0-0-0",
        "away": _wlt(unfiltered_loc_games[unfiltered_loc_games["location"] == "Away"]) if not unfiltered_loc_games.empty else "0-0-0",
        "neutral": _wlt(unfiltered_loc_games[unfiltered_loc_games["location"] == "Neutral"]) if not unfiltered_loc_games.empty else "0-0-0",
    }

    one_goal_df = games_df[(games_df["nu_goals"] - games_df["opp_goals"]).abs() == 1] if gp else games_df
    ot_df = games_df[games_df["is_overtime"] == 1] if gp else games_df
    so_df = games_df[games_df["is_shootout"] == 1] if gp else games_df
    so_losses = int((so_df["shootout_winner"] != "Northeastern").sum()) if not so_df.empty else 0

    goals_ev = ds.goals if target_season == "all" else ds.goals[ds.goals["season"] == target_season]
    if valid_keys:
        goals_ev = goals_ev[[(str(d), str(o)) in valid_keys for d, o in zip(goals_ev["date"], goals_ev["opponent"])]]
    elif gp == 0:
        goals_ev = goals_ev.iloc[0:0]

    scoring_first_record = "0-0-0"
    goals_by_period: list[dict[str, Any]] = []
    goals_by_minute: list[dict[str, Any]] = []
    if not goals_ev.empty:
        period_order = {"1st": 1, "2nd": 2, "3rd": 3, "OT": 4, "1OT": 4, "2OT": 5, "3OT": 6}
        g_sorted = goals_ev.assign(_pord=goals_ev["period"].map(lambda x: period_order.get(str(x).strip(), 99)))
        first_goals = (
            g_sorted.sort_values(["date", "opponent", "_pord", "time_seconds"])
            .drop_duplicates(subset=["date", "opponent"], keep="first")
        )
        nu_first_keys = set(
            zip(
                first_goals[first_goals["team"] == "Northeastern"]["date"].astype(str),
                first_goals[first_goals["team"] == "Northeastern"]["opponent"].astype(str),
            )
        )
        if gp and nu_first_keys:
            mask_sf = [
                (str(d), str(o)) in nu_first_keys
                for d, o in zip(games_df["date"], games_df["opponent"])
            ]
            scoring_first_record = _wlt(games_df[mask_sf])

        for per_name in ["1st", "2nd", "3rd", "OT"]:
            per_sub = goals_ev[goals_ev["period"] == per_name]
            if not per_sub.empty or per_name in ("1st", "2nd", "3rd"):
                goals_by_period.append({
                    "period": per_name,
                    "nu_goals": int((per_sub["team"] == "Northeastern").sum()),
                    "opp_goals": int((per_sub["team"] != "Northeastern").sum()),
                })

        # 5-minute scoring timing buckets across regulation (0-5, 5-10, 10-15, 15-20 per period) + OT
        bucket_defs = [
            ("1st", 0, 300, "1st 0-5m"),
            ("1st", 300, 600, "1st 5-10m"),
            ("1st", 600, 900, "1st 10-15m"),
            ("1st", 900, 1201, "1st 15-20m"),
            ("2nd", 0, 300, "2nd 0-5m"),
            ("2nd", 300, 600, "2nd 5-10m"),
            ("2nd", 600, 900, "2nd 10-15m"),
            ("2nd", 900, 1201, "2nd 15-20m"),
            ("3rd", 0, 300, "3rd 0-5m"),
            ("3rd", 300, 600, "3rd 5-10m"),
            ("3rd", 600, 900, "3rd 10-15m"),
            ("3rd", 900, 1201, "3rd 15-20m"),
        ]
        for per_name, t_min, t_max, label in bucket_defs:
            b_sub = goals_ev[(goals_ev["period"] == per_name) & (goals_ev["time_seconds"] >= t_min) & (goals_ev["time_seconds"] < t_max)]
            goals_by_minute.append({
                "label": label,
                "period": per_name,
                "nu_goals": int((b_sub["team"] == "Northeastern").sum()),
                "opp_goals": int((b_sub["team"] != "Northeastern").sum()),
            })
        ot_sub = goals_ev[goals_ev["period"].isin(["OT", "1OT", "2OT", "3OT"])]
        goals_by_minute.append({
            "label": "OT",
            "period": "OT",
            "nu_goals": int((ot_sub["team"] == "Northeastern").sum()),
            "opp_goals": int((ot_sub["team"] != "Northeastern").sum()),
        })

    so_ev = ds.shootouts if target_season == "all" else ds.shootouts[ds.shootouts["season"] == target_season]
    if valid_keys:
        so_ev = so_ev[[(str(d), str(o)) in valid_keys for d, o in zip(so_ev["date"], so_ev["opponent"])]]
    elif gp == 0:
        so_ev = so_ev.iloc[0:0]
    nu_so_ev = so_ev[so_ev["shooter_team"] == "Northeastern"] if not so_ev.empty else so_ev
    shootout_attempts = int(len(nu_so_ev))
    shootout_made = int((nu_so_ev["result"] == "MADE").sum()) if shootout_attempts > 0 else 0
    shootout_pct = round((shootout_made / shootout_attempts) * 100.0, 1) if shootout_attempts > 0 else 0.0

    return {
        "games_played": gp,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_pct": win_pct,
        "ot_games": ot_games,
        "shootout_wins": shootout_wins,
        "shootout_losses": so_losses,
        "shootout_record": f"{shootout_wins}-{so_losses}",
        "one_goal_record": _wlt(one_goal_df),
        "ot_record": _wlt(ot_df),
        "scoring_first_record": scoring_first_record,
        "location_splits": location_splits,
        "pp_goals": pp_goals,
        "pp_opps": pp_opps,
        "pp_pct": pp_pct,
        "opp_pp_goals": opp_pp_goals,
        "opp_pp_opps": opp_pp_opps,
        "pk_kills": pk_kills,
        "pk_pct": pk_pct,
        "shootout_attempts": shootout_attempts,
        "shootout_made": shootout_made,
        "shootout_pct": shootout_pct,
        "goals_by_period": goals_by_period,
        "goals_by_minute": goals_by_minute,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_diff": goal_diff,
        "gf_per_game": gf_per_game,
        "ga_per_game": ga_per_game,
        "shutouts_for": shutouts_for,
        "shutouts_against": shutouts_against,
        "shots": shots,
        "shot_pct": shot_pct,
        "ppg": ppg,
        "shg": shg,
        "pim": pim,
        "blocked_shots": blocked_shots,
        "faceoffs_won": fow,
        "faceoffs_lost": fol,
        "faceoff_pct": faceoff_pct,
        "multi_goal_games": extras["total_mgg"],
        "hat_tricks": extras["total_htg"],
        "multi_point_games": extras["total_mpg"],
        "saves": saves,
        "save_pct": save_pct,
        "season_breakdown": season_breakdown,
        "games": recent_games,
    }


@app.get("/api/leaders")
def get_leaders(
    season: str | None = Query(default=None),
    scope: str = Query(default="all", pattern="^(all|conference|beanpot|postseason|ncaa)$"),
    location: str = Query(default="all", pattern="^(all|Home|Away|Neutral|home|away|neutral)$"),
    opponent: str | None = Query(default=None),
    limit: int = Query(default=35, ge=1, le=100),
) -> dict[str, Any]:
    ds = _require_datasets()
    target_season = season or (ds.available_seasons[0] if ds.available_seasons else "")
    target_opponent = opponent.strip() if opponent and opponent.strip() else None
    norm_loc = location.capitalize() if location and location.lower() in ("home", "away", "neutral") else "all"

    season_games = _filter_games_by_criteria(ds.games, target_season, scope, None, norm_loc)
    season_opponents = sorted(o for o in season_games["opponent"].dropna().unique() if o)

    stats_url = ""
    season_rows = ds.season_stats if target_season == "all" else ds.season_stats[ds.season_stats["season"] == target_season]
    if not season_rows.empty:
        urls = [u for u in season_rows["stats_url"].unique() if u]
        stats_url = urls[0] if urls else ""

    use_game_logs = (
        target_opponent is not None
        or norm_loc != "all"
        or scope in ("beanpot", "postseason", "ncaa")
    )

    # Case 1: Specific opponent, venue split, or tournament filter selected -> aggregate from game-by-game logs
    if use_game_logs:
        filtered_games = _filter_games_by_criteria(ds.games, target_season, scope, target_opponent, norm_loc)
        valid_keys = set(zip(filtered_games["date"].astype(str), filtered_games["opponent"].astype(str)))

        sk_df = ds.skaters if target_season == "all" else ds.skaters[ds.skaters["season"] == target_season]
        sk_df = sk_df[sk_df["position"] != "G"]
        if valid_keys:
            sk_df = sk_df[[(str(d), str(o)) in valid_keys for d, o in zip(sk_df["date"], sk_df["opponent"])]]
        else:
            sk_df = sk_df.iloc[0:0]

        roster_df = ds.rosters if target_season == "all" else ds.rosters[ds.rosters["season"] == target_season]
        jersey_map = (
            roster_df.drop_duplicates("player_name")
            .set_index("player_name")["jersey_number"]
            .to_dict()
            if not roster_df.empty
            else {}
        )

        # Count PPG, SHG, OTG from goal_events for these filtered games
        g_ev = ds.goals if target_season == "all" else ds.goals[ds.goals["season"] == target_season]
        if valid_keys:
            g_ev = g_ev[[(str(d), str(o)) in valid_keys for d, o in zip(g_ev["date"], g_ev["opponent"])]]
        else:
            g_ev = g_ev.iloc[0:0]
        nu_g_ev = g_ev[g_ev["team"] == "Northeastern"] if not g_ev.empty else g_ev
        ppg_map = nu_g_ev[nu_g_ev["strength"] == "PP"].groupby("scorer").size().to_dict() if not nu_g_ev.empty else {}
        shg_map = nu_g_ev[nu_g_ev["strength"] == "SH"].groupby("scorer").size().to_dict() if not nu_g_ev.empty else {}
        otg_map = nu_g_ev[nu_g_ev["period"].isin(["OT", "1OT", "2OT", "3OT"])].groupby("scorer").size().to_dict() if not nu_g_ev.empty else {}

        skaters_list: list[dict[str, Any]] = []
        if not sk_df.empty:
            sk_df = sk_df.copy()
            sk_df["_mgg"] = (sk_df["goals"] >= 2).astype(int)
            sk_df["_htg"] = (sk_df["goals"] >= 3).astype(int)
            sk_df["_mpg"] = (sk_df["points"] >= 2).astype(int)
            grouped = (
                sk_df.groupby("player_name", as_index=False)
                .agg(
                    position=("position", "last"),
                    captain_role=("captain_role", "last"),
                    gp=("date", "count"),
                    goals=("goals", "sum"),
                    assists=("assists", "sum"),
                    points=("points", "sum"),
                    shots=("shots", "sum"),
                    plus_minus=("plus_minus", "sum"),
                    pim=("penalty_minutes", "sum"),
                    gwg=("gwg", "sum"),
                    blocked_shots=("blocked_shots", "sum"),
                    faceoffs_won=("faceoffs_won", "sum"),
                    faceoffs_lost=("faceoffs_lost", "sum"),
                    multi_goal_games=("_mgg", "sum"),
                    hat_tricks=("_htg", "sum"),
                    multi_point_games=("_mpg", "sum"),
                )
                .sort_values(["points", "goals", "gp"], ascending=[False, False, True])
                .head(limit)
            )
            grouped["ppg"] = grouped["player_name"].map(lambda n: int(ppg_map.get(n, 0)))
            grouped["shg"] = grouped["player_name"].map(lambda n: int(shg_map.get(n, 0)))
            grouped["otg"] = grouped["player_name"].map(lambda n: int(otg_map.get(n, 0)))
            grouped["shot_pct"] = grouped.apply(
                lambda r: round((r["goals"] / r["shots"]) * 100.0, 1) if r["shots"] > 0 else 0.0, axis=1
            )
            grouped["faceoff_pct"] = grouped.apply(
                lambda r: round((r["faceoffs_won"] / (r["faceoffs_won"] + r["faceoffs_lost"])) * 100.0, 1)
                if (r["faceoffs_won"] + r["faceoffs_lost"]) > 0
                else 0.0,
                axis=1,
            )
            grouped["jersey_number"] = grouped["player_name"].map(lambda n: jersey_map.get(n, ""))
            skaters_list = _records(grouped)

        gl_df = ds.goalies if target_season == "all" else ds.goalies[ds.goalies["season"] == target_season]
        if valid_keys:
            gl_df = gl_df[[(str(d), str(o)) in valid_keys for d, o in zip(gl_df["date"], gl_df["opponent"])]]
        else:
            gl_df = gl_df.iloc[0:0]

        goalies_list: list[dict[str, Any]] = []
        if not gl_df.empty:
            gl_df = gl_df.copy()
            gl_df["_mins"] = gl_df["minutes"].apply(_parse_minutes_to_float)
            gl_df["_w"] = (gl_df["decision"] == "W").astype(int)
            gl_df["_l"] = (gl_df["decision"] == "L").astype(int)
            gl_df["_t"] = (gl_df["decision"] == "T").astype(int)
            g_grouped = (
                gl_df.groupby("goalie_name", as_index=False)
                .agg(
                    goalie_gp=("date", "count"),
                    wins=("_w", "sum"),
                    losses=("_l", "sum"),
                    ties=("_t", "sum"),
                    saves=("saves", "sum"),
                    ga=("goals_against", "sum"),
                    shutouts=("shutouts", "sum"),
                    _mins=("_mins", "sum"),
                )
            )
            g_grouped["player_name"] = g_grouped["goalie_name"]
            g_grouped["jersey_number"] = g_grouped["player_name"].map(lambda n: jersey_map.get(n, ""))
            g_grouped["goalie_minutes"] = g_grouped["_mins"].apply(lambda m: f"{int(m)}:{int(round((m % 1) * 60)):02d}")
            g_grouped["gaa"] = g_grouped.apply(
                lambda r: round((r["ga"] * 60.0) / r["_mins"], 2) if r["_mins"] > 0 else 0.0, axis=1
            )
            g_grouped["save_pct"] = g_grouped.apply(
                lambda r: round(r["saves"] / (r["saves"] + r["ga"]), 3) if (r["saves"] + r["ga"]) > 0 else 0.0,
                axis=1,
            )
            g_grouped = g_grouped.sort_values(["goalie_gp", "save_pct"], ascending=[False, False]).head(limit)
            goalies_list = _records(g_grouped.drop(columns=["goalie_name", "_mins"]))

        return {
            "season": target_season,
            "scope": scope,
            "location": norm_loc,
            "opponent": target_opponent,
            "opponents": season_opponents,
            "stats_url": stats_url,
            "team_stats": _build_team_stats(ds, target_season, scope, target_opponent, norm_loc),
            "skaters": skaters_list,
            "goalies": goalies_list,
        }

    # Case 2: All opponents & all venues -> use cumulative season stats (All or Hockey East Conference)
    extras = _skater_log_extras(ds, target_season, scope, None, norm_loc)
    mgg_map = extras["mgg_map"]
    htg_map = extras["htg_map"]
    mpg_map = extras["mpg_map"]
    fow_map = extras["fow_map"]
    fol_map = extras["fol_map"]
    df = season_rows.copy()
    if target_season == "all" and not df.empty:
        # Aggregate career/all-time stats across seasons
        sk_agg = (
            df[(df["gp"] > 0) & (df["position"] != "G")]
            .groupby("player_name", as_index=False)
            .agg(
                jersey_number=("jersey_number", "last"),
                captain_role=("captain_role", "last"),
                position=("position", "last"),
                gp=("conf_gp" if scope == "conference" else "gp", "sum"),
                goals=("conf_goals" if scope == "conference" else "goals", "sum"),
                assists=("conf_assists" if scope == "conference" else "assists", "sum"),
                points=("conf_points" if scope == "conference" else "points", "sum"),
                shots=("conf_shots" if scope == "conference" else "shots", "sum"),
                plus_minus=("conf_plus_minus" if scope == "conference" else "plus_minus", "sum"),
                ppg=("conf_ppg" if scope == "conference" else "ppg", "sum"),
                shg=("conf_shg" if scope == "conference" else "shg", "sum"),
                gwg=("conf_gwg" if scope == "conference" else "gwg", "sum"),
                otg=("conf_otg" if scope == "conference" else "otg", "sum"),
                pim=("conf_pim" if scope == "conference" else "pim", "sum"),
                blocked_shots=("conf_blocked_shots" if scope == "conference" else "blocked_shots", "sum"),
            )
        )
        sk_agg["shot_pct"] = sk_agg.apply(
            lambda r: round((r["goals"] / r["shots"]) * 100.0, 1) if r["shots"] > 0 else 0.0, axis=1
        )
        sk_agg["multi_goal_games"] = sk_agg["player_name"].map(lambda n: mgg_map.get(str(n), 0))
        sk_agg["hat_tricks"] = sk_agg["player_name"].map(lambda n: htg_map.get(str(n), 0))
        sk_agg["multi_point_games"] = sk_agg["player_name"].map(lambda n: mpg_map.get(str(n), 0))
        sk_agg["faceoffs_won"] = sk_agg["player_name"].map(lambda n: fow_map.get(str(n), 0))
        sk_agg["faceoffs_lost"] = sk_agg["player_name"].map(lambda n: fol_map.get(str(n), 0))
        sk_agg["faceoff_pct"] = sk_agg.apply(
            lambda r: round((r["faceoffs_won"] / (r["faceoffs_won"] + r["faceoffs_lost"])) * 100.0, 1)
            if (r["faceoffs_won"] + r["faceoffs_lost"]) > 0
            else 0.0,
            axis=1,
        )
        skaters = sk_agg[sk_agg["gp"] > 0].sort_values(
            ["points", "goals", "gp"], ascending=[False, False, True]
        ).head(limit)

        gl_agg = (
            df[df["goalie_gp"] > 0]
            .groupby("player_name", as_index=False)
            .agg(
                jersey_number=("jersey_number", "last"),
                goalie_gp=("conf_goalie_gp" if scope == "conference" else "goalie_gp", "sum"),
                goalie_gs=("conf_goalie_gs" if scope == "conference" else "goalie_gs", "sum"),
                wins=("conf_wins" if scope == "conference" else "wins", "sum"),
                losses=("conf_losses" if scope == "conference" else "losses", "sum"),
                ties=("conf_ties" if scope == "conference" else "ties", "sum"),
                ga=("conf_ga" if scope == "conference" else "ga", "sum"),
                saves=("conf_saves" if scope == "conference" else "saves", "sum"),
                shutouts=("conf_shutouts" if scope == "conference" else "shutouts", "sum"),
                gaa=("conf_gaa" if scope == "conference" else "gaa", "mean"),
                save_pct=("conf_save_pct" if scope == "conference" else "save_pct", "mean"),
            )
        )
        goalies = gl_agg[gl_agg["goalie_gp"] > 0].sort_values(
            ["goalie_gp", "save_pct"], ascending=[False, False]
        ).head(limit)
        return {
            "season": target_season,
            "scope": scope,
            "location": norm_loc,
            "opponent": None,
            "opponents": season_opponents,
            "stats_url": "",
            "team_stats": _build_team_stats(ds, target_season, scope, None, norm_loc),
            "skaters": _records(skaters),
            "goalies": _records(goalies),
        }

    prefix = "conf_" if scope == "conference" else ""
    sk_gp_col = f"{prefix}gp"
    skaters_src = df[(df[sk_gp_col] > 0) & (df["position"] != "G")].sort_values(
        [f"{prefix}points", f"{prefix}goals", sk_gp_col], ascending=[False, False, True]
    ).head(limit)

    sk_fow = skaters_src["player_name"].map(lambda n: fow_map.get(str(n), 0))
    sk_fol = skaters_src["player_name"].map(lambda n: fol_map.get(str(n), 0))
    sk_fo_tot = sk_fow + sk_fol
    sk_fo_pct = [
        round((w / t) * 100.0, 1) if t > 0 else 0.0
        for w, t in zip(sk_fow, sk_fo_tot)
    ]
    skaters_norm = pd.DataFrame({
        "jersey_number": skaters_src["jersey_number"],
        "player_name": skaters_src["player_name"],
        "captain_role": skaters_src["captain_role"],
        "position": skaters_src["position"],
        "class_year": skaters_src["class_year"],
        "gp": skaters_src[f"{prefix}gp"],
        "goals": skaters_src[f"{prefix}goals"],
        "assists": skaters_src[f"{prefix}assists"],
        "points": skaters_src[f"{prefix}points"],
        "shots": skaters_src[f"{prefix}shots"],
        "shot_pct": skaters_src[f"{prefix}shot_pct"],
        "plus_minus": skaters_src[f"{prefix}plus_minus"],
        "ppg": skaters_src[f"{prefix}ppg"],
        "shg": skaters_src[f"{prefix}shg"],
        "gwg": skaters_src[f"{prefix}gwg"],
        "otg": skaters_src[f"{prefix}otg"],
        "pim": skaters_src[f"{prefix}pim"],
        "blocked_shots": skaters_src[f"{prefix}blocked_shots"],
        "multi_goal_games": skaters_src["player_name"].map(lambda n: mgg_map.get(str(n), 0)),
        "hat_tricks": skaters_src["player_name"].map(lambda n: htg_map.get(str(n), 0)),
        "multi_point_games": skaters_src["player_name"].map(lambda n: mpg_map.get(str(n), 0)),
        "faceoffs_won": sk_fow,
        "faceoffs_lost": sk_fol,
        "faceoff_pct": sk_fo_pct,
    })

    gl_gp_col = f"{prefix}goalie_gp"
    goalies_src = df[df[gl_gp_col] > 0].sort_values(
        [gl_gp_col, f"{prefix}save_pct"], ascending=[False, False]
    ).head(limit)

    goalies_norm = pd.DataFrame({
        "jersey_number": goalies_src["jersey_number"],
        "player_name": goalies_src["player_name"],
        "captain_role": goalies_src["captain_role"],
        "goalie_gp": goalies_src[f"{prefix}goalie_gp"],
        "goalie_gs": goalies_src[f"{prefix}goalie_gs"],
        "goalie_minutes": goalies_src[f"{prefix}goalie_minutes"],
        "wins": goalies_src[f"{prefix}wins"],
        "losses": goalies_src[f"{prefix}losses"],
        "ties": goalies_src[f"{prefix}ties"],
        "gaa": goalies_src[f"{prefix}gaa"],
        "save_pct": goalies_src[f"{prefix}save_pct"],
        "saves": goalies_src[f"{prefix}saves"],
        "ga": goalies_src[f"{prefix}ga"],
        "shutouts": goalies_src[f"{prefix}shutouts"],
    })

    return {
        "season": target_season,
        "scope": scope,
        "location": norm_loc,
        "opponent": None,
        "opponents": season_opponents,
        "stats_url": stats_url,
        "team_stats": _build_team_stats(ds, target_season, scope, None, norm_loc),
        "skaters": _records(skaters_norm),
        "goalies": _records(goalies_norm),
    }


@app.get("/api/games")
def get_games(
    season: str | None = Query(default=None),
    opponent: str | None = Query(default=None),
    limit: int = Query(default=60, ge=1, le=300),
) -> dict[str, Any]:
    ds = _require_datasets()
    df = ds.games.copy()
    if season:
        df = df[df["season"] == season]
    if opponent:
        df = df[df["opponent"].str.contains(opponent, case=False, na=False)]
    df = df.sort_values("date", ascending=False).head(limit)
    return {
        "count": int(len(df)),
        "games": _records(df),
    }


@app.get("/api/rivalry")
def get_rivalry(
    opponent: str = Query(..., min_length=2),
    season: str | None = Query(default=None),
) -> dict[str, Any]:
    ds = _require_datasets()
    df = ds.games[ds.games["opponent"].str.lower() == opponent.strip().lower()].copy()
    if df.empty:
        df = ds.games[ds.games["opponent"].str.contains(opponent.strip(), case=False, na=False)].copy()

    matched_opponent = str(df["opponent"].iloc[0]) if not df.empty else opponent.strip()
    active_season = season.strip() if season and season.strip().lower() != "all" else None
    if active_season:
        df = df[df["season"] == active_season]

    wins = int((df["outcome"] == "W").sum())
    losses = int((df["outcome"] == "L").sum())
    ties = int((df["outcome"] == "T").sum())
    shootout_wins = int(((df["is_shootout"] == 1) & (df["shootout_winner"] == "Northeastern")).sum())
    ot_games = int((df["is_overtime"] == 1).sum())
    nu_goals = int(df["nu_goals"].sum()) if not df.empty else 0
    opp_goals = int(df["opp_goals"].sum()) if not df.empty else 0

    recent = df.sort_values("date", ascending=False)
    return {
        "opponent": matched_opponent,
        "season": active_season or "all",
        "games_played": int(len(df)),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "shootout_wins": shootout_wins,
        "ot_games": ot_games,
        "nu_goals": nu_goals,
        "opp_goals": opp_goals,
        "recent_games": _records(recent),
    }


_PLAYERS_CACHE: list[dict[str, Any]] | None = None


@app.get("/api/players")
def list_players() -> dict[str, Any]:
    global _PLAYERS_CACHE
    ds = _require_datasets()
    if _PLAYERS_CACHE is not None:
        return {"players": _PLAYERS_CACHE}

    players_map: dict[str, dict[str, Any]] = {}

    def _upsert(name: Any, season: Any = "", pos: Any = "") -> None:
        n = str(name).strip() if name is not None else ""
        if not n or n.lower() == "nan":
            return
        k = n.lower()
        s = str(season).strip() if season is not None else ""
        if s.lower() == "nan":
            s = ""
        p = str(pos).strip() if pos is not None else ""
        if p.lower() == "nan":
            p = ""
        if k not in players_map:
            players_map[k] = {
                "player_name": n,
                "position": p,
                "seasons": set(),
            }
        if s:
            players_map[k]["seasons"].add(s)
        if p and not players_map[k]["position"]:
            players_map[k]["position"] = p

    if not ds.rosters.empty:
        for n, s, p in zip(
            ds.rosters["player_name"].fillna(""),
            ds.rosters["season"].fillna(""),
            ds.rosters["position"].fillna("") if "position" in ds.rosters.columns else [""] * len(ds.rosters),
        ):
            _upsert(n, s, p)
    if not ds.season_stats.empty:
        for n, s, p in zip(
            ds.season_stats["player_name"].fillna(""),
            ds.season_stats["season"].fillna(""),
            ds.season_stats["position"].fillna("") if "position" in ds.season_stats.columns else [""] * len(ds.season_stats),
        ):
            _upsert(n, s, p)
    if not ds.skaters.empty:
        for n, s, p in zip(
            ds.skaters["player_name"].fillna(""),
            ds.skaters["season"].fillna(""),
            ds.skaters["position"].fillna("") if "position" in ds.skaters.columns else [""] * len(ds.skaters),
        ):
            _upsert(n, s, p)
    if not ds.goalies.empty:
        for n, s in zip(
            ds.goalies["goalie_name"].fillna(""),
            ds.goalies["season"].fillna(""),
        ):
            _upsert(n, s, "G")

    out = []
    for rec in players_map.values():
        seasons_sorted = sorted(rec["seasons"])
        span = (
            f"{seasons_sorted[0]}–{seasons_sorted[-1]}"
            if len(seasons_sorted) > 1
            else (seasons_sorted[0] if seasons_sorted else "")
        )
        out.append(
            {
                "player_name": rec["player_name"],
                "position": rec["position"],
                "seasons_span": span,
                "latest_season": seasons_sorted[-1] if seasons_sorted else "",
            }
        )
    out.sort(key=lambda x: x["player_name"].lower())
    _PLAYERS_CACHE = out
    return {"players": out}


@app.get("/api/player")
def get_player(name: str = Query(..., min_length=2)) -> dict[str, Any]:
    ds = _require_datasets()
    target = name.strip()

    roster_df = ds.rosters[ds.rosters["player_name"].str.lower() == target.lower()].copy()
    if roster_df.empty:
        roster_df = ds.rosters[ds.rosters["player_name"].str.contains(target, case=False, na=False, regex=False)].copy()

    stats_df = ds.season_stats[ds.season_stats["player_name"].str.lower() == target.lower()].copy()
    if stats_df.empty:
        stats_df = ds.season_stats[ds.season_stats["player_name"].str.contains(target, case=False, na=False, regex=False)].copy()

    sk_logs = ds.skaters[ds.skaters["player_name"].str.lower() == target.lower()].copy()
    gl_logs = ds.goalies[ds.goalies["goalie_name"].str.lower() == target.lower()].copy()

    if roster_df.empty and stats_df.empty and sk_logs.empty and gl_logs.empty:
        raise HTTPException(status_code=404, detail=f"Player '{target}' not found.")

    canonical_name = (
        str(roster_df["player_name"].iloc[0])
        if not roster_df.empty
        else (str(stats_df["player_name"].iloc[0]) if not stats_df.empty else target)
    )

    if not roster_df.empty:
        roster_df = roster_df.sort_values("season", ascending=False)
        latest_bio = roster_df.iloc[0].fillna("").to_dict()
        seasons_played = sorted({str(s) for s in roster_df["season"] if s}, reverse=True)
        imgs = [str(u).strip() for u in roster_df["image_url"].fillna("") if str(u).strip()] if "image_url" in roster_df.columns else []
        image_url = imgs[0] if imgs else ""
    elif not stats_df.empty:
        stats_sorted = stats_df.sort_values("season", ascending=False)
        latest_bio = stats_sorted.iloc[0].fillna("").to_dict()
        seasons_played = sorted({str(s) for s in stats_df["season"] if s}, reverse=True)
        image_url = ""
    else:
        latest_bio = {"player_name": canonical_name}
        seasons_played = []
        image_url = ""

    bio = {
        "player_name": canonical_name,
        "jersey_number": latest_bio.get("jersey_number", ""),
        "position": latest_bio.get("position", ""),
        "class_year": latest_bio.get("class_year", ""),
        "captain_role": latest_bio.get("captain_role", "None"),
        "height": latest_bio.get("height", ""),
        "weight": latest_bio.get("weight", ""),
        "shoots": latest_bio.get("shoots", ""),
        "hometown": latest_bio.get("hometown", ""),
        "previous_team": latest_bio.get("previous_team", ""),
        "previous_school": latest_bio.get("previous_school", ""),
        "major": latest_bio.get("major", ""),
        "head_coach": latest_bio.get("head_coach", ""),
        "roster_url": latest_bio.get("roster_url", ""),
        "image_url": image_url,
        "seasons_played": seasons_played,
    }

    stats_df = stats_df.sort_values("season", ascending=False) if not stats_df.empty else stats_df
    is_goalie = (
        bio["position"] == "G"
        or (not stats_df.empty and int(stats_df["goalie_gp"].sum()) > 0)
        or not gl_logs.empty
    )

    career_skater = None
    if not stats_df.empty and int(stats_df["gp"].sum()) > 0:
        fow = int(sk_logs["faceoffs_won"].sum()) if not sk_logs.empty and "faceoffs_won" in sk_logs.columns else 0
        fol = int(sk_logs["faceoffs_lost"].sum()) if not sk_logs.empty and "faceoffs_lost" in sk_logs.columns else 0
        total_shots = int(stats_df["shots"].sum()) if "shots" in stats_df.columns else 0
        total_goals = int(stats_df["goals"].sum())
        career_skater = {
            "gp": int(stats_df["gp"].sum()),
            "goals": total_goals,
            "assists": int(stats_df["assists"].sum()),
            "points": int(stats_df["points"].sum()),
            "shots": total_shots,
            "shooting_pct": round((total_goals / total_shots) * 100, 1) if total_shots > 0 else 0.0,
            "plus_minus": int(stats_df["plus_minus"].sum()),
            "pim": int(stats_df["pim"].sum()),
            "ppg": int(stats_df["ppg"].sum()),
            "shg": int(stats_df["shg"].sum()),
            "gwg": int(stats_df["gwg"].sum()),
            "otg": int(stats_df["otg"].sum()) if "otg" in stats_df.columns else 0,
            "blocked_shots": int(stats_df["blocked_shots"].sum()),
            "multi_goal_games": int((sk_logs["goals"] >= 2).sum()) if not sk_logs.empty else 0,
            "hat_tricks": int((sk_logs["goals"] >= 3).sum()) if not sk_logs.empty else 0,
            "multi_point_games": int((sk_logs["points"] >= 2).sum()) if not sk_logs.empty else 0,
            "faceoffs_won": fow,
            "faceoffs_lost": fol,
            "faceoff_pct": round((fow / (fow + fol)) * 100, 1) if (fow + fol) > 0 else None,
        }

    career_goalie = None
    if is_goalie and not stats_df.empty and int(stats_df["goalie_gp"].sum()) > 0:
        total_ga = int(stats_df["ga"].sum())
        total_saves = int(stats_df["saves"].sum())
        total_mins = sum(_parse_minutes_to_float(m) for m in stats_df["goalie_minutes"])
        tot_secs = int(round(total_mins * 60))
        career_goalie = {
            "goalie_gp": int(stats_df["goalie_gp"].sum()),
            "goalie_gs": int(stats_df["goalie_gs"].sum()) if "goalie_gs" in stats_df.columns else 0,
            "goalie_minutes": f"{tot_secs // 60}:{tot_secs % 60:02d}",
            "wins": int(stats_df["wins"].sum()),
            "losses": int(stats_df["losses"].sum()),
            "ties": int(stats_df["ties"].sum()),
            "saves": total_saves,
            "shots_against": total_saves + total_ga,
            "ga": total_ga,
            "shutouts": int(stats_df["shutouts"].sum()),
            "gaa": round((total_ga * 60.0) / total_mins, 2) if total_mins > 0 else round(float(stats_df["gaa"].mean()), 2),
            "save_pct": round(total_saves / (total_saves + total_ga), 3) if (total_saves + total_ga) > 0 else 0.0,
        }

    season_rows = _records(stats_df) if not stats_df.empty else []

    # Enrich season rows with faceoff, multi-goal, and multi-point totals aggregated from game-by-game skater logs
    if season_rows and not sk_logs.empty:
        sk_enriched = sk_logs.assign(
            _mgg=(sk_logs["goals"] >= 2).astype(int),
            _htg=(sk_logs["goals"] >= 3).astype(int),
            _mpg=(sk_logs["points"] >= 2).astype(int),
        )
        fo_all = (
            sk_enriched.groupby("season", as_index=False)[["faceoffs_won", "faceoffs_lost", "_mgg", "_htg", "_mpg"]]
            .sum()
            .set_index("season")
            .to_dict(orient="index")
        )
        sk_conf = sk_enriched[sk_enriched["opponent"].isin(HOCKEY_EAST_TEAMS)]
        fo_conf = (
            sk_conf.groupby("season", as_index=False)[["faceoffs_won", "faceoffs_lost", "_mgg", "_htg", "_mpg"]]
            .sum()
            .set_index("season")
            .to_dict(orient="index")
            if not sk_conf.empty
            else {}
        )
        for row in season_rows:
            sea = row.get("season", "")
            all_vals = fo_all.get(sea, {})
            conf_vals = fo_conf.get(sea, {})
            row["faceoffs_won"] = int(all_vals.get("faceoffs_won", 0))
            row["faceoffs_lost"] = int(all_vals.get("faceoffs_lost", 0))
            row["multi_goal_games"] = int(all_vals.get("_mgg", 0))
            row["hat_tricks"] = int(all_vals.get("_htg", 0))
            row["multi_point_games"] = int(all_vals.get("_mpg", 0))
            row["conf_faceoffs_won"] = int(conf_vals.get("faceoffs_won", 0))
            row["conf_faceoffs_lost"] = int(conf_vals.get("faceoffs_lost", 0))
            row["conf_multi_goal_games"] = int(conf_vals.get("_mgg", 0))
            row["conf_hat_tricks"] = int(conf_vals.get("_htg", 0))
            row["conf_multi_point_games"] = int(conf_vals.get("_mpg", 0))

    shootout_stats = {
        "attempts": 0,
        "made": 0,
        "pct": 0.0,
        "winners": 0,
        "faced": 0,
        "saves": 0,
        "allowed": 0,
        "save_pct": 0.0,
    }
    if not ds.shootouts.empty:
        so_sk = ds.shootouts[
            (ds.shootouts["shooter_team"] == "Northeastern")
            & (ds.shootouts["shooter_name"].str.lower() == canonical_name.lower())
        ]
        if not so_sk.empty:
            attempts = int(len(so_sk))
            made = int((so_sk["result"] == "MADE").sum())
            winners = int((so_sk["is_shootout_winner"] == 1).sum()) if "is_shootout_winner" in so_sk.columns else 0
            shootout_stats["attempts"] = attempts
            shootout_stats["made"] = made
            shootout_stats["pct"] = round((made / attempts) * 100, 1) if attempts > 0 else 0.0
            shootout_stats["winners"] = winners
        so_gl = ds.shootouts[
            (ds.shootouts["goalie_team"] == "Northeastern")
            & (ds.shootouts["goalie_name"].str.lower() == canonical_name.lower())
        ]
        if not so_gl.empty:
            faced = int(len(so_gl))
            allowed = int((so_gl["result"] == "MADE").sum())
            saves = faced - allowed
            shootout_stats["faced"] = faced
            shootout_stats["allowed"] = allowed
            shootout_stats["saves"] = saves
            shootout_stats["save_pct"] = round(saves / faced, 3) if faced > 0 else 0.0

    chemistry: list[dict[str, Any]] = []
    if not ds.goals.empty:
        nu_goals_ev = ds.goals[ds.goals["team"] == "Northeastern"]
        c_low = canonical_name.lower()
        partners: dict[str, dict[str, Any]] = {}

        def _bump(partner_name: str, field: str) -> None:
            pn = str(partner_name or "").strip()
            if not pn or pn.lower() == c_low:
                return
            rec = partners.setdefault(
                pn,
                {
                    "player_name": pn,
                    "total_connections": 0,
                    "assisted_by_them": 0,
                    "assisted_for_them": 0,
                },
            )
            rec[field] += 1
            rec["total_connections"] += 1

        rel_goals = nu_goals_ev[
            (nu_goals_ev["scorer"].str.lower() == c_low)
            | (nu_goals_ev["primary_assist"].str.lower() == c_low)
            | (nu_goals_ev["secondary_assist"].str.lower() == c_low)
        ]
        for _, gr in rel_goals.iterrows():
            sc = str(gr.get("scorer", "")).strip()
            a1 = str(gr.get("primary_assist", "")).strip()
            a2 = str(gr.get("secondary_assist", "")).strip()
            if sc.lower() == c_low:
                _bump(a1, "assisted_by_them")
                _bump(a2, "assisted_by_them")
            else:
                if a1.lower() == c_low or a2.lower() == c_low:
                    _bump(sc, "assisted_for_them")

        chemistry = sorted(
            partners.values(),
            key=lambda x: (-x["total_connections"], -x["assisted_for_them"], x["player_name"]),
        )[:12]

    if is_goalie and not gl_logs.empty:
        game_logs = _records(gl_logs.sort_values("date", ascending=False))
    else:
        game_logs = _records(sk_logs.sort_values("date", ascending=False))

    return {
        "bio": bio,
        "is_goalie": is_goalie,
        "career_skater": career_skater,
        "career_goalie": career_goalie,
        "shootout_stats": shootout_stats,
        "chemistry": chemistry,
        "seasons": season_rows,
        "game_logs": game_logs,
    }


@app.get("/api/boxscore")
def get_boxscore(
    date: str = Query(..., min_length=8),
    opponent: str = Query(..., min_length=1),
) -> dict[str, Any]:
    ds = _require_datasets()
    target_date = date.strip()
    target_opp = opponent.strip()

    game_df = ds.games[
        (ds.games["date"].astype(str).str.strip() == target_date)
        & (ds.games["opponent"].astype(str).str.strip().str.lower() == target_opp.lower())
    ]
    if game_df.empty:
        game_df = ds.games[ds.games["date"].astype(str).str.strip() == target_date]
    if game_df.empty:
        raise HTTPException(status_code=404, detail=f"Box score not found for {target_date} vs {target_opp}.")

    game_rec = _records(game_df.head(1))[0]
    canon_opp = str(game_rec.get("opponent", target_opp))

    def _match_game(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        m = df[
            (df["date"].astype(str).str.strip() == target_date)
            & (df["opponent"].astype(str).str.strip().str.lower() == canon_opp.lower())
        ]
        if m.empty and target_opp.lower() != canon_opp.lower():
            m = df[
                (df["date"].astype(str).str.strip() == target_date)
                & (df["opponent"].astype(str).str.strip().str.lower() == target_opp.lower())
            ]
        return m.copy()

    period_order = {"1st": 1, "2nd": 2, "3rd": 3, "OT": 4, "1OT": 4, "2OT": 5, "3OT": 6}

    goals_df = _match_game(ds.goals)
    if not goals_df.empty:
        goals_df = goals_df.assign(
            _pord=goals_df["period"].map(lambda x: period_order.get(str(x).strip(), 99)),
            _tsec=pd.to_numeric(goals_df["time_seconds"], errors="coerce").fillna(0),
        ).sort_values(["_pord", "_tsec"]).drop(columns=["_pord", "_tsec"])

    pen_df = _match_game(ds.penalties)
    if not pen_df.empty:
        nu_players: set[str] = set()
        for src_df, col in (
            (ds.rosters, "player_name"),
            (ds.season_stats, "player_name"),
            (ds.skaters, "player_name"),
            (ds.goalies, "goalie_name"),
        ):
            if not src_df.empty and col in src_df.columns:
                nu_players.update(str(n).strip().lower() for n in src_df[col].dropna() if str(n).strip())
        if nu_players:
            pen_df["team"] = pen_df.apply(
                lambda r: (
                    canon_opp
                    if str(r.get("team", "")).strip() == "Northeastern"
                    and str(r.get("player_name", "")).strip().lower() not in nu_players
                    and str(r.get("player_name", "")).strip().lower() not in ("team", "tm", "")
                    else r.get("team", "")
                ),
                axis=1,
            )
        pen_df = pen_df.assign(
            _pord=pen_df["period"].map(lambda x: period_order.get(str(x).strip(), 99)),
        ).sort_values(["_pord", "time"]).drop(columns=["_pord"])

    so_df = _match_game(ds.shootouts)
    if not so_df.empty and "round" in so_df.columns:
        so_df = so_df.assign(_rnd=pd.to_numeric(so_df["round"], errors="coerce").fillna(0)).sort_values("_rnd").drop(columns=["_rnd"])

    sk_df = _match_game(ds.skaters)
    if not sk_df.empty:
        sk_df = sk_df.sort_values(["points", "goals", "player_name"], ascending=[False, False, True])

    gl_df = _match_game(ds.goalies)

    return {
        "game": game_rec,
        "goals": _records(goals_df) if not goals_df.empty else [],
        "penalties": _records(pen_df) if not pen_df.empty else [],
        "shootouts": _records(so_df) if not so_df.empty else [],
        "skaters": _records(sk_df) if not sk_df.empty else [],
        "goalies": _records(gl_df) if not gl_df.empty else [],
    }


@app.get("/api/penalties")
def get_penalties(
    season: str | None = Query(default=None),
    scope: str = Query(default="all", pattern="^(all|conference)$"),
    opponent: str | None = Query(default=None),
    player: str | None = Query(default=None),
) -> dict[str, Any]:
    ds = _require_datasets()
    df = ds.penalties
    if df.empty:
        return {
            "season": season or "all",
            "scope": scope,
            "opponent": opponent,
            "player": player,
            "summary": {"total_penalties": 0, "total_pim": 0, "minors": 0, "majors": 0, "other": 0},
            "by_infraction": [],
            "by_period": [],
            "by_player": [],
            "by_season": [],
            "events": [],
        }

    df = df[df["team"] == "Northeastern"].copy()
    nu_players: set[str] = set()
    for src_df, col in (
        (ds.rosters, "player_name"),
        (ds.season_stats, "player_name"),
        (ds.skaters, "player_name"),
        (ds.goalies, "goalie_name"),
    ):
        if not src_df.empty and col in src_df.columns:
            nu_players.update(
                str(n).strip().lower()
                for n in src_df[col].dropna()
                if str(n).strip()
            )
    if nu_players:
        df = df[df["player_name"].astype(str).str.strip().str.lower().isin(nu_players)]
    target_season = season.strip() if season and season.strip() and season.strip().lower() != "all" else "all"
    if target_season != "all":
        df = df[df["season"] == target_season]
    if scope == "conference":
        df = df[df["opponent"].isin(HOCKEY_EAST_TEAMS)]
    target_opponent = opponent.strip() if opponent and opponent.strip() else None
    if target_opponent:
        df = df[df["opponent"].str.lower() == target_opponent.lower()]
    target_player = player.strip() if player and player.strip() else None
    if target_player:
        exact = df[df["player_name"].str.lower() == target_player.lower()]
        df = exact if not exact.empty else df[df["player_name"].str.contains(target_player, case=False, na=False)]

    if df.empty:
        return {
            "season": target_season,
            "scope": scope,
            "opponent": target_opponent,
            "player": target_player,
            "summary": {"total_penalties": 0, "total_pim": 0, "minors": 0, "majors": 0, "other": 0},
            "by_infraction": [],
            "by_period": [],
            "by_player": [],
            "by_season": [],
            "events": [],
        }

    pim_series = pd.to_numeric(df["penalty_minutes"], errors="coerce").fillna(0).astype(int)
    df = df.assign(_pim=pim_series)
    total_penalties = int(len(df))
    total_pim = int(df["_pim"].sum())
    minors = int((df["_pim"] == 2).sum())
    majors = int((df["_pim"] == 5).sum())
    other = int((~df["_pim"].isin([2, 5])).sum())

    infraction_series = df["infraction"].fillna("").astype(str).str.strip()
    df = df.assign(_infraction=infraction_series.replace("", "UNSPECIFIED"))
    inf_grp = (
        df.groupby("_infraction", as_index=False)
        .agg(count=("_pim", "size"), pim=("_pim", "sum"))
        .sort_values(["count", "pim", "_infraction"], ascending=[False, False, True])
    )
    by_infraction = [
        {"infraction": str(r["_infraction"]), "count": int(r["count"]), "pim": int(r["pim"])}
        for _, r in inf_grp.iterrows()
    ]

    period_order = {"1st": 1, "2nd": 2, "3rd": 3, "OT": 4, "1OT": 4, "2OT": 5, "3OT": 6}
    per_grp = df.groupby("period", as_index=False).agg(count=("_pim", "size"), pim=("_pim", "sum"))
    per_grp["_ord"] = per_grp["period"].map(lambda x: period_order.get(str(x).strip(), 99))
    per_grp = per_grp.sort_values(["_ord", "period"])
    by_period = [
        {"period": str(r["period"] or "Other"), "count": int(r["count"]), "pim": int(r["pim"])}
        for _, r in per_grp.iterrows()
    ]

    by_player: list[dict[str, Any]] = []
    if not target_player:
        pl_grp = (
            df.assign(
                _minor=(df["_pim"] == 2).astype(int),
                _major=(df["_pim"] == 5).astype(int),
                _other=(~df["_pim"].isin([2, 5])).astype(int),
            )
            .groupby("player_name", as_index=False)
            .agg(
                count=("_pim", "size"),
                pim=("_pim", "sum"),
                minors=("_minor", "sum"),
                majors=("_major", "sum"),
                other=("_other", "sum"),
            )
            .sort_values(["pim", "count", "player_name"], ascending=[False, False, True])
        )
        by_player = [
            {
                "player_name": str(r["player_name"]),
                "count": int(r["count"]),
                "pim": int(r["pim"]),
                "minors": int(r["minors"]),
                "majors": int(r["majors"]),
                "other": int(r["other"]),
            }
            for _, r in pl_grp.iterrows()
            if str(r["player_name"]).strip()
        ]

    sea_grp = (
        df.groupby("season", as_index=False)
        .agg(count=("_pim", "size"), pim=("_pim", "sum"))
        .sort_values("season", ascending=False)
    )
    by_season = [
        {"season": str(r["season"]), "count": int(r["count"]), "pim": int(r["pim"])}
        for _, r in sea_grp.iterrows()
    ]

    events_df = df.drop(columns=["_pim", "_infraction"]).sort_values(["date", "period", "time"], ascending=[False, True, True])
    return {
        "season": target_season,
        "scope": scope,
        "opponent": target_opponent,
        "player": target_player,
        "summary": {
            "total_penalties": total_penalties,
            "total_pim": total_pim,
            "minors": minors,
            "majors": majors,
            "other": other,
        },
        "by_infraction": by_infraction,
        "by_period": by_period,
        "by_player": by_player,
        "by_season": by_season,
        "events": _records(events_df),
    }


@app.get("/api/chat-token")
def get_chat_token(request: Request) -> dict[str, str]:
    _verify_browser_request(request)
    client_ip = _get_client_ip(request)
    if not state.limiter.allow(f"tok:{client_ip}"):
        raise HTTPException(
            status_code=429,
            detail="Too many token requests. Please wait a moment.",
        )
    return {"token": state.token_manager.issue()}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    ds = _require_datasets()
    if state.llm is None:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured on the server.",
        )

    _verify_browser_request(request)

    chat_token = request.headers.get("x-chat-token")
    if not state.token_manager.verify_and_consume(chat_token):
        raise HTTPException(
            status_code=403,
            detail="Invalid or expired chat session token. Please refresh and try again.",
        )

    client_ip = _get_client_ip(request)
    _, turnstile_secret = _turnstile_config()
    issued_turnstile_pass: str | None = None
    if turnstile_secret:
        turnstile_pass = request.headers.get("x-turnstile-pass")
        if not state.turnstile_sessions.verify(turnstile_pass, client_ip):
            turnstile_token = request.headers.get("x-turnstile-token")
            verified = await run_in_threadpool(_verify_turnstile_token, turnstile_token, client_ip)
            if not verified:
                raise HTTPException(
                    status_code=403,
                    detail="Human verification (Turnstile) failed or expired. Please complete the check and try again.",
                )
            issued_turnstile_pass = state.turnstile_sessions.issue(client_ip)
    if not state.chat_min_limiter.allow(client_ip):
        raise HTTPException(
            status_code=429,
            detail=(
                "⏳ **High Traffic Alert — Per-Minute Rate Limit Reached**\n\n"
                "You have asked several questions in a short period. Please wait **30 to 60 seconds** before asking your next question."
            ),
        )
    if not state.chat_hour_limiter.allow(client_ip):
        raise HTTPException(
            status_code=429,
            detail=(
                "⏳ **Hourly Question Limit Reached**\n\n"
                "You've reached the hourly limit for Ask Paws questions. Please wait a bit before asking more questions, "
                "or explore the Stats, Roster, and Opponents tabs in the meantime!"
            ),
        )
    if not state.chat_day_limiter.allow(client_ip):
        raise HTTPException(
            status_code=429,
            detail=(
                "🏒 **Daily Question Limit Reached (180/day)**\n\n"
                "You have reached your personal daily limit of 180 Ask Paws questions. Please check back tomorrow!"
            ),
        )

    history: list[dict[str, str]] = []
    for m in req.history:
        if m.role == "user":
            history.append({"role": "user", "content": m.content[:1000]})
        elif m.role == "assistant" and state.token_manager.verify_history_turn("assistant", m.content, m.sig):
            history.append({"role": "assistant", "content": m.content})

    # Check standalone cache before consuming global daily LLM budget
    if not history and not req.context:
        cached_ans = state.cache.get(req.question)
        if cached_ans is not None:
            return ChatResponse(
                answer=cached_ans,
                cached=True,
                turnstile_pass=issued_turnstile_pass,
                answer_sig=state.token_manager.sign_history_turn("assistant", cached_ans),
            )

    if not state.daily_budget.allow_and_increment():
        raise HTTPException(
            status_code=429,
            detail=(
                "🏒 **Daily API Quota Limit Reached**\n\n"
                "The Northeastern Men's Hockey assistant has reached today's shared AI usage budget. "
                "The daily limit resets automatically at midnight UTC. Please check back then!"
            ),
        )

    try:
        answer, from_cache = await run_in_threadpool(
            answer_question,
            req.question,
            ds,
            state.llm,
            history,
            state.cache,
            req.context,
        )
    except Exception as exc:
        _, friendly = classify_api_error(exc)
        return ChatResponse(answer=friendly, cached=False, turnstile_pass=issued_turnstile_pass)

    return ChatResponse(
        answer=answer,
        cached=from_cache,
        turnstile_pass=issued_turnstile_pass,
        answer_sig=state.token_manager.sign_history_turn("assistant", answer),
    )


class BugReportRequest(BaseModel):
    category: str = Field(..., min_length=2, max_length=60)
    description: str = Field(..., min_length=5, max_length=2000)
    page_context: str | None = Field(default=None, max_length=300)
    contact: str | None = Field(default=None, max_length=120)


class BugReportResponse(BaseModel):
    status: str
    id: str
    created_at: str


def _forward_bug_webhook(entry: dict[str, Any]) -> None:
    webhook_url = (os.getenv("BUG_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return
    lines = [
        f"**Bug Report #{entry['id']}** ({entry['category']})",
        f"> {entry['description']}",
    ]
    if entry.get("page_context"):
        lines.append(f"**View:** `{entry['page_context']}`")
    if entry.get("contact"):
        lines.append(f"**Contact:** {entry['contact']}")
    payload = json.dumps({
        "content": "\n".join(lines)[:1950],
        "allowed_mentions": {"parse": []},
    }).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "NU-Hockey-Explorer/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except (urllib.error.URLError, TimeoutError, OSError):
        pass


@app.post("/api/bug-report", response_model=BugReportResponse)
def submit_bug_report(req: BugReportRequest, request: Request) -> BugReportResponse:
    client_ip = _get_client_ip(request)
    if not state.limiter.allow(f"bug:{client_ip}"):
        raise HTTPException(
            status_code=429,
            detail="Too many reports submitted. Please wait a minute and try again.",
        )

    report_id = uuid.uuid4().hex[:8]
    created_at = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": report_id,
        "created_at": created_at,
        "category": req.category.strip(),
        "description": req.description.strip(),
        "page_context": req.page_context.strip() if req.page_context else "",
        "contact": req.contact.strip() if req.contact else "",
        "user_agent": request.headers.get("user-agent", ""),
    }

    with _bug_report_lock:
        BUG_REPORTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with BUG_REPORTS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    threading.Thread(target=_forward_bug_webhook, args=(entry,), daemon=True).start()

    return BugReportResponse(status="ok", id=report_id, created_at=created_at)


_ALLOWED_IMAGE_HOSTS = {
    "a.espncdn.com",
    "nuhuskies.com",
    "www.nuhuskies.com",
    "images.sidearmdev.com",
    "static.gonu.com",
}
_IMAGE_PROXY_CACHE: dict[str, tuple[bytes, str]] = {}
_IMAGE_PROXY_LOCK = threading.Lock()

try:
    import io
    from PIL import Image, ImageOps
    _PIL_AVAILABLE = True
except Exception:
    _PIL_AVAILABLE = False


def _fetch_proxied_image(url: str) -> tuple[bytes, str]:
    with _IMAGE_PROXY_LOCK:
        cached = _IMAGE_PROXY_CACHE.get(url)
    if cached is not None:
        return cached
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "image/png").split(";")[0].strip() or "image/png"
    if not ctype.startswith("image/"):
        raise HTTPException(status_code=502, detail="Upstream resource is not an image.")
    with _IMAGE_PROXY_LOCK:
        if len(_IMAGE_PROXY_CACHE) >= 1800:
            _IMAGE_PROXY_CACHE.clear()
        _IMAGE_PROXY_CACHE[url] = (data, ctype)
    return data, ctype


def _fetch_and_resize_proxied_image(
    url: str,
    w: int | None = None,
    h: int | None = None,
) -> tuple[bytes, str]:
    if not w and not h:
        return _fetch_proxied_image(url)
    cache_key = f"{url}|w={w or 0}|h={h or 0}"
    with _IMAGE_PROXY_LOCK:
        cached = _IMAGE_PROXY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    raw_data, raw_ctype = _fetch_proxied_image(url)
    if not _PIL_AVAILABLE or "svg" in raw_ctype.lower():
        return raw_data, raw_ctype

    try:
        with Image.open(io.BytesIO(raw_data)) as src_im:
            im = ImageOps.exif_transpose(src_im)
            has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
            im = im.convert("RGBA" if has_alpha else "RGB")
            src_w, src_h = im.size
            if src_w <= 0 or src_h <= 0:
                return raw_data, raw_ctype

            if w and h:
                target_ratio = w / h
                src_ratio = src_w / src_h
                if src_ratio > target_ratio:
                    crop_w = max(1, round(src_h * target_ratio))
                    left = max(0, (src_w - crop_w) // 2)
                    im = im.crop((left, 0, left + crop_w, src_h))
                elif src_ratio < target_ratio:
                    crop_h = max(1, round(src_w / target_ratio))
                    im = im.crop((0, 0, src_w, min(src_h, crop_h)))
                target_size = (w, h)
            elif w:
                target_size = (w, max(1, round(src_h * (w / src_w))))
            else:
                target_size = (max(1, round(src_w * (h / src_h))), h)

            if im.size != target_size:
                im = im.resize(target_size, Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            try:
                im.save(buf, format="WEBP", lossless=True, quality=100)
                out_ctype = "image/webp"
            except Exception:
                buf = io.BytesIO()
                im.save(buf, format="PNG", optimize=True)
                out_ctype = "image/png"
            out_data = buf.getvalue()
    except Exception:
        return raw_data, raw_ctype

    with _IMAGE_PROXY_LOCK:
        if len(_IMAGE_PROXY_CACHE) >= 1800:
            _IMAGE_PROXY_CACHE.clear()
        _IMAGE_PROXY_CACHE[cache_key] = (out_data, out_ctype)
    return out_data, out_ctype


@app.get("/api/image-proxy")
async def image_proxy(
    url: str = Query(..., min_length=10),
    w: int | None = Query(None, ge=16, le=600),
    h: int | None = Query(None, ge=16, le=600),
) -> Response:
    parsed = urllib.parse.urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in _ALLOWED_IMAGE_HOSTS:
        raise HTTPException(status_code=400, detail="Unsupported image host.")
    try:
        data, ctype = await run_in_threadpool(_fetch_and_resize_proxied_image, url.strip(), w, h)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Image unavailable.")
    return Response(
        content=data,
        media_type=ctype,
        headers={"Cache-Control": "public, max-age=86400"},
    )


_RECORDS_BASE_CACHE: dict[str, Any] = {}
_RECORDS_BASE_LOCK = threading.Lock()


def _get_cached_static_records(ds: HockeyDatasets) -> dict[str, Any]:
    v = getattr(ds, "dataset_version", None) or getattr(state, "dataset_version", None) or "default"
    with _RECORDS_BASE_LOCK:
        if _RECORDS_BASE_CACHE.get("version") == v and "data" in _RECORDS_BASE_CACHE:
            return _RECORDS_BASE_CACHE["data"]

    # 1. Single-Game Records
    sk = ds.skaters[ds.skaters["position"] != "G"].copy()
    most_points_game = _records(
        sk.sort_values(["points", "goals", "date"], ascending=[False, False, False])
        .head(15)[["date", "season", "player_name", "position", "opponent", "goals", "assists", "points", "nu_goals", "opp_goals"]]
    )
    most_goals_game = _records(
        sk.sort_values(["goals", "points", "date"], ascending=[False, False, False])
        .head(15)[["date", "season", "player_name", "position", "opponent", "goals", "assists", "points", "nu_goals", "opp_goals"]]
    )
    most_assists_game = _records(
        sk.sort_values(["assists", "points", "date"], ascending=[False, False, False])
        .head(15)[["date", "season", "player_name", "position", "opponent", "goals", "assists", "points", "nu_goals", "opp_goals"]]
    )
    gl = ds.goalies.copy()
    most_saves_game = _records(
        gl.sort_values(["saves", "date"], ascending=[False, False])
        .head(15)[["date", "season", "goalie_name", "opponent", "saves", "goals_against", "save_pct", "decision", "nu_goals", "opp_goals"]]
    )

    # Fastest goals from opening faceoff (1st period, team == Northeastern)
    nu_goals = ds.goals[ds.goals["team"] == "Northeastern"].copy()
    p1_goals = nu_goals[(nu_goals["period"] == "1st") & (nu_goals["time_seconds"] > 0)].sort_values("time_seconds", ascending=True).head(12)
    fastest_opening_goals = _records(
        p1_goals[["date", "season", "scorer", "primary_assist", "secondary_assist", "opponent", "time", "time_seconds", "strength"]]
    )

    # Fastest 2 goals by same player in a single game
    period_offset = {"1st": 0, "2nd": 1200, "3rd": 2400, "OT": 3600, "1OT": 3600, "2OT": 4800, "3OT": 6000}
    nu_g_abs = nu_goals.copy()
    nu_g_abs["_abs_sec"] = nu_g_abs.apply(
        lambda r: period_offset.get(str(r.get("period", "")).strip(), 3600) + float(r.get("time_seconds", 0) or 0),
        axis=1,
    )
    nu_g_abs = nu_g_abs.sort_values(["date", "opponent", "scorer", "_abs_sec"])
    fastest_two_list: list[dict[str, Any]] = []
    for (d_val, opp_val, sc_val), grp in nu_g_abs.groupby(["date", "opponent", "scorer"]):
        if not sc_val or len(grp) < 2:
            continue
        rows = grp.to_dict(orient="records")
        for i in range(len(rows) - 1):
            diff = rows[i + 1]["_abs_sec"] - rows[i]["_abs_sec"]
            if 0 < diff <= 600:
                mins = int(diff) // 60
                secs = int(round(diff - mins * 60))
                fastest_two_list.append({
                    "date": str(d_val),
                    "season": str(rows[i].get("season", "")),
                    "player_name": str(sc_val),
                    "opponent": str(opp_val),
                    "span_seconds": round(float(diff), 1),
                    "span_display": f"{mins}:{secs:02d}",
                    "goal1_time": f"{rows[i]['period']} {rows[i]['time']}",
                    "goal2_time": f"{rows[i + 1]['period']} {rows[i + 1]['time']}",
                })
    fastest_two_list.sort(key=lambda x: x["span_seconds"])
    fastest_two_goals = fastest_two_list[:12]

    # 2. Player & Team Streaks
    sk_sorted = sk.sort_values("date")
    point_streaks: list[dict[str, Any]] = []
    goal_streaks: list[dict[str, Any]] = []
    for pname, grp in sk_sorted.groupby("player_name"):
        if not pname or len(grp) < 4:
            continue
        # Point streak
        cur_len, cur_pts, cur_g, cur_a = 0, 0, 0, 0
        cur_start, cur_end, cur_sea = "", "", ""
        for r in grp.itertuples():
            pts = int(getattr(r, "points", 0) or 0)
            gls = int(getattr(r, "goals", 0) or 0)
            ast = int(getattr(r, "assists", 0) or 0)
            dt = str(getattr(r, "date", ""))
            sea = str(getattr(r, "season", ""))
            if pts > 0:
                if cur_len == 0:
                    cur_start = dt
                    cur_sea = sea
                cur_len += 1
                cur_pts += pts
                cur_g += gls
                cur_a += ast
                cur_end = dt
            else:
                if cur_len >= 6:
                    point_streaks.append({
                        "player_name": str(pname),
                        "season": cur_sea,
                        "streak_games": cur_len,
                        "goals": cur_g,
                        "assists": cur_a,
                        "points": cur_pts,
                        "start_date": cur_start,
                        "end_date": cur_end,
                    })
                cur_len, cur_pts, cur_g, cur_a = 0, 0, 0, 0
        if cur_len >= 6:
            point_streaks.append({
                "player_name": str(pname),
                "season": cur_sea,
                "streak_games": cur_len,
                "goals": cur_g,
                "assists": cur_a,
                "points": cur_pts,
                "start_date": cur_start,
                "end_date": cur_end,
            })

        # Goal streak
        cur_len, cur_g = 0, 0
        cur_start, cur_end, cur_sea = "", "", ""
        for r in grp.itertuples():
            gls = int(getattr(r, "goals", 0) or 0)
            dt = str(getattr(r, "date", ""))
            sea = str(getattr(r, "season", ""))
            if gls > 0:
                if cur_len == 0:
                    cur_start = dt
                    cur_sea = sea
                cur_len += 1
                cur_g += gls
                cur_end = dt
            else:
                if cur_len >= 4:
                    goal_streaks.append({
                        "player_name": str(pname),
                        "season": cur_sea,
                        "streak_games": cur_len,
                        "goals": cur_g,
                        "start_date": cur_start,
                        "end_date": cur_end,
                    })
                cur_len, cur_g = 0, 0
        if cur_len >= 4:
            goal_streaks.append({
                "player_name": str(pname),
                "season": cur_sea,
                "streak_games": cur_len,
                "goals": cur_g,
                "start_date": cur_start,
                "end_date": cur_end,
            })

    point_streaks.sort(key=lambda x: (-x["streak_games"], -x["points"], x["end_date"]))
    goal_streaks.sort(key=lambda x: (-x["streak_games"], -x["goals"], x["end_date"]))

    # Team Win & Unbeaten streaks
    gm_sorted = ds.games.sort_values("date")
    win_streaks: list[dict[str, Any]] = []
    unbeaten_streaks: list[dict[str, Any]] = []
    w_len, w_start, w_end, w_sea = 0, "", "", ""
    u_len, u_w, u_t, u_start, u_end, u_sea = 0, 0, 0, "", "", ""
    for r in gm_sorted.itertuples():
        out = str(getattr(r, "outcome", ""))
        dt = str(getattr(r, "date", ""))
        sea = str(getattr(r, "season", ""))
        if out == "W":
            if w_len == 0:
                w_start, w_sea = dt, sea
            w_len += 1
            w_end = dt
        else:
            if w_len >= 5:
                win_streaks.append({"streak_games": w_len, "season": w_sea, "start_date": w_start, "end_date": w_end})
            w_len = 0

        if out in ("W", "T"):
            if u_len == 0:
                u_start, u_sea = dt, sea
            u_len += 1
            if out == "W":
                u_w += 1
            else:
                u_t += 1
            u_end = dt
        else:
            if u_len >= 6:
                unbeaten_streaks.append({
                    "streak_games": u_len,
                    "record": f"{u_w}-{0}-{u_t}",
                    "season": u_sea,
                    "start_date": u_start,
                    "end_date": u_end,
                })
            u_len, u_w, u_t = 0, 0, 0
    if w_len >= 5:
        win_streaks.append({"streak_games": w_len, "season": w_sea, "start_date": w_start, "end_date": w_end})
    if u_len >= 6:
        unbeaten_streaks.append({
            "streak_games": u_len,
            "record": f"{u_w}-{0}-{u_t}",
            "season": u_sea,
            "start_date": u_start,
            "end_date": u_end,
        })
    win_streaks.sort(key=lambda x: (-x["streak_games"], x["end_date"]))
    unbeaten_streaks.sort(key=lambda x: (-x["streak_games"], x["end_date"]))

    # 3. Active Milestone Watch
    # Pick latest season that has active games/stats (plus current roster players)
    stats_seasons = sorted(ds.season_stats[ds.season_stats["gp"] > 0]["season"].unique(), reverse=True)
    active_season = stats_seasons[0] if stats_seasons else (ds.available_seasons[0] if ds.available_seasons else "")
    latest_roster_season = ds.available_seasons[0] if ds.available_seasons else active_season
    active_names = set(
        ds.rosters[ds.rosters["season"].isin([active_season, latest_roster_season])]["player_name"].dropna().unique()
    ) | set(
        ds.season_stats[ds.season_stats["season"] == active_season]["player_name"].dropna().unique()
    )

    career_df = ds.season_stats[ds.season_stats["player_name"].isin(active_names)].copy()
    milestones: list[dict[str, Any]] = []
    if not career_df.empty:
        sk_c = (
            career_df.groupby("player_name", as_index=False)
            .agg(
                position=("position", "last"),
                class_year=("class_year", "last"),
                jersey_number=("jersey_number", "last"),
                gp=("gp", "sum"),
                goals=("goals", "sum"),
                assists=("assists", "sum"),
                points=("points", "sum"),
                goalie_gp=("goalie_gp", "sum"),
                wins=("wins", "sum"),
                saves=("saves", "sum"),
            )
        )
        thresholds = [
            ("Points", "points", [25, 50, 75, 100, 125, 150], 12),
            ("Goals", "goals", [15, 25, 40, 50, 75], 6),
            ("Assists", "assists", [25, 50, 75, 100], 8),
            ("Games Played", "gp", [50, 100, 125, 150], 12),
            ("Goalie Wins", "wins", [15, 25, 40, 50, 60], 5),
            ("Career Saves", "saves", [500, 1000, 1500, 2000, 2500], 220),
        ]
        for r in sk_c.to_dict(orient="records"):
            for label, col, t_list, max_gap in thresholds:
                val = int(r.get(col, 0) or 0)
                if val <= 0:
                    continue
                for target in t_list:
                    needed = target - val
                    if 0 < needed <= max_gap:
                        milestones.append({
                            "player_name": str(r["player_name"]),
                            "position": str(r.get("position", "")),
                            "class_year": str(r.get("class_year", "")),
                            "jersey_number": str(r.get("jersey_number", "")),
                            "category": label,
                            "current": val,
                            "target": target,
                            "needed": needed,
                            "progress_pct": round((val / target) * 100.0, 1),
                        })
                        break
    milestones.sort(key=lambda x: (-x["progress_pct"], x["needed"], x["player_name"]))

    # 4. Clutch & Late-Game Leaders
    ot_goals_ev = nu_goals[nu_goals["period"].isin(["OT", "1OT", "2OT", "3OT"])]
    ot_leaders_df = (
        ot_goals_ev.groupby("scorer", as_index=False)
        .agg(ot_goals=("date", "count"), gwg=("is_gwg", "sum"))
        .rename(columns={"scorer": "player_name"})
        .sort_values(["ot_goals", "gwg"], ascending=[False, False])
        .head(15)
    ) if not ot_goals_ev.empty else pd.DataFrame()

    p3_gwg_ev = nu_goals[(nu_goals["period"] == "3rd") & (nu_goals["is_gwg"] == 1)]
    p3_gwg_df = (
        p3_gwg_ev.groupby("scorer", as_index=False)
        .agg(third_period_gwg=("date", "count"))
        .rename(columns={"scorer": "player_name"})
        .sort_values("third_period_gwg", ascending=False)
        .head(15)
    ) if not p3_gwg_ev.empty else pd.DataFrame()

    # Final 5 minutes of regulation (3rd period, time_seconds >= 900) or OT tying/go-ahead goals
    late_clutch_ev = nu_goals[
        ((nu_goals["period"] == "3rd") & (nu_goals["time_seconds"] >= 900) & (nu_goals["nu_score_after"] >= nu_goals["opp_score_after"]) & ((nu_goals["nu_score_after"] - nu_goals["opp_score_after"]) <= 1))
        | (nu_goals["period"].isin(["OT", "1OT", "2OT", "3OT"]))
    ]
    late_clutch_df = (
        late_clutch_ev.groupby("scorer", as_index=False)
        .agg(
            clutch_goals=("date", "count"),
            gwg=("is_gwg", "sum"),
        )
        .rename(columns={"scorer": "player_name"})
        .sort_values(["clutch_goals", "gwg"], ascending=[False, False])
        .head(15)
    ) if not late_clutch_ev.empty else pd.DataFrame()

    nu_so = ds.shootouts[ds.shootouts["shooter_team"] == "Northeastern"].copy()
    so_leaders_list: list[dict[str, Any]] = []
    if not nu_so.empty:
        nu_so["_made"] = (nu_so["result"] == "MADE").astype(int)
        so_grp = (
            nu_so.groupby("shooter_name", as_index=False)
            .agg(
                attempts=("round", "count"),
                made=("_made", "sum"),
                winners=("is_shootout_winner", "sum"),
            )
            .rename(columns={"shooter_name": "player_name"})
        )
        so_grp = so_grp[so_grp["made"] > 0]
        so_grp["pct"] = so_grp.apply(lambda r: round((r["made"] / r["attempts"]) * 100.0, 1) if r["attempts"] > 0 else 0.0, axis=1)
        so_grp = so_grp.sort_values(["made", "winners", "pct"], ascending=[False, False, False]).head(15)
        so_leaders_list = _records(so_grp)

    data = {
        "single_game_records": {
            "most_points": most_points_game,
            "most_goals": most_goals_game,
            "most_assists": most_assists_game,
            "most_saves": most_saves_game,
            "fastest_opening_goals": fastest_opening_goals,
            "fastest_two_goals": fastest_two_goals,
        },
        "streaks": {
            "point_streaks": point_streaks[:15],
            "goal_streaks": goal_streaks[:15],
            "team_win_streaks": win_streaks[:10],
            "team_unbeaten_streaks": unbeaten_streaks[:10],
        },
        "milestones": {
            "active_season": active_season,
            "items": milestones[:18],
        },
        "clutch_leaders": {
            "ot_goals": _records(ot_leaders_df),
            "third_period_gwg": _records(p3_gwg_df),
            "late_clutch_goals": _records(late_clutch_df),
            "shootout_leaders": so_leaders_list,
        },
    }
    with _RECORDS_BASE_LOCK:
        _RECORDS_BASE_CACHE["version"] = v
        _RECORDS_BASE_CACHE["data"] = data
    return data


def _build_chemistry_data(ds: HockeyDatasets, season: str = "all", strength: str = "all") -> dict[str, Any]:
    nu_goals = ds.goals[ds.goals["team"] == "Northeastern"].copy()
    if season and season != "all":
        nu_goals = nu_goals[nu_goals["season"] == season]
    if strength and strength.lower() != "all":
        st_up = strength.upper()
        if st_up == "EV":
            nu_goals = nu_goals[~nu_goals["strength"].isin(["PP", "SH"])]
        else:
            nu_goals = nu_goals[nu_goals["strength"] == st_up]

    duos_map: dict[tuple[str, str], dict[str, Any]] = {}
    trios_map: dict[tuple[str, str, str], dict[str, Any]] = {}

    for r in nu_goals.itertuples():
        sc = str(getattr(r, "scorer", "") or "").strip()
        a1 = str(getattr(r, "primary_assist", "") or "").strip()
        a2 = str(getattr(r, "secondary_assist", "") or "").strip()
        st = str(getattr(r, "strength", "EV") or "EV").strip()
        gwg = int(getattr(r, "is_gwg", 0) or 0)
        if not sc:
            continue

        for idx, ast in enumerate([a1, a2]):
            if not ast or ast == sc:
                continue
            pair = tuple(sorted([sc, ast]))
            entry = duos_map.setdefault(pair, {
                "player_a": pair[0],
                "player_b": pair[1],
                "total_goals": 0,
                "primary_connections": 0,
                "secondary_connections": 0,
                "pp_goals": 0,
                "gwg": 0,
                "a_to_b": 0,
                "b_to_a": 0,
            })
            entry["total_goals"] += 1
            if idx == 0:
                entry["primary_connections"] += 1
            else:
                entry["secondary_connections"] += 1
            if st == "PP":
                entry["pp_goals"] += 1
            if gwg:
                entry["gwg"] += 1
            if ast == pair[0]:
                entry["a_to_b"] += 1
            else:
                entry["b_to_a"] += 1

        if a1 and a2 and len({sc, a1, a2}) == 3:
            trio = tuple(sorted([sc, a1, a2]))
            t_entry = trios_map.setdefault(trio, {
                "players": f"{trio[0]} · {trio[1]} · {trio[2]}",
                "player_1": trio[0],
                "player_2": trio[1],
                "player_3": trio[2],
                "total_goals": 0,
                "pp_goals": 0,
                "ev_goals": 0,
                "gwg": 0,
            })
            t_entry["total_goals"] += 1
            if st == "PP":
                t_entry["pp_goals"] += 1
            else:
                t_entry["ev_goals"] += 1
            if gwg:
                t_entry["gwg"] += 1

    top_duos = sorted(
        duos_map.values(),
        key=lambda x: (-x["total_goals"], -x["primary_connections"], x["player_a"]),
    )[:25]
    for d in top_duos:
        d["breakdown"] = f"{d['player_a']}→{d['player_b']} ({d['a_to_b']}) · {d['player_b']}→{d['player_a']} ({d['b_to_a']})"

    top_trios = sorted(
        trios_map.values(),
        key=lambda x: (-x["total_goals"], -x["ev_goals"], x["players"]),
    )[:20]

    return {
        "season": season,
        "strength": strength,
        "top_duos": top_duos,
        "top_trios": top_trios,
    }


def _build_on_this_day(ds: HockeyDatasets, mmdd: str | None = None) -> dict[str, Any]:
    games = ds.games.copy()
    if games.empty:
        return {"requested_mmdd": mmdd or "", "resolved_mmdd": "", "games": [], "highlights": [], "available_dates": []}

    games["mmdd"] = games["date"].astype(str).str.slice(5, 10)
    avail_dates = sorted(games["mmdd"].dropna().unique())
    today_mmdd = datetime.now().strftime("%m-%d")
    req_mmdd = (mmdd or "").strip()
    if not re.match(r"^\d{2}-\d{2}$", req_mmdd):
        req_mmdd = today_mmdd

    resolved_mmdd = req_mmdd
    if resolved_mmdd not in avail_dates and avail_dates:
        # Pick the closest historical hockey date (prefer same or next date on calendar, wrapping around)
        after = [d for d in avail_dates if d >= resolved_mmdd]
        resolved_mmdd = after[0] if after else avail_dates[-1]

    day_games = games[games["mmdd"] == resolved_mmdd].sort_values("date", ascending=False)
    wins = int((day_games["outcome"] == "W").sum())
    losses = int((day_games["outcome"] == "L").sum())
    ties = int((day_games["outcome"] == "T").sum())

    day_dates = set(day_games["date"].astype(str))
    sk_day = ds.skaters[ds.skaters["date"].isin(day_dates)]
    gl_day = ds.goalies[ds.goalies["date"].isin(day_dates)]
    g_day = ds.goals[(ds.goals["date"].isin(day_dates)) & (ds.goals["team"] == "Northeastern")]

    highlights: list[dict[str, Any]] = []
    # Hat tricks & 4+ point performances
    for r in sk_day[(sk_day["goals"] >= 3) | (sk_day["points"] >= 4)].sort_values(["goals", "points"], ascending=[False, False]).itertuples():
        gls = int(getattr(r, "goals", 0) or 0)
        ast = int(getattr(r, "assists", 0) or 0)
        pts = int(getattr(r, "points", 0) or 0)
        dt = str(getattr(r, "date", ""))
        opp = str(getattr(r, "opponent", ""))
        pname = str(getattr(r, "player_name", ""))
        badge = "Hat Trick" if gls >= 3 else f"{pts}-Point Game"
        highlights.append({
            "type": badge,
            "date": dt,
            "season": str(getattr(r, "season", "")),
            "opponent": opp,
            "player_name": pname,
            "headline": f"{pname}: {gls}G, {ast}A ({pts} PTS) vs. {opp}",
        })

    # OT game-winners
    for r in g_day[(g_day["period"].isin(["OT", "1OT", "2OT", "3OT"])) & (g_day["is_gwg"] == 1)].itertuples():
        dt = str(getattr(r, "date", ""))
        opp = str(getattr(r, "opponent", ""))
        sc = str(getattr(r, "scorer", ""))
        tm = str(getattr(r, "time", ""))
        prd = str(getattr(r, "period", "OT"))
        highlights.append({
            "type": "OT Winner",
            "date": dt,
            "season": str(getattr(r, "season", "")),
            "opponent": opp,
            "player_name": sc,
            "headline": f"{sc} scored the {prd} winner at {tm} vs. {opp}",
        })

    # Shutouts & 40+ save performances
    for r in gl_day[(gl_day["shutouts"] > 0) | ((gl_day["saves"] >= 40) & (gl_day["decision"] == "W"))].sort_values("saves", ascending=False).itertuples():
        dt = str(getattr(r, "date", ""))
        opp = str(getattr(r, "opponent", ""))
        gname = str(getattr(r, "goalie_name", ""))
        sv = int(getattr(r, "saves", 0) or 0)
        sho = int(getattr(r, "shutouts", 0) or 0)
        badge = "Shutout" if sho > 0 else "40+ Save Win"
        highlights.append({
            "type": badge,
            "date": dt,
            "season": str(getattr(r, "season", "")),
            "opponent": opp,
            "player_name": gname,
            "headline": f"{gname} posted a {sv}-save {'shutout' if sho > 0 else 'victory'} vs. {opp}",
        })

    return {
        "requested_mmdd": req_mmdd,
        "resolved_mmdd": resolved_mmdd,
        "record": f"{wins}-{losses}-{ties}",
        "games_count": int(len(day_games)),
        "games": _records(day_games.drop(columns=["mmdd"])),
        "highlights": highlights[:12],
        "available_dates": avail_dates,
    }


@app.get("/api/records")
def get_program_records(
    position: str = Query(default="all", pattern="^(all|F|D|G|f|d|g)$"),
    class_year: str = Query(default="all"),
    chemistry_season: str = Query(default="all"),
    chemistry_strength: str = Query(default="all", pattern="^(all|EV|PP|SH|ev|pp|sh)$"),
    mmdd: str | None = Query(default=None),
    limit: int = Query(default=25, ge=5, le=100),
) -> dict[str, Any]:
    ds = _require_datasets()
    pos_filter = position.upper() if position and position.lower() in ("f", "d", "g") else "all"
    cls_filter = class_year.strip() if class_year and class_year.strip().lower() != "all" else "all"

    df = ds.season_stats.copy()
    sk_df = df[(df["gp"] > 0) & (df["position"] != "G")].copy()
    if pos_filter in ("F", "D"):
        sk_df = sk_df[sk_df["position"] == pos_filter]
    if cls_filter != "all":
        sk_df = sk_df[sk_df["class_year"].str.lower() == cls_filter.lower()]

    # Single-season skaters
    ss_sk = sk_df.sort_values(["points", "goals", "gp"], ascending=[False, False, True]).head(limit)
    single_season_skaters = _records(
        ss_sk[[
            "season", "player_name", "position", "class_year", "captain_role",
            "gp", "goals", "assists", "points", "ppg", "shg", "gwg", "otg", "shots", "shot_pct", "plus_minus", "pim",
        ]]
    )

    # Career skaters (filtered by position and optional class_year slice)
    career_sk_list: list[dict[str, Any]] = []
    if not sk_df.empty:
        c_sk = (
            sk_df.groupby("player_name", as_index=False)
            .agg(
                position=("position", "last"),
                seasons=("season", "nunique"),
                first_season=("season", "min"),
                last_season=("season", "max"),
                gp=("gp", "sum"),
                goals=("goals", "sum"),
                assists=("assists", "sum"),
                points=("points", "sum"),
                ppg=("ppg", "sum"),
                shg=("shg", "sum"),
                gwg=("gwg", "sum"),
                otg=("otg", "sum"),
                shots=("shots", "sum"),
                plus_minus=("plus_minus", "sum"),
                pim=("pim", "sum"),
            )
        )
        c_sk["pts_per_gp"] = c_sk.apply(lambda r: round(r["points"] / r["gp"], 2) if r["gp"] > 0 else 0.0, axis=1)
        c_sk["span"] = c_sk.apply(
            lambda r: r["first_season"] if r["first_season"] == r["last_season"] else f"{r['first_season']}–{r['last_season'][-2:]}",
            axis=1,
        )
        c_sk = c_sk.sort_values(["points", "goals", "gp"], ascending=[False, False, True]).head(limit)
        career_sk_list = _records(c_sk)

    # Single-season & Career Goalies
    gl_df = df[df["goalie_gp"] > 0].copy()
    if cls_filter != "all":
        gl_df = gl_df[gl_df["class_year"].str.lower() == cls_filter.lower()]

    ss_gl = gl_df[gl_df["goalie_gp"] >= 10].sort_values(["wins", "save_pct", "shutouts"], ascending=[False, False, False]).head(limit)
    single_season_goalies = _records(
        ss_gl[[
            "season", "player_name", "class_year", "goalie_gp", "goalie_gs",
            "wins", "losses", "ties", "saves", "ga", "gaa", "save_pct", "shutouts",
        ]]
    )

    career_gl_list: list[dict[str, Any]] = []
    if not gl_df.empty:
        c_gl = (
            gl_df.groupby("player_name", as_index=False)
            .agg(
                seasons=("season", "nunique"),
                first_season=("season", "min"),
                last_season=("season", "max"),
                goalie_gp=("goalie_gp", "sum"),
                goalie_gs=("goalie_gs", "sum"),
                wins=("wins", "sum"),
                losses=("losses", "sum"),
                ties=("ties", "sum"),
                saves=("saves", "sum"),
                ga=("ga", "sum"),
                shutouts=("shutouts", "sum"),
                gaa=("gaa", "mean"),
            )
        )
        c_gl["save_pct"] = c_gl.apply(
            lambda r: round(r["saves"] / (r["saves"] + r["ga"]), 3) if (r["saves"] + r["ga"]) > 0 else 0.0,
            axis=1,
        )
        c_gl["gaa"] = c_gl["gaa"].round(2)
        c_gl["span"] = c_gl.apply(
            lambda r: r["first_season"] if r["first_season"] == r["last_season"] else f"{r['first_season']}–{r['last_season'][-2:]}",
            axis=1,
        )
        c_gl = c_gl[c_gl["goalie_gp"] >= 10].sort_values(["wins", "save_pct", "shutouts"], ascending=[False, False, False]).head(limit)
        career_gl_list = _records(c_gl)

    static_rec = _get_cached_static_records(ds)
    chemistry_data = _build_chemistry_data(ds, chemistry_season, chemistry_strength)
    otd_data = _build_on_this_day(ds, mmdd)

    return {
        "filters": {
            "position": pos_filter,
            "class_year": cls_filter,
            "chemistry_season": chemistry_season,
            "chemistry_strength": chemistry_strength,
        },
        "career_skaters": career_sk_list,
        "single_season_skaters": single_season_skaters,
        "career_goalies": career_gl_list,
        "single_season_goalies": single_season_goalies,
        "single_game_records": static_rec["single_game_records"],
        "streaks": static_rec["streaks"],
        "milestones": static_rec["milestones"],
        "clutch_leaders": static_rec["clutch_leaders"],
        "chemistry": chemistry_data,
        "on_this_day": otd_data,
    }


FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST_DIR.is_dir():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def serve_spa(full_path: str):
        if full_path.startswith("api/") or any(part.startswith(".") for part in full_path.split("/") if part):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (FRONTEND_DIST_DIR / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(FRONTEND_DIST_DIR.resolve()):
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST_DIR / "index.html"))

