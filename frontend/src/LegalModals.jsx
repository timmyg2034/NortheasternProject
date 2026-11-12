import React, { useEffect, useRef } from "react";

const LEGAL_CONTENT = {
  disclaimer: {
    title: "Disclaimer",
    body: (
      <>
        <h3>Experimental &ldquo;As-Is&rdquo; Software</h3>
        <p>
          This application is an independent, experimental fan project built for
          casual exploration of Northeastern Men&apos;s Ice Hockey statistics. It is
          provided strictly <strong>&ldquo;as is&rdquo; and &ldquo;as available&rdquo;</strong>{" "}
          without warranties of any kind, express or implied.
        </p>

        <h3>Unofficial Project</h3>
        <p>
          This site is not affiliated with, endorsed by, or officially connected to
          Northeastern University, Northeastern Athletics, or Hockey East. Team
          logos and player headshots are displayed for informational and fan
          reference purposes only.
        </p>

        <h3>AI-Generated Output &amp; Data Accuracy</h3>
        <p>
          Answers in <strong>Ask Paws</strong> are generated dynamically by Google
          Gemini models writing and executing data queries against scraped
          historical archives (1999&ndash;present). AI models can misinterpret
          ambiguous questions or edge cases, and scraped box scores may contain
          upstream omissions (for example, blocked shots and faceoffs were not
          officially tracked by the NCAA prior to 2012&ndash;13). Always verify
          important stats against the linked official box scores or rosters on{" "}
          <a href="https://nuhuskies.com" target="_blank" rel="noreferrer">
            nuhuskies.com
          </a>
          .
        </p>
      </>
    ),
  },
  privacy: {
    title: "Privacy Policy",
    body: (
      <>
        <h3>No Cookies, Local Storage, or User Tracking</h3>
        <p>
          This frontend does <strong>not</strong> set cookies, use browser{" "}
          <code>localStorage</code> or <code>sessionStorage</code>, store{" "}
          <code>IndexedDB</code> data, or run third-party analytics or ad-tracking
          scripts (such as Google Analytics or Sentry).
        </p>

        <h3>What Data Is Processed When You Use the App</h3>
        <ul>
          <li>
            <strong>In-Memory Chat History:</strong> Messages you send in{" "}
            <strong>Ask Paws</strong> live only in your browser tab&apos;s temporary
            memory and are cleared when you refresh the page or click{" "}
            <strong>Clear</strong>.
          </li>
          <li>
            <strong>Server Rate Limiting &amp; Query Caching:</strong> Our FastAPI
            backend has no persistent database. It temporarily holds your IP
            address in memory for a 60-second sliding window to prevent spam on{" "}
            <code>/api/chat</code>, and caches standalone (non-contextual)
            question-and-answer pairs in memory for up to 1 hour to save API
            quota.
          </li>
          <li>
            <strong>Third-Party AI Processing (Google Gemini):</strong> When you
            submit a question in <strong>Ask Paws</strong>, your prompt, recent
            chat turns, and optional page context are sent to Google&apos;s Gemini
            API to generate the query and response. Please avoid entering
            personal or sensitive information into the chat.
          </li>
          <li>
            <strong>External Static Assets:</strong> Player headshot images are
            loaded from <code>nuhuskies.com</code>, and typography is loaded from
            Google Fonts (<code>fonts.googleapis.com</code>). Standard web server
            requests to those hosts are subject to their respective privacy
            policies.
          </li>
        </ul>
      </>
    ),
  },
  terms: {
    title: "Terms of Use",
    body: (
      <>
        <h3>Acceptable Use</h3>
        <p>
          You may use this site for personal, non-commercial, informational, and
          fan purposes. Automated scraping, abusing the{" "}
          <strong>Ask Paws</strong> API, or attempting to bypass rate limits is
          prohibited.
        </p>

        <h3>No Warranty &amp; Limitation of Liability</h3>
        <p>
          Because this is an experimental, student-built analytics tool provided{" "}
          <strong>&ldquo;as is,&rdquo;</strong> we make no guarantees regarding
          uptime, completeness, or accuracy. In no event shall the project
          maintainers be liable for any damages arising from your use of or
          reliance on any statistics or AI-generated answers shown here.
        </p>

        <h3>Changes</h3>
        <p>
          Features, data coverage, and these terms may be updated or discontinued
          at any time without notice.
        </p>
      </>
    ),
  },
};

export default function LegalModal({ type, onClose }) {
  const closeBtnRef = useRef(null);
  const content = type ? LEGAL_CONTENT[type] : null;

  useEffect(() => {
    if (!type) return;
    closeBtnRef.current?.focus();
    function onKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [type, onClose]);

  if (!content) return null;

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="legal-modal-title"
      >
        <div className="modal-header">
          <h2 id="legal-modal-title">{content.title}</h2>
          <button
            ref={closeBtnRef}
            type="button"
            className="chat-drawer-btn"
            onClick={onClose}
            aria-label={`Close ${content.title}`}
          >
            Close
          </button>
        </div>
        <div className="modal-body">{content.body}</div>
      </div>
    </div>
  );
}

