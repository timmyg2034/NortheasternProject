import React, { useEffect, useRef, useState } from "react";

const CATEGORIES = [
  "Data / Stat Issue",
  "Ask Paws AI",
  "UI / Layout",
  "Broken Link / Image",
  "Other",
];

export default function BugReportModal({ open, onClose, apiBase, pageContext }) {
  const closeBtnRef = useRef(null);
  const [category, setCategory] = useState(CATEGORIES[0]);
  const [description, setDescription] = useState("");
  const [contact, setContact] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [submittedId, setSubmittedId] = useState("");

  useEffect(() => {
    if (!open) return;
    setError("");
    setSubmittedId("");
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    closeBtnRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    const trimmed = description.trim();
    if (trimmed.length < 5) {
      setError("Please describe the issue in at least a few words.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch(`${apiBase}/api/bug-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category,
          description: trimmed,
          page_context: pageContext || "",
          contact: contact.trim() || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Could not submit bug report.");
      }
      setSubmittedId(data.id);
      setDescription("");
      setContact("");
    } catch (err) {
      setError(err.message || "Failed to send bug report.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal-card bug-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bug-modal-title"
      >
        <div className="modal-header">
          <h2 id="bug-modal-title">Report a Bug</h2>
          <button
            ref={closeBtnRef}
            type="button"
            className="chat-drawer-btn"
            onClick={onClose}
            aria-label="Close bug report modal"
          >
            Close
          </button>
        </div>

        <div className="modal-body">
          {submittedId ? (
            <div className="bug-success">
              <h3>Thanks for the report!</h3>
              <p>
                Your feedback has been logged as reference{" "}
                <strong>#{submittedId}</strong>. We appreciate you helping improve
                the Northeastern Men&apos;s Hockey Explorer.
              </p>
              <div className="bug-actions">
                <button
                  type="button"
                  className="btn-primary"
                  onClick={onClose}
                >
                  Done
                </button>
              </div>
            </div>
          ) : (
            <form className="bug-form" onSubmit={handleSubmit}>
              <p className="muted" style={{ marginTop: 0 }}>
                Spot a wrong stat, broken headshot/logo, or AI quirk? Let us know
                below.
              </p>

              <label className="bug-field">
                <span>Category</span>
                <select
                  className="select-input"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>

              <label className="bug-field">
                <span>What happened?</span>
                <textarea
                  className="text-input bug-textarea"
                  rows={4}
                  maxLength={2000}
                  placeholder="Describe what you expected vs. what you saw..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  required
                />
              </label>

              <label className="bug-field">
                <span>Name or Email (optional)</span>
                <input
                  type="text"
                  className="text-input"
                  maxLength={120}
                  placeholder="Only if you'd like a follow-up"
                  value={contact}
                  onChange={(e) => setContact(e.target.value)}
                />
              </label>

              {pageContext && (
                <div className="bug-context">
                  <strong>Current view:</strong> {pageContext}
                </div>
              )}

              {error && <div className="bug-error">{error}</div>}

              <div className="bug-actions">
                <button
                  type="button"
                  className="bug-cancel-btn"
                  onClick={onClose}
                  disabled={submitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={submitting}
                >
                  {submitting ? "Sending..." : "Submit Report"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

