import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

function PawSvg({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="4.8" cy="11.6" r="1.8" />
      <circle cx="8.8" cy="7.2" r="2" />
      <circle cx="15.2" cy="7.2" r="2" />
      <circle cx="19.2" cy="11.6" r="1.8" />
      <path d="M12 11.5c-3.1 0-5.4 2.4-5.4 5 0 1.7 1.2 2.8 2.9 2.8.9 0 1.6-.3 2.5-.3s1.6.3 2.5.3c1.7 0 2.9-1.1 2.9-2.8 0-2.6-2.3-5-5.4-5Z" />
    </svg>
  );
}

function PawsIcon({ large = false }) {
  const [imgFailed, setImgFailed] = useState(false);
  if (imgFailed) {
    return <PawSvg className={large ? "paws-icon-lg" : "tab-icon"} />;
  }
  return (
    <img
      src="/paws_logo.png"
      alt=""
      aria-hidden="true"
      className={large ? "paws-icon-lg" : "paws-icon"}
      onError={() => setImgFailed(true)}
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

const OPPONENT_LOGO_ALIASES = {
  "uconn": "Connecticut",
  "university of connecticut": "Connecticut",
  "umass": "Massachusetts",
  "umass-amherst": "Massachusetts",
  "university of massachusetts": "Massachusetts",
  "umass lowell": "Massachusetts Lowell",
  "umass-lowell": "Massachusetts Lowell",
  "university of massachusetts lowell": "Massachusetts Lowell",
  "unh": "New Hampshire",
  "u. of new hampshire": "New Hampshire",
  "university of new hampshire": "New Hampshire",
  "rpi": "Rensselaer",
  "providence college": "Providence",
  "quinnipiac university": "Quinnipiac",
  "merrimack college": "Merrimack",
  "harvard university": "Harvard",
  "brown university": "Brown",
  "colgate university": "Colgate",
  "bentley university": "Bentley",
  "stonehill college": "Stonehill",
  "union college": "Union",
  "army west point": "Army",
  "university of vermont": "Vermont",
  "univ. of maine": "Maine",
  "university of maine": "Maine",
  "university of denver": "Denver",
  "minnesota-duluth": "Minnesota Duluth",
  "alaska-anchorage": "Alaska Anchorage",
  "university of alaska anchorage": "Alaska Anchorage",
};

const OPPONENT_LOGOS_LOWER = Object.fromEntries(
  Object.entries(OPPONENT_LOGOS).map(([k, v]) => [k.toLowerCase(), v])
);

function resolveOpponentLogo(name) {
  if (!name) return "";
  if (OPPONENT_LOGOS[name]) return OPPONENT_LOGOS[name];
  const cleaned = String(name)
    .replace(/^(?:#\d+(?:\/\d+|\/RV)?\s+|No\.\s*\d+(?:\/\d+)?\s+|\[\d+\]\s+)+/gi, "")
    .replace(/\s*\((?:exh\.?|championship game)\)\s*$/gi, "")
    .trim();
  if (OPPONENT_LOGOS[cleaned]) return OPPONENT_LOGOS[cleaned];
  const low = cleaned.toLowerCase();
  if (OPPONENT_LOGOS_LOWER[low]) return OPPONENT_LOGOS_LOWER[low];
  const alias = OPPONENT_LOGO_ALIASES[low];
  return alias ? OPPONENT_LOGOS[alias] || "" : "";
}

function proxyImageUrl(url, width, height) {
  if (!url) return "";
  if (url.startsWith("/") || url.startsWith("data:") || url.startsWith("blob:")) return url;
  const params = new URLSearchParams({ url });
  if (width) params.set("w", String(width));
  if (height) params.set("h", String(height));
  return `${API_BASE}/api/image-proxy?${params.toString()}`;
}

function proxyImageSrcSet(url, width, height) {
  if (!url || !width) return undefined;
  if (url.startsWith("/") || url.startsWith("data:") || url.startsWith("blob:")) return undefined;
  return [1, 2, 3]
    .map((dpr) => `${proxyImageUrl(url, width * dpr, height ? height * dpr : undefined)} ${dpr}x`)
    .join(", ");
}

function OpponentLogo({ name, large = false }) {
  const src = resolveOpponentLogo(name);
  if (!src) return null;
  return (
    <img
      src={proxyImageUrl(src)}
      alt=""
      aria-hidden="true"
      className={large ? "opp-logo-lg" : "opp-logo-sm"}
      loading="lazy"
      onError={(e) => {
        e.currentTarget.style.display = "none";
      }}
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

function formatFaceoffs(won, lost) {
  const w = Number(won || 0);
  const l = Number(lost || 0);
  return `${w}-${w + l}`;
}

const VALID_TABS = ["chat", "leaders", "records", "roster", "rivalry", "beanpot", "compare"];

const TAB_LABELS = {
  chat: "Ask Paws",
  leaders: "Stats",
  records: "Records",
  roster: "Roster",
  rivalry: "Opponents",
  beanpot: "Beanpot",
  compare: "Compare",
};

const SCOPE_LABELS = {
  all: "All Games",
  conference: "Hockey East",
  beanpot: "Beanpot",
  postseason: "Hockey East Postseason",
  ncaa: "NCAA Tournament",
};

function safeExternalUrl(url) {
  if (!url) return "";
  try {
    const parsed = new URL(String(url), window.location.origin);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : "";
  } catch {
    return "";
  }
}

function parseMinutesToFloat(val) {
  const text = String(val || "").trim();
  if (text.includes(":")) {
    const [m, s] = text.split(":");
    const mins = Number(m) || 0;
    const secs = Number(s) || 0;
    return mins + secs / 60;
  }
  return Number(text) || 0;
}

const MARKDOWN_COMPONENTS = {
  a: ({ href, children, ...props }) => {
    const safe = safeExternalUrl(href);
    if (!safe) return <span>{children}</span>;
    return (
      <a href={safe} target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    );
  },
};

function BeanpotIcon() {
  return (
    <svg className="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="9" r="5.5" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 13.8 7.5 21l4.5-2.2L16.5 21 15 13.8" />
    </svg>
  );
}

function CompareIcon() {
  return (
    <svg className="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 4v16m0-16-3 3m3-3 3 3M17 20V4m0 16-3-3m3 3 3-3" />
    </svg>
  );
}

function BookIcon() {
  return (
    <svg className="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
    </svg>
  );
}

function ShareIcon() {
  return (
    <svg className="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" style={{ width: 15, height: 15 }}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 1 1 0-2.684m0 2.684 6.632 3.316m-6.632-6 6.632-3.316m0 0a3 3 0 1 0 5.367-2.684 3 3 0 0 0-5.367 2.684Zm0 9.316a3 3 0 1 0 5.368 2.684 3 3 0 0 0-5.368-2.684Z" />
    </svg>
  );
}

function PlayerFormSparkline({ logs, isGoalie, mode = "cumulative" }) {
  const chrono = useMemo(() => {
    if (!logs || logs.length < 2) return [];
    return [...logs].sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
  }, [logs]);

  if (chrono.length < 2) return null;

  const points = [];
  let cumPts = 0;
  let cumGoals = 0;
  let cumSaves = 0;
  for (let i = 0; i < chrono.length; i += 1) {
    const g = chrono[i];
    if (isGoalie) {
      const sv = Number(g.saves || 0);
      cumSaves += sv;
      const winStart = Math.max(0, i - 4);
      const slice = chrono.slice(winStart, i + 1);
      const rSv = slice.reduce((acc, x) => acc + Number(x.saves || 0), 0);
      const rGa = slice.reduce((acc, x) => acc + Number(x.goals_against || 0), 0);
      const rollSvPct = rSv + rGa > 0 ? rSv / (rSv + rGa) : 0;
      points.push({
        idx: i + 1,
        date: g.date,
        opponent: g.opponent,
        primary: mode === "rolling" ? Number((rollSvPct * 100).toFixed(1)) : cumSaves,
        secondary: sv,
      });
    } else {
      const pts = Number(g.points || 0);
      const gls = Number(g.goals || 0);
      cumPts += pts;
      cumGoals += gls;
      const winStart = Math.max(0, i - 4);
      const slice = chrono.slice(winStart, i + 1);
      const rollPts = slice.reduce((acc, x) => acc + Number(x.points || 0), 0) / slice.length;
      const rollGoals = slice.reduce((acc, x) => acc + Number(x.goals || 0), 0) / slice.length;
      points.push({
        idx: i + 1,
        date: g.date,
        opponent: g.opponent,
        primary: mode === "rolling" ? Number(rollPts.toFixed(2)) : cumPts,
        secondary: mode === "rolling" ? Number(rollGoals.toFixed(2)) : cumGoals,
      });
    }
  }

  const w = 640;
  const h = 155;
  const padL = 36;
  const padR = 16;
  const padT = 16;
  const padB = 26;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;
  const maxVal = Math.max(!isGoalie && mode === "rolling" ? 0.5 : 1, ...points.map((p) => Math.max(p.primary, p.secondary || 0)));
  const minVal = isGoalie && mode === "rolling" ? Math.max(0, Math.min(...points.map((p) => p.primary)) - 2) : 0;
  const span = Math.max(!isGoalie && mode === "rolling" ? 0.5 : 1, maxVal - minVal);

  const toX = (i) => padL + (points.length > 1 ? (i / (points.length - 1)) * plotW : plotW / 2);
  const toY = (v) => padT + plotH - ((v - minVal) / span) * plotH;

  const primaryPath = points.map((p, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(p.primary).toFixed(1)}`).join(" ");
  const areaPath = `${primaryPath} L${toX(points.length - 1).toFixed(1)},${(padT + plotH).toFixed(1)} L${toX(0).toFixed(1)},${(padT + plotH).toFixed(1)} Z`;
  const secondaryPath = !isGoalie
    ? points.map((p, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(p.secondary).toFixed(1)}`).join(" ")
    : "";

  return (
    <div className="sparkline-wrap">
      <svg viewBox={`0 0 ${w} ${h}`} className="sparkline-svg" role="img" aria-label="Player performance trend chart">
        <defs>
          <linearGradient id="nuSparkGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#c8102e" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#c8102e" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((t) => {
          const y = padT + plotH * (1 - t);
          const val = minVal + span * t;
          return (
            <g key={t}>
              <line x1={padL} y1={y} x2={w - padR} y2={y} stroke="rgba(17,24,39,0.12)" strokeDasharray="3 3" />
              <text x={padL - 6} y={y + 4} textAnchor="end" fill="#4b5563" fontSize="10">
                {isGoalie && mode === "rolling"
                  ? `${val.toFixed(0)}%`
                  : !isGoalie && mode === "rolling"
                    ? val.toFixed(1)
                    : Math.round(val)}
              </text>
            </g>
          );
        })}
        <path d={areaPath} fill="url(#nuSparkGrad)" />
        {!isGoalie && secondaryPath && (
          <path d={secondaryPath} fill="none" stroke="#d97706" strokeWidth="1.8" strokeDasharray="4 3" />
        )}
        <path d={primaryPath} fill="none" stroke="#c8102e" strokeWidth="2.4" />
        {points.length <= 45 &&
          points.map((p, i) => (
            <circle key={p.date + i} cx={toX(i)} cy={toY(p.primary)} r="2.8" fill="#c8102e">
              <title>{`Game ${p.idx} (${p.date} vs. ${p.opponent}): ${p.primary}`}</title>
            </circle>
          ))}
        <text x={padL} y={h - 6} fill="#4b5563" fontSize="10">
          {points[0]?.date}
        </text>
        <text x={w - padR} y={h - 6} textAnchor="end" fill="#4b5563" fontSize="10">
          {points[points.length - 1]?.date} ({points.length} GP)
        </text>
      </svg>
      <div className="sparkline-legend">
        <span className="legend-item">
          <span className="legend-dot" style={{ background: "#c8102e" }} />
          {isGoalie
            ? mode === "rolling"
              ? "5-Game Rolling SV%"
              : "Cumulative Saves"
            : mode === "rolling"
              ? "5-Game Rolling PTS/GP"
              : "Cumulative Points"}
        </span>
        {!isGoalie && (
          <span className="legend-item">
            <span className="legend-dot" style={{ background: "#d97706" }} />
            {mode === "rolling" ? "5-Game Rolling G/GP" : "Cumulative Goals"}
          </span>
        )}
      </div>
    </div>
  );
}

function CompareFormChart({ pA, pB }) {
  if (!pA?.game_logs?.length || !pB?.game_logs?.length) return null;
  if (pA.is_goalie !== pB.is_goalie) return null;
  const isGoalie = Boolean(pA.is_goalie);

  const buildSeries = (logs) => {
    const chrono = [...logs].sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
    let cum = 0;
    return chrono.map((g, i) => {
      cum += isGoalie ? Number(g.saves || 0) : Number(g.points || 0);
      return { gp: i + 1, val: cum };
    });
  };

  const sA = buildSeries(pA.game_logs);
  const sB = buildSeries(pB.game_logs);
  if (sA.length < 2 && sB.length < 2) return null;

  const maxGP = Math.max(2, sA.length, sB.length);
  const maxVal = Math.max(1, sA[sA.length - 1]?.val || 0, sB[sB.length - 1]?.val || 0);
  const w = 640;
  const h = 165;
  const padL = 38;
  const padR = 18;
  const padT = 16;
  const padB = 26;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;
  const toX = (gp) => padL + ((gp - 1) / (maxGP - 1)) * plotW;
  const toY = (v) => padT + plotH - (v / maxVal) * plotH;

  const pathA = sA.map((pt, i) => `${i === 0 ? "M" : "L"}${toX(pt.gp).toFixed(1)},${toY(pt.val).toFixed(1)}`).join(" ");
  const pathB = sB.map((pt, i) => `${i === 0 ? "M" : "L"}${toX(pt.gp).toFixed(1)},${toY(pt.val).toFixed(1)}`).join(" ");

  return (
    <div className="card">
      <div className="card-header">
        <h3>Career Trajectory by Games Played ({isGoalie ? "Cumulative Saves" : "Cumulative Points"})</h3>
        <span className="muted">Aligned by career game number (1 to {maxGP} GP)</span>
      </div>
      <div className="sparkline-wrap">
        <svg viewBox={`0 0 ${w} ${h}`} className="sparkline-svg" role="img" aria-label="Career trajectory comparison chart">
          {[0, 0.5, 1].map((t) => {
            const y = padT + plotH * (1 - t);
            return (
              <g key={t}>
                <line x1={padL} y1={y} x2={w - padR} y2={y} stroke="rgba(17,24,39,0.12)" strokeDasharray="3 3" />
                <text x={padL - 6} y={y + 4} textAnchor="end" fill="#4b5563" fontSize="10">
                  {Math.round(maxVal * t)}
                </text>
              </g>
            );
          })}
          <path d={pathA} fill="none" stroke="#c8102e" strokeWidth="2.5" />
          <path d={pathB} fill="none" stroke="#0284c7" strokeWidth="2.5" />
          <text x={padL} y={h - 6} fill="#4b5563" fontSize="10">Game 1</text>
          <text x={w - padR} y={h - 6} textAnchor="end" fill="#4b5563" fontSize="10">Game {maxGP}</text>
        </svg>
        <div className="sparkline-legend">
          <span className="legend-item">
            <span className="legend-dot" style={{ background: "#c8102e" }} />
            {pA.bio.player_name} ({sA[sA.length - 1]?.val || 0} in {sA.length} GP)
          </span>
          <span className="legend-item">
            <span className="legend-dot" style={{ background: "#0284c7" }} />
            {pB.bio.player_name} ({sB[sB.length - 1]?.val || 0} in {sB.length} GP)
          </span>
        </div>
      </div>
    </div>
  );
}

function GoalsTimingChart({ buckets }) {
  if (!buckets || buckets.length === 0) return null;
  const maxVal = Math.max(1, ...buckets.map((b) => Math.max(b.nu_goals || 0, b.opp_goals || 0)));
  return (
    <div className="timing-chart-wrap">
      <div className="timing-chart-header">
        <h3 style={{ margin: 0 }}>Scoring Timing Density (5-Minute Game Segments)</h3>
        <div className="sparkline-legend">
          <span className="legend-item">
            <span className="legend-dot" style={{ background: "#c8102e" }} />
            Northeastern
          </span>
          <span className="legend-item">
            <span className="legend-dot" style={{ background: "#64748b" }} />
            Opponents
          </span>
        </div>
      </div>
      <div className="timing-bars-grid">
        {buckets.map((b) => {
          const nuGoals = b.nu_goals || 0;
          const oppGoals = b.opp_goals || 0;
          const nuH = Math.round((nuGoals / maxVal) * 84);
          const oppH = Math.round((oppGoals / maxVal) * 84);
          return (
            <div key={b.label} className="timing-col" title={`${b.label}: NU ${nuGoals} – Opp ${oppGoals}`}>
              <div className="timing-bars-pair">
                <div className="timing-bar-slot">
                  {nuGoals > 0 && <span className="timing-bar-val">{nuGoals}</span>}
                  <div
                    className={`timing-bar nu${nuGoals > 0 ? "" : " zero"}`}
                    style={{ height: `${Math.max(4, nuH)}%` }}
                  />
                </div>
                <div className="timing-bar-slot">
                  {oppGoals > 0 && <span className="timing-bar-val">{oppGoals}</span>}
                  <div
                    className={`timing-bar opp${oppGoals > 0 ? "" : " zero"}`}
                    style={{ height: `${Math.max(4, oppH)}%` }}
                  />
                </div>
              </div>
              <div className="timing-lbl">{b.label.replace("m", "")}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get("tab");
    return VALID_TABS.includes(t) ? t : "chat";
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
  const closeLegalModal = useCallback(() => setLegalModal(null), []);
  const closeBugModal = useCallback(() => setBugModalOpen(false), []);
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
  const [leadersError, setLeadersError] = useState("");
  const [leaderSort, setLeaderSort] = useState({ key: "points", dir: "desc" });
  const [leaderScope, setLeaderScope] = useState("all");
  const [leaderLocation, setLeaderLocation] = useState("all");
  const [leaderOpponent, setLeaderOpponent] = useState("");
  const [statsView, setStatsView] = useState("players"); // "players" | "team"

  // Records & History state
  const [recordsData, setRecordsData] = useState(null);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordsError, setRecordsError] = useState("");
  const [recordsSubTab, setRecordsSubTab] = useState("recordbook"); // "recordbook" | "milestones" | "chemistry" | "onthisday"
  const [recordsLeaderboardMode, setRecordsLeaderboardMode] = useState("career"); // "career" | "season"
  const [recordsPosition, setRecordsPosition] = useState("all");
  const [recordsClassYear, setRecordsClassYear] = useState("all");
  const [recordSkaterSort, setRecordSkaterSort] = useState({ key: "points", dir: "desc" });
  const [recordGoalieSort, setRecordGoalieSort] = useState({ key: "wins", dir: "desc" });
  const [chemSeason, setChemSeason] = useState("all");
  const [chemStrength, setChemStrength] = useState("all");
  const [otdMmdd, setOtdMmdd] = useState("");
  const [otdPickerOpen, setOtdPickerOpen] = useState(false);
  const [otdPickerMonth, setOtdPickerMonth] = useState(null);
  const [streakMode, setStreakMode] = useState("all_time"); // "all_time" | "season_openers"
  const [streakCat, setStreakCat] = useState("points"); // "points" | "goals" | "assists" | "team"

  // Beanpot Hub state
  const [beanpotData, setBeanpotData] = useState(null);
  const [beanpotLoading, setBeanpotLoading] = useState(false);
  const [beanpotError, setBeanpotError] = useState("");
  const [beanpotSubTab, setBeanpotSubTab] = useState("overview"); // "overview" | "history" | "leaders" | "moments"
  const [beanpotHistoryFilter, setBeanpotHistoryFilter] = useState("all"); // "all" | "titles" | "finals"
  const [beanpotSkaterSort, setBeanpotSkaterSort] = useState({ key: "points", dir: "desc" });
  const [beanpotGoalieSort, setBeanpotGoalieSort] = useState({ key: "wins", dir: "desc" });
  const [beanpotClipModal, setBeanpotClipModal] = useState(null);

  // Roster state
  const [roster, setRoster] = useState(null);
  const [rosterLoading, setRosterLoading] = useState(false);
  const [rosterError, setRosterError] = useState("");
  const [rosterSearch, setRosterSearch] = useState("");
  const [rosterView, setRosterView] = useState("position"); // "position" | "all"

  // Rivalry state
  const [selectedRival, setSelectedRival] = useState("Boston University");
  const [rivalryScope, setRivalryScope] = useState("all"); // "season" | "all"
  const [rivalry, setRivalry] = useState(null);
  const [rivalryLoading, setRivalryLoading] = useState(false);
  const [rivalryError, setRivalryError] = useState("");

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
  const [playerChartMode, setPlayerChartMode] = useState("cumulative"); // "cumulative" | "rolling"
  const [shareCopied, setShareCopied] = useState(false);
  const [allGamesList, setAllGamesList] = useState([]);
  const [rivalryPage, setRivalryPage] = useState(1);
  const [penaltyView, setPenaltyView] = useState(null);
  const [penaltyData, setPenaltyData] = useState(null);
  const [penaltyLoading, setPenaltyLoading] = useState(false);
  const [penaltyError, setPenaltyError] = useState("");
  const [penaltyPage, setPenaltyPage] = useState(1);
  const [penaltySeasonFilter, setPenaltySeasonFilter] = useState("all");
  const [penaltyInfractionFilter, setPenaltyInfractionFilter] = useState("all");
  const [boxscoreModal, setBoxscoreModal] = useState(null);
  const [boxscoreData, setBoxscoreData] = useState(null);
  const [boxscoreLoading, setBoxscoreLoading] = useState(false);
  const [boxscoreError, setBoxscoreError] = useState("");
  const boxscoreModalRef = useRef(null);
  const boxscoreCloseRef = useRef(null);
  const boxscoreReqIdRef = useRef(0);
  const [allPlayers, setAllPlayers] = useState([]);
  const [playersLoading, setPlayersLoading] = useState(false);
  const [playersError, setPlayersError] = useState("");
  const [compareAName, setCompareAName] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("compareA") || "";
  });
  const [compareBName, setCompareBName] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("compareB") || "";
  });
  const [compareAQuery, setCompareAQuery] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("compareA") || "";
  });
  const [compareBQuery, setCompareBQuery] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("compareB") || "";
  });
  const [compareAFocus, setCompareAFocus] = useState(false);
  const [compareBFocus, setCompareBFocus] = useState(false);
  const [compareAData, setCompareAData] = useState(null);
  const [compareBData, setCompareBData] = useState(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState("");
  const [compareMode, setCompareMode] = useState("career"); // "career" | "per_game" | "season" | "opponent"
  const [compareSeasonA, setCompareSeasonA] = useState("");
  const [compareSeasonB, setCompareSeasonB] = useState("");
  const [compareOpponent, setCompareOpponent] = useState("");
  const hasInAppHistory = useRef(false);

  function isPlayerGoalie(name, playerData) {
    if (playerData && typeof playerData.is_goalie === "boolean") {
      return playerData.is_goalie;
    }
    const target = (name || "").trim().toLowerCase();
    if (!target) return null;
    const found = allPlayers.find((p) => p.player_name.toLowerCase() === target);
    return found ? found.position === "G" : null;
  }

  function filterPlayerMatches(query, roleFilter = null) {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const tokens = q.split(/\s+/).filter(Boolean);
    const matches = allPlayers.filter((p) => {
      if (roleFilter === "goalie" && p.position !== "G") return false;
      if (roleFilter === "skater" && p.position === "G") return false;
      const lower = p.player_name.toLowerCase();
      return tokens.every((t) => lower.includes(t));
    });
    matches.sort((a, b) => {
      const aWords = a.player_name.toLowerCase().split(/\s+/);
      const bWords = b.player_name.toLowerCase().split(/\s+/);
      const aPrefix = aWords.some((w) => w.startsWith(tokens[0])) ? 0 : 1;
      const bPrefix = bWords.some((w) => w.startsWith(tokens[0])) ? 0 : 1;
      if (aPrefix !== bPrefix) return aPrefix - bPrefix;
      return a.player_name.localeCompare(b.player_name);
    });
    return matches.slice(0, 12);
  }

  useEffect(() => {
    if (allPlayers.length > 0 || playersLoading) return;
    setPlayersLoading(true);
    setPlayersError("");
    fetch(`${API_BASE}/api/players`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Failed to load players (${r.status})`))))
      .then((d) => setAllPlayers(d.players || []))
      .catch((err) => setPlayersError(err.message || "Unable to load players"))
      .finally(() => setPlayersLoading(false));
  }, [allPlayers.length]);

  useEffect(() => {
    const a = compareAName.trim();
    const b = compareBName.trim();
    if (tab === "compare") {
      const url = new URL(window.location.href);
      if (a) url.searchParams.set("compareA", a);
      else url.searchParams.delete("compareA");
      if (b) url.searchParams.set("compareB", b);
      else url.searchParams.delete("compareB");
      window.history.replaceState({ tab, player: selectedPlayer, penaltyView }, "", url.toString());
    }
    if (tab !== "compare") return;
    if (!a && !b) {
      setCompareAData(null);
      setCompareBData(null);
      setCompareError("");
      return;
    }
    let cancelled = false;
    setCompareLoading(true);
    setCompareError("");

    const fetchPlayer = (name) =>
      name.length >= 2
        ? fetch(`${API_BASE}/api/player?name=${encodeURIComponent(name)}`).then(async (r) => {
            const d = await r.json();
            if (!r.ok) throw new Error(d.detail || `Player '${name}' not found`);
            return d;
          })
        : Promise.resolve(null);

    Promise.all([a ? fetchPlayer(a) : Promise.resolve(null), b ? fetchPlayer(b) : Promise.resolve(null)])
      .then(([resA, resB]) => {
        if (cancelled) return;
        setCompareAData(resA);
        setCompareBData(resB);
        if (resA?.seasons?.length) {
          setCompareSeasonA((prev) =>
            resA.seasons.some((s) => s.season === prev) ? prev : resA.seasons[0].season
          );
        }
        if (resB?.seasons?.length) {
          setCompareSeasonB((prev) =>
            resB.seasons.some((s) => s.season === prev) ? prev : resB.seasons[0].season
          );
        }
      })
      .catch((err) => {
        if (!cancelled) setCompareError(err.message || "Unable to compare players");
      })
      .finally(() => {
        if (!cancelled) setCompareLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [tab, compareAName, compareBName]);

  function openCompareWith(playerName) {
    const name = playerName || "";
    setCompareAName(name);
    setCompareAQuery(name);
    navigateTab("compare");
  }

  async function openBoxScore(date, opponent) {
    if (!date || !opponent) return;
    const reqId = ++boxscoreReqIdRef.current;
    setBoxscoreModal({ date, opponent });
    setBoxscoreData(null);
    setBoxscoreLoading(true);
    setBoxscoreError("");
    const url = new URL(window.location.href);
    url.searchParams.set("boxscore", `${date}|${opponent}`);
    window.history.replaceState({ tab, player: selectedPlayer, penaltyView }, "", url.toString());
    try {
      const params = new URLSearchParams({ date, opponent });
      const res = await fetch(`${API_BASE}/api/boxscore?${params.toString()}`);
      const data = await res.json().catch(() => ({}));
      if (boxscoreReqIdRef.current !== reqId) return;
      if (!res.ok) throw new Error(data.detail || "Unable to load box score");
      setBoxscoreData(data);
    } catch (err) {
      if (boxscoreReqIdRef.current !== reqId) return;
      setBoxscoreError(err.message || "Unable to load box score");
    } finally {
      if (boxscoreReqIdRef.current === reqId) {
        setBoxscoreLoading(false);
      }
    }
  }

  function closeBoxScore() {
    boxscoreReqIdRef.current += 1;
    setBoxscoreModal(null);
    setBoxscoreData(null);
    setBoxscoreLoading(false);
    setBoxscoreError("");
    const url = new URL(window.location.href);
    url.searchParams.delete("boxscore");
    window.history.replaceState({ tab, player: selectedPlayer, penaltyView }, "", url.toString());
  }

  const closeBoxScoreRef = useRef(null);
  closeBoxScoreRef.current = closeBoxScore;

  useEffect(() => {
    if (!boxscoreModal) return;
    const prevFocus = document.activeElement;
    const focusTimer = window.setTimeout(() => {
      boxscoreCloseRef.current?.focus();
    }, 0);

    function onBoxscoreKey(e) {
      if (e.key === "Escape") {
        closeBoxScoreRef.current?.();
        return;
      }
      if (e.key === "Tab" && boxscoreModalRef.current) {
        const focusable = Array.from(
          boxscoreModalRef.current.querySelectorAll(
            'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
          )
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    window.addEventListener("keydown", onBoxscoreKey);
    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener("keydown", onBoxscoreKey);
      if (prevFocus && typeof prevFocus.focus === "function") {
        prevFocus.focus();
      }
    };
  }, [Boolean(boxscoreModal)]);

  function fallbackCopyText(text) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.top = "-9999px";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      if (ok) {
        setShareCopied(true);
        window.setTimeout(() => setShareCopied(false), 2000);
      }
    } catch {}
  }

  function handleCopyShareLink() {
    const shareUrl = window.location.href;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(shareUrl).then(() => {
        setShareCopied(true);
        window.setTimeout(() => setShareCopied(false), 2000);
      }).catch(() => fallbackCopyText(shareUrl));
    } else {
      fallbackCopyText(shareUrl);
    }
  }

  const sortedPlayersForMatching = useMemo(() => {
    const seen = new Set();
    const names = [];
    for (const p of allPlayers) {
      const pname = p.player_name;
      if (!pname || pname.length < 5 || seen.has(pname)) continue;
      seen.add(pname);
      names.push(pname);
    }
    names.sort((a, b) => b.length - a.length);
    return names.map((pname) => {
      const escaped = pname.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return {
        name: pname,
        regex: new RegExp(`(?:^|[^A-Za-z0-9])${escaped}(?:$|[^A-Za-z0-9])`),
      };
    });
  }, [allPlayers]);

  function extractAnswerEntities(text) {
    if (!text) return { players: [], games: [] };
    const foundPlayers = [];
    for (const entry of sortedPlayersForMatching) {
      if (entry.regex.test(text)) {
        foundPlayers.push(entry.name);
        if (foundPlayers.length >= 5) break;
      }
    }
    const foundGames = [];
    const seenG = new Set();
    const dateMatches = text.match(/\b(1999|20[0-2]\d)-\d{2}-\d{2}\b/g) || [];
    for (const dt of dateMatches) {
      if (seenG.has(dt)) continue;
      const gm = allGamesList.find((g) => g.date === dt);
      if (gm && gm.opponent) {
        seenG.add(dt);
        foundGames.push({ date: dt, opponent: gm.opponent });
        if (foundGames.length >= 4) break;
      }
    }
    return { players: foundPlayers, games: foundGames };
  }

  async function loadPenaltyBreakdown(pv) {
    setPenaltyView(pv);
    setPenaltyLoading(true);
    setPenaltyError("");
    setPenaltyPage(1);
    setPenaltySeasonFilter("all");
    setPenaltyInfractionFilter("all");
    try {
      const params = new URLSearchParams({
        season: pv.season || "all",
        scope: pv.scope || "all",
      });
      if (pv.location && pv.location !== "all") params.set("location", pv.location);
      if (pv.opponent) params.set("opponent", pv.opponent);
      if (pv.player) params.set("player", pv.player);
      const res = await fetch(`${API_BASE}/api/penalties?${params.toString()}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Unable to load penalty breakdown");
      setPenaltyData(data);
    } catch (err) {
      setPenaltyError(err.message || "Unable to load penalty breakdown");
    } finally {
      setPenaltyLoading(false);
    }
  }

  useEffect(() => {
    // Seed initial history state so Mouse Button 4 / Back returns cleanly
    window.history.replaceState(
      { tab, player: selectedPlayer, penaltyView: null },
      "",
      window.location.href
    );
    const initParams = new URLSearchParams(window.location.search);
    const initBox = initParams.get("boxscore");
    if (initBox && initBox.includes("|")) {
      const [bDate, bOpp] = initBox.split("|");
      if (bDate && bOpp) openBoxScore(bDate, bOpp);
    }

    function handlePopState(e) {
      const state = e.state;
      const params = new URLSearchParams(window.location.search);
      boxscoreReqIdRef.current += 1;
      setBoxscoreModal(null);
      setBoxscoreData(null);
      setBoxscoreLoading(false);
      setBoxscoreError("");
      let nextTab = "chat";
      if (state) {
        nextTab = VALID_TABS.includes(state.tab) ? state.tab : "chat";
        setTab(nextTab);
        setSelectedPlayer(state.player || null);
        if (state.penaltyView) {
          loadPenaltyBreakdown(state.penaltyView);
        } else {
          setPenaltyView(null);
          setPenaltyData(null);
          setPenaltyError("");
        }
      } else {
        const t = params.get("tab");
        nextTab = VALID_TABS.includes(t) ? t : "chat";
        setTab(nextTab);
        setSelectedPlayer(params.get("player") || null);
        setPenaltyView(null);
        setPenaltyData(null);
        setPenaltyError("");
      }
      if (nextTab === "compare") {
        const cmpA = params.get("compareA") || "";
        const cmpB = params.get("compareB") || "";
        setCompareAName(cmpA);
        setCompareAQuery(cmpA);
        setCompareBName(cmpB);
        setCompareBQuery(cmpB);
      }
      setPlayerError("");
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  function navigateTab(nextTab) {
    if (nextTab === tab && !selectedPlayer && !penaltyView && !boxscoreModal) return;
    hasInAppHistory.current = true;
    boxscoreReqIdRef.current += 1;
    setBoxscoreModal(null);
    setBoxscoreData(null);
    setBoxscoreLoading(false);
    setBoxscoreError("");
    setTab(nextTab);
    setPenaltyView(null);
    setPenaltyData(null);
    setSelectedPlayer(null);
    setPlayerData(null);
    setPlayerError("");
    const url = new URL(window.location.href);
    url.searchParams.set("tab", nextTab);
    url.searchParams.delete("player");
    url.searchParams.delete("penalties");
    url.searchParams.delete("boxscore");
    window.history.pushState({ tab: nextTab, player: null, penaltyView: null }, "", url.toString());
  }

  function openPlayer(name) {
    hasInAppHistory.current = true;
    boxscoreReqIdRef.current += 1;
    setBoxscoreModal(null);
    setBoxscoreData(null);
    setBoxscoreLoading(false);
    setBoxscoreError("");
    setPenaltyView(null);
    setPenaltyData(null);
    setSelectedPlayer(name);
    setPlayerScope("all");
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    url.searchParams.set("player", name);
    url.searchParams.delete("penalties");
    url.searchParams.delete("boxscore");
    window.history.pushState({ tab, player: name, penaltyView: null }, "", url.toString());
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
    url.searchParams.delete("penalties");
    window.history.replaceState({ tab, player: null, penaltyView: null }, "", url.toString());
  }

  function openPenaltyBreakdown({ mode, player = "", season = "all", scope = "all", location = "all", opponent = "" }) {
    const pv = { mode, player, season, scope, location, opponent };
    hasInAppHistory.current = true;
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    if (selectedPlayer) url.searchParams.set("player", selectedPlayer);
    url.searchParams.set("penalties", mode);
    window.history.pushState({ tab, player: selectedPlayer, penaltyView: pv }, "", url.toString());
    loadPenaltyBreakdown(pv);
  }

  function closePenaltyBreakdown() {
    if (hasInAppHistory.current) {
      window.history.back();
      return;
    }
    setPenaltyView(null);
    setPenaltyData(null);
    setPenaltyError("");
    const url = new URL(window.location.href);
    url.searchParams.delete("penalties");
    window.history.replaceState({ tab, player: selectedPlayer, penaltyView: null }, "", url.toString());
  }

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/health`)
      .then((r) => (r.ok ? r.json().catch(() => null) : null))
      .then((data) => {
        if (!cancelled && data) setHealth(data);
      })
      .catch(() => {});

    fetch(`${API_BASE}/api/seasons`)
      .then((r) => (r.ok ? r.json().catch(() => null) : null))
      .then((data) => {
        if (cancelled || !data) return;
        const s = data.seasons || [];
        setSeasons(s);
        setOpponents(data.opponents || []);
        if (s.length > 0) setSelectedSeason(s[0]);
      })
      .catch(() => {});

    fetch(`${API_BASE}/api/games?limit=1200`)
      .then((r) => (r.ok ? r.json().catch(() => null) : null))
      .then((data) => {
        if (!cancelled && data) setAllGamesList(data.games || []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (tab !== "records") return;
    let cancelled = false;
    setRecordsLoading(true);
    setRecordsError("");
    const params = new URLSearchParams({
      position: recordsPosition,
      class_year: recordsClassYear,
      chemistry_season: chemSeason,
      chemistry_strength: chemStrength,
      limit: "1000",
    });
    if (otdMmdd) params.set("mmdd", otdMmdd);
    fetch(`${API_BASE}/api/records?${params.toString()}`)
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || `Failed to load records (${r.status})`);
        return data;
      })
      .then((data) => {
        if (!cancelled) setRecordsData(data);
      })
      .catch((err) => {
        if (!cancelled) setRecordsError(err.message || "Unable to load program records.");
      })
      .finally(() => {
        if (!cancelled) setRecordsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, recordsPosition, recordsClassYear, chemSeason, chemStrength, otdMmdd]);

  const fetchBeanpotData = useCallback(() => {
    setBeanpotLoading(true);
    setBeanpotError("");
    fetch(`${API_BASE}/api/beanpot`)
      .then(async (r) => {
        if (!r.ok) {
          const text = await r.text().catch(() => "");
          throw new Error(text || `Request failed (${r.status})`);
        }
        return r.json();
      })
      .then((data) => setBeanpotData(data))
      .catch((err) => setBeanpotError(err?.message || "Failed to load Beanpot data."))
      .finally(() => setBeanpotLoading(false));
  }, []);

  useEffect(() => {
    if (tab !== "beanpot" || beanpotData || beanpotLoading || beanpotError) return;
    fetchBeanpotData();
  }, [tab, beanpotData, beanpotLoading, beanpotError, fetchBeanpotData]);

  useEffect(() => {
    if (!selectedSeason) return;
    let cancelled = false;
    if (tab === "leaders") {
      setLeadersLoading(true);
      setLeadersError("");
      const params = new URLSearchParams({
        season: selectedSeason,
        scope: leaderScope,
        location: leaderLocation,
        limit: "35",
      });
      if (leaderOpponent) {
        params.set("opponent", leaderOpponent);
      }
      fetch(`${API_BASE}/api/leaders?${params.toString()}`)
        .then(async (r) => {
          const data = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(data.detail || `Failed to load stats (${r.status})`);
          return data;
        })
        .then((data) => {
          if (cancelled) return;
          setLeaders(data);
          if (leaderOpponent && !(data.opponents || []).includes(leaderOpponent)) {
            setLeaderOpponent("");
          }
        })
        .catch((err) => {
          if (!cancelled) setLeadersError(err.message || "Unable to load stats.");
        })
        .finally(() => {
          if (!cancelled) setLeadersLoading(false);
        });
    } else if (tab === "roster") {
      if (selectedSeason === "all") {
        if (seasons[0]) setSelectedSeason(seasons[0]);
        return;
      }
      setRosterLoading(true);
      setRosterError("");
      fetch(`${API_BASE}/api/roster?season=${encodeURIComponent(selectedSeason)}`)
        .then(async (r) => {
          const data = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(data.detail || `Failed to load roster (${r.status})`);
          return data;
        })
        .then((data) => {
          if (!cancelled) setRoster(data);
        })
        .catch((err) => {
          if (!cancelled) setRosterError(err.message || "Unable to load roster.");
        })
        .finally(() => {
          if (!cancelled) setRosterLoading(false);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [tab, selectedSeason, leaderScope, leaderLocation, leaderOpponent, seasons]);

  useEffect(() => {
    if (tab !== "rivalry" || !selectedRival) return;
    if (rivalryScope === "season" && !seasons[0]) return;
    let cancelled = false;
    setRivalryPage(1);
    setRivalryLoading(true);
    setRivalryError("");
    const params = new URLSearchParams({ opponent: selectedRival });
    if (rivalryScope === "season" && seasons[0]) {
      params.set("season", seasons[0]);
    }
    fetch(`${API_BASE}/api/rivalry?${params.toString()}`)
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || `Failed to load opponent history (${r.status})`);
        return data;
      })
      .then((data) => {
        if (!cancelled) setRivalry(data);
      })
      .catch((err) => {
        if (!cancelled) setRivalryError(err.message || "Unable to load opponent history.");
      })
      .finally(() => {
        if (!cancelled) setRivalryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, selectedRival, rivalryScope, seasons]);

  useEffect(() => {
    if (!selectedPlayer) return;
    let cancelled = false;
    setPlayerLoading(true);
    setPlayerError("");
    fetch(`${API_BASE}/api/player?name=${encodeURIComponent(selectedPlayer)}`)
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || "Player not found");
        if (cancelled) return;
        setPlayerData(data);
        const logSeasons = Array.from(
          new Set((data.game_logs || []).map((g) => g.season).filter(Boolean))
        ).sort((a, b) => b.localeCompare(a));
        setPlayerLogSeason(logSeasons[0] || "all");
        setPlayerOpponent("all");
      })
      .catch((err) => {
        if (!cancelled) setPlayerError(err.message || "Player not found");
      })
      .finally(() => {
        if (!cancelled) setPlayerLoading(false);
      });
    return () => {
      cancelled = true;
    };
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
      return `User is viewing ${selectedSeason === "all" ? "All-Time" : selectedSeason} Leaders (${leaderScope}, Venue: ${leaderLocation}${leaderOpponent ? `, vs. ${leaderOpponent}` : ""}).`;
    }
    if (tab === "records") {
      return `User is viewing Program Record Book & History (${recordsSubTab}).`;
    }
    if (tab === "roster") {
      return `User is viewing ${selectedSeason} Roster.`;
    }
    if (tab === "rivalry") {
      return `User is viewing Opponent history vs. ${selectedRival}.`;
    }
    if (tab === "beanpot") {
      return `User is viewing Beanpot Tournament Hub (${beanpotSubTab}).`;
    }
    if (tab === "compare") {
      return `User is viewing Compare Players (${compareAName || "Player A"} vs. ${compareBName || "Player B"}).`;
    }
    return null;
  }, [selectedPlayer, tab, selectedSeason, leaderScope, leaderLocation, leaderOpponent, selectedRival, recordsSubTab, beanpotSubTab, compareAName, compareBName]);

  const sortedSkaters = useMemo(() => {
    if (!leaders?.skaters) return [];
    const list = [...leaders.skaters];
    const { key, dir } = leaderSort;
    list.sort((a, b) => {
      const av = Number(a[key] ?? 0);
      const bv = Number(b[key] ?? 0);
      if (bv !== av) return dir === "desc" ? bv - av : av - bv;
      const ptDiff = Number(b.points ?? 0) - Number(a.points ?? 0);
      if (ptDiff !== 0) return ptDiff;
      const gDiff = Number(b.goals ?? 0) - Number(a.goals ?? 0);
      if (gDiff !== 0) return gDiff;
      return String(a.player_name || "").localeCompare(String(b.player_name || ""));
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

    const history = messages.slice(-16).map((m) => ({
      role: m.role,
      content: m.content,
      ...(m.sig ? { sig: m.sig } : {}),
    }));
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setInput("");
    setChatLoading(true);

    try {
      const hasContextTarget = Boolean(selectedPlayer || tab !== "chat");
      let effectiveUseContext = drawerUseContext;
      if (hasContextTarget && drawerUseContext) {
        const lowerQ = q.toLowerCase();
        const mentionsPronoun = /\b(he|him|his|himself|this player)\b/i.test(lowerQ);
        const playerTokens = (selectedPlayer || "")
          .toLowerCase()
          .split(/\s+/)
          .filter((t) => t.length >= 3);
        const mentionsCurrentPlayer = playerTokens.some((t) => lowerQ.includes(t));
        const isBroadAllStatsQuery = /\b(top\s+\d+|who\s+(leads?|led|has\s+the\s+most|had\s+the\s+most|scored\s+the\s+most)|which\s+players?|all[- ]time|program\s+history|team\s+record|northeastern\s+record|leaderboard|leaders?)\b/i.test(
          lowerQ
        );
        if (isBroadAllStatsQuery && !mentionsPronoun && !mentionsCurrentPlayer) {
          effectiveUseContext = false;
          setDrawerUseContext(false);
        }
      }
      const activeContext = hasContextTarget
        ? (effectiveUseContext ? pageContext : null)
        : null;

      async function waitForTurnstileToken(maxAttempts = 60) {
        if (!turnstileSiteKey) return "";
        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
          let tok = turnstileTokenRef.current;
          if (!tok && window.turnstile && turnstileWidgetRef.current !== null) {
            try {
              tok = window.turnstile.getResponse(turnstileWidgetRef.current) || "";
            } catch {}
          }
          if (tok) return tok;
          await new Promise((r) => window.setTimeout(r, 100));
        }
        return "";
      }

      let token = await fetchChatToken();
      let activePass = turnstilePass;
      let tsToken = "";
      if (!activePass && turnstileSiteKey) {
        tsToken = await waitForTurnstileToken();
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
        } else if (window.turnstile && turnstileWidgetRef.current !== null) {
          turnstileTokenRef.current = "";
          try {
            window.turnstile.reset(turnstileWidgetRef.current);
          } catch {}
        }
        token = await fetchChatToken();
        const retryTsToken = turnstileSiteKey ? await waitForTurnstileToken() : "";
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
        { role: "assistant", content: data.answer, cached: data.cached, sig: data.answer_sig || undefined },
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
      if (e.key === "Escape" && !legalModal && !bugModalOpen && !boxscoreModal) {
        setChatDrawerOpen(false);
      }
    }
    window.addEventListener("keydown", onDrawerKey);
    return () => window.removeEventListener("keydown", onDrawerKey);
  }, [chatDrawerOpen, legalModal, bugModalOpen, boxscoreModal]);

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
          <div className="header-actions">
            {health?.latest_game_date && (
              <div className="header-pill">
                <span className="header-pill-label">
                  <span className="live-dot" aria-hidden="true" />
                  Latest Game
                </span>
                <span className="header-pill-date">{health.latest_game_date}</span>
              </div>
            )}
            <button
              type="button"
              className="header-action-btn"
              onClick={handleCopyShareLink}
              title="Copy a direct link to this current view"
            >
              <ShareIcon />
              <span>{shareCopied ? "Copied Link!" : "Share View"}</span>
            </button>
          </div>
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
            className={`tab-btn ${!selectedPlayer && tab === "records" ? "active" : ""}`}
            aria-current={!selectedPlayer && tab === "records" ? "page" : undefined}
            onClick={() => navigateTab("records")}
          >
            <BookIcon />
            <span>Records</span>
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
          <button
            type="button"
            className={`tab-btn ${!selectedPlayer && tab === "beanpot" ? "active" : ""}`}
            aria-current={!selectedPlayer && tab === "beanpot" ? "page" : undefined}
            onClick={() => navigateTab("beanpot")}
          >
            <BeanpotIcon />
            <span>Beanpot</span>
          </button>
          <button
            type="button"
            className={`tab-btn ${!selectedPlayer && tab === "compare" ? "active" : ""}`}
            aria-current={!selectedPlayer && tab === "compare" ? "page" : undefined}
            onClick={() => navigateTab("compare")}
          >
            <CompareIcon />
            <span>Compare</span>
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
              <a href="https://nuhuskies.com" target="_blank" rel="noopener noreferrer" style={{ color: "inherit", fontWeight: 700 }}>
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
                    {` • ${SCOPE_LABELS[penaltyView.scope] || "All Games"}`}
                    {penaltyView.location && penaltyView.location !== "all" ? ` • ${penaltyView.location} Venue` : ""}
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
                <p className="error-text" role="alert">
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
                                    <button
                                      type="button"
                                      className="link-btn"
                                      onClick={() => openBoxScore(ev.date, ev.opponent)}
                                    >
                                      View
                                    </button>
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
                &larr; Back to {TAB_LABELS[tab] || "Stats"}
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => openCompareWith(playerData?.bio?.player_name || selectedPlayer)}
              >
                Compare with...
              </button>
              {safeExternalUrl(playerData?.bio?.roster_url) && (
                <a
                  href={safeExternalUrl(playerData.bio.roster_url)}
                  target="_blank"
                  rel="noopener noreferrer"
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
                <p className="error-text">{playerError}</p>
              </div>
            )}

            {!playerLoading && !playerError && playerData && (
              <>
                <div className="player-hero">
                  <div className="player-hero-left">
                    {playerData.bio.image_url ? (
                      <img
                        src={proxyImageUrl(playerData.bio.image_url, 80, 100)}
                        srcSet={proxyImageSrcSet(playerData.bio.image_url, 80, 100)}
                        alt={playerData.bio.player_name}
                        className="player-avatar-lg"
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                        }}
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
                          {formatPct3(playerData.career_skater.faceoffs_won, playerData.career_skater.faceoffs_lost) ?? "N/A"}
                        </div>
                        <div className="lbl">
                          {playerData.career_skater.faceoffs_won + playerData.career_skater.faceoffs_lost > 0
                            ? `FO% (${formatFaceoffs(playerData.career_skater.faceoffs_won, playerData.career_skater.faceoffs_lost)})`
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
                                  <td>{tracked ? formatFaceoffs(fow, fol) : <span className="muted">N/A</span>}</td>
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

                {playerData.chemistry?.length > 0 && (
                  <div className="card">
                    <div className="card-header">
                      <h2>Line Chemistry — Top Goal Connections</h2>
                      <span className="muted">Career scoring combinations</span>
                    </div>
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Teammate</th>
                            <th>Total Connections</th>
                            <th>Assisted by Them</th>
                            <th>Their Goals Assisted</th>
                          </tr>
                        </thead>
                        <tbody>
                          {playerData.chemistry.map((c) => (
                            <tr key={c.player_name}>
                              <td>
                                <button
                                  type="button"
                                  className="player-link"
                                  onClick={() => openPlayer(c.player_name)}
                                >
                                  {c.player_name}
                                </button>
                              </td>
                              <td><strong>{c.total_connections}</strong></td>
                              <td>{c.assisted_by_them}</td>
                              <td>{c.assisted_for_them}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
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
                      <div className="card-header" style={{ flexWrap: "wrap", gap: 10 }}>
                        <h2>Game Log ({visibleLogs.length} Games)</h2>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                          {visibleLogs.length >= 2 && (
                            <div className="segmented" role="group" aria-label="Trend chart mode">
                              <button
                                type="button"
                                className={`segmented-btn ${playerChartMode === "cumulative" ? "active" : ""}`}
                                onClick={() => setPlayerChartMode("cumulative")}
                              >
                                Cumulative
                              </button>
                              <button
                                type="button"
                                className={`segmented-btn ${playerChartMode === "rolling" ? "active" : ""}`}
                                onClick={() => setPlayerChartMode("rolling")}
                              >
                                5-Game Rolling
                              </button>
                            </div>
                          )}
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
                      </div>
                      {visibleLogs.length >= 2 && (
                        <PlayerFormSparkline
                          logs={visibleLogs}
                          isGoalie={Boolean(playerData.is_goalie)}
                          mode={playerChartMode}
                        />
                      )}
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
                                  <td>
                                    <span className="opp-with-logo">
                                      <OpponentLogo name={g.opponent} />
                                      <span>{g.opponent}</span>
                                    </span>
                                  </td>
                                  <td>{`${g.nu_goals}-${g.opp_goals}`}</td>
                                  <td>{g.decision}</td>
                                  <td>{g.saves}</td>
                                  <td>{g.goals_against}</td>
                                  <td>{Number(g.save_pct || 0).toFixed(3)}</td>
                                  <td>
                                    <button
                                      type="button"
                                      className="link-btn"
                                      onClick={() => openBoxScore(g.date, g.opponent)}
                                    >
                                      View
                                    </button>
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
                                    <td>{tracked ? formatFaceoffs(g.faceoffs_won, g.faceoffs_lost) : <span className="muted">N/A</span>}</td>
                                    <td>{foPct ?? <span className="muted">N/A</span>}</td>
                                    <td>{g.penalty_minutes}</td>
                                    <td>
                                      <button
                                        type="button"
                                        className="link-btn"
                                        onClick={() => openBoxScore(g.date, g.opponent)}
                                      >
                                        View
                                      </button>
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
                                  {selectedOppStats.has_tracked_blk_fo
                                    ? (formatPct3(selectedOppStats.faceoffs_won, selectedOppStats.faceoffs_lost) ?? "N/A")
                                    : "N/A"}
                                </div>
                                <div className="lbl">
                                  {selectedOppStats.has_tracked_blk_fo &&
                                  selectedOppStats.faceoffs_won + selectedOppStats.faceoffs_lost > 0
                                    ? `FO% (${formatFaceoffs(selectedOppStats.faceoffs_won, selectedOppStats.faceoffs_lost)})`
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
                                        <button
                                          type="button"
                                          className="link-btn"
                                          onClick={() => openBoxScore(g.date, g.opponent || selectedOppStats?.opponent)}
                                        >
                                          View
                                        </button>
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
                                        <button
                                          type="button"
                                          className="link-btn"
                                          onClick={() => openBoxScore(g.date, g.opponent || selectedOppStats?.opponent)}
                                        >
                                          View
                                        </button>
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
                                        ? formatFaceoffs(row.faceoffs_won, row.faceoffs_lost)
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
              {messages.map((m, idx) => {
                const entities = m.role === "assistant" ? extractAnswerEntities(m.content) : null;
                return (
                  <div key={idx} className={`msg-row ${m.role}`}>
                    <div className={`msg ${m.role}`}>
                      {m.role === "assistant" ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                          {m.content}
                        </ReactMarkdown>
                      ) : (
                        m.content
                      )}
                    </div>
                    {m.role === "assistant" && entities && (entities.players.length > 0 || entities.games.length > 0) && (
                      <div className="entity-chips-row">
                        {entities.players.map((pName) => (
                          <button
                            key={pName}
                            type="button"
                            className="entity-chip"
                            onClick={() => openPlayer(pName)}
                          >
                            👤 {pName} &rarr;
                          </button>
                        ))}
                        {entities.games.map((g) => (
                          <button
                            key={`${g.date}-${g.opponent}`}
                            type="button"
                            className="entity-chip"
                            onClick={() => openBoxScore(g.date, g.opponent)}
                          >
                            🏒 Box Score: {g.date} vs. {g.opponent} &rarr;
                          </button>
                        ))}
                      </div>
                    )}
                    {m.role === "assistant" && m.cached && (
                      <span className="msg-meta">Instant cached answer</span>
                    )}
                  </div>
                );
              })}
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
                maxLength={1000}
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
            <div className="controls-group" style={{ flexWrap: "wrap" }}>
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
                  <select
                    aria-label="Filter by tournament or game scope"
                    className="select-input"
                    value={leaderScope}
                    onChange={(e) => setLeaderScope(e.target.value)}
                  >
                    <option value="all">All Games</option>
                    <option value="conference">Hockey East (Conf.)</option>
                    <option value="beanpot">Beanpot Tournament</option>
                    <option value="postseason">Hockey East Postseason</option>
                    <option value="ncaa">NCAA Tournament</option>
                  </select>

                  <select
                    aria-label="Filter by venue"
                    className="select-input"
                    value={leaderLocation}
                    onChange={(e) => setLeaderLocation(e.target.value)}
                  >
                    <option value="all">All Venues</option>
                    <option value="Home">Home</option>
                    <option value="Away">Away</option>
                    <option value="Neutral">Neutral Site</option>
                  </select>

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
                      : leaderScope === "beanpot"
                        ? "Beanpot Tournament Stats"
                        : leaderScope === "postseason"
                          ? "Hockey East Postseason Stats"
                          : leaderScope === "ncaa"
                            ? "NCAA Tournament Stats"
                            : "Team Stats"}
                </span>
              </h2>
              <span className="muted">
                {[
                  leaderOpponent ? `vs. ${leaderOpponent}` : null,
                  leaderLocation !== "all" ? `${leaderLocation} Venue` : null,
                  leaderScope === "conference"
                    ? "Hockey East games"
                    : leaderScope === "beanpot"
                      ? "Beanpot games"
                      : leaderScope === "postseason"
                        ? "HE Postseason"
                        : leaderScope === "ncaa"
                          ? "NCAA Tournament"
                          : "All games",
                ]
                  .filter(Boolean)
                  .join(" • ")}
              </span>
            </div>
            {leadersLoading && <p className="muted">Loading team stats...</p>}
            {!leadersLoading && leadersError && (
              <p className="error-text" role="alert">{leadersError}</p>
            )}
            {!leadersLoading && !leadersError && (!leaders?.team_stats || leaders.team_stats.games_played === 0) && (
              <p className="muted">No team stats found for this filter combination.</p>
            )}
            {!leadersLoading && !leadersError && leaders?.team_stats && leaders.team_stats.games_played > 0 && (() => {
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
                    {ts.pp_pct !== null && ts.pp_pct !== undefined ? (
                      <div className="stat-box">
                        <div className="val">{`${ts.pp_pct}%`}</div>
                        <div className="lbl">{`Power Play (${ts.pp_goals}/${ts.pp_opps}, ${ts.shg || 0} SHG)`}</div>
                      </div>
                    ) : (
                      ts.ppg !== null && (
                        <div className="stat-box">
                          <div className="val">{`${ts.ppg} / ${ts.shg}`}</div>
                          <div className="lbl">PPG / SHG</div>
                        </div>
                      )
                    )}
                    {ts.pk_pct !== null && ts.pk_pct !== undefined && (
                      <div className="stat-box">
                        <div className="val">{`${ts.pk_pct}%`}</div>
                        <div className="lbl">{`Penalty Kill (${ts.pk_kills}/${ts.opp_pp_opps})`}</div>
                      </div>
                    )}
                    {ts.location_splits && (
                      <div className="stat-box">
                        <div className="val" style={{ fontSize: 15 }}>
                          {`${ts.location_splits.home} / ${ts.location_splits.away}`}
                        </div>
                        <div className="lbl">
                          {`Home / Away (${ts.location_splits.neutral} Neutral)`}
                        </div>
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
                          location: leaderLocation,
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
                        {hasModernTracking(selectedSeason)
                          ? (formatPct3(ts.faceoffs_won, ts.faceoffs_lost) ?? "N/A")
                          : "N/A"}
                      </div>
                      <div className="lbl">
                        {hasModernTracking(selectedSeason) && ts.faceoffs_won + ts.faceoffs_lost > 0
                          ? `Faceoff % (${formatFaceoffs(ts.faceoffs_won, ts.faceoffs_lost)})`
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

                  {ts.goals_by_minute?.length > 0 && (
                    <GoalsTimingChart buckets={ts.goals_by_minute} />
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

                  {(selectedSeason !== "all" || ["beanpot", "postseason", "ncaa"].includes(leaderScope)) && ts.games?.length > 0 && (
                    <>
                      <h3 style={{ marginTop: 20 }}>
                        {selectedSeason === "all" ? "Tournament Games" : "Season Games"}
                      </h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Date</th>
                              <th>Opponent</th>
                              <th>Venue</th>
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
                                <td>
                                  {g.venue
                                    ? `${g.venue}${g.location ? ` (${g.location})` : ""}`
                                    : g.location || "—"}
                                </td>
                                <td><OutcomeBadge outcome={g.outcome} /></td>
                                <td>{`${g.nu_goals}-${g.opp_goals}`}</td>
                                <td>{g.overtime_status}</td>
                                <td>
                                  <button
                                    type="button"
                                    className="link-btn"
                                    onClick={() => openBoxScore(g.date, g.opponent)}
                                  >
                                    View
                                  </button>
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
                      : leaderScope === "beanpot"
                        ? "Beanpot Player Stats"
                        : leaderScope === "postseason"
                          ? "Hockey East Postseason Player Stats"
                          : leaderScope === "ncaa"
                            ? "NCAA Tournament Player Stats"
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
            {!leadersLoading && leadersError && (
              <p className="error-text" role="alert">{leadersError}</p>
            )}
            {!leadersLoading && !leadersError && sortedSkaters.length === 0 && (
              <p className="muted">No skater stats found for this filter combination.</p>
            )}
            {!leadersLoading && !leadersError && sortedSkaters.length > 0 && (
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
                        ["faceoffs_won", "FO", "Faceoffs (Won-Total)"],
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
                                src={proxyImageUrl(p.image_url, 32, 32)}
                                srcSet={proxyImageSrcSet(p.image_url, 32, 32)}
                                alt=""
                                className="player-avatar-sm"
                                loading="lazy"
                                onError={(e) => {
                                  e.currentTarget.style.display = "none";
                                }}
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
                          {hasModernTracking(selectedSeason) && p.faceoffs_won !== undefined
                            ? formatFaceoffs(p.faceoffs_won, p.faceoffs_lost)
                            : <span className="muted">N/A</span>}
                        </td>
                        <td>
                          {hasModernTracking(selectedSeason)
                            ? (formatPct3(p.faceoffs_won, p.faceoffs_lost) ?? <span className="muted">N/A</span>)
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
                            <span className="roster-player-cell">
                              {g.image_url && (
                                <img
                                  src={proxyImageUrl(g.image_url, 32, 32)}
                                  srcSet={proxyImageSrcSet(g.image_url, 32, 32)}
                                  alt=""
                                  className="player-avatar-sm"
                                  loading="lazy"
                                  onError={(e) => {
                                    e.currentTarget.style.display = "none";
                                  }}
                                />
                              )}
                              <button
                                type="button"
                                className="player-link"
                                onClick={() => openPlayer(g.player_name)}
                              >
                                {g.player_name}
                              </button>
                            </span>
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
              {safeExternalUrl(roster?.roster_url) && (
                <a
                  href={safeExternalUrl(roster.roster_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-ghost"
                  style={{ textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                >
                  Official Roster
                </a>
              )}
            </div>
            {rosterLoading && <p className="muted">Loading roster...</p>}
            {!rosterLoading && rosterError && (
              <p className="error-text" role="alert">{rosterError}</p>
            )}
            {!rosterLoading && !rosterError && (() => {
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
                            src={proxyImageUrl(p.image_url, 32, 32)}
                            srcSet={proxyImageSrcSet(p.image_url, 32, 32)}
                            alt=""
                            className="player-avatar-sm"
                            loading="lazy"
                            onError={(e) => {
                              e.currentTarget.style.display = "none";
                            }}
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
            {!rivalryLoading && rivalryError && (
              <p className="error-text" role="alert">{rivalryError}</p>
            )}
            {!rivalryLoading && !rivalryError && rivalry && (
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
                              <th>Venue</th>
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
                                <td>
                                  {g.venue
                                    ? `${g.venue}${g.location ? ` (${g.location})` : ""}`
                                    : g.location || "—"}
                                </td>
                                <td><OutcomeBadge outcome={g.outcome} /></td>
                                <td>{`${g.nu_goals}-${g.opp_goals}`}</td>
                                <td>{g.overtime_status}</td>
                                <td>
                                  <button
                                    type="button"
                                    className="link-btn"
                                    onClick={() => openBoxScore(g.date, g.opponent || selectedRival)}
                                  >
                                    View
                                  </button>
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

        {tab === "compare" && (
          <section style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="card">
              <div className="card-header" style={{ marginBottom: 14 }}>
                <div>
                  <h2 style={{ margin: 0 }}>Compare Players</h2>
                  <p className="muted" style={{ margin: "4px 0 0 0", fontSize: 13 }}>
                    Side-by-side comparison of any two Northeastern players across career, per-game rates, specific seasons, or vs. an opponent.
                  </p>
                </div>
                <div className="segmented" role="group" aria-label="Comparison mode">
                  {[
                    ["career", "Career"],
                    ["per_game", "Per Game"],
                    ["season", "By Season"],
                    ["opponent", "vs. Opponent"],
                  ].map(([id, label]) => (
                    <button
                      key={id}
                      type="button"
                      className={`segmented-btn ${compareMode === id ? "active" : ""}`}
                      aria-pressed={compareMode === id}
                      onClick={() => setCompareMode(id)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {(() => {
                const goalieA = isPlayerGoalie(compareAName, compareAData);
                const goalieB = isPlayerGoalie(compareBName, compareBData);
                const roleForA = goalieB === true ? "goalie" : goalieB === false ? "skater" : null;
                const roleForB = goalieA === true ? "goalie" : goalieA === false ? "skater" : null;

                const matchesA = compareAFocus && compareAQuery.trim() && compareAQuery.trim() !== compareAName
                  ? filterPlayerMatches(compareAQuery, roleForA)
                  : [];
                const matchesB = compareBFocus && compareBQuery.trim() && compareBQuery.trim() !== compareBName
                  ? filterPlayerMatches(compareBQuery, roleForB)
                  : [];

                return (
                  <div className="compare-picker-grid">
                    <div style={{ position: "relative" }}>
                      <label className="muted" htmlFor="compare-a-input" style={{ fontSize: 12, display: "block", marginBottom: 4 }}>
                        Player A
                      </label>
                      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                        <input
                          id="compare-a-input"
                          className="text-input"
                          type="text"
                          autoComplete="off"
                          placeholder={
                            roleForA === "goalie"
                              ? "Search goalies (e.g. Devon Levi, Cayden Primeau)"
                              : roleForA === "skater"
                                ? "Search skaters (e.g. Justin, Hryckowian)"
                                : "Search first or last name (e.g. Justin, Hryckowian)"
                          }
                          value={compareAQuery}
                          onFocus={() => setCompareAFocus(true)}
                          onBlur={() => setTimeout(() => setCompareAFocus(false), 150)}
                          onChange={(e) => {
                            const val = e.target.value;
                            setCompareAQuery(val);
                            setCompareAFocus(true);
                            if (!val.trim()) setCompareAName("");
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && matchesA.length > 0) {
                              e.preventDefault();
                              const pick = matchesA[0].player_name;
                              setCompareAQuery(pick);
                              setCompareAName(pick);
                              setCompareAFocus(false);
                            } else if (e.key === "Escape") {
                              setCompareAFocus(false);
                            }
                          }}
                          style={{ paddingRight: compareAQuery ? 28 : undefined, width: "100%" }}
                        />
                        {compareAQuery && (
                          <button
                            type="button"
                            className="compare-clear-btn"
                            aria-label="Clear Player A"
                            onClick={() => {
                              setCompareAQuery("");
                              setCompareAName("");
                            }}
                          >
                            ×
                          </button>
                        )}
                      </div>
                      {compareAFocus && compareAQuery.trim() && compareAQuery.trim() !== compareAName && (
                        <div className="compare-dropdown" role="listbox" aria-label="Player A matches">
                          {matchesA.length > 0 ? (
                            matchesA.map((p) => (
                              <button
                                key={p.player_name}
                                type="button"
                                role="option"
                                aria-selected={false}
                                className="compare-dropdown-item"
                                onMouseDown={(e) => {
                                  e.preventDefault();
                                  setCompareAQuery(p.player_name);
                                  setCompareAName(p.player_name);
                                  setCompareAFocus(false);
                                }}
                              >
                                <span style={{ fontWeight: 600 }}>{p.player_name}</span>
                                <span className="muted" style={{ fontSize: 11, whiteSpace: "nowrap" }}>
                                  {[p.position, p.seasons_span].filter(Boolean).join(" • ")}
                                </span>
                              </button>
                            ))
                          ) : (
                            <div className="muted" style={{ padding: "8px 10px", fontSize: 12 }}>
                              {playersLoading
                                ? "Loading player list..."
                                : playersError
                                  ? playersError
                                  : roleForA === "goalie"
                                    ? "No matching goalies found"
                                    : roleForA === "skater"
                                      ? "No matching skaters found"
                                      : "No matching players found"}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    <button
                      type="button"
                      className="btn-ghost compare-swap-btn"
                      title="Swap players"
                      aria-label="Swap Player A and Player B"
                      onClick={() => {
                        const tmpNameA = compareAName;
                        const tmpNameB = compareBName;
                        const tmpQueryA = compareAQuery;
                        const tmpQueryB = compareBQuery;
                        const tmpSeasonA = compareSeasonA;
                        const tmpSeasonB = compareSeasonB;
                        const tmpDataA = compareAData;
                        const tmpDataB = compareBData;
                        setCompareAName(tmpNameB);
                        setCompareBName(tmpNameA);
                        setCompareAQuery(tmpQueryB);
                        setCompareBQuery(tmpQueryA);
                        setCompareSeasonA(tmpSeasonB);
                        setCompareSeasonB(tmpSeasonA);
                        setCompareAData(tmpDataB);
                        setCompareBData(tmpDataA);
                      }}
                    >
                      ⇄
                    </button>

                    <div style={{ position: "relative" }}>
                      <label className="muted" htmlFor="compare-b-input" style={{ fontSize: 12, display: "block", marginBottom: 4 }}>
                        Player B
                      </label>
                      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                        <input
                          id="compare-b-input"
                          className="text-input"
                          type="text"
                          autoComplete="off"
                          placeholder={
                            roleForB === "goalie"
                              ? "Search goalies (e.g. Devon Levi, Cayden Primeau)"
                              : roleForB === "skater"
                                ? "Search skaters (e.g. Aidan, McDonough)"
                                : "Search first or last name (e.g. Aidan, McDonough)"
                          }
                          value={compareBQuery}
                          onFocus={() => setCompareBFocus(true)}
                          onBlur={() => setTimeout(() => setCompareBFocus(false), 150)}
                          onChange={(e) => {
                            const val = e.target.value;
                            setCompareBQuery(val);
                            setCompareBFocus(true);
                            if (!val.trim()) setCompareBName("");
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && matchesB.length > 0) {
                              e.preventDefault();
                              const pick = matchesB[0].player_name;
                              setCompareBQuery(pick);
                              setCompareBName(pick);
                              setCompareBFocus(false);
                            } else if (e.key === "Escape") {
                              setCompareBFocus(false);
                            }
                          }}
                          style={{ paddingRight: compareBQuery ? 28 : undefined, width: "100%" }}
                        />
                        {compareBQuery && (
                          <button
                            type="button"
                            className="compare-clear-btn"
                            aria-label="Clear Player B"
                            onClick={() => {
                              setCompareBQuery("");
                              setCompareBName("");
                            }}
                          >
                            ×
                          </button>
                        )}
                      </div>
                      {compareBFocus && compareBQuery.trim() && compareBQuery.trim() !== compareBName && (
                        <div className="compare-dropdown" role="listbox" aria-label="Player B matches">
                          {matchesB.length > 0 ? (
                            matchesB.map((p) => (
                              <button
                                key={p.player_name}
                                type="button"
                                role="option"
                                aria-selected={false}
                                className="compare-dropdown-item"
                                onMouseDown={(e) => {
                                  e.preventDefault();
                                  setCompareBQuery(p.player_name);
                                  setCompareBName(p.player_name);
                                  setCompareBFocus(false);
                                }}
                              >
                                <span style={{ fontWeight: 600 }}>{p.player_name}</span>
                                <span className="muted" style={{ fontSize: 11, whiteSpace: "nowrap" }}>
                                  {[p.position, p.seasons_span].filter(Boolean).join(" • ")}
                                </span>
                              </button>
                            ))
                          ) : (
                            <div className="muted" style={{ padding: "8px 10px", fontSize: 12 }}>
                              {playersLoading
                                ? "Loading player list..."
                                : playersError
                                  ? playersError
                                  : roleForB === "goalie"
                                    ? "No matching goalies found"
                                    : roleForB === "skater"
                                      ? "No matching skaters found"
                                      : "No matching players found"}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}

              {!compareAName && !compareBName && (
                <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                  <span className="muted" style={{ fontSize: 12 }}>Try a matchup:</span>
                  {[
                    ["Justin Hryckowian", "Aidan McDonough"],
                    ["Devon Levi", "Cayden Primeau"],
                    ["Dylan Hryckowian", "Jack Williams"],
                  ].map(([a, b]) => (
                    <button
                      key={`${a}-${b}`}
                      type="button"
                      className="btn-ghost"
                      style={{ fontSize: 12, padding: "4px 10px" }}
                      onClick={() => {
                        setCompareAName(a);
                        setCompareAQuery(a);
                        setCompareBName(b);
                        setCompareBQuery(b);
                      }}
                    >
                      {a} vs. {b}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {compareLoading && (
              <div className="card" role="status" aria-live="polite">
                <p className="muted" style={{ margin: 0 }}>Loading player comparison...</p>
              </div>
            )}

            {compareError && (
              <div className="card" role="alert">
                <p className="error-text" style={{ margin: 0 }}>{compareError}</p>
              </div>
            )}

            {!compareLoading && (compareAData || compareBData) && (() => {
              const pA = compareAData;
              const pB = compareBData;

              const renderHero = (pdata, label) => {
                if (!pdata) {
                  return (
                    <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 110 }}>
                      <span className="muted">Select {label} to compare</span>
                    </div>
                  );
                }
                const bio = pdata.bio || {};
                return (
                  <div className="card" style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    {bio.image_url ? (
                      <img
                        src={proxyImageUrl(bio.image_url, 60, 76)}
                        srcSet={proxyImageSrcSet(bio.image_url, 60, 76)}
                        alt={bio.player_name}
                        className="player-avatar-md"
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                        }}
                      />
                    ) : (
                      <div className="jersey-box" style={{ width: 56, height: 56, fontSize: 18 }}>
                        {bio.jersey_number || "--"}
                      </div>
                    )}
                    <div style={{ minWidth: 0 }}>
                      <button
                        type="button"
                        className="link-btn"
                        style={{ fontSize: 17, fontWeight: 700, textAlign: "left" }}
                        onClick={() => openPlayer(bio.player_name)}
                      >
                        {bio.jersey_number ? `#${bio.jersey_number} ` : ""}
                        {bio.player_name}
                      </button>
                      <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                        {[
                          bio.position,
                          bio.seasons_played?.length ? `${bio.seasons_played.length} Season${bio.seasons_played.length > 1 ? "s" : ""}` : null,
                          bio.shoots ? `Shoots ${bio.shoots}` : null,
                        ]
                          .filter(Boolean)
                          .join(" • ")}
                      </div>
                      {(bio.height || bio.weight || bio.hometown) && (
                        <div className="muted" style={{ fontSize: 12 }}>
                          {[bio.height, bio.weight ? `${bio.weight} lbs` : null, bio.hometown].filter(Boolean).join(" • ")}
                        </div>
                      )}
                    </div>
                  </div>
                );
              };

              const directChem =
                pA && pB && pA.chemistry?.find((c) => c.player_name?.toLowerCase() === pB.bio?.player_name?.toLowerCase());

              const oppsA = new Set((pA?.game_logs || []).map((g) => g.opponent).filter(Boolean));
              const oppsB = new Set((pB?.game_logs || []).map((g) => g.opponent).filter(Boolean));
              const allOpponents = (pA && pB
                ? Array.from(oppsA).filter((opp) => oppsB.has(opp))
                : Array.from(new Set([...oppsA, ...oppsB]))
              ).sort();

              const activeOpp = compareOpponent && allOpponents.includes(compareOpponent)
                ? compareOpponent
                : allOpponents[0] || "";

              const aggOpponent = (pdata) => {
                if (!pdata || !activeOpp) return null;
                const logs = (pdata.game_logs || []).filter((g) => g.opponent === activeOpp);
                if (pdata.is_goalie) {
                  const gp = logs.length;
                  const wins = logs.filter((g) => g.decision === "W").length;
                  const losses = logs.filter((g) => g.decision === "L").length;
                  const ties = logs.filter((g) => g.decision === "T").length;
                  const saves = logs.reduce((s, g) => s + Number(g.saves || 0), 0);
                  const ga = logs.reduce((s, g) => s + Number(g.goals_against || 0), 0);
                  const shutouts = logs.reduce((s, g) => s + Number(g.shutouts || 0), 0);
                  const mins = logs.reduce((s, g) => s + parseMinutesToFloat(g.minutes), 0);
                  const sa = saves + ga;
                  return {
                    gp,
                    wins,
                    losses,
                    ties,
                    saves,
                    goals_against: ga,
                    save_pct: sa > 0 ? saves / sa : 0,
                    gaa: mins > 0 ? (ga * 60) / mins : 0,
                    shutouts,
                  };
                }
                const gp = logs.length;
                const goals = logs.reduce((s, g) => s + Number(g.goals || 0), 0);
                const assists = logs.reduce((s, g) => s + Number(g.assists || 0), 0);
                const points = logs.reduce((s, g) => s + Number(g.points || 0), 0);
                const shots = logs.reduce((s, g) => s + Number(g.shots || 0), 0);
                const plus_minus = logs.reduce((s, g) => s + Number(g.plus_minus || 0), 0);
                const pim = logs.reduce((s, g) => s + Number(g.penalty_minutes || 0), 0);
                const blocked_shots = logs.reduce((s, g) => s + Number(g.blocked_shots || 0), 0);
                const faceoffs_won = logs.reduce((s, g) => s + Number(g.faceoffs_won || 0), 0);
                const faceoffs_lost = logs.reduce((s, g) => s + Number(g.faceoffs_lost || 0), 0);
                const gwg = logs.reduce((s, g) => s + Number(g.gwg || 0), 0);
                const foTotal = faceoffs_won + faceoffs_lost;
                return {
                  gp,
                  goals,
                  assists,
                  points,
                  shots,
                  shooting_pct: shots > 0 ? (goals / shots) * 100 : 0,
                  plus_minus,
                  pim,
                  blocked_shots,
                  faceoffs_won,
                  faceoffs_lost,
                  faceoff_pct: foTotal > 0 ? (faceoffs_won / foTotal) * 100 : 0,
                  gwg,
                };
              };

              const getStatsObj = (pdata, seasonSel) => {
                if (!pdata) return null;
                if (compareMode === "season") {
                  const row = (pdata.seasons || []).find((s) => s.season === seasonSel) || pdata.seasons?.[0];
                  if (!row) return null;
                  if (pdata.is_goalie) {
                    return { ...row, gp: row.goalie_gp ?? row.gp ?? 0 };
                  }
                  return row;
                }
                if (compareMode === "opponent") {
                  return aggOpponent(pdata);
                }
                return pdata.is_goalie ? pdata.career_goalie : pdata.career_skater;
              };

              const statsA = getStatsObj(pA, compareSeasonA);
              const statsB = getStatsObj(pB, compareSeasonB);

              const bothGoalies = Boolean(pA?.is_goalie && pB?.is_goalie);
              const bothSkaters = Boolean(pA && pB && !pA.is_goalie && !pB.is_goalie);
              const mixedPositions = Boolean(pA && pB && pA.is_goalie !== pB.is_goalie);

              const buildSkaterRows = (sA, sB) => {
                const gpA = Number(sA?.gp || 0);
                const gpB = Number(sB?.gp || 0);
                const getShotPct = (s) => {
                  if (!s) return 0;
                  if (s.shooting_pct !== undefined && s.shooting_pct !== null) {
                    return Number(s.shooting_pct);
                  }
                  if (s.shot_pct !== undefined && s.shot_pct !== null) {
                    const raw = Number(s.shot_pct);
                    if (raw > 1) return raw;
                    const sh = Number(s.shots || 0);
                    const gl = Number(s.goals || 0);
                    return sh > 0 ? (gl / sh) * 100 : raw * 100;
                  }
                  const sh = Number(s.shots || 0);
                  const gl = Number(s.goals || 0);
                  return sh > 0 ? (gl / sh) * 100 : 0;
                };
                const getFoPct = (s) => {
                  if (!s) return null;
                  const fw = Number(s.faceoffs_won || 0);
                  const fl = Number(s.faceoffs_lost || 0);
                  if (fw + fl > 0) {
                    return (fw / (fw + fl)) * 100;
                  }
                  if (s.faceoff_pct !== undefined && s.faceoff_pct !== null && Number(s.faceoff_pct) > 0) {
                    const raw = Number(s.faceoff_pct);
                    return raw <= 1 ? raw * 100 : raw;
                  }
                  return null;
                };
                if (compareMode === "per_game") {
                  const rate = (val, gp, dec = 2) => (gp > 0 ? Number((Number(val || 0) / gp).toFixed(dec)) : 0);
                  return [
                    { label: "Games Played (GP)", a: gpA, b: gpB, fmt: (v) => v },
                    { label: "Goals / Game", a: rate(sA?.goals, gpA), b: rate(sB?.goals, gpB), fmt: (v) => v.toFixed(2) },
                    { label: "Assists / Game", a: rate(sA?.assists, gpA), b: rate(sB?.assists, gpB), fmt: (v) => v.toFixed(2) },
                    { label: "Points / Game", a: rate(sA?.points, gpA), b: rate(sB?.points, gpB), fmt: (v) => v.toFixed(2) },
                    { label: "Shots / Game", a: rate(sA?.shots, gpA), b: rate(sB?.shots, gpB), fmt: (v) => v.toFixed(2) },
                    { label: "Shooting %", a: getShotPct(sA), b: getShotPct(sB), fmt: (v) => `${v.toFixed(1)}%` },
                    { label: "Blocks / Game", a: rate(sA?.blocked_shots, gpA), b: rate(sB?.blocked_shots, gpB), fmt: (v) => v.toFixed(2) },
                    { label: "Faceoff %", a: getFoPct(sA), b: getFoPct(sB), fmt: (v) => (v === null ? "—" : `${v.toFixed(1)}%`) },
                    { label: "PIM / Game", a: rate(sA?.pim, gpA), b: rate(sB?.pim, gpB), fmt: (v) => v.toFixed(2), neutral: true },
                  ];
                }
                const foA = Number(sA?.faceoffs_won || 0) + Number(sA?.faceoffs_lost || 0);
                const foB = Number(sB?.faceoffs_won || 0) + Number(sB?.faceoffs_lost || 0);
                const foPctA = getFoPct(sA);
                const foPctB = getFoPct(sB);
                return [
                  { label: "Games Played (GP)", a: gpA, b: gpB, fmt: (v) => v },
                  { label: "Goals (G)", a: Number(sA?.goals || 0), b: Number(sB?.goals || 0), fmt: (v) => v },
                  { label: "Assists (A)", a: Number(sA?.assists || 0), b: Number(sB?.assists || 0), fmt: (v) => v },
                  { label: "Points (PTS)", a: Number(sA?.points || 0), b: Number(sB?.points || 0), fmt: (v) => v },
                  { label: "+/-", a: Number(sA?.plus_minus || 0), b: Number(sB?.plus_minus || 0), fmt: (v) => (v > 0 ? `+${v}` : v) },
                  { label: "Shots on Goal (SOG)", a: Number(sA?.shots || 0), b: Number(sB?.shots || 0), fmt: (v) => v },
                  { label: "Shooting %", a: getShotPct(sA), b: getShotPct(sB), fmt: (v) => `${v.toFixed(1)}%` },
                  { label: "Power-Play Goals (PPG)", a: Number(sA?.ppg || 0), b: Number(sB?.ppg || 0), fmt: (v) => v },
                  { label: "Short-Handed Goals (SHG)", a: Number(sA?.shg || 0), b: Number(sB?.shg || 0), fmt: (v) => v },
                  { label: "Game-Winning Goals (GWG)", a: Number(sA?.gwg || 0), b: Number(sB?.gwg || 0), fmt: (v) => v },
                  { label: "Blocked Shots (BLK)", a: Number(sA?.blocked_shots || 0), b: Number(sB?.blocked_shots || 0), fmt: (v) => v },
                  {
                    label: "Faceoffs (W-Total)",
                    a: foPctA,
                    b: foPctB,
                    displayA: foA > 0 ? `${sA.faceoffs_won}-${foA} (${foPctA.toFixed(1)}%)` : foPctA !== null ? `${foPctA.toFixed(1)}%` : "—",
                    displayB: foB > 0 ? `${sB.faceoffs_won}-${foB} (${foPctB.toFixed(1)}%)` : foPctB !== null ? `${foPctB.toFixed(1)}%` : "—",
                  },
                  { label: "Penalty Minutes (PIM)", a: Number(sA?.pim || 0), b: Number(sB?.pim || 0), fmt: (v) => v, neutral: true },
                ];
              };

              const buildGoalieRows = (sA, sB) => {
                const gpA = Number(sA?.gp ?? sA?.goalie_gp ?? 0);
                const gpB = Number(sB?.gp ?? sB?.goalie_gp ?? 0);
                const gaA = Number(sA?.goals_against ?? sA?.ga ?? 0);
                const gaB = Number(sB?.goals_against ?? sB?.ga ?? 0);
                if (compareMode === "per_game") {
                  const rate = (val, gp) => (gp > 0 ? Number((Number(val || 0) / gp).toFixed(2)) : 0);
                  return [
                    { label: "Games Played (GP)", a: gpA, b: gpB, fmt: (v) => v },
                    { label: "Save % (SV%)", a: Number(sA?.save_pct || 0), b: Number(sB?.save_pct || 0), fmt: (v) => v.toFixed(3) },
                    ...(sA?.gaa !== undefined && sB?.gaa !== undefined
                      ? [{ label: "Goals Against Avg (GAA)", a: Number(sA.gaa || 0), b: Number(sB.gaa || 0), fmt: (v) => v.toFixed(2), lowerBetter: true }]
                      : []),
                    { label: "Saves / Game", a: rate(sA?.saves, gpA), b: rate(sB?.saves, gpB), fmt: (v) => v.toFixed(1) },
                    { label: "Goals Against / Game", a: rate(gaA, gpA), b: rate(gaB, gpB), fmt: (v) => v.toFixed(2), lowerBetter: true },
                  ];
                }
                return [
                  { label: "Games Played (GP)", a: gpA, b: gpB, fmt: (v) => v },
                  { label: "Wins (W)", a: Number(sA?.wins || 0), b: Number(sB?.wins || 0), fmt: (v) => v },
                  { label: "Losses (L)", a: Number(sA?.losses || 0), b: Number(sB?.losses || 0), fmt: (v) => v, lowerBetter: true },
                  { label: "Ties (T)", a: Number(sA?.ties || 0), b: Number(sB?.ties || 0), fmt: (v) => v, neutral: true },
                  { label: "Save % (SV%)", a: Number(sA?.save_pct || 0), b: Number(sB?.save_pct || 0), fmt: (v) => v.toFixed(3) },
                  ...(sA?.gaa !== undefined && sB?.gaa !== undefined
                    ? [{ label: "Goals Against Avg (GAA)", a: Number(sA.gaa || 0), b: Number(sB.gaa || 0), fmt: (v) => v.toFixed(2), lowerBetter: true }]
                    : []),
                  { label: "Saves (SV)", a: Number(sA?.saves || 0), b: Number(sB?.saves || 0), fmt: (v) => v },
                  { label: "Goals Against (GA)", a: gaA, b: gaB, fmt: (v) => v, lowerBetter: true },
                  { label: "Shutouts (SO)", a: Number(sA?.shutouts || 0), b: Number(sB?.shutouts || 0), fmt: (v) => v },
                ];
              };

              const rows = bothGoalies
                ? buildGoalieRows(statsA, statsB)
                : bothSkaters
                  ? buildSkaterRows(statsA, statsB)
                  : [];

              return (
                <>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 14 }}>
                    {renderHero(pA, "Player A")}
                    {renderHero(pB, "Player B")}
                  </div>

                  {directChem && (
                    <div className="card chemistry-banner">
                      <strong>Teammate Goal Chemistry:</strong> {pA.bio.player_name} and {pB.bio.player_name} connected on{" "}
                      <strong>{directChem.total_connections}</strong> Northeastern goal{directChem.total_connections === 1 ? "" : "s"} (
                      {pA.bio.player_name} scored {directChem.assisted_by_them}x off {pB.bio.player_name}, assisted{" "}
                      {directChem.assisted_for_them}x).
                    </div>
                  )}

                  {compareMode === "season" && pA && pB && (
                    <div className="card" style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span className="muted" style={{ fontSize: 13 }}>{pA.bio.player_name} Season:</span>
                        <select
                          className="select-input"
                          value={compareSeasonA}
                          onChange={(e) => setCompareSeasonA(e.target.value)}
                        >
                          {(pA.seasons || []).map((s) => (
                            <option key={s.season} value={s.season}>{s.season}</option>
                          ))}
                        </select>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span className="muted" style={{ fontSize: 13 }}>{pB.bio.player_name} Season:</span>
                        <select
                          className="select-input"
                          value={compareSeasonB}
                          onChange={(e) => setCompareSeasonB(e.target.value)}
                        >
                          {(pB.seasons || []).map((s) => (
                            <option key={s.season} value={s.season}>{s.season}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  )}

                  {compareMode === "opponent" && pA && pB && (
                    <div className="card" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
                      {allOpponents.length > 0 ? (
                        <>
                          <span className="muted" style={{ fontSize: 13 }}>Opponent:</span>
                          <select
                            className="select-input"
                            value={activeOpp}
                            onChange={(e) => setCompareOpponent(e.target.value)}
                          >
                            {allOpponents.map((opp) => (
                              <option key={opp} value={opp}>{opp}</option>
                            ))}
                          </select>
                        </>
                      ) : (
                        <span className="muted" style={{ fontSize: 13 }}>
                          No shared opponents found between {pA.bio.player_name} and {pB.bio.player_name}.
                        </span>
                      )}
                    </div>
                  )}

                  {mixedPositions && (
                    <div className="card">
                      <p className="muted" style={{ margin: 0 }}>
                        {pA.bio.player_name} ({pA.is_goalie ? "Goalie" : "Skater"}) and {pB.bio.player_name} (
                        {pB.is_goalie ? "Goalie" : "Skater"}) play different positions, so direct stat-by-stat comparison isn&apos;t available.
                      </p>
                    </div>
                  )}

                  {rows.length > 0 && !(compareMode === "opponent" && !activeOpp) && (
                    <div className="card">
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th style={{ textAlign: "right", width: "30%" }}>{pA.bio.player_name}</th>
                              <th style={{ textAlign: "center", width: "40%" }}>Stat</th>
                              <th style={{ textAlign: "left", width: "30%" }}>{pB.bio.player_name}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map((r) => {
                              const comparable =
                                !r.neutral &&
                                r.a !== null &&
                                r.b !== null &&
                                r.a !== r.b;
                              const aBetter =
                                comparable &&
                                (r.lowerBetter ? r.a < r.b : r.a > r.b);
                              const bBetter =
                                comparable &&
                                (r.lowerBetter ? r.b < r.a : r.b > r.a);
                              return (
                                <tr key={r.label}>
                                  <td
                                    style={{
                                      textAlign: "right",
                                      fontWeight: aBetter ? 700 : 400,
                                      color: aBetter ? "#15803d" : undefined,
                                    }}
                                  >
                                    {r.displayA ?? r.fmt(r.a)}
                                  </td>
                                  <td style={{ textAlign: "center" }} className="muted">
                                    {r.label}
                                  </td>
                                  <td
                                    style={{
                                      textAlign: "left",
                                      fontWeight: bBetter ? 700 : 400,
                                      color: bBetter ? "#15803d" : undefined,
                                    }}
                                  >
                                    {r.displayB ?? r.fmt(r.b)}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {!mixedPositions && pA && pB && (
                    <CompareFormChart pA={pA} pB={pB} />
                  )}
                </>
              );
            })()}
          </section>
        )}

        {tab === "records" && (
          <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="controls-row" style={{ flexWrap: "wrap", gap: 10 }}>
              <div className="segmented" role="group" aria-label="Records and History sections">
                <button
                  type="button"
                  className={`segmented-btn ${recordsSubTab === "recordbook" ? "active" : ""}`}
                  onClick={() => setRecordsSubTab("recordbook")}
                >
                  Record Book
                </button>
                <button
                  type="button"
                  className={`segmented-btn ${recordsSubTab === "milestones" ? "active" : ""}`}
                  onClick={() => setRecordsSubTab("milestones")}
                >
                  Milestones &amp; Clutch
                </button>
                <button
                  type="button"
                  className={`segmented-btn ${recordsSubTab === "chemistry" ? "active" : ""}`}
                  onClick={() => setRecordsSubTab("chemistry")}
                >
                  Chemistry &amp; Lines
                </button>
                <button
                  type="button"
                  className={`segmented-btn ${recordsSubTab === "onthisday" ? "active" : ""}`}
                  onClick={() => setRecordsSubTab("onthisday")}
                >
                  On This Day
                </button>
              </div>
            </div>

            {recordsLoading && !recordsData && (
              <div className="card">
                <p className="muted">Loading Northeastern Record Book &amp; Archives...</p>
              </div>
            )}

            {!recordsLoading && recordsError && (
              <div className="card" role="alert">
                <p className="error-text" style={{ margin: 0 }}>{recordsError}</p>
              </div>
            )}

            {recordsData && !recordsError && recordsSubTab === "recordbook" && (() => {
              const isSeasonMode = recordsLeaderboardMode === "season";
              const posFilter = recordsPosition;
              const classFilter = recordsClassYear;

              const matchPos = (posVal) => {
                if (posFilter === "all") return true;
                return (posVal || "").toUpperCase() === posFilter.toUpperCase();
              };
              const matchClass = (cls) => {
                if (classFilter === "all") return true;
                return (cls || "").toLowerCase() === classFilter.toLowerCase();
              };

              const classRank = {
                "fr.": 1,
                "so.": 2,
                "jr.": 3,
                "sr.": 4,
                "gr.": 5,
              };

              const toggleRecordSkaterSort = (key) => {
                const defaultAsc = ["player_name", "position", "class_year"].includes(key);
                setRecordSkaterSort((prev) =>
                  prev.key === key
                    ? { key, dir: prev.dir === "desc" ? "asc" : "desc" }
                    : { key, dir: defaultAsc ? "asc" : "desc" }
                );
              };

              const toggleRecordGoalieSort = (key) => {
                const defaultAsc = ["player_name", "class_year", "gaa"].includes(key);
                setRecordGoalieSort((prev) =>
                  prev.key === key
                    ? { key, dir: prev.dir === "desc" ? "asc" : "desc" }
                    : { key, dir: defaultAsc ? "asc" : "desc" }
                );
              };

              const getSkaterSortVal = (r, key) => {
                if (key === "player_name") return String(r.player_name || "").toLowerCase();
                if (key === "position") return String(r.position || r.position_group || "").toLowerCase();
                if (key === "season") return String(r.season || r.first_season || "");
                if (key === "class_year") return classRank[String(r.class_year || "").toLowerCase()] || 99;
                if (key === "pts_per_gp") {
                  return r.pts_per_gp !== undefined && r.pts_per_gp !== null
                    ? Number(r.pts_per_gp)
                    : r.gp > 0
                      ? Number(r.points || 0) / Number(r.gp)
                      : 0;
                }
                return Number(r[key] ?? 0);
              };

              const getGoalieSortVal = (r, key) => {
                if (key === "player_name") return String(r.player_name || "").toLowerCase();
                if (key === "season") return String(r.season || r.first_season || "");
                if (key === "class_year") return classRank[String(r.class_year || "").toLowerCase()] || 99;
                if (key === "gp") return Number(r.gp ?? r.goalie_gp ?? 0);
                return Number(r[key] ?? 0);
              };

              const rawSkaters = isSeasonMode
                ? (recordsData.single_season_skaters || [])
                : (recordsData.career_skaters || []);
              const filteredSkaters = rawSkaters
                .filter((r) => matchPos(r.position_group || r.position) && (!isSeasonMode || matchClass(r.class_year)))
                .slice()
                .sort((a, b) => {
                  const k = recordSkaterSort.key;
                  const dirMult = recordSkaterSort.dir === "asc" ? 1 : -1;
                  const va = getSkaterSortVal(a, k);
                  const vb = getSkaterSortVal(b, k);
                  if (typeof va === "string" || typeof vb === "string") {
                    const cmp = String(va).localeCompare(String(vb));
                    if (cmp !== 0) return cmp * dirMult;
                  } else if (va !== vb) {
                    return (va - vb) * dirMult;
                  }
                  return Number(b.points || 0) - Number(a.points || 0) || Number(b.goals || 0) - Number(a.goals || 0);
                })
                .slice(0, 50);

              const rawGoalies = isSeasonMode
                ? (recordsData.single_season_goalies || [])
                : (recordsData.career_goalies || []);
              const filteredGoalies = rawGoalies
                .filter((r) => !isSeasonMode || matchClass(r.class_year))
                .slice()
                .sort((a, b) => {
                  const k = recordGoalieSort.key;
                  const dirMult = recordGoalieSort.dir === "asc" ? 1 : -1;
                  const va = getGoalieSortVal(a, k);
                  const vb = getGoalieSortVal(b, k);
                  if (typeof va === "string" || typeof vb === "string") {
                    const cmp = String(va).localeCompare(String(vb));
                    if (cmp !== 0) return cmp * dirMult;
                  } else if (va !== vb) {
                    return (va - vb) * dirMult;
                  }
                  return Number(b.wins || 0) - Number(a.wins || 0) || Number(b.save_pct || 0) - Number(a.save_pct || 0);
                })
                .slice(0, 35);

              const skaterColumns = [
                ["player_name", "Player", "Player Name"],
                ["position", "Pos", "Position"],
                ...(isSeasonMode
                  ? [
                      ["season", "Season", "Season"],
                      ["class_year", "Class", "Class Year"],
                    ]
                  : [["season", "Seasons", "Career Span"]]),
                ["gp", "GP", "Games Played"],
                ["goals", "G", "Goals"],
                ["assists", "A", "Assists"],
                ["points", "PTS", "Points"],
                ["pts_per_gp", "PTS/G", "Points Per Game"],
                ["ppg", "PPG", "Power-Play Goals"],
                ["shg", "SHG", "Short-Handed Goals"],
                ["gwg", "GWG", "Game-Winning Goals"],
                ["shots", "SOG", "Shots on Goal"],
                ["plus_minus", "+/-", "Plus/Minus"],
                ["pim", "PIM", "Penalty Minutes"],
              ];

              const goalieColumns = [
                ["player_name", "Goalie", "Goalie Name"],
                ...(isSeasonMode
                  ? [
                      ["season", "Season", "Season"],
                      ["class_year", "Class", "Class Year"],
                    ]
                  : [["season", "Seasons", "Career Span"]]),
                ["gp", "GP", "Games Played"],
                ["wins", "W", "Wins"],
                ["losses", "L", "Losses"],
                ["ties", "T", "Ties"],
                ["save_pct", "SV%", "Save Percentage"],
                ["gaa", "GAA", "Goals Against Average"],
                ["saves", "SV", "Saves"],
                ["ga", "GA", "Goals Against"],
                ["shutouts", "SO", "Shutouts"],
              ];

              const sgr = recordsData.single_game_records || {};
              const streaks = recordsData.streaks || {};

              return (
                <>
                  <div className="card">
                    <div className="card-header" style={{ flexWrap: "wrap", gap: 12 }}>
                      <div>
                        <h2>Program Leaderboards (1999&ndash;Present)</h2>
                        <span className="muted">
                          {isSeasonMode
                            ? "All-time single-season benchmarks — tap any column header to sort"
                            : "All-time career totals across the modern Huskies archive — tap any column header to sort"}
                        </span>
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                        <div className="segmented" role="group" aria-label="Leaderboard timeframe">
                          <button
                            type="button"
                            className={`segmented-btn ${recordsLeaderboardMode === "career" ? "active" : ""}`}
                            onClick={() => setRecordsLeaderboardMode("career")}
                          >
                            Career Leaders
                          </button>
                          <button
                            type="button"
                            className={`segmented-btn ${recordsLeaderboardMode === "season" ? "active" : ""}`}
                            onClick={() => setRecordsLeaderboardMode("season")}
                          >
                            Single-Season
                          </button>
                        </div>

                        <select
                          aria-label="Filter leaderboard by position"
                          className="select-input"
                          value={recordsPosition}
                          onChange={(e) => setRecordsPosition(e.target.value)}
                        >
                          <option value="all">All Positions</option>
                          <option value="F">Forwards (F)</option>
                          <option value="D">Defensemen (D)</option>
                          <option value="G">Goalies Only (G)</option>
                        </select>

                        {isSeasonMode && (
                          <select
                            aria-label="Filter single-season records by class year"
                            className="select-input"
                            value={recordsClassYear}
                            onChange={(e) => setRecordsClassYear(e.target.value)}
                          >
                            <option value="all">All Class Years</option>
                            <option value="Fr.">Freshmen (Fr.)</option>
                            <option value="So.">Sophomores (So.)</option>
                            <option value="Jr.">Juniors (Jr.)</option>
                            <option value="Sr.">Seniors (Sr.)</option>
                            <option value="Gr.">Graduates (Gr.)</option>
                          </select>
                        )}
                      </div>
                    </div>

                    {recordsPosition !== "G" && (
                      <>
                        <h3 className="sub-heading">
                          {isSeasonMode ? "Single-Season Skater Leaders" : "Career Skater Leaders"}
                        </h3>
                        <div className="table-wrap" style={{ marginBottom: 18 }}>
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th scope="col">#</th>
                              {skaterColumns.map(([colKey, label, fullLabel]) => {
                                const isSorted = recordSkaterSort.key === colKey;
                                const ariaSort = isSorted
                                  ? recordSkaterSort.dir === "desc"
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
                                    aria-label={`Sort skaters by ${fullLabel}`}
                                    onClick={() => toggleRecordSkaterSort(colKey)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter" || e.key === " ") {
                                        e.preventDefault();
                                        toggleRecordSkaterSort(colKey);
                                      }
                                    }}
                                  >
                                    {label} {isSorted ? (recordSkaterSort.dir === "desc" ? "↓" : "↑") : ""}
                                  </th>
                                );
                              })}
                            </tr>
                          </thead>
                          <tbody>
                            {filteredSkaters.map((sk, idx) => {
                              const ptsPerGp = sk.pts_per_gp ?? (sk.gp > 0 ? sk.points / sk.gp : 0);
                              return (
                                <tr key={`${sk.player_name}-${sk.season || idx}`}>
                                  <td>{idx + 1}</td>
                                  <td>
                                    <button
                                      type="button"
                                      className="link-btn"
                                      onClick={() => openPlayer(sk.player_name)}
                                    >
                                      {sk.player_name}
                                    </button>
                                  </td>
                                  <td>{sk.position || sk.position_group}</td>
                                  {isSeasonMode ? (
                                    <>
                                      <td>{sk.season}</td>
                                      <td>{sk.class_year || "-"}</td>
                                    </>
                                  ) : (
                                    <td className="muted" style={{ fontSize: 12 }}>
                                      {sk.span || (sk.first_season === sk.last_season
                                        ? sk.first_season
                                        : `${sk.first_season}–${String(sk.last_season || "").slice(-2)}`)}
                                    </td>
                                  )}
                                  <td>{sk.gp}</td>
                                  <td>{sk.goals}</td>
                                  <td>{sk.assists}</td>
                                  <td><strong>{sk.points}</strong></td>
                                  <td>{Number(ptsPerGp || 0).toFixed(2)}</td>
                                  <td>{sk.ppg}</td>
                                  <td>{sk.shg}</td>
                                  <td>{sk.gwg}</td>
                                  <td>{sk.shots}</td>
                                  <td>{sk.plus_minus > 0 ? `+${sk.plus_minus}` : sk.plus_minus}</td>
                                  <td>{sk.pim}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      </>
                    )}

                    {(recordsPosition === "all" || recordsPosition === "G") && (
                      <>
                        <h3 className="sub-heading">
                          {isSeasonMode
                            ? "Single-Season Goalie Leaders (min. 10 GP)"
                            : "Career Goalie Leaders (min. 10 GP)"}
                        </h3>
                        <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th scope="col">#</th>
                              {goalieColumns.map(([colKey, label, fullLabel]) => {
                                const isSorted = recordGoalieSort.key === colKey;
                                const ariaSort = isSorted
                                  ? recordGoalieSort.dir === "desc"
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
                                    aria-label={`Sort goalies by ${fullLabel}`}
                                    onClick={() => toggleRecordGoalieSort(colKey)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter" || e.key === " ") {
                                        e.preventDefault();
                                        toggleRecordGoalieSort(colKey);
                                      }
                                    }}
                                  >
                                    {label} {isSorted ? (recordGoalieSort.dir === "desc" ? "↓" : "↑") : ""}
                                  </th>
                                );
                              })}
                            </tr>
                          </thead>
                          <tbody>
                            {filteredGoalies.map((gl, idx) => (
                              <tr key={`${gl.player_name}-${gl.season || idx}`}>
                                <td>{idx + 1}</td>
                                <td>
                                  <button
                                    type="button"
                                    className="link-btn"
                                    onClick={() => openPlayer(gl.player_name)}
                                  >
                                    {gl.player_name}
                                  </button>
                                </td>
                                {isSeasonMode ? (
                                  <>
                                    <td>{gl.season}</td>
                                    <td>{gl.class_year || "-"}</td>
                                  </>
                                ) : (
                                  <td className="muted" style={{ fontSize: 12 }}>
                                    {gl.span || (gl.first_season === gl.last_season
                                      ? gl.first_season
                                      : `${gl.first_season}–${String(gl.last_season || "").slice(-2)}`)}
                                  </td>
                                )}
                                <td>{gl.gp ?? gl.goalie_gp}</td>
                                <td><strong>{gl.wins}</strong></td>
                                <td>{gl.losses}</td>
                                <td>{gl.ties}</td>
                                <td><strong>{Number(gl.save_pct || 0).toFixed(3)}</strong></td>
                                <td>{Number(gl.gaa || 0).toFixed(2)}</td>
                                <td>{gl.saves}</td>
                                <td>{gl.ga}</td>
                                <td><strong>{gl.shutouts}</strong></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      </>
                    )}
                  </div>

                  <div className="records-grid-2col">
                    <div className="card">
                      <div className="card-header">
                        <h2>Single-Game Points &amp; Goals Records</h2>
                        <span className="muted">Click any date to open Box Score</span>
                      </div>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Player</th>
                              <th>PTS (G-A)</th>
                              <th>Opponent</th>
                              <th>Date</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(sgr.most_points || []).slice(0, 10).map((r, i) => (
                              <tr key={`pts-${i}`}>
                                <td>
                                  <button type="button" className="link-btn" onClick={() => openPlayer(r.player_name)}>
                                    {r.player_name}
                                  </button>
                                </td>
                                <td><strong>{r.points}</strong> ({r.goals}G, {r.assists}A)</td>
                                <td>
                                  <span className="opp-with-logo">
                                    <OpponentLogo name={r.opponent} />
                                    <span>{r.opponent}</span>
                                  </span>
                                </td>
                                <td>
                                  <button type="button" className="link-btn" onClick={() => openBoxScore(r.date, r.opponent)}>
                                    {r.date}
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header">
                        <h2>Single-Game Goalie Save Records</h2>
                        <span className="muted">Most saves in a single game</span>
                      </div>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Goalie</th>
                              <th>SV (GA)</th>
                              <th>Opponent</th>
                              <th>Date</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(sgr.most_saves || []).slice(0, 10).map((r, i) => {
                              const gName = r.player_name || r.goalie_name;
                              const gaVal = r.ga ?? r.goals_against ?? 0;
                              return (
                                <tr key={`sv-${i}`}>
                                  <td>
                                    <button type="button" className="link-btn" onClick={() => openPlayer(gName)}>
                                      {gName}
                                    </button>
                                  </td>
                                  <td><strong>{r.saves}</strong> ({gaVal} GA)</td>
                                  <td>
                                    <span className="opp-with-logo">
                                      <OpponentLogo name={r.opponent} />
                                      <span>{r.opponent}</span>
                                    </span>
                                  </td>
                                  <td>
                                    <button type="button" className="link-btn" onClick={() => openBoxScore(r.date, r.opponent)}>
                                      {r.date}
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header">
                        <h2>Fastest Goals &amp; Rapid-Fire Braces</h2>
                        <span className="muted">From opening faceoff &amp; fastest 2 goals by one player</span>
                      </div>
                      <h3 className="sub-heading">Fastest Goal From Opening Faceoff</h3>
                      <div className="table-wrap" style={{ marginBottom: 14 }}>
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Player</th>
                              <th>Time (P1)</th>
                              <th>Opponent</th>
                              <th>Date</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(sgr.fastest_opening_goals || []).slice(0, 6).map((r, i) => {
                              const pName = r.player_name || r.scorer;
                              const secs = r.seconds ?? r.time_seconds;
                              return (
                                <tr key={`fo-${i}`}>
                                  <td>
                                    <button type="button" className="link-btn" onClick={() => openPlayer(pName)}>
                                      {pName}
                                    </button>
                                  </td>
                                  <td><strong>{r.time}</strong> ({secs}s)</td>
                                  <td>
                                    <span className="opp-with-logo">
                                      <OpponentLogo name={r.opponent} />
                                      <span>{r.opponent}</span>
                                    </span>
                                  </td>
                                  <td>
                                    <button type="button" className="link-btn" onClick={() => openBoxScore(r.date, r.opponent)}>
                                      {r.date}
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      <h3 className="sub-heading">Fastest 2 Goals by Same Player</h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Player</th>
                              <th>Span</th>
                              <th>Opponent</th>
                              <th>Date</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(sgr.fastest_two_goals || []).slice(0, 6).map((r, i) => (
                              <tr key={`f2-${i}`}>
                                <td>
                                  <button type="button" className="link-btn" onClick={() => openPlayer(r.player_name)}>
                                    {r.player_name}
                                  </button>
                                </td>
                                <td><strong>{r.span_display}</strong></td>
                                <td>
                                  <span className="opp-with-logo">
                                    <OpponentLogo name={r.opponent} />
                                    <span>{r.opponent}</span>
                                  </span>
                                </td>
                                <td>
                                  <button type="button" className="link-btn" onClick={() => openBoxScore(r.date, r.opponent)}>
                                    {r.date}
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header" style={{ flexWrap: "wrap", gap: 10 }}>
                        <div>
                          <h2>Longest Player &amp; Team Streaks</h2>
                          <span className="muted">
                            {streakMode === "season_openers"
                              ? "Consecutive games to open a season (Game 1 onward)"
                              : "Consecutive games (1999–Present)"}
                          </span>
                        </div>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <div className="segmented">
                            <button
                              type="button"
                              className={`segmented-btn ${streakMode === "all_time" ? "active" : ""}`}
                              onClick={() => setStreakMode("all_time")}
                            >
                              All-Time
                            </button>
                            <button
                              type="button"
                              className={`segmented-btn ${streakMode === "season_openers" ? "active" : ""}`}
                              onClick={() => setStreakMode("season_openers")}
                            >
                              Season Openers
                            </button>
                          </div>
                          <div className="segmented">
                            {[
                              ["points", "Points"],
                              ["goals", "Goals"],
                              ["assists", "Assists"],
                              ["team", "Team"],
                            ].map(([k, lbl]) => (
                              <button
                                key={k}
                                type="button"
                                className={`segmented-btn ${streakCat === k ? "active" : ""}`}
                                onClick={() => setStreakCat(k)}
                              >
                                {lbl}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      {streakCat !== "team" ? (() => {
                        const openers = streaks.season_openers || {};
                        const rows =
                          streakMode === "season_openers"
                            ? (openers[streakCat] || [])
                            : streakCat === "goals"
                              ? (streaks.goal_streaks || [])
                              : streakCat === "assists"
                                ? (streaks.assist_streaks || [])
                                : (streaks.point_streaks || []);
                        const catTitle =
                          streakCat === "goals"
                            ? "Goal Streaks"
                            : streakCat === "assists"
                              ? "Assist Streaks"
                              : "Point Streaks";
                        return (
                          <>
                            <h3 className="sub-heading">
                              {streakMode === "season_openers" ? `Season-Opening ${catTitle}` : `Longest Player ${catTitle}`}
                            </h3>
                            <div className="table-wrap">
                              <table className="data-table">
                                <thead>
                                  <tr>
                                    <th>Player</th>
                                    <th>Season</th>
                                    <th>Games</th>
                                    <th>Totals</th>
                                    <th>Span</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {rows.slice(0, 10).map((r, i) => (
                                    <tr key={`${streakMode}-${streakCat}-${i}`}>
                                      <td>
                                        <button type="button" className="link-btn" onClick={() => openPlayer(r.player_name)}>
                                          {r.player_name}
                                        </button>
                                      </td>
                                      <td>{r.season}</td>
                                      <td><strong>{r.length ?? r.streak_games} GP</strong></td>
                                      <td>
                                        {streakCat === "goals" && r.points == null
                                          ? `${r.goals}G`
                                          : streakCat === "assists" && r.points == null
                                            ? `${r.assists}A`
                                            : `${r.goals}G, ${r.assists}A (${r.points} PTS)`}
                                      </td>
                                      <td className="muted" style={{ fontSize: 12 }}>{r.start_date} &rarr; {r.end_date}</td>
                                    </tr>
                                  ))}
                                  {rows.length === 0 && (
                                    <tr>
                                      <td colSpan={5} className="muted">No qualifying streaks found.</td>
                                    </tr>
                                  )}
                                </tbody>
                              </table>
                            </div>
                          </>
                        );
                      })() : (() => {
                        const openers = streaks.season_openers || {};
                        const wRows = streakMode === "season_openers" ? (openers.team_wins || []) : (streaks.team_win_streaks || []);
                        const uRows = streakMode === "season_openers" ? (openers.team_unbeaten || []) : (streaks.team_unbeaten_streaks || []);
                        return (
                          <>
                            <h3 className="sub-heading">
                              {streakMode === "season_openers" ? "Season-Opening Team Win & Unbeaten Streaks" : "Longest Team Win & Unbeaten Streaks"}
                            </h3>
                            <div className="table-wrap">
                              <table className="data-table">
                                <thead>
                                  <tr>
                                    <th>Type</th>
                                    <th>Season</th>
                                    <th>Streak</th>
                                    <th>Record</th>
                                    <th>Span</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {wRows.slice(0, 5).map((r, i) => {
                                    const len = r.length ?? r.streak_games;
                                    return (
                                      <tr key={`tws-${streakMode}-${i}`}>
                                        <td>Win Streak</td>
                                        <td>{r.season}</td>
                                        <td><strong>{len} Wins</strong></td>
                                        <td>{r.record || `${len}-0-0`}</td>
                                        <td className="muted" style={{ fontSize: 12 }}>{r.start_date} &rarr; {r.end_date}</td>
                                      </tr>
                                    );
                                  })}
                                  {uRows.slice(0, 5).map((r, i) => {
                                    const len = r.length ?? r.streak_games;
                                    return (
                                      <tr key={`tus-${streakMode}-${i}`}>
                                        <td>Unbeaten</td>
                                        <td>{r.season}</td>
                                        <td><strong>{len} GP</strong></td>
                                        <td>{r.record}</td>
                                        <td className="muted" style={{ fontSize: 12 }}>{r.start_date} &rarr; {r.end_date}</td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  </div>
                </>
              );
            })()}

            {recordsData && !recordsError && recordsSubTab === "milestones" && (() => {
              const ms = recordsData.milestones || { active_season: "", items: [] };
              const cl = recordsData.clutch_leaders || {};
              return (
                <>
                  <div className="card">
                    <div className="card-header">
                      <div>
                        <h2>Active Roster Milestone Watch ({ms.active_season})</h2>
                        <span className="muted">
                          Current Huskies approaching major career GP, Points, Goals, Assists, Saves, or Wins benchmarks
                        </span>
                      </div>
                    </div>
                    {ms.items?.length > 0 ? (
                      <div className="milestone-grid">
                        {ms.items.map((item, idx) => {
                          const pctVal = item.pct ?? item.progress_pct ?? 0;
                          return (
                            <div key={`${item.player_name}-${item.category}-${idx}`} className="milestone-card">
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
                                <button
                                  type="button"
                                  className="link-btn"
                                  style={{ fontWeight: 700, fontSize: 15 }}
                                  onClick={() => openPlayer(item.player_name)}
                                >
                                  {item.player_name}
                                </button>
                                <span className="muted" style={{ fontSize: 12 }}>
                                  {item.position} {item.class_year ? `• ${item.class_year}` : ""}
                                </span>
                              </div>
                              <div style={{ fontSize: 13, marginTop: 4 }}>
                                Needs <strong>{item.needed}</strong> more for <strong>{item.target} {item.category}</strong>
                              </div>
                              <div className="milestone-progress-track">
                                <div
                                  className="milestone-progress-fill"
                                  style={{ width: `${Math.min(100, pctVal)}%` }}
                                />
                              </div>
                              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }} className="muted">
                                <span>Current: {item.current}</span>
                                <span>Target: {item.target} ({pctVal}%)</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="muted">No active roster milestones currently within threshold.</p>
                    )}
                  </div>

                  {(() => {
                    const activeStreaks = recordsData.streaks?.active || {};
                    const activeSeasonLabel = activeStreaks.season || ms.active_season;
                    const streakCols = [
                      { key: "points", title: "Point Streaks", statLabel: (r) => `${r.goals}G, ${r.assists}A (${r.points} PTS)` },
                      { key: "goals", title: "Goal Streaks", statLabel: (r) => `${r.goals}G (${r.points} PTS)` },
                      { key: "assists", title: "Assist Streaks", statLabel: (r) => `${r.assists}A (${r.points} PTS)` },
                    ];
                    return (
                      <div className="card">
                        <div className="card-header">
                          <div>
                            <h2>Active Game Streaks ({activeSeasonLabel})</h2>
                            <span className="muted">
                              Consecutive games with a point, goal, or assist (2+ GP){activeStreaks.latest_game_date ? ` • Through ${activeStreaks.latest_game_date}` : ""}
                            </span>
                          </div>
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
                          {streakCols.map((col) => {
                            const list = activeStreaks[col.key] || [];
                            return (
                              <div key={col.key}>
                                <h3 className="sub-heading" style={{ marginTop: 0 }}>{col.title}</h3>
                                {list.length > 0 ? (
                                  <div className="table-wrap">
                                    <table className="data-table">
                                      <thead>
                                        <tr>
                                          <th>Player</th>
                                          <th>Streak</th>
                                          <th>Totals</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {list.map((r) => (
                                          <tr key={`${col.key}-${r.player_name}`}>
                                            <td>
                                              <button
                                                type="button"
                                                className="link-btn"
                                                onClick={() => openPlayer(r.player_name)}
                                              >
                                                {r.player_name}
                                              </button>
                                            </td>
                                            <td>
                                              <strong>{r.streak_games} GP</strong>
                                            </td>
                                            <td>
                                              <div>{col.statLabel(r)}</div>
                                              <div className="muted" style={{ fontSize: 11 }}>
                                                {r.start_date} &rarr; {r.end_date}
                                              </div>
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                ) : (
                                  <p className="muted" style={{ fontSize: 13 }}>No active {col.key} streaks (2+ GP).</p>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })()}

                  <div className="records-grid-2col">
                    <div className="card">
                      <div className="card-header">
                        <h2>Career Overtime Goal Leaders</h2>
                        <span className="muted">Sudden-death OT goals (1999&ndash;Present)</span>
                      </div>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>#</th>
                              <th>Player</th>
                              <th>OT Goals</th>
                              <th>OT GWGs</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(cl.ot_goals || []).map((r, i) => (
                              <tr key={r.player_name}>
                                <td>{i + 1}</td>
                                <td>
                                  <button type="button" className="link-btn" onClick={() => openPlayer(r.player_name)}>
                                    {r.player_name}
                                  </button>
                                </td>
                                <td><strong>{r.ot_goals}</strong></td>
                                <td>{r.gwg ?? r.ot_goals}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header">
                        <h2>Late-Game Clutch Goal Leaders</h2>
                        <span className="muted">Tying or go-ahead goals in final 5:00 of P3 or OT</span>
                      </div>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>#</th>
                              <th>Player</th>
                              <th>Clutch Goals</th>
                              <th>GWGs</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(cl.late_clutch_goals || []).map((r, i) => (
                              <tr key={r.player_name}>
                                <td>{i + 1}</td>
                                <td>
                                  <button type="button" className="link-btn" onClick={() => openPlayer(r.player_name)}>
                                    {r.player_name}
                                  </button>
                                </td>
                                <td><strong>{r.late_clutch_goals ?? r.clutch_goals}</strong></td>
                                <td>{r.gwg ?? "-"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header">
                        <h2>3rd-Period Game-Winning Goals</h2>
                        <span className="muted">Career regulation GWGs scored in Period 3</span>
                      </div>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>#</th>
                              <th>Player</th>
                              <th>P3 GWGs</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(cl.third_period_gwg || []).map((r, i) => (
                              <tr key={r.player_name}>
                                <td>{i + 1}</td>
                                <td>
                                  <button type="button" className="link-btn" onClick={() => openPlayer(r.player_name)}>
                                    {r.player_name}
                                  </button>
                                </td>
                                <td><strong>{r.third_period_gwg}</strong></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header">
                        <h2>Shootout Conversion Leaders</h2>
                        <span className="muted">Official Hockey East &amp; tournament shootouts</span>
                      </div>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Player</th>
                              <th>Made / Att</th>
                              <th>SO %</th>
                              <th>SO Winners</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(cl.shootout_leaders || []).map((r) => (
                              <tr key={r.player_name}>
                                <td>
                                  <button type="button" className="link-btn" onClick={() => openPlayer(r.player_name)}>
                                    {r.player_name}
                                  </button>
                                </td>
                                <td><strong>{r.made} / {r.attempts}</strong></td>
                                <td>{r.pct}%</td>
                                <td>{r.winners}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </>
              );
            })()}

            {recordsData && !recordsError && recordsSubTab === "chemistry" && (() => {
              const chem = recordsData.chemistry || { top_duos: [], top_trios: [] };
              return (
                <>
                  <div className="card">
                    <div className="card-header" style={{ flexWrap: "wrap", gap: 12 }}>
                      <div>
                        <h2>Team-Wide Scoring Chemistry &amp; Line Combinations</h2>
                        <span className="muted">
                          Most prolific Goal + Assist duos and Goal + Primary + Secondary Assist trios
                        </span>
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                        <select
                          aria-label="Filter chemistry by season"
                          className="select-input"
                          value={chemSeason}
                          onChange={(e) => setChemSeason(e.target.value)}
                        >
                          <option value="all">All Seasons (1999&ndash;Present)</option>
                          {seasons.map((s) => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                        <div className="segmented" role="group" aria-label="Strength filter">
                          {[
                            { id: "all", label: "All Strengths" },
                            { id: "EV", label: "Even Strength" },
                            { id: "PP", label: "Power Play" },
                            { id: "SH", label: "Short-Handed" },
                          ].map((st) => (
                            <button
                              key={st.id}
                              type="button"
                              className={`segmented-btn ${chemStrength === st.id ? "active" : ""}`}
                              onClick={() => setChemStrength(st.id)}
                            >
                              {st.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="records-grid-2col">
                      <div>
                        <h3 className="sub-heading">Top Scoring Duos (Goal + Assist)</h3>
                        <div className="table-wrap">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>#</th>
                                <th>Duo</th>
                                <th>Total</th>
                                <th>Primary / Sec</th>
                                <th>Directional Split</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(chem.top_duos || []).map((d, i) => (
                                <tr key={`${d.player_a}-${d.player_b}`}>
                                  <td>{i + 1}</td>
                                  <td>
                                    <button type="button" className="link-btn" onClick={() => openPlayer(d.player_a)}>
                                      {d.player_a}
                                    </button>
                                    {" + "}
                                    <button type="button" className="link-btn" onClick={() => openPlayer(d.player_b)}>
                                      {d.player_b}
                                    </button>
                                  </td>
                                  <td><strong>{d.total_connections ?? d.total_goals}</strong></td>
                                  <td>{d.primary_connections} A1 / {d.secondary_connections} A2</td>
                                  <td className="muted" style={{ fontSize: 12 }}>
                                    {d.a_to_b}x ({d.player_a.split(" ").slice(-1)[0]}&rarr;{d.player_b.split(" ").slice(-1)[0]}) &bull;{" "}
                                    {d.b_to_a}x ({d.player_b.split(" ").slice(-1)[0]}&rarr;{d.player_a.split(" ").slice(-1)[0]})
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>

                      <div>
                        <h3 className="sub-heading">Top Scoring Trios (Goal + A1 + A2)</h3>
                        <div className="table-wrap">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>#</th>
                                <th>Trio Combination</th>
                                <th>Goals Together</th>
                                <th>EV / PP</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(chem.top_trios || []).map((t, i) => {
                                const trioPlayers = Array.isArray(t.players)
                                  ? t.players
                                  : [t.player_1, t.player_2, t.player_3].filter(Boolean);
                                return (
                                  <tr key={trioPlayers.join("-") || i}>
                                    <td>{i + 1}</td>
                                    <td>
                                      {trioPlayers.map((pName, pIdx) => (
                                        <React.Fragment key={pName}>
                                          {pIdx > 0 ? " + " : ""}
                                          <button type="button" className="link-btn" onClick={() => openPlayer(pName)}>
                                            {pName}
                                          </button>
                                        </React.Fragment>
                                      ))}
                                    </td>
                                    <td><strong>{t.total_goals_together ?? t.total_goals}</strong></td>
                                    <td className="muted" style={{ fontSize: 12 }}>
                                      {t.ev_goals ?? 0} EV / {t.pp_goals ?? 0} PP
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              );
            })()}

            {recordsData && !recordsError && recordsSubTab === "onthisday" && (() => {
              const otd = recordsData.on_this_day || {};
              return (
                <div className="card">
                  <div className="card-header" style={{ flexWrap: "wrap", gap: 12 }}>
                    <div>
                      <h2>
                        On This Day in DogHouse History ({otd.resolved_mmdd || "Today"})
                      </h2>
                      <span className="muted">
                        All-Time Record on {otd.resolved_mmdd}: <strong>{otd.record || "0-0-0"}</strong> ({otd.games_count || 0} Games)
                        {otd.requested_mmdd && otd.resolved_mmdd && otd.requested_mmdd !== otd.resolved_mmdd
                          ? ` • No games on ${otd.requested_mmdd}, showing closest date`
                          : ""}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, position: "relative" }}>
                      {(() => {
                        const activeMmdd = otdMmdd || otd.resolved_mmdd || "01-01";
                        const activeM = Number(activeMmdd.slice(0, 2)) || 1;
                        const activeD = Number(activeMmdd.slice(3, 5)) || 1;
                        const monthNames = [
                          "January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December",
                        ];
                        const monthShort = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
                        const daysInMonth = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
                        const viewM = otdPickerMonth || activeM;
                        const availSet = new Set(otd.available_dates || []);
                        const mmStr = String(viewM).padStart(2, "0");
                        const totalDays = daysInMonth[viewM - 1] || 31;
                        return (
                          <>
                            <span className="field-label">Pick Date:</span>
                            <button
                              id="otd-select"
                              type="button"
                              className="select-input"
                              style={{ display: "inline-flex", alignItems: "center", gap: 8, cursor: "pointer", minWidth: 118, justifyContent: "space-between" }}
                              onClick={() => {
                                setOtdPickerMonth(activeM);
                                setOtdPickerOpen((prev) => !prev);
                              }}
                              aria-expanded={otdPickerOpen}
                            >
                              <span>{`${monthShort[activeM - 1]} ${activeD}`}</span>
                              <span aria-hidden="true">📅</span>
                            </button>
                            {otdMmdd && (
                              <button
                                type="button"
                                className="btn-ghost"
                                style={{ padding: "6px 10px", fontSize: 12 }}
                                onClick={() => {
                                  setOtdMmdd("");
                                  setOtdPickerOpen(false);
                                }}
                              >
                                Today
                              </button>
                            )}
                            {otdPickerOpen && (
                              <>
                                <div
                                  style={{ position: "fixed", inset: 0, zIndex: 40 }}
                                  onClick={() => setOtdPickerOpen(false)}
                                />
                                <div
                                  className="card"
                                  style={{
                                    position: "absolute",
                                    top: "calc(100% + 6px)",
                                    right: 0,
                                    zIndex: 50,
                                    width: 268,
                                    padding: 12,
                                    boxShadow: "0 12px 32px rgba(0,0,0,0.28)",
                                  }}
                                >
                                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, marginBottom: 10 }}>
                                    <button
                                      type="button"
                                      className="btn-ghost"
                                      style={{ padding: "4px 8px", fontSize: 13 }}
                                      onClick={() => setOtdPickerMonth(viewM === 1 ? 12 : viewM - 1)}
                                      aria-label="Previous month"
                                    >
                                      &lsaquo;
                                    </button>
                                    <select
                                      className="select-input"
                                      style={{ padding: "4px 8px", fontSize: 13, flex: 1 }}
                                      value={viewM}
                                      onChange={(e) => setOtdPickerMonth(Number(e.target.value))}
                                      aria-label="Select month"
                                    >
                                      {monthNames.map((mName, idx) => (
                                        <option key={mName} value={idx + 1}>{mName}</option>
                                      ))}
                                    </select>
                                    <button
                                      type="button"
                                      className="btn-ghost"
                                      style={{ padding: "4px 8px", fontSize: 13 }}
                                      onClick={() => setOtdPickerMonth(viewM === 12 ? 1 : viewM + 1)}
                                      aria-label="Next month"
                                    >
                                      &rsaquo;
                                    </button>
                                  </div>
                                  <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
                                    {Array.from({ length: totalDays }, (_, i) => i + 1).map((dayNum) => {
                                      const ddStr = String(dayNum).padStart(2, "0");
                                      const key = `${mmStr}-${ddStr}`;
                                      const isSelected = key === activeMmdd;
                                      const hasGames = availSet.has(key);
                                      return (
                                        <button
                                          key={key}
                                          type="button"
                                          onClick={() => {
                                            setOtdMmdd(key);
                                            setOtdPickerOpen(false);
                                          }}
                                          title={hasGames ? `${monthShort[viewM - 1]} ${dayNum} (has games)` : `${monthShort[viewM - 1]} ${dayNum} (no games)`}
                                          style={{
                                            padding: "6px 0",
                                            borderRadius: 6,
                                            border: isSelected ? "1px solid var(--nu-red)" : "1px solid transparent",
                                            background: isSelected ? "var(--nu-red)" : "transparent",
                                            color: isSelected ? "#fff" : "inherit",
                                            fontWeight: hasGames ? 700 : 400,
                                            opacity: isSelected || hasGames ? 1 : 0.4,
                                            cursor: "pointer",
                                            fontSize: 12,
                                          }}
                                        >
                                          {dayNum}
                                        </button>
                                      );
                                    })}
                                  </div>
                                  <div className="muted" style={{ fontSize: 11, marginTop: 8, textAlign: "center" }}>
                                    Bold dates have historical games
                                  </div>
                                </div>
                              </>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  </div>

                  {otd.highlights?.length > 0 && (
                    <div style={{ marginBottom: 16 }}>
                      <h3 className="sub-heading">Memorable Moments on {otd.resolved_mmdd}</h3>
                      <div className="milestone-grid">
                        {otd.highlights.map((h, i) => (
                          <div key={i} className="milestone-card" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", gap: 8 }}>
                            <div style={{ fontSize: 13 }}>
                              <span style={{ color: "var(--nu-red)", fontWeight: 700, marginRight: 6 }}>
                                [{h.type}]
                              </span>
                              {h.text || h.headline} ({h.date})
                            </div>
                            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                              {h.player_name && (
                                <button type="button" className="link-btn" style={{ fontSize: 12 }} onClick={() => openPlayer(h.player_name)}>
                                  Player Profile &rarr;
                                </button>
                              )}
                              <button type="button" className="link-btn" style={{ fontSize: 12 }} onClick={() => openBoxScore(h.date, h.opponent)}>
                                View Box Score &rarr;
                              </button>
                              {(h.video_id || h.video_url) && (
                                <button
                                  type="button"
                                  className="link-btn"
                                  style={{ fontSize: 12 }}
                                  onClick={() => setBeanpotClipModal(h)}
                                  title={h.clip_start != null ? "Watch highlight clip" : (h.video_title || "Watch game highlights")}
                                >
                                  {h.clip_start != null ? "▶ Clip" : "▶ Highlights"}
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Season</th>
                          <th>Opponent</th>
                          <th>Venue</th>
                          <th>Tournament / Type</th>
                          <th>Result</th>
                          <th>Score</th>
                          <th>Box Score</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(otd.games || []).map((g) => (
                          <tr key={`${g.date}-${g.opponent}`}>
                            <td><strong>{g.date}</strong></td>
                            <td>{g.season}</td>
                            <td>
                              <span className="opp-with-logo">
                                <OpponentLogo name={g.opponent} />
                                <span>{g.opponent}</span>
                              </span>
                            </td>
                            <td>
                              {g.venue
                                ? `${g.venue}${g.location ? ` (${g.location})` : ""}`
                                : g.location || "—"}
                            </td>
                            <td>{g.beanpot_round ? `${g.game_type} (${g.beanpot_round})` : g.game_type}</td>
                            <td>
                              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                                <OutcomeBadge outcome={g.outcome} />
                                {g.beanpot_note && (
                                  <span
                                    className="pill"
                                    title={g.beanpot_note}
                                    style={{ cursor: "help", fontSize: 11 }}
                                  >
                                    ⓘ {g.beanpot_badge || "NCAA Tie"}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td>
                              <strong>{`${g.nu_goals}-${g.opp_goals}`}</strong>
                              {g.overtime_status && g.overtime_status !== "REG" ? ` (${g.overtime_status})` : ""}
                            </td>
                            <td>
                              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                <button
                                  type="button"
                                  className="link-btn"
                                  onClick={() => openBoxScore(g.date, g.opponent)}
                                >
                                  Box Score
                                </button>
                                {(g.video_id || g.video_url) && (
                                  <button
                                    type="button"
                                    className="link-btn"
                                    onClick={() =>
                                      setBeanpotClipModal({
                                        type: "Beanpot",
                                        date: g.date,
                                        headline:
                                          g.video_title ||
                                          `${g.opponent} • ${g.outcome} ${g.nu_goals}-${g.opp_goals}`,
                                        video_id: g.video_id,
                                        video_url: g.video_url,
                                      })
                                    }
                                    title={g.video_title || "Watch game highlights"}
                                  >
                                    ▶ Highlights
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })()}
          </section>
        )}

        {tab === "beanpot" && (
          <section className="card" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div className="card-header">
              <div>
                <h2 style={{ margin: 0 }}>The Beanpot — Northeastern Huskies Hub</h2>
                <p className="muted" style={{ margin: "4px 0 0" }}>
                  Boston&apos;s annual tournament at TD Garden &bull; 9 All-Time Championships (1980, 1984, 1985, 1988, 2018, 2019, 2020, 2023, 2024)
                </p>
              </div>
              <div className="segmented" role="tablist" aria-label="Beanpot sections">
                {[
                  ["overview", "Overview & Titles"],
                  ["history", "Tournament History"],
                  ["leaders", "Beanpot Leaders"],
                  ["moments", "Iconic Moments"],
                ].map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={beanpotSubTab === key}
                    className={`segmented-btn ${beanpotSubTab === key ? "active" : ""}`}
                    onClick={() => setBeanpotSubTab(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {beanpotError ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 10 }}>
                <p className="error-text" role="alert" style={{ margin: 0 }}>
                  Could not load Beanpot data: {beanpotError}
                </p>
                <button type="button" className="btn-ghost" onClick={fetchBeanpotData}>
                  Retry
                </button>
              </div>
            ) : beanpotLoading || !beanpotData ? (
              <p className="muted">Loading Beanpot history and statistics...</p>
            ) : (
              <>
                <div className="stat-grid">
                  <div className="stat-box">
                    <div className="val">9</div>
                    <div className="lbl">All-Time Titles (5 since 2018)</div>
                  </div>
                  <div className="stat-box">
                    <div className="val">{beanpotData.summary?.record || "—"}</div>
                    <div className="lbl">Record (2000–2026)</div>
                  </div>
                  <div className="stat-box">
                    <div className="val">{beanpotData.summary?.finals_appearances ?? 0}</div>
                    <div className="lbl">Finals Since 2000 ({beanpotData.summary?.championships ?? 0} Won)</div>
                  </div>
                  <div className="stat-box">
                    <div className="val">
                      {beanpotData.summary ? `${beanpotData.summary.goals_for}-${beanpotData.summary.goals_against}` : "—"}
                    </div>
                    <div className="lbl">Goals (NU–Opp, 2000–2026)</div>
                  </div>
                </div>

                {beanpotSubTab === "overview" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                    <div>
                      <h3>Northeastern vs. Beanpot Rivals (2000–2026 Box-Score Era)</h3>
                      <p className="muted" style={{ marginTop: 0 }}>
                        Semifinal record: <strong>{beanpotData.summary?.semifinal_record}</strong> &bull;
                        Championship games: <strong>{beanpotData.summary?.championship_record}</strong> &bull;
                        Consolation games: <strong>{beanpotData.summary?.consolation_record}</strong>
                      </p>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Opponent</th>
                              <th>GP</th>
                              <th>W-L-T</th>
                              <th>GF-GA</th>
                              <th>OT Games</th>
                              <th>SO Games</th>
                              <th>Finals Met</th>
                              <th>Titles Won vs.</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(beanpotData.rivals || []).map((rv) => (
                              <tr key={rv.opponent}>
                                <td>
                                  <span className="opp-with-logo">
                                    <OpponentLogo name={rv.opponent} />
                                    <strong>{rv.opponent}</strong>
                                  </span>
                                </td>
                                <td>{rv.gp}</td>
                                <td><strong>{`${rv.wins}-${rv.losses}-${rv.ties}`}</strong></td>
                                <td>{`${rv.gf}-${rv.ga}`}</td>
                                <td>{rv.ot_games}</td>
                                <td>{rv.so_games}</td>
                                <td>{rv.finals_vs}</td>
                                <td><strong>{rv.titles_won_vs}</strong></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div>
                      <h3>All 9 Northeastern Beanpot Championships (1952–Present)</h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Year</th>
                              <th>Final Opponent</th>
                              <th>Score</th>
                              <th>Beanpot MVP</th>
                              <th>Eberly Award</th>
                              <th>Highlight</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(beanpotData.nu_championships || []).map((c) => (
                              <tr key={c.year}>
                                <td><strong>{c.year}</strong></td>
                                <td>
                                  <span className="opp-with-logo">
                                    <OpponentLogo name={c.opponent} />
                                    <span>{c.opponent}</span>
                                  </span>
                                </td>
                                <td><strong>{c.score}</strong></td>
                                <td>{c.mvp}</td>
                                <td>{c.eberly}</td>
                                <td className="muted">{c.note}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div>
                      <h3>All-Time Men&apos;s Beanpot Titles by School (1952–2026)</h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>School</th>
                              <th>Titles</th>
                              <th>Finals Appearances</th>
                              <th>Last Championship</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(beanpotData.all_time_titles || []).map((s) => (
                              <tr key={s.school}>
                                <td>
                                  <strong>{s.school}</strong>
                                </td>
                                <td><strong>{s.titles}</strong></td>
                                <td>{s.finals}</td>
                                <td>{s.last_title}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}

                {beanpotSubTab === "history" && (() => {
                  const boxTournaments = beanpotData.tournaments || [];
                  const allTimeTournaments = beanpotData.all_time_tournaments || boxTournaments;
                  const filtered =
                    beanpotHistoryFilter === "all_time"
                      ? allTimeTournaments
                      : beanpotHistoryFilter === "titles"
                        ? allTimeTournaments.filter((t) => t.finish === "Champion")
                        : beanpotHistoryFilter === "finals"
                          ? allTimeTournaments.filter((t) => t.finish === "Champion" || t.finish === "Runner-Up")
                          : boxTournaments;
                  const renderGameCell = (g, labelPrefix) => {
                    if (!g) return <span className="muted">—</span>;
                    const soDetail =
                      g.overtime_status === "SO" && g.shootout_winner && g.shootout_winner !== "None"
                        ? `SO • ${g.shootout_winner === "Northeastern" ? "NU" : g.shootout_winner} Won`
                        : g.overtime_status;
                    const otLabel = g.overtime_status && g.overtime_status !== "REG" ? ` (${soDetail})` : "";
                    return (
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                        <span className="opp-with-logo">
                          <OpponentLogo name={g.opponent} />
                          <span>
                            {labelPrefix ? <strong>{labelPrefix}: </strong> : ""}
                            {g.opponent} &bull; <OutcomeBadge outcome={g.outcome} /> <strong>{`${g.nu_goals}-${g.opp_goals}`}</strong>{otLabel}
                          </span>
                        </span>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                          {g.has_boxscore !== false && (
                            <button
                              type="button"
                              className="link-btn"
                              onClick={() => openBoxScore(g.date, g.opponent)}
                            >
                              Box
                            </button>
                          )}
                          {(g.video_id || g.video_url) && (
                            <button
                              type="button"
                              className="link-btn"
                              onClick={() =>
                                setBeanpotClipModal({
                                  type: labelPrefix || "Semifinal",
                                  date: g.date,
                                  headline:
                                    g.video_title ||
                                    `${g.opponent} • ${g.outcome} ${g.nu_goals}-${g.opp_goals}${otLabel}`,
                                  video_id: g.video_id,
                                  video_url: g.video_url,
                                })
                              }
                              title={g.video_title || "Watch game highlights"}
                            >
                              ▶ Highlights
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  };
                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                      <div className="card-header">
                        <div className="segmented">
                          {[
                            ["all", `Box-Score Era (${boxTournaments.length})`],
                            ["all_time", `All-Time 1952–2026 (${allTimeTournaments.length})`],
                            ["titles", "Championships"],
                            ["finals", "Finals Appearances"],
                          ].map(([k, lbl]) => (
                            <button
                              key={k}
                              type="button"
                              className={`segmented-btn ${beanpotHistoryFilter === k ? "active" : ""}`}
                              onClick={() => setBeanpotHistoryFilter(k)}
                            >
                              {lbl}
                            </button>
                          ))}
                        </div>
                        <span className="muted" style={{ fontSize: 12 }}>
                          Note: No tournament in 1953; 2021 cancelled (COVID-19). Box scores available 2000–2026.
                        </span>
                      </div>

                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Year</th>
                              <th>Semifinal (Round 1)</th>
                              <th>Round 2 (Final / Consolation)</th>
                              <th>Finish</th>
                              <th>Awards / Champion</th>
                            </tr>
                          </thead>
                          <tbody>
                            {filtered.map((t) => (
                              <tr key={t.year}>
                                <td>
                                  <strong>{t.year}</strong>
                                  {t.edition ? <span className="muted" style={{ fontSize: 11, marginLeft: 5 }}>({t.edition})</span> : null}
                                </td>
                                <td>{renderGameCell(t.semifinal, "")}</td>
                                <td>{renderGameCell(t.round2, t.round2_label)}</td>
                                <td>
                                  <span
                                    className={t.finish === "Champion" ? "champion-text" : undefined}
                                    style={t.finish === "Champion" ? undefined : { fontWeight: 700 }}
                                  >
                                    {t.finish === "Champion" ? "🏆 Champion" : t.finish}
                                  </span>
                                </td>
                                <td className="muted" style={{ fontSize: 12 }}>
                                  {[
                                    t.champion && t.finish !== "Champion" ? `Champion: ${t.champion}` : "",
                                    t.mvp ? `MVP: ${t.mvp}` : "",
                                    t.eberly ? `Eberly: ${t.eberly}` : "",
                                    t.note && !t.mvp ? t.note : "",
                                  ]
                                    .filter(Boolean)
                                    .join(" • ")}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })()}

                {beanpotSubTab === "leaders" && (() => {
                  const toggleBpSkaterSort = (key) => {
                    setBeanpotSkaterSort((prev) =>
                      prev.key === key ? { key, dir: prev.dir === "desc" ? "asc" : "desc" } : { key, dir: "desc" }
                    );
                  };
                  const toggleBpGoalieSort = (key) => {
                    setBeanpotGoalieSort((prev) =>
                      prev.key === key
                        ? { key, dir: prev.dir === "desc" ? "asc" : "desc" }
                        : { key, dir: key === "gaa" ? "asc" : "desc" }
                    );
                  };
                  const sortRows = (rows, sortSpec) => {
                    const list = [...(rows || [])];
                    const { key, dir } = sortSpec;
                    list.sort((a, b) => {
                      if (key === "player_name" || key === "goalie_name" || key === "span") {
                        const av = String(a[key] || "");
                        const bv = String(b[key] || "");
                        return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
                      }
                      const av = Number(a[key] ?? 0);
                      const bv = Number(b[key] ?? 0);
                      return dir === "desc" ? bv - av : av - bv;
                    });
                    return list;
                  };
                  const bpSkaters = sortRows(beanpotData.skater_leaders, beanpotSkaterSort);
                  const bpGoalies = sortRows(beanpotData.goalie_leaders, beanpotGoalieSort);

                  const skTh = (key, label) => {
                    const active = beanpotSkaterSort.key === key;
                    return (
                      <th
                        key={key}
                        scope="col"
                        className={`sortable ${active ? "sorted" : ""}`}
                        aria-sort={active ? (beanpotSkaterSort.dir === "desc" ? "descending" : "ascending") : "none"}
                        onClick={() => toggleBpSkaterSort(key)}
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggleBpSkaterSort(key);
                          }
                        }}
                      >
                        {label} {active ? (beanpotSkaterSort.dir === "desc" ? "↓" : "↑") : ""}
                      </th>
                    );
                  };
                  const glTh = (key, label) => {
                    const active = beanpotGoalieSort.key === key;
                    return (
                      <th
                        key={key}
                        scope="col"
                        className={`sortable ${active ? "sorted" : ""}`}
                        aria-sort={active ? (beanpotGoalieSort.dir === "desc" ? "descending" : "ascending") : "none"}
                        onClick={() => toggleBpGoalieSort(key)}
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggleBpGoalieSort(key);
                          }
                        }}
                      >
                        {label} {active ? (beanpotGoalieSort.dir === "desc" ? "↓" : "↑") : ""}
                      </th>
                    );
                  };

                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
                      <div>
                        <h3>Beanpot Career Skater Leaders (2000–2026)</h3>
                        <div className="table-wrap">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>#</th>
                                {skTh("player_name", "Player")}
                                {skTh("span", "Years")}
                                {skTh("gp", "GP")}
                                {skTh("goals", "G")}
                                {skTh("assists", "A")}
                                {skTh("points", "PTS")}
                                {skTh("pts_per_gp", "P/GP")}
                                {skTh("ppg", "PPG")}
                                {skTh("gwg", "GWG")}
                                {skTh("plus_minus", "+/-")}
                                {skTh("pim", "PIM")}
                              </tr>
                            </thead>
                            <tbody>
                              {bpSkaters.map((r, idx) => (
                                <tr key={r.player_name}>
                                  <td>{idx + 1}</td>
                                  <td>
                                    <button
                                      type="button"
                                      className="link-btn"
                                      onClick={() => openPlayer(r.player_name)}
                                    >
                                      {r.player_name}
                                    </button>
                                  </td>
                                  <td>{r.span}</td>
                                  <td>{r.gp}</td>
                                  <td>{r.goals}</td>
                                  <td>{r.assists}</td>
                                  <td><strong>{r.points}</strong></td>
                                  <td>{Number(r.pts_per_gp ?? 0).toFixed(2)}</td>
                                  <td>{r.ppg}</td>
                                  <td>{r.gwg}</td>
                                  <td>{r.plus_minus > 0 ? `+${r.plus_minus}` : r.plus_minus}</td>
                                  <td>{r.pim}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>

                      <div>
                        <h3>Beanpot Career Goalie Leaders (2000–2026)</h3>
                        <div className="table-wrap">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>#</th>
                                {glTh("goalie_name", "Goalie")}
                                {glTh("span", "Years")}
                                {glTh("gp", "GP")}
                                {glTh("wins", "W")}
                                {glTh("losses", "L")}
                                {glTh("ties", "T")}
                                {glTh("saves", "SV")}
                                {glTh("ga", "GA")}
                                {glTh("save_pct", "SV%")}
                                {glTh("gaa", "GAA")}
                                {glTh("shutouts", "SO")}
                              </tr>
                            </thead>
                            <tbody>
                              {bpGoalies.map((r, idx) => (
                                <tr key={r.goalie_name}>
                                  <td>{idx + 1}</td>
                                  <td>
                                    <button
                                      type="button"
                                      className="link-btn"
                                      onClick={() => openPlayer(r.goalie_name)}
                                    >
                                      {r.goalie_name}
                                    </button>
                                  </td>
                                  <td>{r.span}</td>
                                  <td>{r.gp}</td>
                                  <td><strong>{r.wins}</strong></td>
                                  <td>{r.losses}</td>
                                  <td>{r.ties}</td>
                                  <td>{r.saves}</td>
                                  <td>{r.ga}</td>
                                  <td><strong>{Number(r.save_pct ?? 0).toFixed(3)}</strong></td>
                                  <td>{Number(r.gaa ?? 0).toFixed(2)}</td>
                                  <td>{r.shutouts}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  );
                })()}

                {beanpotSubTab === "moments" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <h3 style={{ margin: 0 }}>Iconic Beanpot Performances &amp; Moments (2000–2026)</h3>
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th>Type</th>
                            <th>Moment</th>
                            <th>Box Score</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(beanpotData.moments || []).map((m, i) => (
                            <tr key={`${m.date}-${m.player_name}-${m.type}-${i}`}>
                              <td><strong>{m.date}</strong></td>
                              <td><span className="pill">{m.type}</span></td>
                              <td>{m.headline}</td>
                              <td>
                                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                  <button
                                    type="button"
                                    className="link-btn"
                                    onClick={() => openBoxScore(m.date, m.opponent)}
                                  >
                                    View
                                  </button>
                                  {(m.video_id || m.video_url) && (
                                    <button
                                      type="button"
                                      className="link-btn"
                                      onClick={() => setBeanpotClipModal(m)}
                                      title={m.clip_start != null ? "Watch highlight clip" : (m.video_title || "Watch game highlights")}
                                    >
                                      {m.clip_start != null ? "▶ Clip" : "▶ Highlights"}
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
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

      <LegalModal type={legalModal} onClose={closeLegalModal} />
      <BugReportModal
        open={bugModalOpen}
        onClose={closeBugModal}
        apiBase={API_BASE}
        pageContext={
          selectedPlayer
            ? `Player: ${selectedPlayer} (${playerScope})`
            : tab === "leaders"
              ? `Stats (${statsView}) • Season: ${selectedSeason || "latest"} • Scope: ${leaderScope}${leaderOpponent ? ` • vs ${leaderOpponent}` : ""}`
              : tab === "records"
                ? `Records (${recordsSubTab})`
                : tab === "beanpot"
                  ? `Beanpot (${beanpotSubTab})`
                  : tab === "compare"
                    ? `Compare (${compareAName || "—"} vs ${compareBName || "—"})`
                    : tab === "roster"
                      ? `Roster • Season: ${selectedSeason || "latest"} • View: ${rosterView}`
                    : tab === "rivalry"
                      ? `Opponents • ${selectedRival} • ${rivalryScope === "season" ? seasons[0] || "This Season" : "All-Time"}`
                      : "Ask Paws Chat"
        }
      />

      {beanpotClipModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) setBeanpotClipModal(null);
          }}
        >
          <div
            className="modal-card"
            style={{ maxWidth: 820, width: "94vw" }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="beanpot-clip-modal-title"
          >
            <div className="modal-header">
              <div style={{ minWidth: 0 }}>
                <h2 id="beanpot-clip-modal-title" style={{ margin: 0, fontSize: 18 }}>
                  {beanpotClipModal.type} &bull; {beanpotClipModal.date}
                </h2>
                <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
                  {beanpotClipModal.headline}
                </p>
              </div>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setBeanpotClipModal(null)}
                aria-label="Close video clip"
              >
                ✕
              </button>
            </div>
            {beanpotClipModal.video_id && (
              <div style={{ position: "relative", paddingBottom: "56.25%", height: 0, overflow: "hidden", borderRadius: 10, background: "#000", marginTop: 12 }}>
                <iframe
                  title={beanpotClipModal.headline}
                  src={`https://www.youtube.com/embed/${beanpotClipModal.video_id}?${[
                    beanpotClipModal.clip_start != null ? `start=${beanpotClipModal.clip_start}` : "",
                    beanpotClipModal.clip_end != null ? `end=${beanpotClipModal.clip_end}` : "",
                    "autoplay=1",
                    "rel=0",
                  ].filter(Boolean).join("&")}`}
                  style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", border: 0 }}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              </div>
            )}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12, gap: 12, flexWrap: "wrap" }}>
              <span className="muted" style={{ fontSize: 12 }}>
                If playback is unavailable in the embed, open directly on YouTube.
              </span>
              {beanpotClipModal.video_url && (
                <a
                  href={beanpotClipModal.video_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-ghost"
                  style={{ textDecoration: "none" }}
                >
                  Watch on YouTube ↗
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      {boxscoreModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeBoxScore();
          }}
        >
          <div
            ref={boxscoreModalRef}
            className="modal-card boxscore-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="boxscore-modal-title"
          >
            <div className="modal-header">
              <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                <OpponentLogo
                  name={boxscoreData?.game?.opponent || boxscoreModal.opponent}
                  large
                />
                <div style={{ minWidth: 0 }}>
                  <h2 id="boxscore-modal-title" style={{ margin: 0, fontSize: 18 }}>
                    Northeastern vs. {boxscoreData?.game?.opponent || boxscoreModal.opponent}
                  </h2>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {boxscoreModal.date}
                    {boxscoreData?.game?.season ? ` • ${boxscoreData.game.season}` : ""}
                    {boxscoreData?.game?.venue ? ` • ${boxscoreData.game.venue}` : ""}
                    {boxscoreData?.game?.location ? ` • ${boxscoreData.game.location}` : ""}
                  </div>
                </div>
              </div>
              <button
                ref={boxscoreCloseRef}
                type="button"
                className="chat-drawer-btn"
                onClick={closeBoxScore}
                aria-label="Close Box Score"
              >
                Close
              </button>
            </div>
            <div className="modal-body">
              {boxscoreLoading && <p className="muted">Loading box score...</p>}
              {boxscoreError && <p className="error-text">{boxscoreError}</p>}
              {!boxscoreLoading && !boxscoreError && boxscoreData && (
                <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                  <div className="boxscore-banner">
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <OutcomeBadge outcome={boxscoreData.game?.outcome} />
                      <strong style={{ fontSize: 18 }}>
                        NU {boxscoreData.game?.nu_goals ?? "-"} – {boxscoreData.game?.opp_goals ?? "-"}{" "}
                        {boxscoreData.game?.opponent}
                      </strong>
                      {boxscoreData.game?.overtime_status && (
                        <span className="muted" style={{ fontSize: 13 }}>
                          ({boxscoreData.game.overtime_status})
                        </span>
                      )}
                    </div>
                    {safeExternalUrl(boxscoreData.game?.boxscore_url) && (
                      <a
                        href={safeExternalUrl(boxscoreData.game.boxscore_url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: 13 }}
                      >
                        Official Box Score ↗
                      </a>
                    )}
                  </div>

                  <div>
                    <h3 className="sub-heading">Scoring Summary</h3>
                    {boxscoreData.goals?.length ? (
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Per</th>
                              <th>Time</th>
                              <th>Team</th>
                              <th>Scorer</th>
                              <th>Assists</th>
                              <th>Type</th>
                            </tr>
                          </thead>
                          <tbody>
                            {boxscoreData.goals.map((gl, idx) => {
                              const isNU = gl.team === "Northeastern";
                              const assists = [gl.primary_assist, gl.secondary_assist].filter(Boolean);
                              return (
                                <tr key={`${gl.period}-${gl.time}-${idx}`}>
                                  <td>{gl.period}</td>
                                  <td>{gl.time}</td>
                                  <td>{gl.team}</td>
                                  <td>
                                    {isNU && gl.scorer ? (
                                      <button
                                        type="button"
                                        className="link-btn"
                                        onClick={() => {
                                          closeBoxScore();
                                          openPlayer(gl.scorer);
                                        }}
                                      >
                                        {gl.scorer}
                                      </button>
                                    ) : (
                                      gl.scorer || "-"
                                    )}
                                  </td>
                                  <td>
                                    {assists.length === 0
                                      ? "Unassisted"
                                      : assists.map((a, aIdx) => (
                                          <React.Fragment key={`${a}-${aIdx}`}>
                                            {aIdx > 0 ? ", " : ""}
                                            {isNU ? (
                                              <button
                                                type="button"
                                                className="link-btn"
                                                onClick={() => {
                                                  closeBoxScore();
                                                  openPlayer(a);
                                                }}
                                              >
                                                {a}
                                              </button>
                                            ) : (
                                              a
                                            )}
                                          </React.Fragment>
                                        ))}
                                  </td>
                                  <td>
                                    {[gl.strength, gl.is_gwg ? "GWG" : ""].filter(Boolean).join(" • ") || "EV"}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                        No goals recorded in this game.
                      </p>
                    )}
                  </div>

                  {boxscoreData.shootouts?.length > 0 && (
                    <div>
                      <h3 className="sub-heading">Shootout</h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Rd</th>
                              <th>Team</th>
                              <th>Shooter</th>
                              <th>Result</th>
                            </tr>
                          </thead>
                          <tbody>
                            {boxscoreData.shootouts.map((so, idx) => {
                              const isNU = so.shooter_team === "Northeastern";
                              const shooter = (so.shooter_name || "").trim();
                              const canLink = isNU && shooter && !["team", "tm"].includes(shooter.toLowerCase());
                              return (
                                <tr key={`so-${idx}`}>
                                  <td>{so.round}</td>
                                  <td>{so.shooter_team}</td>
                                  <td>
                                    {canLink ? (
                                      <button
                                        type="button"
                                        className="link-btn"
                                        onClick={() => {
                                          closeBoxScore();
                                          openPlayer(shooter);
                                        }}
                                      >
                                        {shooter}
                                      </button>
                                    ) : (
                                      shooter || "-"
                                    )}
                                  </td>
                                  <td>{so.result || "-"}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {boxscoreData.skaters?.length > 0 && (
                    <div>
                      <h3 className="sub-heading">Northeastern Skaters</h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Player</th>
                              <th>G</th>
                              <th>A</th>
                              <th>PTS</th>
                              <th>SOG</th>
                              <th>+/-</th>
                              <th>BLK</th>
                              <th>PIM</th>
                              <th>FO</th>
                            </tr>
                          </thead>
                          <tbody>
                            {boxscoreData.skaters.map((sk) => {
                              const foW = Number(sk.faceoffs_won || 0);
                              const foL = Number(sk.faceoffs_lost || 0);
                              const foTotal = foW + foL;
                              return (
                                <tr key={sk.player_name}>
                                  <td>
                                    <button
                                      type="button"
                                      className="link-btn"
                                      onClick={() => {
                                        closeBoxScore();
                                        openPlayer(sk.player_name);
                                      }}
                                    >
                                      {sk.player_name}
                                    </button>
                                  </td>
                                  <td>{sk.goals}</td>
                                  <td>{sk.assists}</td>
                                  <td><strong>{sk.points}</strong></td>
                                  <td>{sk.shots}</td>
                                  <td>{sk.plus_minus > 0 ? `+${sk.plus_minus}` : sk.plus_minus}</td>
                                  <td>
                                    {hasModernTracking(boxscoreData.game?.season)
                                      ? sk.blocked_shots
                                      : <span className="muted">N/A</span>}
                                  </td>
                                  <td>{sk.penalty_minutes}</td>
                                  <td>
                                    {foTotal > 0 ? `${foW}-${foTotal}` : <span className="muted">-</span>}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {boxscoreData.goalies?.length > 0 && (
                    <div>
                      <h3 className="sub-heading">Northeastern Goalies</h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Goalie</th>
                              <th>DEC</th>
                              <th>MIN</th>
                              <th>SV</th>
                              <th>GA</th>
                              <th>SV%</th>
                            </tr>
                          </thead>
                          <tbody>
                            {boxscoreData.goalies.map((gl) => (
                              <tr key={gl.goalie_name}>
                                <td>
                                  <button
                                    type="button"
                                    className="link-btn"
                                    onClick={() => {
                                      closeBoxScore();
                                      openPlayer(gl.goalie_name);
                                    }}
                                  >
                                    {gl.goalie_name}
                                  </button>
                                </td>
                                <td>{gl.decision || "-"}</td>
                                <td>{gl.minutes || "-"}</td>
                                <td>{gl.saves}</td>
                                <td>{gl.goals_against}</td>
                                <td>{Number(gl.save_pct || 0).toFixed(3)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {boxscoreData.penalties?.length > 0 && (
                    <div>
                      <h3 className="sub-heading">Penalties</h3>
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Per</th>
                              <th>Time</th>
                              <th>Team</th>
                              <th>Player</th>
                              <th>Infraction</th>
                              <th>PIM</th>
                            </tr>
                          </thead>
                          <tbody>
                            {boxscoreData.penalties.map((p, idx) => {
                              const isNU = p.team === "Northeastern";
                              const penPlayer = (p.player_name || "").trim();
                              const canLink = isNU && penPlayer && !["team", "tm"].includes(penPlayer.toLowerCase());
                              return (
                                <tr key={`pen-${idx}`}>
                                  <td>{p.period}</td>
                                  <td>{p.time}</td>
                                  <td>{p.team}</td>
                                  <td>
                                    {canLink ? (
                                      <button
                                        type="button"
                                        className="link-btn"
                                        onClick={() => {
                                          closeBoxScore();
                                          openPlayer(penPlayer);
                                        }}
                                      >
                                        {penPlayer}
                                      </button>
                                    ) : (
                                      penPlayer || "-"
                                    )}
                                  </td>
                                  <td>{p.infraction || "-"}</td>
                                  <td>{p.penalty_minutes}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

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
              {messages.map((m, idx) => {
                const entities = m.role === "assistant" ? extractAnswerEntities(m.content) : null;
                return (
                  <div key={idx} className={`msg-row ${m.role}`}>
                    <div className={`msg ${m.role}`}>
                      {m.role === "assistant" ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                          {m.content}
                        </ReactMarkdown>
                      ) : (
                        m.content
                      )}
                    </div>
                    {m.role === "assistant" && entities && (entities.players.length > 0 || entities.games.length > 0) && (
                      <div className="entity-chips-row">
                        {entities.players.map((pName) => (
                          <button
                            key={pName}
                            type="button"
                            className="entity-chip"
                            onClick={() => openPlayer(pName)}
                          >
                            👤 {pName} &rarr;
                          </button>
                        ))}
                        {entities.games.map((g) => (
                          <button
                            key={`${g.date}-${g.opponent}`}
                            type="button"
                            className="entity-chip"
                            onClick={() => openBoxScore(g.date, g.opponent)}
                          >
                            🏒 {g.date} vs. {g.opponent} &rarr;
                          </button>
                        ))}
                      </div>
                    )}
                    {m.role === "assistant" && m.cached && (
                      <span className="msg-meta">Instant cached answer</span>
                    )}
                  </div>
                );
              })}
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
                maxLength={1000}
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
