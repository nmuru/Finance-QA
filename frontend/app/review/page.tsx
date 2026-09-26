"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ReviewStatus = { status: string; results?: Record<string, string>; error?: string };

export default function ReviewPage() {
  const [content, setContent] = useState("");
  const [status, setStatus] = useState("Loading review...");
  const [error, setError] = useState("");

  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get("runId");
    if (!runId) { setError("No analysis run was supplied."); return; }
    let cancelled = false;
    const poll = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/analysis/${encodeURIComponent(runId)}/status`, { cache: "no-store" });
        if (!response.ok) throw new Error("The analysis workspace is no longer available.");
        const data = await response.json() as ReviewStatus;
        if (cancelled) return;
        const result = data.results?.["review-code-base"] || "";
        if (result) { setContent(result); setStatus("Review complete"); return; }
        if (data.status === "failed") { setError(data.error || "Review Code Base failed."); setStatus("Review failed"); return; }
        setStatus("Reviewing available SDLC artifacts and verifying important findings...");
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load the review.");
      }
    };
    poll();
    const timer = window.setInterval(poll, 1500);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  function backToWorkspace() {
    if (window.history.length > 1) {
      window.history.back();
      return;
    }
    window.location.href = "/";
  }

  return <main style={{ maxWidth: 1000, margin: "0 auto", padding: "32px 24px", fontFamily: "Arial, Helvetica, sans-serif" }}>
    <div style={{ marginBottom: 20 }}><button type="button" onClick={backToWorkspace} style={{ padding: "8px 12px", borderRadius: 6, border: "1px solid #d1d5db", background: "white", cursor: "pointer" }}>Back to workspace</button></div>
    <h1>Review Code Base</h1>
    <p style={{ color: "#4b5563" }}>{status}</p>
    {error && <div style={{ padding: 12, borderRadius: 6, background: "#fef2f2", color: "#991b1b" }}>{error}</div>}
    {content && <article style={{ marginTop: 28, lineHeight: 1.6 }}><ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown></article>}
  </main>;
}
