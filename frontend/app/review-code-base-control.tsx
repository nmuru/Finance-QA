"use client";

import { useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ReviewCodeBaseControlProps = {
  repoUrl: string;
  provider: string;
  model: string;
  apiKey: string;
  runId: string | null;
  completedPhases: string[];
};

export default function ReviewCodeBaseControl({ repoUrl, provider, model, apiKey, runId, completedPhases }: ReviewCodeBaseControlProps) {
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("");

  async function review() {
    if (!runId || running || completedPhases.length === 0 || !apiKey.trim()) return;
    setMessage("");

    if (!repoUrl.trim()) return;

    setRunning(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/analyze`, {
        method: "POST",
        headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
        body: JSON.stringify({
          repo_url: repoUrl,
          selected_phases: ["review-code-base"],
          work_id: runId,
          provider,
          model,
          api_key: apiKey,
        }),
      });
      if (!response.ok) {
        let detail = "Review SDLC failed.";
        try {
          const data = await response.json();
          if (typeof data?.detail === "string") detail = data.detail;
        } catch {}
        throw new Error(detail);
      }
      if (!response.body) throw new Error("The review stream was not available.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const block of events) {
          const data = block
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim())
            .join("\n");
          if (!data) continue;
          const event = JSON.parse(data) as { type?: string; error?: string };
          if (event.type === "analysis_failed") throw new Error(event.error || "Review SDLC failed.");
          if (event.type === "analysis_completed") {
            window.location.href = `/review?runId=${encodeURIComponent(runId)}`;
            return;
          }
        }
      }
      window.location.href = `/review?runId=${encodeURIComponent(runId)}`;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Review SDLC failed.");
    } finally {
      setRunning(false);
    }
  }

  if (!runId || completedPhases.length === 0 || !apiKey.trim()) return null;

  return (
    <div style={{ marginTop: 8 }}>
      <button
        type="button"
        onClick={review}
        disabled={running}
        className="phase-tab"
        style={{ width: "100%", border: "1px solid var(--accent)", background: "white", cursor: running ? "wait" : "pointer" }}
        title="Review the completed SDLC artifacts against the repository"
      >
        <span className="phase-number">RV</span>
        <span className="phase-name">{running ? "Reviewing Repo..." : "Review Repo"}</span>
        <span className="phase-status">→</span>
      </button>
      {message && (
        <div style={{ marginTop: 6, padding: 8, borderRadius: 6, background: "#fff", border: "1px solid #fecaca", color: "#991b1b", fontSize: 12 }}>
          {message}
        </div>
      )}
    </div>
  );
}
