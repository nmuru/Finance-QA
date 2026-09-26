"use client";

import { useEffect } from "react";

// const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_BASE_URL = "https://financial-dossier.onrender.com";
const STORAGE_KEY = "reverse-engineer-sdlc:v1-workspace";
const TOTAL_PHASES = 4;

type Failure = { phase?: string; phase_name?: string; error_type?: string; error?: string };

function readWorkspace() {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as { runId?: string; completedPhases?: string[] } : null;
  } catch {
    return null;
  }
}

export default function V1WorkspaceDisplayControl() {
  useEffect(() => {
    let cancelled = false;

    const update = async () => {
      const stored = readWorkspace();
      if (!stored?.runId || stored.runId === "vercel-demo") return;

      let completed = stored.completedPhases?.length ?? 0;
      let statusValue = "";
      let failures: Failure[] = [];
      try {
        const response = await fetch(`${API_BASE_URL}/api/analysis/${stored.runId}/status`, { cache: "no-store" });
        if (response.ok) {
          const status = await response.json() as { completed_phases?: string[]; status?: string; failures?: Failure[] };
          completed = status.completed_phases?.length ?? completed;
          statusValue = status.status ?? "";
          failures = status.failures ?? [];
        }
      } catch {
        // Keep the last locally persisted count if the backend is temporarily unavailable.
      }

      if (cancelled) return;
      const progress = `${completed} of ${TOTAL_PHASES} phases have completed. You can read completed phases while the remaining phases continue running.`;
      const progressScreen = Array.from(document.querySelectorAll<HTMLElement>(".progress-screen")).find(
        (screen) => screen.querySelector(".eyebrow")?.textContent?.trim() === "ANALYSIS IN PROGRESS",
      );
      progressScreen?.querySelector("p")?.replaceChildren(progress);

      const sidebarProgress = document.querySelector<HTMLElement>(".progress-label");
      if (sidebarProgress) {
        const text = sidebarProgress.textContent ?? "";
        if (text.includes("phases") || text === "Analysis") sidebarProgress.textContent =
          statusValue === "failed" ? "Analysis failed" : `${completed} of ${TOTAL_PHASES} phases completed`;
      }

      if (statusValue === "failed" && failures.length > 0) {
        const failure = failures[0];
        const detail = `${failure.phase_name || failure.phase || "Selected phase"} failed${failure.error_type ? ` (${failure.error_type})` : ""}: ${failure.error || "No additional error detail was recorded."}`;
        document.querySelectorAll<HTMLElement>(".progress-screen").forEach((screen) => {
          if (screen.querySelector(".eyebrow")?.textContent?.trim() === "ANALYSIS FAILED") {
            const paragraph = screen.querySelector("p");
            if (paragraph) paragraph.textContent = detail;
          }
        });
      }

      document.querySelectorAll<HTMLElement>(".completion-banner").forEach((banner) => {
        if (banner.textContent?.includes("ANALYSIS STOPPED")) {
          const paragraph = banner.querySelector("p");
          if (paragraph) paragraph.textContent = `${completed} of ${TOTAL_PHASES} phases completed before stop.`;
        }
      });
    };

    update();
    const timer = window.setInterval(update, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return null;
}
