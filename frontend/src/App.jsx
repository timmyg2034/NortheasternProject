import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import LegalModal from "./LegalModals.jsx";
import BugReportModal from "./BugReportModal.jsx";
import OPPONENT_LOGOS from "./opponentLogos.json";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const STARTER_QUESTIONS = [
  "Who leads Northeastern in points this season?",
  "What is our record against Boston University since 2015?",
  "Who were the captains in 2025-26?",
  "Who scored the most recent winning shootout goal?",
  "How many shutouts did Devon Levi record?",
];

const HOCKEY_EAST_SET = new Set([
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
]);

function PawsIcon({ large = false }) {
  return (
    <img
      src="/paws_logo.png"
      alt=""
      aria-hidden="true"
      className={large ? "paws-icon-lg" : "paws-icon"}
    />
  );
}

function TrophyIcon() {
  return (
    <svg className="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6m12 5h1.5a2.5 2.5 0 0 0 0-5H18M6 4h12v6a6 6 0 0 1-12 0V4Zm6 12v4m-4 0h8" />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg className="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2m8-10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm14 10v-2a4 4 0 0 0-3-3.87m-4-12a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

function SwordsIcon() {
  return (
    <svg className="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="11" cy="11" r="8" />
      <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-4.3-4.3" />
    </svg>
  );
}

function CaptainBadge({ role }) {
  if (role === "C") {
    return (
      <span className="pill pill-c" title="Captain" aria-label="Team Captain">
        C
      </span>
    );
  }
  if (role === "A") {
    return (
      <span className="pill pill-a" title="Alternate Captain" aria-label="Alternate Captain">
        A
      </span>
    );
  }
  return null;
}

function OpponentLogo({ name, large = false }) {
  const src = OPPONENT_LOGOS[name];
  if (!src) return null;
  return (
    <img
      src={src}
      alt=""
      aria-hidden="true"
      className={large ? "opp-logo-lg" : "opp-logo-sm"}
      loading="lazy"
    />
  );
}

function OutcomeBadge({ outcome }) {
  if (outcome === "W") return <span className="pill pill-w" aria-label="Win">W</span>;
  if (outcome === "L") return <span className="pill pill-l" aria-label="Loss">L</span>;
  return <span className="pill pill-t" aria-label="Tie">{outcome || "T"}</span>;
}

function hasModernTracking(season) {
  if (!season || season === "all") return true;
  const yr = parseInt(String(season).slice(0, 4), 10);
  return Number.isFinite(yr) && yr >= 2012;
}

function formatRatio3(num, den) {
  const n = Number(num || 0);
  const d = Number(den || 0);
  if (!d) return null;
  return (n / d).toFixed(3).replace(/^0/, "");
}

function formatPct3(won, lost) {
  return formatRatio3(won, Number(won || 0) + Number(lost || 0));
}

export default function App() {
  const [tab, setTab] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get("tab");
    return ["chat", "leaders", "roster", "rivalry"].includes(t) ? t : "chat";
  });
  const [seasons, setSeasons] = useState([]);
  const [opponents, setOpponents] = useState([]);
  const [selectedSeason, setSelectedSeason] = useState("");
  const [health, setHealth] = useState(null);

  // Chat state
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatDrawerOpen, setChatDrawerOpen] = useState(false);
  const [drawerUseContext, setDrawerUseContext] = useState(true);
  const [noticeDismissed, setNoticeDismissed] = useState(false);
  const [legalModal, setLegalModal] = useState(null); // "disclaimer" | "privacy" | "terms" | null
  const [bugModalOpen, setBugModalOpen] = useState(false);
  const messagesEndRef = useRef(null);
  const drawerEndRef = useRef(null);
  const turnstileContainerRef = useRef(null);
  const turnstileWidgetRef = useRef(null);
  const turnstileTokenRef = useRef("");
  const [turnstilePass, setTurnstilePass] = useState(() => {
    try {
      return window.sessionStorage.getItem("nu_turnstile_pass") || "";
    } catch {
      return "";
    }
  });
  const turnstileSiteKey = health?.turnstile_site_key || "";

  useEffect(() => {
    if (!turnstileSiteKey || turnstilePass || !turnstileContainerRef.current) {
      if (turnstileWidgetRef.current !== null && window.turnstile) {
        try {
          window.turnstile.remove(turnstileWidgetRef.current);
        } catch {}
        turnstileWidgetRef.current = null;
      }
      return;
    }
    let cancelled = false;
    let timer = null;

    function initTurnstile() {
      if (cancelled || !turnstileContainerRef.current) return;
      if (!window.turnstile) {
        timer = window.setTimeout(initTurnstile, 250);
        return;
      }
      if (turnstileWidgetRef.current !== null) return;
      turnstileWidgetRef.current = window.turnstile.render(turnstileContainerRef.current, {
        sitekey: turnstileSiteKey,
        action: "ask_paws",
        appearance: "interaction-only",
        callback: (token) => {
          turnstileTokenRef.current = token || "";
        },
        "expired-callback": () => {
          turnstileTokenRef.current = "";
        },
        "error-callback": () => {
          turnstileTokenRef.current = "";
        },
      });
    }

    initTurnstile();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
      if (turnstileWidgetRef.current !== null && window.turnstile) {
        try {
          window.turnstile.remove(turnstileWidgetRef.current);
        } catch {}
        turnstileWidgetRef.current = null;
      }
    };
  }, [turnstileSiteKey, turnstilePass]);

  // Leaders / Stats state
  const [leaders, setLeaders] = useState(null);
  const [leadersLoading, setLeadersLoading] = useState(false);
  const [leaderSort, setLeaderSort] = useState({ key: "points", dir: "desc" });
  const [leaderScope, setLeaderScope] = useState("all");
  const [leaderOpponent, setLeaderOpponent] = useState("");
  const [statsView, setStatsView] = useState("players"); // "players" | "team"

  // Roster state
  const [roster, setRoster] = useState(null);
  const [rosterLoading, setRosterLoading] = useState(false);
  const [rosterSearch, setRosterSearch] = useState("");
  const [rosterView, setRosterView] = useState("position"); // "position" | "all"

  // Rivalry state
  const [selectedRival, setSelectedRival] = useState("Boston University");
  const [rivalryScope, setRivalryScope] = useState("all"); // "season" | "all"
  const [rivalry, setRivalry] = useState(null);
  const [rivalryLoading, setRivalryLoading] = useState(false);

  // Player profile state
  const [selectedPlayer, setSelectedPlayer] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("player") || null;
  });
  const [playerData, setPlayerData] = useState(null);
  const [playerLoading, setPlayerLoading] = useState(false);
  const [playerError, setPlayerError] = useState("");
  const [playerScope, setPlayerScope] = useState("all");
  const [playerLogSeason, setPlayerLogSeason] = useState("all");
  const [playerOpponent, setPlayerOpponent] = useState("all");
  const [rivalryPage, setRivalryPage] = useState(1);
  const [penaltyView, setPenaltyView] = useState(null);
  const [penaltyData, setPenaltyData] = useState(null);
  const [penaltyLoading, setPenaltyLoading] = useState(false);
  const [penaltyError, setPenaltyError] = useState("");
  const [penaltyPage, setPenaltyPage] = useState(1);
  const [penaltySeasonFilter, setPenaltySeasonFilter] = useState("all");
  const [penaltyInfractionFilter, setPenaltyInfractionFilter] = useState("all");
  const hasInAppHistory = useRef(false);

  useEffect(() => {
    // Seed initial history state so Mouse Button 4 / Back returns cleanly
    window.history.replaceState({ tab, player: selectedPlayer }, "", window.location.href);

    function handlePopState(e) {
      const state = e.state;
      if (state) {
        setTab(state.tab || "chat");
        setSelectedPlayer(state.player || null);
      } else {
        const params = new URLSearchParams(window.location.search);
        const t = params.get("tab");
        setTab(["chat", "leaders", "roster", "rivalry"].includes(t) ? t : "chat");
        setSelectedPlayer(params.get("player") || null);
      }
      setPenaltyView(null);
      setPlayerError("");
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  function navigateTab(nextTab) {
    if (nextTab === tab && !selectedPlayer && !penaltyView) return;
    hasInAppHistory.current = true;
    setTab(nextTab);
    setPenaltyView(null);
    setPenaltyData(null);
    setSelectedPlayer(null);
    setPlayerData(null);
    setPlayerError("");
    const url = new URL(window.location.href);
    url.searchParams.set("tab", nextTab);
    url.searchParams.delete("player");
    window.history.pushState({ tab: nextTab, player: null }, "", url.toString());
  }

  function openPlayer(name) {
    hasInAppHistory.current = true;
    setPenaltyView(null);
    setPenaltyData(null);
    setSelectedPlayer(name);
    setPlayerScope("all");
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    url.searchParams.set("player", name);
    window.history.pushState({ tab, player: name }, "", url.toString());
  }

  function closePlayer() {
    if (hasInAppHistory.current) {
      window.history.back();
      return;
    }
    setSelectedPlayer(null);
    setPlayerData(null);
    setPlayerError("");
    const url = new URL(window.location.href);
    url.searchParams.delete("player");
    window.history.replaceState({ tab, player: null }, "", url.toString());
  }

  async function openPenaltyBreakdown({ mode, player = "", season = "all", scope = "all", opponent = "" }) {
    setPenaltyView({ mode, player, season, scope, opponent });
    setPenaltyLoading(true);
    setPenaltyError("");
    setPenaltyPage(1);
    setPenaltySeasonFilter("all");
    setPenaltyInfractionFilter("all");
    try {
      const params = new URLSearchParams({
        season: season || "all",
        scope: scope || "all",
      });
      if (opponent) params.set("opponent", opponent);
      if (player) params.set("player", player);
      const res = await fetch(`${API_BASE}/api/penalties?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Unable to load penalty breakdown");
      setPenaltyData(data);
    } catch (err) {
      setPenaltyError(err.message || "Unable to load penalty breakdown");
    } finally {
      setPenaltyLoading(false);
    }
  }

  function closePenaltyBreakdown() {
    setPenaltyView(null);
    setPenaltyData(null);
    setPenaltyError("");
  }

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => r.json())
      .then((data) => setHealth(data))
      .catch(() => {});

    fetch(`${API_BASE}/api/seasons`)
      .then((r) => r.json())
      .then((data) => {
        const s = data.seasons || [];
        setSeasons(s);
        setOpponents(data.opponents || []);
        if (s.length > 0) setSelectedSeason(s[0]);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedSeason) return;
    if (tab === "leaders") {
      setLeadersLoading(true);
      const params = new URLSearchParams({
        season: selectedSeason,
        scope: leaderScope,
        limit: "35",
      });
      if (leaderOpponent) {
        params.set("opponent", leaderOpponent);
      }
      fetch(`${API_BASE}/api/leaders?${params.toString()}`)
        .then((r) => r.json())
        .then((data) => {
          setLeaders(data);
          if (leaderOpponent && !(data.opponents || []).includes(leaderOpponent)) {
            setLeaderOpponent("");
          }
        })
        .finally(() => setLeadersLoading(false));
    } else if (tab === "roster") {
      const rosterSeason = selectedSeason === "all" ? (seasons[0] || "") : selectedSeason;
      if (selectedSeason === "all" && rosterSeason) {
        setSelectedSeason(rosterSeason);
      }
      if (!rosterSeason) return;
      setRosterLoading(true);
      fetch(`${API_BASE}/api/roster?season=${encodeURIComponent(rosterSeason)}`)
        .then((r) => r.json())
        .then((data) => setRoster(data))
        .finally(() => setRosterLoading(false));
    }
  }, [tab, selectedSeason, leaderScope, leaderOpponent, seasons]);

  useEffect(() => {
    if (tab !== "rivalry" || !selectedRival) return;
    if (rivalryScope === "season" && !seasons[0]) return;
    setRivalryPage(1);
    setRivalryLoading(true);
    const params = new URLSearchParams({ opponent: selectedRival });
    if (rivalryScope === "season" && seasons[0]) {
      params.set("season", seasons[0]);
    }
    fetch(`${API_BASE}/api/rivalry?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => setRivalry(data))
      .finally(() => setRivalryLoading(false));
  }, [tab, selectedRival, rivalryScope, seasons]);

  useEffect(() => {
    if (!selectedPlayer) return;
    setPlayerLoading(true);
    setPlayerError("");
    fetch(`${API_BASE}/api/player?name=${encodeURIComponent(selectedPlayer)}`)
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || "Player not found");
        setPlayerData(data);
        const logSeasons = Array.from(
          new Set((data.game_logs || []).map((g) => g.season).filter(Boolean))
        ).sort((a, b) => b.localeCompare(a));
        setPlayerLogSeason(logSeasons[0] || "all");
        setPlayerOpponent("all");
      })
      .catch((err) => setPlayerError(err.message))
      .finally(() => setPlayerLoading(false));
  }, [selectedPlayer]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    drawerEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading, chatDrawerOpen]);

  const pageContext = useMemo(() => {
    if (selectedPlayer) {
      return `User is viewing Player Profile for ${selectedPlayer}.`;
    }
    if (tab === "leaders") {
      return `User is viewing ${selectedSeason === "all" ? "All-Time" : selectedSeason} Leaders (${leaderScope === "conference" ? "Hockey East" : "All Games"}${leaderOpponent ? `, vs. ${leaderOpponent}` : ""}).`;
    }
    if (tab === "roster") {
      return `User is viewing ${selectedSeason} Roster.`;
    }
    if (tab === "rivalry") {
      return `User is viewing Opponent history vs. ${selectedRival}.`;
    }
    return null;
  }, [selectedPlayer, tab, selectedSeason, leaderScope, leaderOpponent, selectedRival]);

  const sortedSkaters = useMemo(() => {
    if (!leaders?.skaters) return [];
    const list = [...leaders.skaters];
    const { key, dir } = leaderSort;
    list.sort((a, b) => {
      const av = Number(a[key] ?? 0);
      const bv = Number(b[key] ?? 0);
      return dir === "desc" ? bv - av : av - bv;
    });
    return list;
  }, [leaders, leaderSort]);

  const filteredRoster = useMemo(() => {
    if (!roster?.players) return [];
    const q = rosterSearch.trim().toLowerCase();
    if (!q) return roster.players;
    return roster.players.filter(
      (p) =>
        String(p.player_name || "").toLowerCase().includes(q) ||
        String(p.jersey_number || "").toLowerCase().includes(q) ||
        String(p.hometown || "").toLowerCase().includes(q) ||
        String(p.position || "").toLowerCase().includes(q)
    );
  }, [roster, rosterSearch]);

  function toggleSort(key) {
    setLeaderSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "desc" ? "asc" : "desc" }
        : { key, dir: "desc" }
    );
  }

  async function fetchChatToken() {
    const res = await fetch(`${API_BASE}/api/chat-token`);
    if (!res.ok) return "";
    const data = await res.json().catch(() => ({}));
    return data?.token || "";
  }

  async function sendQuestion(questionText) {
    const q = questionText.trim();
    if (!q || chatLoading) return;

    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setInput("");
    setChatLoading(true);

    try {
      const activeContext =
        selectedPlayer || tab !== "chat"
          ? (drawerUseContext ? pageContext : null)
          : null;

      let token = await fetchChatToken();
      let activePass = turnstilePass;
      let tsToken = "";
      if (!activePass && turnstileSiteKey) {
        tsToken = turnstileTokenRef.current;
        if (!tsToken && window.turnstile && turnstileWidgetRef.current !== null) {
          tsToken = window.turnstile.getResponse(turnstileWidgetRef.current) || "";
          if (!tsToken) {
            for (let attempt = 0; attempt < 15 && !turnstileTokenRef.current; attempt += 1) {
              await new Promise((r) => window.setTimeout(r, 100));
            }
            tsToken =
              turnstileTokenRef.current ||
              window.turnstile.getResponse(turnstileWidgetRef.current) ||
              "";
          }
        }
      }
      let res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "X-Chat-Token": token } : {}),
          ...(activePass ? { "X-Turnstile-Pass": activePass } : {}),
          ...(!activePass && tsToken ? { "X-Turnstile-Token": tsToken } : {}),
        },
        body: JSON.stringify({
          question: q,
          history,
          context: activeContext,
        }),
      });

      if (res.status === 403) {
        if (activePass) {
          activePass = "";
          setTurnstilePass("");
          try {
            window.sessionStorage.removeItem("nu_turnstile_pass");
          } catch {}
        }
        token = await fetchChatToken();
        const retryTsToken = turnstileTokenRef.current;
        if (token) {
          res = await fetch(`${API_BASE}/api/chat`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Chat-Token": token,
              ...(retryTsToken ? { "X-Turnstile-Token": retryTsToken } : {}),
            },
            body: JSON.stringify({
              question: q,
              history,
              context: activeContext,
            }),
          });
        }
      }

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (turnstileWidgetRef.current !== null && window.turnstile) {
          turnstileTokenRef.current = "";
          try {
            window.turnstile.reset(turnstileWidgetRef.current);
          } catch {}
        }
        const errorDetail =
          data?.detail ||
          (res.status === 429
            ? "⏳ **High Traffic Alert — Per-Minute Rate Limit Reached**\n\nPlease wait 30–60 seconds before asking your next question."
            : "Sorry, I encountered an issue fetching that answer. Please try again in a moment.");
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: errorDetail },
        ]);
        return;
      }
      if (data.turnstile_pass) {
        setTurnstilePass(data.turnstile_pass);
        try {
          window.sessionStorage.setItem("nu_turnstile_pass", data.turnstile_pass);
        } catch {}
        turnstileTokenRef.current = "";
      }
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer, cached: data.cached },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Sorry, something went wrong: ${err.message}` },
      ]);
    } finally {
      setChatLoading(false);
    }

  }

  const hockeyEastOpponents = useMemo(
    () => opponents.filter((o) => HOCKEY_EAST_SET.has(o)),
    [opponents]
  );
  const otherOpponents = useMemo(
    () => opponents.filter((o) => !HOCKEY_EAST_SET.has(o)),
    [opponents]
  );

  useEffect(() => {
    if (!chatDrawerOpen) return;
    function onDrawerKey(e) {
      if (e.key === "Escape" && !legalModal && !bugModalOpen) {
        setChatDrawerOpen(false);
      }
    }
    window.addEventListener("keydown", onDrawerKey);
    return () => window.removeEventListener("keydown", onDrawerKey);
  }, [chatDrawerOpen, legalModal, bugModalOpen]);

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <div className="sticky-top">
        <header className="app-header">
          <div className="brand">
            <img
              src="/nu_husky_logo.png"
              alt="Northeastern Huskies logo"
              className="brand-logo"
            />
            <div>
              <h1>Northeastern Men&apos;s Hockey</h1>
              <p>
                DogHouse Stats Explorer &bull; 1999&ndash;Present
                {health?.games_count ? ` • ${health.games_count} Games` : ""}
              </p>
            </div>
          </div>
          {health?.latest_game_date && (
            <div className="header-pill">
              <span className="header-pill-label">
                <span className="live-dot" aria-hidden="true" />
                Latest Game
              </span>
              <span className="header-pill-date">{health.latest_game_date}</span>
            </div>
          )}
        </header>

        <nav className="tab-bar" aria-label="Main navigation">
          <button
            type="button"
            className={`tab-btn ${!selectedPlayer && tab === "chat" ? "active" : ""}`}
            aria-current={!selectedPlayer && tab === "chat" ? "page" : undefined}
            onClick={() => navigateTab("chat")}
          >
            <PawsIcon />
            <span>Ask Paws</span>
          </button>
          <button
            type="button"
            className={`tab-btn ${!selectedPlayer && tab === "leaders" ? "active" : ""}`}
            aria-current={!selectedPlayer && tab === "leaders" ? "page" : undefined}
            onClick={() => navigateTab("leaders")}
          >
            <TrophyIcon />
            <span>Stats</span>
          </button>
          <button
            type="button"
            className={`tab-btn ${!selectedPlayer && tab === "roster" ? "active" : ""}`}
            aria-current={!selectedPlayer && tab === "roster" ? "page" : undefined}
            onClick={() => navigateTab("roster")}
          >
            <UsersIcon />
            <span>Roster</span>
          </button>
          <button
            type="button"
            className={`tab-btn ${!selectedPlayer && tab === "rivalry" ? "active" : ""}`}
            aria-current={!selectedPlayer && tab === "rivalry" ? "page" : undefined}
            onClick={() => navigateTab("rivalry")}
          >
            <SwordsIcon />
            <span>Opponents</span>
          </button>
        </nav>
      </div>

      <main id="main-content" className="main-content" tabIndex={-1}>
        {!noticeDismissed && (
          <div className="notice-banner" role="note">
            <span>
              <strong>Unofficial Fan Analytics:</strong> Stats are scraped from public
              archives and <strong>Ask Paws</strong> uses AI (Google Gemini) to query
              data&mdash;please verify important figures against official{" "}
              <a href="https://nuhuskies.com" target="_blank" rel="noreferrer" style={{ color: "inherit", fontWeight: 700 }}>
                nuhuskies.com
              </a>{" "}
              box scores.
            </span>
            <button
              type="button"
              className="notice-close"
              onClick={() => setNoticeDismissed(true)}
              aria-label="Dismiss notice"
            >
              Dismiss
            </button>
          </div>
        )}
        {penaltyView ? (
          <section style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="controls-row">
              <button type="button" className="btn-ghost" onClick={closePenaltyBreakdown}>
                &larr; Back to {penaltyView.mode === "player" ? penaltyView.player : "Team Stats"}
              </button>
            </div>

            <div className="card">
              <div className="card-header">
                <div>
                  <h2>
                    {penaltyView.mode === "player"
                      ? `${penaltyView.player} — Penalty Breakdown`
                      : "Northeastern Penalty Breakdown"}
                  </h2>
                  <p className="muted" style={{ marginTop: 4 }}>
                    {penaltyView.season === "all" ? "All-Time (1999–present)" : penaltyView.season}
                    {penaltyView.scope === "conference" ? " • Hockey East" : " • All Games"}
                    {penaltyView.opponent ? ` • vs. ${penaltyView.opponent}` : ""}
                  </p>
                </div>
              </div>

              {penaltyLoading && (
                <p className="muted" role="status" aria-live="polite">
                  Loading penalty breakdown...
                </p>
              )}
              {penaltyError && (
                <p className="muted" role="alert">
                  {penaltyError}
                </p>
              )}

              {!penaltyLoading && !penaltyError && penaltyData && (() => {
                const s = penaltyData.summary || {};
                const maxInfCount = Math.max(1, ...(penaltyData.by_infraction || []).map((x) => x.count));
                const filteredEvents = (penaltyData.events || []).filter((ev) => {
                  if (penaltySeasonFilter !== "all" && ev.season !== penaltySeasonFilter) return false;
                  const inf = (ev.infraction || "").trim() || "UNSPECIFIED";
                  if (penaltyInfractionFilter !== "all" && inf !== penaltyInfractionFilter) return false;
                  return true;
                });
                const pageSize = 20;
                const totalEvents = filteredEvents.length;
                const totalPages = Math.max(1, Math.ceil(totalEvents / pageSize));
                const safePage = Math.min(penaltyPage, totalPages);
                const startIdx = (safePage - 1) * pageSize;
                const visibleEvents = filteredEvents.slice(startIdx, startIdx + pageSize);

                return (
                  <>
                    <div className="stat-grid">
                      <div className="stat-box">
                        <div className="val">{s.total_penalties ?? 0}</div>
                        <div className="lbl">Total Penalties</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{s.total_pim ?? 0}</div>
                        <div className="lbl">Penalty Min</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{s.minors ?? 0}</div>
                        <div className="lbl">Minors (2m)</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{s.majors ?? 0}</div>
                        <div className="lbl">Majors (5m)</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{s.other ?? 0}</div>
                        <div className="lbl">Misconduct / Other</div>
                      </div>
                    </div>

                    {penaltyData.by_period?.length > 0 && (
                      <>
                        <h3 style={{ marginTop: 18 }}>By Period</h3>
                        <div className="stat-grid" style={{ marginTop: 8 }}>
                          {penaltyData.by_period.map((p) => (
                            <div key={p.period} className="stat-box">
                              <div className="val">{p.count}</div>
                              <div className="lbl">{`${p.period} (${p.pim} PIM)`}</div>
                            </div>
                          ))}
                        </div>
                      </>
                    )}

                    {penaltyData.by_infraction?.length > 0 && (
                      <>
                        <h3 style={{ marginTop: 18 }}>By Infraction</h3>
                        <p className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
                          Click an infraction to filter the penalty log below.
                        </p>
                        <div className="table-wrap">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>Infraction</th>
                                <th>Penalties</th>
                                <th>PIM</th>
                                <th>Share</th>
                              </tr>
                            </thead>
                            <tbody>
                              {penaltyData.by_infraction.map((row) => {
                                const pct = s.total_penalties
                                  ? Math.round((row.count / s.total_penalties) * 100)
                                  : 0;
                                const isSelected = penaltyInfractionFilter === row.infraction;
                                return (
                                  <tr key={row.infraction}>
                                    <td>
                                      <button
                                        type="button"
                                        className="link-btn"
                                        style={{ fontWeight: isSelected ? 800 : 600 }}
                                        onClick={() => {
                                          setPenaltyInfractionFilter(isSelected ? "all" : row.infraction);
                                          setPenaltyPage(1);
                                        }}
                                      >
                                        {row.infraction}
                                      </button>
                                    </td>
                                    <td>{row.count}</td>
                                    <td><strong>{row.pim}</strong></td>
                                    <td>
                                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                        <div className="penalty-bar-wrap" aria-hidden="true">
                                          <div
                                            className="penalty-bar-fill"
                                            style={{ width: `${Math.round((row.count / maxInfCount) * 100)}%` }}
                                          />
                                        </div>
                                        <span className="muted">{pct}%</span>
                                      </div>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )}

                    {penaltyView.mode === "team" && penaltyData.by_player?.length > 0 && (
                      <>
                        <h3 style={{ marginTop: 20 }}>By Player ({penaltyData.by_player.length})</h3>
                        <div className="table-wrap" style={{ marginTop: 8 }}>
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>Player</th>
                                <th>Penalties</th>
                                <th>2m</th>
                                <th>5m</th>
                                <th>Other</th>
                                <th>Total PIM</th>
                              </tr>
                            </thead>
                            <tbody>
                              {penaltyData.by_player.slice(0, 35).map((pl) => (
                                <tr key={pl.player_name}>
                                  <td>
                                    <button
                                      type="button"
                                      className="link-btn"
                                      onClick={() =>
                                        openPenaltyBreakdown({
                                          mode: "player",
                                          player: pl.player_name,
                                          season: penaltyView.season,
                                          scope: penaltyView.scope,
                                          opponent: penaltyView.opponent,
                                        })
                                      }
                                    >
                                      {pl.player_name}
                                    </button>
                                  </td>
                                  <td>{pl.count}</td>
                                  <td>{pl.minors}</td>
                                  <td>{pl.majors}</td>
                                  <td>{pl.other}</td>
                                  <td><strong>{pl.pim}</strong></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )}

                    <div className="card-header" style={{ marginTop: 22 }}>
                      <h3>Penalty Log ({totalEvents})</h3>
                      <div className="controls-row">
                        {penaltyData.by_season?.length > 1 && (
                          <select
                            aria-label="Filter penalty log by season"
                            className="select-input"
                            value={penaltySeasonFilter}
                            onChange={(e) => {
                              setPenaltySeasonFilter(e.target.value);
                              setPenaltyPage(1);
                            }}
                          >
                            <option value="all">All Seasons</option>
                            {penaltyData.by_season.map((sb) => (
                              <option key={sb.season} value={sb.season}>
                                {sb.season} ({sb.count})
                              </option>
                            ))}
                          </select>
                        )}
                        {penaltyData.by_infraction?.length > 1 && (
                          <select
                            aria-label="Filter penalty log by infraction"
                            className="select-input"
                            value={penaltyInfractionFilter}
                            onChange={(e) => {
                              setPenaltyInfractionFilter(e.target.value);
                              setPenaltyPage(1);
                            }}
                          >
                            <option value="all">All Infractions</option>
                            {penaltyData.by_infraction.map((inf) => (
                              <option key={inf.infraction} value={inf.infraction}>
                                {inf.infraction} ({inf.count})
                              </option>
                            ))}
                          </select>
                        )}
                      </div>
                    </div>

                    {totalEvents === 0 ? (
                      <p className="muted">No penalty events match the selected filters.</p>
                    ) : (
                      <>
                        <div className="table-wrap">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>Date</th>
                                <th>Season</th>
                                {penaltyView.mode === "team" && <th>Player</th>}
                                <th>Opponent</th>
                                <th>Period</th>
                                <th>Time</th>
                                <th>Infraction</th>
                                <th>PIM</th>
                                <th>Box</th>
                              </tr>
                            </thead>
                            <tbody>
                              {visibleEvents.map((ev, idx) => (
                                <tr key={`${ev.date}-${ev.period}-${ev.time}-${ev.player_name}-${idx}`}>
                                  <td>{ev.date}</td>
                                  <td>{ev.season}</td>
                                  {penaltyView.mode === "team" && (
                                    <td>
                                      <button
                                        type="button"
                                        className="link-btn"
                                        onClick={() => openPlayer(ev.player_name)}
                                      >
                                        {ev.player_name}
                                      </button>
                                    </td>
                                  )}
                                  <td>
                                    <span className="opp-with-logo">
                                      <OpponentLogo name={ev.opponent} />
                                      <span>{ev.opponent}</span>
                                    </span>
                                  </td>
                                  <td>{ev.period}</td>
                                  <td>{ev.time}</td>
                                  <td>{ev.infraction || "UNSPECIFIED"}</td>
                                  <td><strong>{ev.penalty_minutes}</strong></td>
                                  <td>
                                    {ev.boxscore_url ? (
                                      <a href={ev.boxscore_url} target="_blank" rel="noreferrer">
                                        View
                                      </a>
                                    ) : (
                                      "-"
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {totalPages > 1 && (
                          <nav className="pagination-bar" aria-label="Penalty log pagination">
                            <span className="muted">
                              Showing {startIdx + 1}–{Math.min(startIdx + pageSize, totalEvents)} of {totalEvents} penalties
                            </span>
                            <div className="pagination-controls">
                              <button
                                type="button"
                                className="btn-ghost"
                                onClick={() => setPenaltyPage((p) => Math.max(1, p - 1))}
                                disabled={safePage <= 1}
                              >
                                Previous
                              </button>
                              <span className="muted" aria-live="polite">
                                Page {safePage} of {totalPages}
                              </span>
                              <button
                                type="button"
                                className="btn-ghost"
                                onClick={() => setPenaltyPage((p) => Math.min(totalPages, p + 1))}
                                disabled={safePage >= totalPages}
                              >
                                Next
                              </button>
                            </div>
                          </nav>
                        )}
                      </>
                    )}
                  </>
                );
              })()}
            </div>
          </section>
        ) : selectedPlayer ? (
          <section style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="controls-row">
              <button type="button" className="btn-ghost" onClick={closePlayer}>
                &larr; Back to {tab === "roster" ? "Roster" : "Leaders"}
              </button>
              {playerData?.bio?.roster_url && (
                <a
                  href={playerData.bio.roster_url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-ghost"
                  style={{ textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                >
                  Official Bio
                </a>
              )}
            </div>

            {playerLoading && (
              <div className="card" role="status" aria-live="polite">
                <p className="muted">Loading player statistics...</p>
              </div>
            )}

            {playerError && (
              <div className="card" role="alert">
                <p className="muted">{playerError}</p>
              </div>
            )}

            {!playerLoading && !playerError && playerData && (
              <>
                <div className="player-hero">
                  <div className="player-hero-left">
                    {playerData.bio.image_url ? (
                      <img
                        src={playerData.bio.image_url}
                        alt={playerData.bio.player_name}
                        className="player-avatar-lg"
                      />
                    ) : (
                      <div className="jersey-box">
                        {playerData.bio.jersey_number || "--"}
                      </div>
                    )}
                    <div>
                      <h2>
                        {playerData.bio.jersey_number ? `#${playerData.bio.jersey_number} ` : ""}
                        {playerData.bio.player_name}{" "}
                        <CaptainBadge role={playerData.bio.captain_role} />
                      </h2>
                      <div className="player-meta-line">
                        {[
                          playerData.bio.position,
                          playerData.bio.class_year,
                          playerData.bio.seasons_played?.length
                            ? `${playerData.bio.seasons_played.length} Season${playerData.bio.seasons_played.length > 1 ? "s" : ""}`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" • ")}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="card">
                  <h3>Player Bio</h3>
                  <div className="bio-grid">
                    <div className="bio-item">
                      <div className="bio-k">Ht / Wt</div>
                      <div className="bio-v">
                        {playerData.bio.height
                          ? `${playerData.bio.height}${playerData.bio.weight ? ` / ${playerData.bio.weight} lbs` : ""}`
                          : "-"}
                      </div>
                    </div>
                    <div className="bio-item">
                      <div className="bio-k">Shoots</div>
                      <div className="bio-v">{playerData.bio.shoots || "-"}</div>
                    </div>
                    <div className="bio-item">
                      <div className="bio-k">Hometown</div>
                      <div className="bio-v">{playerData.bio.hometown || "-"}</div>
                    </div>
                    <div className="bio-item">
                      <div className="bio-k">Previous Team</div>
                      <div className="bio-v">{playerData.bio.previous_team || "-"}</div>
                    </div>
                    {playerData.bio.major && (
                      <div className="bio-item">
                        <div className="bio-k">Major</div>
                        <div className="bio-v">{playerData.bio.major}</div>
                      </div>
                    )}
                  </div>
                </div>

                {playerData.career_skater && !playerData.is_goalie && (
                  <div className="card">
                    <h3>Career Totals</h3>
                    <div className="stat-grid" style={{ marginBottom: 0 }}>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.gp}</div>
                        <div className="lbl">GP</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.goals}</div>
                        <div className="lbl">Goals</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.assists}</div>
                        <div className="lbl">Assists</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.points}</div>
                        <div className="lbl">Points</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">
                          {playerData.career_skater.plus_minus > 0
                            ? `+${playerData.career_skater.plus_minus}`
                            : playerData.career_skater.plus_minus}
                        </div>
                        <div className="lbl">+/-</div>
                      </div>
                      <button
                        type="button"
                        className="stat-box stat-box-btn"
                        onClick={() =>
                          openPenaltyBreakdown({
                            mode: "player",
                            player: playerData.bio.player_name,
                            season: "all",
                          })
                        }
                        aria-label={`View penalty breakdown for ${playerData.bio.player_name}`}
                      >
                        <div className="val">{playerData.career_skater.pim}</div>
                        <div className="lbl">PIM</div>
                        <div className="stat-box-hint">Breakdown &rarr;</div>
                      </button>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.ppg ?? 0}</div>
                        <div className="lbl">PPG</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.shg ?? 0}</div>
                        <div className="lbl">SHG</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.gwg ?? 0}</div>
                        <div className="lbl">GWG</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.otg ?? 0}</div>
                        <div className="lbl">OTG</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.multi_point_games ?? 0}</div>
                        <div className="lbl">Multi-Point Games</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.multi_goal_games ?? 0}</div>
                        <div className="lbl">Multi-Goal Games</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_skater.hat_tricks ?? 0}</div>
                        <div className="lbl">Hat Tricks</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">
                          {playerData.career_skater.faceoff_pct !== null &&
                          playerData.career_skater.faceoff_pct !== undefined
                            ? `${playerData.career_skater.faceoff_pct}%`
                            : "N/A"}
                        </div>
                        <div className="lbl">
                          {playerData.career_skater.faceoff_pct !== null &&
                          playerData.career_skater.faceoff_pct !== undefined
                            ? `FO% (${playerData.career_skater.faceoffs_won}-${playerData.career_skater.faceoffs_lost})`
                            : "FO%"}
                        </div>
                      </div>
                      {playerData.shootout_stats?.attempts > 0 && (
                        <div className="stat-box">
                          <div className="val">
                            {`${playerData.shootout_stats.made}/${playerData.shootout_stats.attempts} (${playerData.shootout_stats.pct}%)`}
                          </div>
                          <div className="lbl">
                            {playerData.shootout_stats.winners > 0
                              ? `Shootout (${playerData.shootout_stats.winners} W)`
                              : "Shootout"}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {playerData.career_goalie && (
                  <div className="card">
                    <h3>Career Goalie Totals</h3>
                    <div className="stat-grid" style={{ marginBottom: 0 }}>
                      <div className="stat-box">
                        <div className="val">{playerData.career_goalie.goalie_gp}</div>
                        <div className="lbl">GP</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_goalie.goalie_gs ?? 0}</div>
                        <div className="lbl">GS</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{`${playerData.career_goalie.wins}-${playerData.career_goalie.losses}-${playerData.career_goalie.ties}`}</div>
                        <div className="lbl">W-L-T</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{Number(playerData.career_goalie.gaa).toFixed(2)}</div>
                        <div className="lbl">GAA</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{Number(playerData.career_goalie.save_pct).toFixed(3)}</div>
                        <div className="lbl">SV%</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_goalie.saves ?? 0}</div>
                        <div className="lbl">Saves</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_goalie.goalie_minutes || "0:00"}</div>
                        <div className="lbl">Minutes</div>
                      </div>
                      <div className="stat-box">
                        <div className="val">{playerData.career_goalie.shutouts}</div>
                        <div className="lbl">Shutouts</div>
                      </div>
                      {playerData.shootout_stats?.faced > 0 && (
                        <div className="stat-box">
                          <div className="val">{Number(playerData.shootout_stats.save_pct).toFixed(3)}</div>
                          <div className="lbl">
                            {`SO SV% (${playerData.shootout_stats.saves}/${playerData.shootout_stats.faced})`}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {playerData.seasons?.length > 0 && (
                  <div className="card">
                    <div className="card-header">
                      <h2>Season-by-Season Stats</h2>
                      <div className="segmented" role="group" aria-label="Season stats scope">
                        <button
                          type="button"
                          className={`segmented-btn ${playerScope === "all" ? "active" : ""}`}
                          onClick={() => setPlayerScope("all")}
                        >
                          All Games
                        </button>
                        <button
                          type="button"
                          className={`segmented-btn ${playerScope === "conference" ? "active" : ""}`}
                          onClick={() => setPlayerScope("conference")}
                        >
                          Hockey East
                        </button>
                      </div>
                    </div>

                    <div className="table-wrap">
                      {playerData.is_goalie ? (
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Season</th>
                              <th>GP</th>
                              <th>W-L-T</th>
                              <th>GAA</th>
                              <th>SV%</th>
                              <th>SV</th>
                              <th>GA</th>
                              <th>SO</th>
                            </tr>
                          </thead>
                          <tbody>
                            {playerData.seasons.map((s) => {
                              const p = playerScope === "conference" ? "conf_" : "";
                              return (
                                <tr key={s.season}>
                                  <td><strong>{s.season}</strong></td>
                                  <td>{s[`${p}goalie_gp`]}</td>
                                  <td>{`${s[`${p}wins`]}-${s[`${p}losses`]}-${s[`${p}ties`]}`}</td>
                                  <td>{Number(s[`${p}gaa`] || 0).toFixed(2)}</td>
                                  <td>{Number(s[`${p}save_pct`] || 0).toFixed(3)}</td>
                                  <td>{s[`${p}saves`]}</td>
                                  <td>{s[`${p}ga`]}</td>
                                  <td>{s[`${p}shutouts`]}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      ) : (
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Season</th>
                              <th>GP</th>
                              <th>G</th>
                              <th>A</th>
                              <th>PTS</th>
                              <th>SOG</th>
                              <th>SH%</th>
                              <th>+/-</th>
                              <th>PPG</th>
                              <th>SHG</th>
                              <th>GWG</th>
                              <th>MPG</th>
                              <th>MGG</th>
                              <th>HTG</th>
                              <th>BLK</th>
                              <th>FO</th>
                              <th>FO%</th>
                              <th>PIM</th>
                            </tr>
                          </thead>
                          <tbody>
                            {playerData.seasons.map((s) => {
                              const p = playerScope === "conference" ? "conf_" : "";
                              const pm = s[`${p}plus_minus`];
                              const tracked = hasModernTracking(s.season);
                              const fow = s[`${p}faceoffs_won`];
                              const fol = s[`${p}faceoffs_lost`];
                              const foPct = tracked ? formatPct3(fow, fol) : null;
                              return (
                                <tr key={s.season}>
                                  <td><strong>{s.season}</strong></td>
                                  <td>{s[`${p}gp`]}</td>
                                  <td>{s[`${p}goals`]}</td>
                                  <td>{s[`${p}assists`]}</td>
                                  <td><strong>{s[`${p}points`]}</strong></td>
                                  <td>{s[`${p}shots`]}</td>
                                  <td>{formatRatio3(s[`${p}goals`], s[`${p}shots`]) ?? ".000"}</td>
                                  <td>{pm > 0 ? `+${pm}` : pm}</td>
                                  <td>{s[`${p}ppg`]}</td>
                                  <td>{s[`${p}shg`]}</td>
                                  <td>{s[`${p}gwg`]}</td>
                                  <td>{s[`${p}multi_point_games`] ?? 0}</td>
                                  <td>{s[`${p}multi_goal_games`] ?? 0}</td>
                                  <td>{s[`${p}hat_tricks`] ?? 0}</td>
                                  <td>{tracked ? s[`${p}blocked_shots`] : <span className="muted">N/A</span>}</td>
                                  <td>{tracked ? `${fow || 0}-${fol || 0}` : <span className="muted">N/A</span>}</td>
                                  <td>{foPct ?? <span className="muted">N/A</span>}</td>
                                  <td>{s[`${p}pim`]}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </div>
                )}

                {playerData.game_logs?.length > 0 && (() => {
                  const logSeasons = Array.from(
                    new Set(playerData.game_logs.map((g) => g.season).filter(Boolean))
                  ).sort((a, b) => b.localeCompare(a));
                  const visibleLogs =
                    playerLogSeason === "all"
                      ? playerData.game_logs
                      : playerData.game_logs.filter((g) => g.season === playerLogSeason);

                  return (
                    <div className="card">
                      <div className="card-header">
                        <h2>Game Log ({visibleLogs.length} Games)</h2>
                        <select
                          aria-label="Filter game log by season"
                          className="select-input"
                          value={playerLogSeason}
                          onChange={(e) => setPlayerLogSeason(e.target.value)}
                        >
                          <option value="all">All Seasons ({playerData.game_logs.length})</option>
                          {logSeasons.map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="table-wrap">
                        {playerData.is_goalie ? (
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>Date</th>
                                <th>Opponent</th>
                                <th>Score</th>
                                <th>Dec</th>
                                <th>SV</th>
                                <th>GA</th>
                                <th>SV%</th>
                                <th>Box</th>
                              </tr>
                            </thead>
                            <tbody>
                              {visibleLogs.map((g, i) => (
                                <tr key={`${g.date}-${i}`}>
                                  <td>{g.date}</td>
                                  <td>{g.opponent}</td>
                                  <td>{`${g.nu_goals}-${g.opp_goals}`}</td>
                                  <td>{g.decision}</td>
                                  <td>{g.saves}</td>
                                  <td>{g.goals_against}</td>
                                  <td>{Number(g.save_pct || 0).toFixed(3)}</td>
                                  <td>
                                    {g.boxscore_url ? (
                                      <a href={g.boxscore_url} target="_blank" rel="noreferrer">View</a>
                                    ) : "-"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>Date</th>
                                <th>Opponent</th>
                                <th>Score</th>
                                <th>G</th>
                                <th>A</th>
                                <th>PTS</th>
                                <th>SOG</th>
                                <th>+/-</th>
                                <th>BLK</th>
                                <th>FO</th>
                                <th>FO%</th>
                                <th>PIM</th>
                                <th>Box</th>
                              </tr>
                            </thead>
                            <tbody>
                              {visibleLogs.map((g, i) => {
                                const tracked = hasModernTracking(g.season);
                                const foPct = tracked ? formatPct3(g.faceoffs_won, g.faceoffs_lost) : null;
                                return (
                                  <tr key={`${g.date}-${i}`}>
                                    <td>{g.date}</td>
                                    <td>
                                      <span className="opp-with-logo">
                                        <OpponentLogo name={g.opponent} />
                                        <span>{g.opponent}</span>
                                      </span>
                                    </td>
                                    <td>{`${g.nu_goals}-${g.opp_goals}`}</td>
                                    <td>{g.goals}</td>
                                    <td>{g.assists}</td>
                                    <td><strong>{g.points}</strong></td>
                                    <td>{g.shots}</td>
                                    <td>{g.plus_minus > 0 ? `+${g.plus_minus}` : g.plus_minus}</td>
                                    <td>{tracked ? g.blocked_shots : <span className="muted">N/A</span>}</td>
                                    <td>{tracked ? `${g.faceoffs_won}-${g.faceoffs_lost}` : <span className="muted">N/A</span>}</td>
                                    <td>{foPct ?? <span className="muted">N/A</span>}</td>
                                    <td>{g.penalty_minutes}</td>
                                    <td>
                                      {g.boxscore_url ? (
                                        <a href={g.boxscore_url} target="_blank" rel="noreferrer">View</a>
                                      ) : "-"}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {playerData.game_logs?.length > 0 && (() => {
                  const parseMinutes = (val) => {
                    const text = String(val || "").trim();
                    if (text.includes(":")) {
                      const [m, s] = text.split(":");
                      const mins = Number(m) || 0;
                      const secs = Number(s) || 0;
                      return mins + secs / 60;
                    }
                    return Number(text) || 0;
                  };

                  const byOppMap = new Map();
                  for (const g of playerData.game_logs) {
                    const opp = String(g.opponent || "").trim();
                    if (!opp) continue;
                    let entry = byOppMap.get(opp);
                    if (!entry) {
                      entry = {
                        opponent: opp,
                        gp: 0,
                        goals: 0,
                        assists: 0,
                        points: 0,
                        shots: 0,
                        plus_minus: 0,
                        blocked_shots: 0,
                        multi_point_games: 0,
                        multi_goal_games: 0,
                        hat_tricks: 0,
                        has_tracked_blk_fo: false,
                        faceoffs_won: 0,
                        faceoffs_lost: 0,
                        pim: 0,
                        wins: 0,
                        losses: 0,
                        ties: 0,
                        saves: 0,
                        ga: 0,
                        shutouts: 0,
                        minutes: 0,
                        games: [],
                      };
                      byOppMap.set(opp, entry);
                    }
                    entry.gp += 1;
                    entry.games.push(g);
                    if (playerData.is_goalie) {
                      const dec = String(g.decision || "").trim().toUpperCase();
                      if (dec === "W") entry.wins += 1;
                      else if (dec === "L") entry.losses += 1;
                      else if (dec === "T") entry.ties += 1;
                      entry.saves += Number(g.saves || 0);
                      entry.ga += Number(g.goals_against || 0);
                      entry.shutouts += Number(g.shutouts || 0);
                      entry.minutes += parseMinutes(g.minutes);
                    } else {
                      const gGoals = Number(g.goals || 0);
                      const gPoints = Number(g.points || 0);
                      entry.goals += gGoals;
                      if (gPoints >= 2) entry.multi_point_games += 1;
                      if (gGoals >= 2) entry.multi_goal_games += 1;
                      if (gGoals >= 3) entry.hat_tricks += 1;
                      entry.assists += Number(g.assists || 0);
                      entry.points += gPoints;
                      entry.shots += Number(g.shots || 0);
                      entry.plus_minus += Number(g.plus_minus || 0);
                      entry.pim += Number(g.penalty_minutes || 0);
                      if (hasModernTracking(g.season)) {
                        entry.has_tracked_blk_fo = true;
                        entry.blocked_shots += Number(g.blocked_shots || 0);
                        entry.faceoffs_won += Number(g.faceoffs_won || 0);
                        entry.faceoffs_lost += Number(g.faceoffs_lost || 0);
                      }
                    }
                  }

                  const oppRows = Array.from(byOppMap.values()).sort((a, b) => {
                    if (b.gp !== a.gp) return b.gp - a.gp;
                    return playerData.is_goalie ? b.saves - a.saves : b.points - a.points;
                  });
                  const oppNamesAlpha = oppRows
                    .map((r) => r.opponent)
                    .sort((a, b) => a.localeCompare(b));
                  const selectedOppStats =
                    playerOpponent !== "all" ? byOppMap.get(playerOpponent) || null : null;

                  return (
                    <div className="card">
                      <div className="card-header">
                        <h2>
                          {selectedOppStats
                            ? `Career vs. ${selectedOppStats.opponent}`
                            : `Career Stats by Opponent (${oppRows.length})`}
                        </h2>
                        <select
                          aria-label="Filter career stats by opponent"
                          className="select-input"
                          value={playerOpponent}
                          onChange={(e) => setPlayerOpponent(e.target.value)}
                        >
                          <option value="all">All Opponents ({oppRows.length})</option>
                          {oppNamesAlpha.map((opp) => (
                            <option key={opp} value={opp}>
                              {opp}
                            </option>
                          ))}
                        </select>
                      </div>

                      {selectedOppStats ? (
                        <>
                          {playerData.is_goalie ? (
                            <div className="stat-grid" style={{ marginBottom: 16 }}>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.gp}</div>
                                <div className="lbl">GP</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">{`${selectedOppStats.wins}-${selectedOppStats.losses}-${selectedOppStats.ties}`}</div>
                                <div className="lbl">W-L-T</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">
                                  {selectedOppStats.minutes > 0
                                    ? ((selectedOppStats.ga * 60) / selectedOppStats.minutes).toFixed(2)
                                    : "0.00"}
                                </div>
                                <div className="lbl">GAA</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">
                                  {selectedOppStats.saves + selectedOppStats.ga > 0
                                    ? (
                                        selectedOppStats.saves /
                                        (selectedOppStats.saves + selectedOppStats.ga)
                                      ).toFixed(3)
                                    : ".000"}
                                </div>
                                <div className="lbl">SV%</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.saves}</div>
                                <div className="lbl">Saves</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.ga}</div>
                                <div className="lbl">GA</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.shutouts}</div>
                                <div className="lbl">Shutouts</div>
                              </div>
                            </div>
                          ) : (
                            <div className="stat-grid" style={{ marginBottom: 16 }}>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.gp}</div>
                                <div className="lbl">GP</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.goals}</div>
                                <div className="lbl">Goals</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.assists}</div>
                                <div className="lbl">Assists</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.points}</div>
                                <div className="lbl">Points</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.shots}</div>
                                <div className="lbl">SOG</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">
                                  {formatRatio3(selectedOppStats.goals, selectedOppStats.shots) ?? ".000"}
                                </div>
                                <div className="lbl">SH%</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">
                                  {selectedOppStats.plus_minus > 0
                                    ? `+${selectedOppStats.plus_minus}`
                                    : selectedOppStats.plus_minus}
                                </div>
                                <div className="lbl">+/-</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">
                                  {selectedOppStats.has_tracked_blk_fo
                                    ? selectedOppStats.blocked_shots
                                    : "N/A"}
                                </div>
                                <div className="lbl">Blocks</div>
                              </div>
                              <button
                                type="button"
                                className="stat-box stat-box-btn"
                                onClick={() =>
                                  openPenaltyBreakdown({
                                    mode: "player",
                                    player: playerData.bio.player_name,
                                    season: "all",
                                    opponent: selectedOppStats.opponent,
                                  })
                                }
                                aria-label={`View ${playerData.bio.player_name} penalty breakdown vs ${selectedOppStats.opponent}`}
                              >
                                <div className="val">{selectedOppStats.pim}</div>
                                <div className="lbl">PIM</div>
                                <div className="stat-box-hint">Breakdown &rarr;</div>
                              </button>
                                <div className="stat-box">
                                <div className="val">{selectedOppStats.multi_point_games}</div>
                                <div className="lbl">Multi-Point Games</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.multi_goal_games}</div>
                                <div className="lbl">Multi-Goal Games</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">{selectedOppStats.hat_tricks}</div>
                                <div className="lbl">Hat Tricks</div>
                              </div>
                              <div className="stat-box">
                                <div className="val">
                                  {selectedOppStats.has_tracked_blk_fo &&
                                  selectedOppStats.faceoffs_won + selectedOppStats.faceoffs_lost > 0
                                    ? `${(
                                        (selectedOppStats.faceoffs_won /
                                          (selectedOppStats.faceoffs_won +
                                            selectedOppStats.faceoffs_lost)) *
                                        100
                                      ).toFixed(1)}%`
                                    : "N/A"}
                                </div>
                                <div className="lbl">
                                  {selectedOppStats.has_tracked_blk_fo &&
                                  selectedOppStats.faceoffs_won + selectedOppStats.faceoffs_lost > 0
                                    ? `FO% (${selectedOppStats.faceoffs_won}-${selectedOppStats.faceoffs_lost})`
                                    : "FO%"}
                                </div>
                              </div>
                            </div>
                          )}

                          <div className="table-wrap">
                            {playerData.is_goalie ? (
                              <table className="data-table">
                                <thead>
                                  <tr>
                                    <th>Date</th>
                                    <th>Season</th>
                                    <th>Score</th>
                                    <th>Dec</th>
                                    <th>SV</th>
                                    <th>GA</th>
                                    <th>SV%</th>
                                    <th>Box</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {selectedOppStats.games.map((g, i) => (
                                    <tr key={`${g.date}-${i}`}>
                                      <td>{g.date}</td>
                                      <td>{g.season}</td>
                                      <td>{`${g.nu_goals}-${g.opp_goals}`}</td>
                                      <td>{g.decision}</td>
                                      <td>{g.saves}</td>
                                      <td>{g.goals_against}</td>
                                      <td>{Number(g.save_pct || 0).toFixed(3)}</td>
                                      <td>
                                        {g.boxscore_url ? (
                                          <a href={g.boxscore_url} target="_blank" rel="noreferrer">View</a>
                                        ) : "-"}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            ) : (
                              <table className="data-table">
                                <thead>
                                  <tr>
                                    <th>Date</th>
                                    <th>Season</th>
                                    <th>Score</th>
                                    <th>G</th>
                                    <th>A</th>
                                    <th>PTS</th>
                                    <th>SOG</th>
                                    <th>+/-</th>
                                    <th>BLK</th>
                                    <th>PIM</th>
                                    <th>Box</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {selectedOppStats.games.map((g, i) => (
                                    <tr key={`${g.date}-${i}`}>
                                      <td>{g.date}</td>
                                      <td>{g.season}</td>
                                      <td>{`${g.nu_goals}-${g.opp_goals}`}</td>
                                      <td>{g.goals}</td>
                                      <td>{g.assists}</td>
                                      <td><strong>{g.points}</strong></td>
                                      <td>{g.shots}</td>
                                      <td>{g.plus_minus > 0 ? `+${g.plus_minus}` : g.plus_minus}</td>
                                      <td>{hasModernTracking(g.season) ? g.blocked_shots : <span className="muted">N/A</span>}</td>
                                      <td>{g.penalty_minutes}</td>
                                      <td>
                                        {g.boxscore_url ? (
                                          <a href={g.boxscore_url} target="_blank" rel="noreferrer">View</a>
                                        ) : "-"}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </div>
                        </>
                      ) : (
                        <div className="table-wrap">
                          {playerData.is_goalie ? (
                            <table className="data-table">
                              <thead>
                                <tr>
                                  <th>Opponent</th>
                                  <th>GP</th>
                                  <th>W-L-T</th>
                                  <th>GAA</th>
                                  <th>SV%</th>
                                  <th>SV</th>
                                  <th>GA</th>
                                  <th>SO</th>
                                </tr>
                              </thead>
                              <tbody>
                                {oppRows.map((row) => (
                                  <tr key={row.opponent}>
                                    <td>
                                      <button
                                        type="button"
                                        className="link-btn opp-with-logo"
                                        onClick={() => setPlayerOpponent(row.opponent)}
                                      >
                                        <OpponentLogo name={row.opponent} />
                                        <span>{row.opponent}</span>
                                      </button>
                                    </td>
                                    <td>{row.gp}</td>
                                    <td>{`${row.wins}-${row.losses}-${row.ties}`}</td>
                                    <td>
                                      {row.minutes > 0
                                        ? ((row.ga * 60) / row.minutes).toFixed(2)
                                        : "0.00"}
                                    </td>
                                    <td>
                                      {row.saves + row.ga > 0
                                        ? (row.saves / (row.saves + row.ga)).toFixed(3)
                                        : ".000"}
                                    </td>
                                    <td>{row.saves}</td>
                                    <td>{row.ga}</td>
                                    <td>{row.shutouts}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            <table className="data-table">
                              <thead>
                                <tr>
                                  <th>Opponent</th>
                                  <th>GP</th>
                                  <th>G</th>
                                  <th>A</th>
                                  <th>PTS</th>
                                  <th>SOG</th>
                                  <th>SH%</th>
                                  <th>+/-</th>
                                  <th>BLK</th>
                                  <th>FO</th>
                                  <th>FO%</th>
                                  <th>PIM</th>
                                  <th>MPG</th>
                                  <th>MGG</th>
                                  <th>HTG</th>
                                </tr>
                              </thead>
                              <tbody>
                                {oppRows.map((row) => (
                                  <tr key={row.opponent}>
                                    <td>
                                      <button
                                        type="button"
                                        className="link-btn opp-with-logo"
                                        onClick={() => setPlayerOpponent(row.opponent)}
                                      >
                                        <OpponentLogo name={row.opponent} />
                                        <span>{row.opponent}</span>
                                      </button>
                                    </td>
                                    <td>{row.gp}</td>
                                    <td>{row.goals}</td>
                                    <td>{row.assists}</td>
                                    <td><strong>{row.points}</strong></td>
                                    <td>{row.shots}</td>
                                    <td>{formatRatio3(row.goals, row.shots) ?? ".000"}</td>
                                    <td>{row.plus_minus > 0 ? `+${row.plus_minus}` : row.plus_minus}</td>
                                    <td>{row.has_tracked_blk_fo ? row.blocked_shots : <span className="muted">N/A</span>}</td>
                                    <td>
                                      {row.has_tracked_blk_fo
                                        ? `${row.faceoffs_won}-${row.faceoffs_lost}`
                                        : <span className="muted">N/A</span>}
                                    </td>
                                    <td>
                                      {row.has_tracked_blk_fo
                                        ? formatPct3(row.faceoffs_won, row.faceoffs_lost) ?? ".000"
                                        : <span className="muted">N/A</span>}
                                    </td>
                                    <td>{row.pim}</td>
                                    <td>{row.multi_point_games}</td>
                                    <td>{row.multi_goal_games}</td>
                                    <td>{row.hat_tricks}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </>
            )}
          </section>
        ) : (
        <>
        {tab === "chat" && (
          <section className="chat-box">
            {messages.length === 0 ? (
              <div className="card hero-card">
                <h2>Ask Paws About Huskies Hockey</h2>
                <p>
                  Instant answers from official box scores, rosters, Beanpot games,
                  shootouts, and Hockey East archives (1999&ndash;present).
                </p>
                <div className="starter-grid">
                  {STARTER_QUESTIONS.map((q) => (
                    <button
                      key={q}
                      className="starter-chip"
                      onClick={() => sendQuestion(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="controls-row">
                <span className="muted">Conversation active</span>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => setMessages([])}
                >
                  Clear chat
                </button>
              </div>
            )}

            <div className="messages" role="log" aria-live="polite" aria-relevant="additions">
              {messages.map((m, idx) => (
                <div key={idx} className={`msg-row ${m.role}`}>
                  <div className={`msg ${m.role}`}>
                    {m.role === "assistant" ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {m.content}
                      </ReactMarkdown>
                    ) : (
                      m.content
                    )}
                  </div>
                  {m.role === "assistant" && m.cached && (
                    <span className="msg-meta">Instant cached answer</span>
                  )}
                </div>
              ))}
              {chatLoading && (
                <div className="msg-row assistant" role="status" aria-live="polite">
                  <div className="msg assistant">
                    <span className="typing-dots">Querying NU archives...</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <form
              className="chat-form"
              onSubmit={(e) => {
                e.preventDefault();
                sendQuestion(input);
              }}
            >
              <input
                className="text-input"
                type="text"
                aria-label="Ask Paws a hockey stats question"
                placeholder="Ask Paws about players, games, Beanpot, shootouts..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={chatLoading}
              />
              <button
                className="btn-primary"
                type="submit"
                disabled={chatLoading || !input.trim()}
              >
                Ask
              </button>
            </form>
          </section>
        )}

        {(tab === "leaders" || tab === "roster") && (
          <div className="controls-row">
            <div className="controls-group">
              <label htmlFor="season-select" className="field-label">
                Season
              </label>
              <select
                id="season-select"
                className="select-input"
                value={selectedSeason}
                onChange={(e) => setSelectedSeason(e.target.value)}
              >
                {tab === "leaders" && (
                  <option value="all">All Seasons (1999&ndash;Present)</option>
                )}
                {seasons.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>

              {tab === "leaders" && (
                <>
                  <div className="segmented" role="group" aria-label="Game scope">
                    <button
                      type="button"
                      className={`segmented-btn ${leaderScope === "all" ? "active" : ""}`}
                      aria-pressed={leaderScope === "all"}
                      onClick={() => setLeaderScope("all")}
                    >
                      All Games
                    </button>
                    <button
                      type="button"
                      className={`segmented-btn ${leaderScope === "conference" ? "active" : ""}`}
                      aria-pressed={leaderScope === "conference"}
                      onClick={() => setLeaderScope("conference")}
                    >
                      Hockey East
                    </button>
                  </div>

                  <select
                    aria-label="Filter stats by opponent"
                    className="select-input"
                    value={leaderOpponent}
                    onChange={(e) => setLeaderOpponent(e.target.value)}
                  >
                    <option value="">
                      {leaderScope === "conference" ? "All Hockey East Opponents" : "All Opponents"}
                    </option>
                    {(leaders?.opponents || []).map((opp) => (
                      <option key={opp} value={opp}>
                        vs. {opp}
                      </option>
                    ))}
                  </select>
                </>
              )}
            </div>

            {tab === "leaders" && (
              <div className="controls-group">
                <div className="segmented" role="group" aria-label="Stats view">
                  <button
                    type="button"
                    className={`segmented-btn ${statsView === "players" ? "active" : ""}`}
                    aria-pressed={statsView === "players"}
                    onClick={() => setStatsView("players")}
                  >
                    Individual Players
                  </button>
                  <button
                    type="button"
                    className={`segmented-btn ${statsView === "team" ? "active" : ""}`}
                    aria-pressed={statsView === "team"}
                    onClick={() => setStatsView("team")}
                  >
                    Team Stats
                  </button>
                </div>
              </div>
            )}

            {tab === "roster" && (
              <div className="controls-group">
                <div className="segmented" role="group" aria-label="Roster view">
                  <button
                    type="button"
                    className={`segmented-btn ${rosterView === "position" ? "active" : ""}`}
                    aria-pressed={rosterView === "position"}
                    onClick={() => setRosterView("position")}
                  >
                    By Position
                  </button>
                  <button
                    type="button"
                    className={`segmented-btn ${rosterView === "all" ? "active" : ""}`}
                    aria-pressed={rosterView === "all"}
                    onClick={() => setRosterView("all")}
                  >
                    All Roster
                  </button>
                </div>

                <div className="search-wrap">
                  <SearchIcon />
                  <input
                    type="search"
                    className="text-input search-input"
                    aria-label="Filter roster by player, number, or hometown"
                    placeholder="Filter by name, #, hometown..."
                    value={rosterSearch}
                    onChange={(e) => setRosterSearch(e.target.value)}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "leaders" && statsView === "team" && (
          <section className="card">
            <div className="card-header">
              <h2 className="opp-with-logo">
                {leaderOpponent && <OpponentLogo name={leaderOpponent} large />}
                <span>
                  {selectedSeason === "all" ? "All-Time" : selectedSeason}{" "}
                  {leaderOpponent
                    ? `Team Stats vs. ${leaderOpponent}`
                    : leaderScope === "conference"
                      ? "Hockey East Team Stats"
                      : "Team Stats"}
                </span>
              </h2>
              <span className="muted">
                {leaderOpponent
                  ? `Filtered to games vs. ${leaderOpponent}`
                  : leaderScope === "conference"
                    ? "Hockey East conference games"
                    : "All games"}
              </span>
            </div>
            {leadersLoading && <p className="muted">Loading team stats...</p>}
            {!leadersLoading && (!leaders?.team_stats || leaders.team_stats.games_played === 0) && (
              <p className="muted">No team stats found for this filter combination.</p>
            )}
            {!leadersLoading && leaders?.team_stats && leaders.team_stats.games_played > 0 && (() => {
              const ts = leaders.team_stats;
              const diffStr = ts.goal_diff > 0 ? `+${ts.goal_diff}` : String(ts.goal_diff);
              const winPctStr = Number(ts.win_pct || 0).toFixed(3).replace(/^0/, "");
              const savePctStr = ts.saves > 0 ? Number(ts.save_pct || 0).toFixed(3).replace(/^0/, "") : null;
              return (
                <>
                  <div className="stat-grid">
                    <div className="stat-box">
                      <div className="val">{`${ts.wins}-${ts.losses}-${ts.ties}`}</div>
                      <div className="lbl">{`Record (${ts.games_played} GP)`}</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{winPctStr}</div>
                      <div className="lbl">Win %</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.goals_for}</div>
                      <div className="lbl">{`Goals For (${ts.gf_per_game}/gm)`}</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.goals_against}</div>
                      <div className="lbl">{`Goals Against (${ts.ga_per_game}/gm)`}</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{diffStr}</div>
                      <div className="lbl">Goal Diff</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.shots > 0 ? ts.shots : "N/A"}</div>
                      <div className="lbl">{ts.shots > 0 ? `Shots (${ts.shot_pct}%)` : "Shots"}</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.shutouts_for}</div>
                      <div className="lbl">{`Shutouts (${ts.shutouts_against} Against)`}</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.saves > 0 ? ts.saves : "N/A"}</div>
                      <div className="lbl">{savePctStr ? `Saves (${savePctStr} SV%)` : "Saves"}</div>
                    </div>
                    {ts.ppg !== null && (
                      <div className="stat-box">
                        <div className="val">{`${ts.ppg} / ${ts.shg}`}</div>
                        <div className="lbl">PPG / SHG</div>
                      </div>
                    )}
                    <button
                      type="button"
                      className="stat-box stat-box-btn"
                      onClick={() =>
                        openPenaltyBreakdown({
                          mode: "team",
                          season: selectedSeason,
                          scope: leaderScope,
                          opponent: leaderOpponent,
                        })
                      }
                      aria-label="View team penalty breakdown"
                    >
                      <div className="val">{ts.pim}</div>
                      <div className="lbl">Penalty Min</div>
                      <div className="stat-box-hint">Breakdown &rarr;</div>
                    </button>
                    <div className="stat-box">
                      <div className="val">
                        {hasModernTracking(selectedSeason) ? ts.blocked_shots : "N/A"}
                      </div>
                      <div className="lbl">Blocks</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.multi_goal_games ?? 0}</div>
                      <div className="lbl">
                        {`Multi-Goal Games (${ts.hat_tricks ?? 0} Hat Tricks)`}
                      </div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.multi_point_games ?? 0}</div>
                      <div className="lbl">Multi-Point Games</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">
                        {hasModernTracking(selectedSeason) && ts.faceoff_pct !== null && ts.faceoff_pct !== undefined
                          ? `${ts.faceoff_pct}%`
                          : "N/A"}
                      </div>
                      <div className="lbl">
                        {hasModernTracking(selectedSeason) && ts.faceoff_pct !== null && ts.faceoff_pct !== undefined
                          ? `Faceoff % (${ts.faceoffs_won}-${ts.faceoffs_lost})`
                          : "Faceoff %"}
                      </div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.one_goal_record || "0-0-0"}</div>
                      <div className="lbl">1-Goal Games</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.ot_record || "0-0-0"}</div>
                      <div className="lbl">{`OT Record (${ts.ot_games ?? 0} OT)`}</div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.shootout_record || "0-0"}</div>
                      <div className="lbl">
                        {ts.shootout_attempts > 0
                          ? `Shootout (${ts.shootout_made}/${ts.shootout_attempts}, ${ts.shootout_pct}%)`
                          : "Shootout Record"}
                      </div>
                    </div>
                    <div className="stat-box">
                      <div className="val">{ts.scoring_first_record || "0-0-0"}</div>
                      <div className="lbl">When Scoring First</div>
                    </div>
                  </div>

                  {ts.goals_by_period?.length > 0 && (
                    <>
                      <h3 style={{ marginTop: 20 }}>Goals by Period</h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Team</th>
                              {ts.goals_by_period.map((p) => (
                                <th key={p.period}>{p.period}</th>
                              ))}
                              <th>Total</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr>
                              <td><strong>Northeastern</strong></td>
                              {ts.goals_by_period.map((p) => (
                                <td key={p.period}>{p.nu_goals}</td>
                              ))}
                              <td>
                                <strong>
                                  {ts.goals_by_period.reduce((acc, p) => acc + (p.nu_goals || 0), 0)}
                                </strong>
                              </td>
                            </tr>
                            <tr>
                              <td>Opponents</td>
                              {ts.goals_by_period.map((p) => (
                                <td key={p.period}>{p.opp_goals}</td>
                              ))}
                              <td>
                                <strong>
                                  {ts.goals_by_period.reduce((acc, p) => acc + (p.opp_goals || 0), 0)}
                                </strong>
                              </td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}

                  {selectedSeason === "all" && ts.season_breakdown?.length > 0 && (
                    <>
                      <h3 style={{ marginTop: 20 }}>Season-by-Season Record</h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Season</th>
                              <th>GP</th>
                              <th>W-L-T</th>
                              <th>Win %</th>
                              <th>GF</th>
                              <th>GA</th>
                              <th>Diff</th>
                            </tr>
                          </thead>
                          <tbody>
                            {ts.season_breakdown.map((row) => (
                              <tr key={row.season}>
                                <td>{row.season}</td>
                                <td>{row.gp}</td>
                                <td>{`${row.wins}-${row.losses}-${row.ties}`}</td>
                                <td>{Number(row.win_pct || 0).toFixed(3).replace(/^0/, "")}</td>
                                <td>{row.goals_for}</td>
                                <td>{row.goals_against}</td>
                                <td>{row.goal_diff > 0 ? `+${row.goal_diff}` : row.goal_diff}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}

                  {selectedSeason !== "all" && ts.games?.length > 0 && (
                    <>
                      <h3 style={{ marginTop: 20 }}>Season Games</h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Date</th>
                              <th>Opponent</th>
                              <th>Result</th>
                              <th>Score</th>
                              <th>OT/SO</th>
                              <th>Box Score</th>
                            </tr>
                          </thead>
                          <tbody>
                            {ts.games.map((g) => (
                              <tr key={`${g.date}-${g.opponent}`}>
                                <td>{g.date}</td>
                                <td>
                                  <span className="opp-with-logo">
                                    <OpponentLogo name={g.opponent} />
                                    <span>{g.opponent}</span>
                                  </span>
                                </td>
                                <td><OutcomeBadge outcome={g.outcome} /></td>
                                <td>{`${g.nu_goals}-${g.opp_goals}`}</td>
                                <td>{g.overtime_status}</td>
                                <td>
                                  {g.boxscore_url ? (
                                    <a href={g.boxscore_url} target="_blank" rel="noreferrer">
                                      View
                                    </a>
                                  ) : (
                                    "-"
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </>
              );
            })()}
          </section>
        )}

        {tab === "leaders" && statsView === "players" && (
          <section className="card">
            <div className="card-header">
              <h2 className="opp-with-logo">
                {leaderOpponent && <OpponentLogo name={leaderOpponent} large />}
                <span>
                  {selectedSeason === "all" ? "All-Time" : selectedSeason}{" "}
                  {leaderOpponent
                    ? `Player Stats vs. ${leaderOpponent}`
                    : leaderScope === "conference"
                      ? "Hockey East Player Stats"
                      : "Skater Stats"}
                </span>
              </h2>
              <span className="muted">
                {leaderOpponent
                  ? "Includes all games vs. school • Tap headers to sort"
                  : "Tap column headers to sort"}
              </span>
            </div>
            {leadersLoading && <p className="muted">Loading stats...</p>}
            {!leadersLoading && sortedSkaters.length === 0 && (
              <p className="muted">No skater stats found for this filter combination.</p>
            )}
            {!leadersLoading && sortedSkaters.length > 0 && (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      <th scope="col">Player</th>
                      <th scope="col">Pos</th>
                      {[
                        ["gp", "GP", "Games Played"],
                        ["goals", "G", "Goals"],
                        ["assists", "A", "Assists"],
                        ["points", "PTS", "Points"],
                        ["shots", "SOG", "Shots on Goal"],
                        ["shot_pct", "SH%", "Shooting Percentage"],
                        ["plus_minus", "+/-", "Plus/Minus"],
                        ["ppg", "PPG", "Power Play Goals"],
                        ["shg", "SHG", "Short-Handed Goals"],
                        ["gwg", "GWG", "Game-Winning Goals"],
                        ["blocked_shots", "BLK", "Blocked Shots"],
                        ["faceoff_pct", "FO%", "Faceoff Percentage"],
                        ["pim", "PIM", "Penalty Minutes"],
                        ["multi_point_games", "MPG", "Multi-Point Games"],
                        ["multi_goal_games", "MGG", "Multi-Goal Games"],
                        ["hat_tricks", "HTG", "Hat Tricks"],
                      ].map(([colKey, label, fullLabel]) => {
                        const isSorted = leaderSort.key === colKey;
                        const ariaSort = isSorted
                          ? leaderSort.dir === "desc"
                            ? "descending"
                            : "ascending"
                          : "none";
                        return (
                          <th
                            key={colKey}
                            scope="col"
                            className="sortable"
                            aria-sort={ariaSort}
                            tabIndex={0}
                            aria-label={`Sort by ${fullLabel}`}
                            onClick={() => toggleSort(colKey)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                toggleSort(colKey);
                              }
                            }}
                          >
                            {label} {isSorted ? (leaderSort.dir === "desc" ? "↓" : "↑") : ""}
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedSkaters.map((p) => (
                      <tr key={p.player_name}>
                        <td>{p.jersey_number}</td>
                        <td>
                          <span className="roster-player-cell">
                            {p.image_url && (
                              <img
                                src={p.image_url}
                                alt=""
                                className="player-avatar-sm"
                                loading="lazy"
                              />
                            )}
                            <button
                              type="button"
                              className="player-link"
                              onClick={() => openPlayer(p.player_name)}
                            >
                              {p.player_name}
                            </button>
                            <CaptainBadge role={p.captain_role} />
                          </span>
                        </td>
                        <td>{p.position}</td>
                        <td>{p.gp}</td>
                        <td>{p.goals}</td>
                        <td>{p.assists}</td>
                        <td><strong>{p.points}</strong></td>
                        <td>{p.shots ?? <span className="muted">N/A</span>}</td>
                        <td>
                          {p.shots !== undefined
                            ? (formatRatio3(p.goals, p.shots) ?? ".000")
                            : p.shot_pct !== undefined
                              ? (Number(p.shot_pct) / 100).toFixed(3).replace(/^0/, "")
                              : <span className="muted">N/A</span>}
                        </td>
                        <td>{p.plus_minus > 0 ? `+${p.plus_minus}` : p.plus_minus}</td>
                        <td>{p.ppg !== undefined && p.ppg !== null ? p.ppg : <span className="muted">N/A</span>}</td>
                        <td>{p.shg !== undefined && p.shg !== null ? p.shg : <span className="muted">N/A</span>}</td>
                        <td>{p.gwg !== undefined && p.gwg !== null ? p.gwg : <span className="muted">N/A</span>}</td>
                        <td>{hasModernTracking(selectedSeason) ? p.blocked_shots : <span className="muted">N/A</span>}</td>
                        <td>
                          {hasModernTracking(selectedSeason) && p.faceoff_pct !== null && p.faceoff_pct !== undefined
                            ? `${p.faceoff_pct}%`
                            : <span className="muted">N/A</span>}
                        </td>
                        <td>{p.pim}</td>
                        <td>{p.multi_point_games ?? 0}</td>
                        <td>{p.multi_goal_games ?? 0}</td>
                        <td>{p.hat_tricks ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {!leadersLoading && leaders?.goalies?.length > 0 && (
              <>
                <h3 style={{ marginTop: 20 }}>Goalies</h3>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Goalie</th>
                        <th>GP</th>
                        <th>GS</th>
                        <th>MIN</th>
                        <th>W-L-T</th>
                        <th>GAA</th>
                        <th>SV%</th>
                        <th>SO</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leaders.goalies.map((g) => (
                        <tr key={g.player_name}>
                          <td>{g.jersey_number}</td>
                          <td>
                            <button
                              type="button"
                              className="player-link"
                              onClick={() => openPlayer(g.player_name)}
                            >
                              {g.player_name}
                            </button>
                          </td>
                          <td>{g.goalie_gp}</td>
                          <td>{g.goalie_gs ?? 0}</td>
                          <td>{g.goalie_minutes || "0:00"}</td>
                          <td>{`${g.wins}-${g.losses}-${g.ties}`}</td>
                          <td>{Number(g.gaa).toFixed(2)}</td>
                          <td>{Number(g.save_pct).toFixed(3)}</td>
                          <td>{g.shutouts}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        )}

        {tab === "roster" && (
          <section className="card">
            <div className="card-header">
              <h2>
                {selectedSeason} Roster
                {roster?.head_coach ? ` — Coach ${roster.head_coach}` : ""}
              </h2>
              {roster?.roster_url && (
                <a
                  href={roster.roster_url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-ghost"
                  style={{ textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                >
                  Official Roster
                </a>
              )}
            </div>
            {rosterLoading && <p className="muted">Loading roster...</p>}
            {!rosterLoading && (() => {
              const forwards = filteredRoster.filter((p) => p.position === "F");
              const defensemen = filteredRoster.filter((p) => p.position === "D");
              const goalies = filteredRoster.filter((p) => p.position === "G");
              const other = filteredRoster.filter((p) => !["F", "D", "G"].includes(p.position));

              const renderRows = (list) =>
                list.map((p) => (
                  <tr key={`${p.jersey_number}-${p.player_name}`}>
                    <td><strong>{p.jersey_number}</strong></td>
                    <td>
                      <span className="roster-player-cell">
                        {p.image_url && (
                          <img
                            src={p.image_url}
                            alt=""
                            className="player-avatar-sm"
                            loading="lazy"
                          />
                        )}
                        <button
                          type="button"
                          className="player-link"
                          onClick={() => openPlayer(p.player_name)}
                        >
                          {p.player_name}
                        </button>
                        <CaptainBadge role={p.captain_role} />
                      </span>
                    </td>
                    <td>{p.position}</td>
                    <td>{p.class_year}</td>
                    <td>{p.height ? `${p.height} / ${p.weight || "-"}` : "-"}</td>
                    <td>{p.hometown}</td>
                  </tr>
                ));

              const renderSection = (title, list, label = "Player", marginTop = 0) => (
                <div style={marginTop ? { marginTop } : undefined}>
                  <h3>{title} ({list.length})</h3>
                  {list.length === 0 ? (
                    <p className="muted">No matching {title.toLowerCase()}.</p>
                  ) : (
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>{label}</th>
                            <th>Pos</th>
                            <th>Yr</th>
                            <th>Ht / Wt</th>
                            <th>Hometown</th>
                          </tr>
                        </thead>
                        <tbody>{renderRows(list)}</tbody>
                      </table>
                    </div>
                  )}
                </div>
              );

              if (rosterView === "all") {
                return renderSection("Full Roster", filteredRoster, "Player", 0);
              }

              return (
                <>
                  {renderSection("Forwards", forwards, "Forward", 0)}
                  {renderSection("Defensemen", defensemen, "Defenseman", 20)}
                  {renderSection("Goalies", goalies, "Goalie", 20)}
                  {other.length > 0 && renderSection("Other", other, "Player", 20)}
                </>
              );
            })()}
          </section>
        )}

        {tab === "rivalry" && (
          <section className="card">
            <div className="card-header">
              <h2>
                Head-to-Head ({rivalryScope === "season" && seasons[0] ? seasons[0] : "1999\u2013Present"})
              </h2>
              <div className="controls-row">
                <div className="segmented" role="group" aria-label="Matchup timeframe">
                  <button
                    type="button"
                    className={`segmented-btn ${rivalryScope === "season" ? "active" : ""}`}
                    aria-pressed={rivalryScope === "season"}
                    onClick={() => setRivalryScope("season")}
                  >
                    {seasons[0] ? `This Season (${seasons[0]})` : "This Season"}
                  </button>
                  <button
                    type="button"
                    className={`segmented-btn ${rivalryScope === "all" ? "active" : ""}`}
                    aria-pressed={rivalryScope === "all"}
                    onClick={() => setRivalryScope("all")}
                  >
                    All-Time
                  </button>
                </div>
                <select
                  aria-label="Select opponent"
                  className="select-input"
                  value={selectedRival}
                  onChange={(e) => setSelectedRival(e.target.value)}
                >
                <optgroup label="Hockey East">
                  {hockeyEastOpponents.map((opp) => (
                    <option key={opp} value={opp}>
                      {opp}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Other Opponents">
                  {otherOpponents.map((opp) => (
                    <option key={opp} value={opp}>
                      {opp}
                    </option>
                  ))}
                </optgroup>
              </select>
              </div>
            </div>

            {rivalryLoading && <p className="muted" role="status" aria-live="polite">Loading matchup history...</p>}
            {!rivalryLoading && rivalry && (
              <>
                <div className="stat-grid">
                  <div className="stat-box">
                    <div className="val">{`${rivalry.wins}-${rivalry.losses}-${rivalry.ties}`}</div>
                    <div className="lbl">NU Record</div>
                  </div>
                  <div className="stat-box">
                    <div className="val">{rivalry.games_played}</div>
                    <div className="lbl">Games</div>
                  </div>
                  <div className="stat-box">
                    <div className="val">{rivalry.ot_games}</div>
                    <div className="lbl">OT / SO</div>
                  </div>
                  <div className="stat-box">
                    <div className="val">{`${rivalry.nu_goals}-${rivalry.opp_goals}`}</div>
                    <div className="lbl">Goals (NU-Opp)</div>
                  </div>
                </div>

                <h3 className="opp-with-logo">
                  <OpponentLogo name={rivalry.opponent} large />
                  <span>
                    {rivalryScope === "season" && seasons[0]
                      ? `${seasons[0]} Meetings vs. ${rivalry.opponent}`
                      : `All Meetings vs. ${rivalry.opponent}`}
                  </span>
                </h3>
                {rivalry.recent_games.length === 0 ? (
                  <p className="muted">
                    No recorded games against {rivalry.opponent}
                    {rivalryScope === "season" && seasons[0] ? ` in ${seasons[0]}` : ""}.
                  </p>
                ) : (() => {
                  const pageSize = 15;
                  const totalGames = rivalry.recent_games.length;
                  const totalPages = Math.max(1, Math.ceil(totalGames / pageSize));
                  const safePage = Math.min(rivalryPage, totalPages);
                  const startIdx = (safePage - 1) * pageSize;
                  const visibleGames = rivalry.recent_games.slice(startIdx, startIdx + pageSize);
                  return (
                    <>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Date</th>
                              <th>Season</th>
                              <th>Result</th>
                              <th>Score</th>
                              <th>OT/SO</th>
                              <th>Box Score</th>
                            </tr>
                          </thead>
                          <tbody>
                            {visibleGames.map((g) => (
                              <tr key={`${g.date}-${g.opponent}`}>
                                <td>{g.date}</td>
                                <td>{g.season}</td>
                                <td><OutcomeBadge outcome={g.outcome} /></td>
                                <td>{`${g.nu_goals}-${g.opp_goals}`}</td>
                                <td>{g.overtime_status}</td>
                                <td>
                                  {g.boxscore_url ? (
                                    <a href={g.boxscore_url} target="_blank" rel="noreferrer">
                                      View
                                    </a>
                                  ) : (
                                    "-"
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {totalPages > 1 && (
                        <nav className="pagination-bar" aria-label="Opponent games pagination">
                          <span className="muted">
                            Showing {startIdx + 1}–{Math.min(startIdx + pageSize, totalGames)} of {totalGames} games
                          </span>
                          <div className="pagination-controls">
                            <button
                              type="button"
                              className="btn-ghost"
                              onClick={() => setRivalryPage((p) => Math.max(1, p - 1))}
                              disabled={safePage <= 1}
                              aria-label="Previous page of opponent games"
                            >
                              Previous
                            </button>
                            <span className="muted" aria-live="polite">
                              Page {safePage} of {totalPages}
                            </span>
                            <button
                              type="button"
                              className="btn-ghost"
                              onClick={() => setRivalryPage((p) => Math.min(totalPages, p + 1))}
                              disabled={safePage >= totalPages}
                              aria-label="Next page of opponent games"
                            >
                              Next
                            </button>
                          </div>
                        </nav>
                      )}
                    </>
                  );
                })()}
              </>
            )}
          </section>
        )}
        </>
        )}
      </main>

      <footer className="app-footer">
        <span>
          Unofficial fan-built Northeastern Men&apos;s Hockey explorer &bull; Not affiliated
          with Northeastern University
        </span>
        <div className="footer-links">
          <button
            type="button"
            className="footer-link"
            onClick={() => setLegalModal("disclaimer")}
          >
            Disclaimer
          </button>
          <button
            type="button"
            className="footer-link"
            onClick={() => setLegalModal("privacy")}
          >
            Privacy Policy
          </button>
          <button
            type="button"
            className="footer-link"
            onClick={() => setLegalModal("terms")}
          >
            Terms of Use
          </button>
          <button
            type="button"
            className="footer-link"
            onClick={() => setBugModalOpen(true)}
          >
            Report a Bug
          </button>
        </div>
      </footer>

      <LegalModal type={legalModal} onClose={() => setLegalModal(null)} />
      <BugReportModal
        open={bugModalOpen}
        onClose={() => setBugModalOpen(false)}
        apiBase={API_BASE}
        pageContext={
          selectedPlayer
            ? `Player: ${selectedPlayer} (${playerScope})`
            : tab === "leaders"
              ? `Stats (${statsView}) • Season: ${selectedSeason || "latest"} • Scope: ${leaderScope}${leaderOpponent ? ` • vs ${leaderOpponent}` : ""}`
              : tab === "roster"
                ? `Roster • Season: ${selectedSeason || "latest"} • View: ${rosterView}`
                : tab === "rivalry"
                  ? `Opponents • ${selectedRival} • ${rivalryScope === "season" ? seasons[0] || "This Season" : "All-Time"}`
                  : "Ask Paws Chat"
        }
      />

      {(selectedPlayer || tab !== "chat") && (
        !chatDrawerOpen ? (
          <button
            type="button"
            className="chat-fab"
            onClick={() => setChatDrawerOpen(true)}
          >
            <PawsIcon large />
            <span>{selectedPlayer ? `Ask Paws about ${selectedPlayer}` : "Ask Paws"}</span>
          </button>
        ) : (
          <aside className="chat-drawer" aria-label="Ask Paws Stats Assistant">
            <div className="chat-drawer-header">
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <PawsIcon large />
                <div className="chat-drawer-title">Ask Paws</div>
              </div>
              <div className="chat-drawer-actions">
                {messages.length > 0 && (
                  <button
                    type="button"
                    className="chat-drawer-btn"
                    onClick={() => setMessages([])}
                  >
                    Clear
                  </button>
                )}
                <button
                  type="button"
                  className="chat-drawer-btn"
                  onClick={() => setChatDrawerOpen(false)}
                  aria-label="Close AI chat"
                >
                  Close
                </button>
              </div>
            </div>

            <div className="chat-drawer-context-bar">
              <span className="muted" style={{ fontSize: 12 }}>
                {drawerUseContext
                  ? (selectedPlayer ? `Focused on ${selectedPlayer}` : `Focused on current ${tab} view`)
                  : "Searching all NU archives (1999–present)"}
              </span>
              <div className="chat-context-toggle" role="group" aria-label="Chat context scope">
                <button
                  type="button"
                  className={`chat-context-opt ${drawerUseContext ? "active" : ""}`}
                  aria-pressed={drawerUseContext}
                  onClick={() => setDrawerUseContext(true)}
                >
                  This Page
                </button>
                <button
                  type="button"
                  className={`chat-context-opt ${!drawerUseContext ? "active" : ""}`}
                  aria-pressed={!drawerUseContext}
                  onClick={() => setDrawerUseContext(false)}
                >
                  All Data
                </button>
              </div>
            </div>

            <div className="chat-drawer-body" role="log" aria-live="polite" aria-relevant="additions">
              {messages.length === 0 && (
                <p className="muted" style={{ margin: 0 }}>
                  {drawerUseContext && selectedPlayer
                    ? `Ask anything about ${selectedPlayer} — e.g. "How many overtime goals did he score?" or "Best game vs. BU?"`
                    : "Ask any question about Northeastern hockey stats, games, or players."}
                </p>
              )}
              {messages.map((m, idx) => (
                <div key={idx} className={`msg-row ${m.role}`}>
                  <div className={`msg ${m.role}`}>
                    {m.role === "assistant" ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {m.content}
                      </ReactMarkdown>
                    ) : (
                      m.content
                    )}
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div className="msg-row assistant" role="status" aria-live="polite">
                  <div className="msg assistant">
                    <span className="typing-dots">Querying NU archives...</span>
                  </div>
                </div>
              )}
              <div ref={drawerEndRef} />
            </div>

            <form
              className="chat-drawer-form"
              onSubmit={(e) => {
                e.preventDefault();
                sendQuestion(input);
              }}
            >
              <input
                className="text-input"
                type="text"
                aria-label="Ask a follow-up question"
                placeholder={
                  drawerUseContext && selectedPlayer
                    ? `Ask Paws about ${selectedPlayer}...`
                    : "Ask Paws anything..."
                }
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={chatLoading}
              />
              <button
                className="btn-primary"
                type="submit"
                disabled={chatLoading || !input.trim()}
              >
                Ask
              </button>
            </form>
          </aside>
        )
      )}
      <div ref={turnstileContainerRef} className="turnstile-slot" />
    </div>
  );
}
