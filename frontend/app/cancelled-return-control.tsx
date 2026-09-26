"use client";

import { useEffect } from "react";

export default function CancelledReturnControl() {
  useEffect(() => {
    const handleReturnToWorkspace = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const button = target?.closest("button");
      if (!button || button.textContent?.trim() !== "Back to Main Page") return;

      event.preventDefault();
      event.stopPropagation();

      const selectionTab = document.querySelector<HTMLButtonElement>("button.selection-tab");
      selectionTab?.click();
    };

    document.addEventListener("click", handleReturnToWorkspace, true);
    return () => document.removeEventListener("click", handleReturnToWorkspace, true);
  }, []);

  return null;
}
