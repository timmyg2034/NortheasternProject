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

        <h3>Unofficial Project &amp; Trademarks</h3>
        <p>
          This site is not affiliated with, endorsed by, or officially connected to
          Northeastern University, Northeastern Athletics, the NCAA, Hockey East, or
          any opponent institution. All school names, athletic marks, logos, and
          player headshots are the property of their respective owners and are used
          strictly for non-commercial, informational, and statistical reference
          under nominative fair use.
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

        <h3>Corrections &amp; Takedown Requests</h3>
        <p>
          If you are a student-athlete, rights holder, or university representative
          and wish to request a statistical correction or the removal of a specific
          headshot, logo, or record, please submit a request using the{" "}
          <strong>Report a Bug</strong> link in the footer (select{" "}
          <em>Content / Takedown Request</em>) and it will be addressed promptly.
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
          This frontend does <strong>not</strong> set tracking cookies, use browser{" "}
          <code>localStorage</code> or <code>sessionStorage</code>, store{" "}
          <code>IndexedDB</code> data, or run third-party analytics or ad-tracking
          scripts (such as Google Analytics or Meta Pixel). A minimal Progressive
          Web App manifest and network-first service worker (<code>sw.js</code>) are
          included solely to support standalone mobile home-screen installation.
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
            backend has no persistent user database. It temporarily holds your
            client IP address in memory for a 60-second sliding window to prevent
            automated abuse on <code>/api/chat</code> and{" "}
            <code>/api/bug-report</code>, and caches standalone (non-contextual)
            question-and-answer pairs in memory for up to 24 hours to conserve API
            quota.
          </li>
          <li>
            <strong>Third-Party AI Processing (Google Gemini):</strong> When you
            submit a question in <strong>Ask Paws</strong>, your prompt, recent
            chat turns, and optional page context are transmitted to Google&apos;s
            Gemini API to generate the query and response. Please do not enter
            personal, confidential, or sensitive information into the chat.
          </li>
          <li>
            <strong>Bug &amp; Takedown Reports:</strong> If you voluntarily submit a
            report via the <strong>Report a Bug</strong> form, the category,
            description, current page context, optional contact field, and browser{" "}
            <code>User-Agent</code> header are recorded on the server and forwarded
            to the maintainer&apos;s notification webhook solely to resolve the
            issue.
          </li>
          <li>
            <strong>Bot Protection (Cloudflare Turnstile):</strong> When enabled,
            <strong>Ask Paws</strong> uses Cloudflare Turnstile to verify human
            traffic without intrusive puzzles. Turnstile evaluates browser signals
            under Cloudflare&apos;s privacy policy.
          </li>
          <li>
            <strong>External Static Assets:</strong> Player headshot images are
            loaded from <code>nuhuskies.com</code>, and typography is loaded from
            Google Fonts (<code>fonts.googleapis.com</code>). Standard web requests
            to those hosts are governed by their respective privacy policies.
          </li>
        </ul>

        <h3>Children&apos;s Privacy</h3>
        <p>
          This service is directed to general audiences and is not directed to
          children under 13. We do not knowingly collect personal information from
          children under 13.
        </p>
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
          <strong>Ask Paws</strong> API, submitting off-topic prompts or prompt
          injections, or attempting to bypass rate limits or security controls is
          strictly prohibited.
        </p>

        <h3>Intellectual Property &amp; Third-Party Marks</h3>
        <p>
          Underlying code and compilation are provided for personal fan use. All
          university trademarks, logos, and athlete likenesses remain the property
          of their respective institutions and rightsholders.
        </p>

        <h3>No Warranty &amp; Limitation of Liability</h3>
        <p>
          Because this is an experimental, fan-built analytics tool provided{" "}
          <strong>&ldquo;as is,&rdquo;</strong> we make no guarantees regarding
          uptime, completeness, or accuracy. Not for use in wagering or official
          record-keeping. In no event shall the project maintainers be liable for
          any damages arising from your use of or reliance on any statistics or
          AI-generated answers shown here.
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
  const modalRef = useRef(null);
  const closeBtnRef = useRef(null);
  const content = type ? LEGAL_CONTENT[type] : null;

  useEffect(() => {
    if (!type) return;
    const previouslyFocused = document.activeElement;
    closeBtnRef.current?.focus();

    function onKeyDown(e) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "Tab" && modalRef.current) {
        const focusables = modalRef.current.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      if (previouslyFocused && typeof previouslyFocused.focus === "function") {
        previouslyFocused.focus();
      }
    };
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
        ref={modalRef}
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
