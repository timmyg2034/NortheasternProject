"""FastAPI backend for Northeastern Men's Hockey Stats Explorer."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
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
from fastapi.responses import FileResponse
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


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=16)
    context: str | None = Field(default=None, max_length=300)


class ChatResponse(BaseModel):
    answer: str
    cached: bool = False
    turnstile_pass: str | None = None


class _AppState:
    datasets: HockeyDatasets | None = None
    llm: Any = None
    cache: ResponseCache = ResponseCache(ttl_seconds=86400, max_entries=1000)
    limiter: RateLimiter = RateLimiter(max_requests=20, window_seconds=60)
    chat_min_limiter: RateLimiter = RateLimiter(max_requests=RATE_LIMIT_MAX, window_seconds=60)
    chat_hour_limiter: RateLimiter = RateLimiter(max_requests=RATE_LIMIT_HOUR_MAX, window_seconds=3600)
    chat_day_limiter: RateLimiter = RateLimiter(max_requests=RATE_LIMIT_DAY_MAX, window_seconds=86400)
    daily_budget: DailyBudgetTracker = DailyBudgetTracker(max_daily_calls=MAX_DAILY_LLM_CALLS)
    token_manager: ChatTokenManager = ChatTokenManager()
    turnstile_sessions: TurnstileSessionManager = TurnstileSessionManager()


state = _AppState()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    state.datasets = load_datasets(DATA_DIR)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
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


def _build_team_stats(
    ds: Any,
    target_season: str,
    scope: str,
    target_opponent: str | None,
) -> dict[str, Any]:
    games_df = ds.games if target_season == "all" else ds.games[ds.games["season"] == target_season]
    if scope == "conference":
        games_df = games_df[games_df["opponent"].isin(HOCKEY_EAST_TEAMS)]
    if target_opponent:
        games_df = games_df[games_df["opponent"].str.lower() == target_opponent.lower()]

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

    ppg: int | None = None
    shg: int | None = None
    if target_opponent:
        sk_df = ds.skaters if target_season == "all" else ds.skaters[ds.skaters["season"] == target_season]
        sk_df = sk_df[(sk_df["opponent"].str.lower() == target_opponent.lower()) & (sk_df["position"] != "G")]
        shots = int(sk_df["shots"].sum()) if not sk_df.empty else 0
        pim = int(sk_df["penalty_minutes"].sum()) if not sk_df.empty else 0
        blocked_shots = int(sk_df["blocked_shots"].sum()) if not sk_df.empty else 0

        gl_df = ds.goalies if target_season == "all" else ds.goalies[ds.goalies["season"] == target_season]
        gl_df = gl_df[gl_df["opponent"].str.lower() == target_opponent.lower()]
        saves = int(gl_df["saves"].sum()) if not gl_df.empty else 0
        ga = int(gl_df["goals_against"].sum()) if not gl_df.empty else 0
    else:
        prefix = "conf_" if scope == "conference" else ""
        season_rows = ds.season_stats if target_season == "all" else ds.season_stats[ds.season_stats["season"] == target_season]
        sk_rows = season_rows[season_rows["position"] != "G"]
        shots = int(sk_rows[f"{prefix}shots"].sum()) if not sk_rows.empty else 0
        ppg = int(sk_rows[f"{prefix}ppg"].sum()) if not sk_rows.empty else 0
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
        if target_season != "all" and gp > 0
        else []
    )

    return {
        "games_played": gp,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_pct": win_pct,
        "ot_games": ot_games,
        "shootout_wins": shootout_wins,
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
        "saves": saves,
        "save_pct": save_pct,
        "season_breakdown": season_breakdown,
        "games": recent_games,
    }


@app.get("/api/leaders")
def get_leaders(
    season: str | None = Query(default=None),
    scope: str = Query(default="all", pattern="^(all|conference)$"),
    opponent: str | None = Query(default=None),
    limit: int = Query(default=35, ge=1, le=100),
) -> dict[str, Any]:
    ds = _require_datasets()
    target_season = season or (ds.available_seasons[0] if ds.available_seasons else "")
    target_opponent = opponent.strip() if opponent and opponent.strip() else None

    season_games = ds.games if target_season == "all" else ds.games[ds.games["season"] == target_season]
    season_opponents = sorted(o for o in season_games["opponent"].dropna().unique() if o)
    if scope == "conference":
        season_opponents = [o for o in season_opponents if o in HOCKEY_EAST_TEAMS]

    stats_url = ""
    season_rows = ds.season_stats if target_season == "all" else ds.season_stats[ds.season_stats["season"] == target_season]
    if not season_rows.empty:
        urls = [u for u in season_rows["stats_url"].unique() if u]
        stats_url = urls[0] if urls else ""

    # Case 1: Specific opponent selected -> aggregate from game-by-game logs
    if target_opponent:
        sk_df = ds.skaters if target_season == "all" else ds.skaters[ds.skaters["season"] == target_season]
        sk_df = sk_df[(sk_df["opponent"].str.lower() == target_opponent.lower()) & (sk_df["position"] != "G")]

        roster_df = ds.rosters if target_season == "all" else ds.rosters[ds.rosters["season"] == target_season]
        jersey_map = (
            roster_df.drop_duplicates("player_name")
            .set_index("player_name")["jersey_number"]
            .to_dict()
            if not roster_df.empty
            else {}
        )

        skaters_list: list[dict[str, Any]] = []
        if not sk_df.empty:
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
                )
                .sort_values(["points", "goals", "gp"], ascending=[False, False, True])
                .head(limit)
            )
            grouped["shot_pct"] = grouped.apply(
                lambda r: round((r["goals"] / r["shots"]) * 100.0, 1) if r["shots"] > 0 else 0.0, axis=1
            )
            grouped["jersey_number"] = grouped["player_name"].map(lambda n: jersey_map.get(n, ""))
            skaters_list = _records(grouped)

        gl_df = ds.goalies if target_season == "all" else ds.goalies[ds.goalies["season"] == target_season]
        gl_df = gl_df[gl_df["opponent"].str.lower() == target_opponent.lower()]

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
            "opponent": target_opponent,
            "opponents": season_opponents,
            "stats_url": stats_url,
            "team_stats": _build_team_stats(ds, target_season, scope, target_opponent),
            "skaters": skaters_list,
            "goalies": goalies_list,
        }

    # Case 2: All opponents -> use cumulative season stats (All or Hockey East Conference)
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
                pim=("conf_pim" if scope == "conference" else "pim", "sum"),
                blocked_shots=("conf_blocked_shots" if scope == "conference" else "blocked_shots", "sum"),
            )
        )
        sk_agg["shot_pct"] = sk_agg.apply(
            lambda r: round((r["goals"] / r["shots"]) * 100.0, 1) if r["shots"] > 0 else 0.0, axis=1
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
            "opponent": None,
            "opponents": season_opponents,
            "stats_url": "",
            "team_stats": _build_team_stats(ds, target_season, scope, None),
            "skaters": _records(skaters),
            "goalies": _records(goalies),
        }

    prefix = "conf_" if scope == "conference" else ""
    sk_gp_col = f"{prefix}gp"
    skaters_src = df[(df[sk_gp_col] > 0) & (df["position"] != "G")].sort_values(
        [f"{prefix}points", f"{prefix}goals", sk_gp_col], ascending=[False, False, True]
    ).head(limit)

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
        "pim": skaters_src[f"{prefix}pim"],
        "blocked_shots": skaters_src[f"{prefix}blocked_shots"],
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
        "opponent": None,
        "opponents": season_opponents,
        "stats_url": stats_url,
        "team_stats": _build_team_stats(ds, target_season, scope, None),
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


@app.get("/api/player")
def get_player(name: str = Query(..., min_length=2)) -> dict[str, Any]:
    ds = _require_datasets()
    target = name.strip()

    roster_df = ds.rosters[ds.rosters["player_name"].str.lower() == target.lower()].copy()
    if roster_df.empty:
        roster_df = ds.rosters[ds.rosters["player_name"].str.contains(target, case=False, na=False)].copy()

    stats_df = ds.season_stats[ds.season_stats["player_name"].str.lower() == target.lower()].copy()
    if stats_df.empty:
        stats_df = ds.season_stats[ds.season_stats["player_name"].str.contains(target, case=False, na=False)].copy()

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
        career_skater = {
            "gp": int(stats_df["gp"].sum()),
            "goals": int(stats_df["goals"].sum()),
            "assists": int(stats_df["assists"].sum()),
            "points": int(stats_df["points"].sum()),
            "plus_minus": int(stats_df["plus_minus"].sum()),
            "pim": int(stats_df["pim"].sum()),
            "ppg": int(stats_df["ppg"].sum()),
            "shg": int(stats_df["shg"].sum()),
            "gwg": int(stats_df["gwg"].sum()),
            "blocked_shots": int(stats_df["blocked_shots"].sum()),
        }

    career_goalie = None
    if is_goalie and not stats_df.empty and int(stats_df["goalie_gp"].sum()) > 0:
        total_ga = int(stats_df["ga"].sum())
        total_saves = int(stats_df["saves"].sum())
        total_mins = sum(_parse_minutes_to_float(m) for m in stats_df["goalie_minutes"])
        career_goalie = {
            "goalie_gp": int(stats_df["goalie_gp"].sum()),
            "wins": int(stats_df["wins"].sum()),
            "losses": int(stats_df["losses"].sum()),
            "ties": int(stats_df["ties"].sum()),
            "saves": total_saves,
            "ga": total_ga,
            "shutouts": int(stats_df["shutouts"].sum()),
            "gaa": round((total_ga * 60.0) / total_mins, 2) if total_mins > 0 else round(float(stats_df["gaa"].mean()), 2),
            "save_pct": round(total_saves / (total_saves + total_ga), 3) if (total_saves + total_ga) > 0 else 0.0,
        }

    season_rows = _records(stats_df) if not stats_df.empty else []

    # Enrich season rows with faceoff totals aggregated from game-by-game skater logs
    if season_rows and not sk_logs.empty:
        fo_all = (
            sk_logs.groupby("season", as_index=False)[["faceoffs_won", "faceoffs_lost"]]
            .sum()
            .set_index("season")
            .to_dict(orient="index")
        )
        sk_conf = sk_logs[sk_logs["opponent"].isin(HOCKEY_EAST_TEAMS)]
        fo_conf = (
            sk_conf.groupby("season", as_index=False)[["faceoffs_won", "faceoffs_lost"]]
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
            row["conf_faceoffs_won"] = int(conf_vals.get("faceoffs_won", 0))
            row["conf_faceoffs_lost"] = int(conf_vals.get("faceoffs_lost", 0))

    if is_goalie and not gl_logs.empty:
        game_logs = _records(gl_logs.sort_values("date", ascending=False))
    else:
        game_logs = _records(sk_logs.sort_values("date", ascending=False))

    return {
        "bio": bio,
        "is_goalie": is_goalie,
        "career_skater": career_skater,
        "career_goalie": career_goalie,
        "seasons": season_rows,
        "game_logs": game_logs,
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

    history = [{"role": m.role, "content": m.content} for m in req.history]
    # Check standalone cache before consuming global daily LLM budget
    if not history and not req.context:
        cached_ans = state.cache.get(req.question)
        if cached_ans is not None:
            return ChatResponse(answer=cached_ans, cached=True, turnstile_pass=issued_turnstile_pass)

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

    return ChatResponse(answer=answer, cached=from_cache, turnstile_pass=issued_turnstile_pass)


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

