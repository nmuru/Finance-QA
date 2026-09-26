"use client";

import { useEffect, useState } from "react";

const API_BASE_URL = "https://financial-dossier.onrender.com";
const STORAGE_KEY = "reverse-engineer-sdlc:v1-workspace";

export default function WorkspaceCloseControl() {
  const [runId, setRunId] = useState<string | null>(null);

  useEffect(() => {
    const refresh = () => {
      try {
        window.localStorage.removeItem(STORAGE_KEY);
        const raw = window.sessionStorage.getItem(STORAGE_KEY);
        const stored = raw ? JSON.parse(raw) as { runId?: string } : null;
        setRunId(stored?.runId && stored.runId !== "vercel-demo" ? stored.runId : null);
      } catch {
        setRunId(null);
      }
    };
    refresh();
    window.addEventListener("storage", refresh);
    const timer = window.setInterval(refresh, 1000);
    return () => {
      window.removeEventListener("storage", refresh);
      window.clearInterval(timer);
    };
  }, []);

  async function waitForTerminal(runId: string) {
    const deadline = Date.now() + 120000;
    while (Date.now() < deadline) {
      const response = await fetch(`${API_BASE_URL}/api/analysis/${runId}/status`, { cache: "no-store" });
      if (response.ok) {
        const status = await response.json() as { status?: string };
        if (["completed", "failed", "cancelled"].includes(status.status ?? "")) return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 500));
    }
    throw new Error("The running analysis did not stop within the expected time. The workspace was not closed.");
  }

  async function closeWorkspace() {
    if (!runId) return;
    if (!window.confirm("Stop and exit this workspace? Any running analysis will be stopped first, and this workspace’s server-side results will be deleted. Refreshing the page does not close the workspace.")) return;
    try {
      const statusResponse = await fetch(`${API_BASE_URL}/api/analysis/${runId}/status`, { cache: "no-store" });
      if (statusResponse.ok) {
        const status = await statusResponse.json() as { status?: string };
        if (["running", "cancelling"].includes(status.status ?? "")) {
          const stopResponse = await fetch(`${API_BASE_URL}/api/analysis/${runId}/stop`, { method: "POST" });
          if (!stopResponse.ok) throw new Error("The backend did not accept the request to stop the running analysis.");
          await waitForTerminal(runId);
        }
      }

      const response = await fetch(`${API_BASE_URL}/api/analysis/${runId}/close`, { method: "POST", keepalive: true });
      if (!response.ok) throw new Error("The backend did not accept the workspace close request.");
      window.sessionStorage.removeItem(STORAGE_KEY);
      window.localStorage.removeItem(STORAGE_KEY);
      window.location.reload();
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Unable to close the workspace.");
    }
  }

  if (!runId) return null;

  return <button type="button" onClick={closeWorkspace} style={{ position: "fixed", top: 58, right: 14, zIndex: 50, minHeight: 34, padding: "0 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", color: "var(--text)", fontSize: 24, fontWeight: 700 }}>Stop & Exit</button>;
}
