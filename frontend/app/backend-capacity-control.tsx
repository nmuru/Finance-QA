"use client";

import { useEffect, useState } from "react";

// const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_BASE_URL = "https://financial-dossier.onrender.com";
const STORAGE_KEY = "reverse-engineer-sdlc:v1-workspace";
const MESSAGE = "Please try again later due to temporary backend memory limitations.";

export default function BackendCapacityControl() {
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let consecutiveFailures = 0;

    const check = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
        if (!response.ok) throw new Error("Backend unavailable");
        consecutiveFailures = 0;

        let memoryFailure = false;
        try {
          const raw = window.sessionStorage.getItem(STORAGE_KEY);
          if (raw) {
            const stored = JSON.parse(raw) as { runId?: string };
            if (stored.runId && stored.runId !== "vercel-demo") {
              const statusResponse = await fetch(`${API_BASE_URL}/api/analysis/${stored.runId}/status`, { cache: "no-store" });
              if (statusResponse.ok) {
                const status = await statusResponse.json() as { error?: string };
                memoryFailure = status.error === MESSAGE;
              }
            }
          }
        } catch {
          memoryFailure = false;
        }

        if (!cancelled) setUnavailable(memoryFailure);
      } catch {
        consecutiveFailures += 1;
        let activeAnalysis = false;
        try {
          const raw = window.sessionStorage.getItem(STORAGE_KEY);
          if (raw) {
            const stored = JSON.parse(raw) as { status?: string };
            activeAnalysis = stored.status === "running" || stored.status === "cancelling";
          }
        } catch {
          activeAnalysis = false;
        }
        if (!cancelled && activeAnalysis && consecutiveFailures >= 2) setUnavailable(true);
      }
    };

    check();
    const timer = window.setInterval(check, 6000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  if (!unavailable) return null;
  return (
    <div style={{ position: "fixed", top: 16, left: "50%", transform: "translateX(-50%)", zIndex: 1000, maxWidth: "min(680px, calc(100vw - 32px))", padding: "14px 18px", border: "1px solid currentColor", borderRadius: 8, background: "Canvas", color: "CanvasText", boxShadow: "0 4px 18px rgba(0,0,0,0.12)", textAlign: "center", fontSize: 14 }}>
      {MESSAGE}
    </div>
  );
}
