"use client";

import { FormEvent, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Phase = { id: string; label: string };
type AnalysisEvent =
  | { type: "phase_completed"; phase: string; phase_name: string; raw_analysis: string; run_id: string; provenance?: { model: string } }
  | { type: "analysis_completed"; run_id: string; completed_phases: string[] }
  | { type: "analysis_cancelled"; run_id: string; completed_phases: string[] }
  | { type: "analysis_failed"; error: string };

const analyses: Phase[] = [
  { id: "revenue-earnings-engine", label: "Revenue & Earnings Engine" },
  { id: "financial-resilience", label: "Financial Resilience" },
  { id: "capital-cash-deployment", label: "Capital & Cash Deployment" },
  { id: "accounting-signals-anomalies", label: "Accounting Signals & Anomalies" },
];

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [companyName, setCompanyName] = useState("");
  const [query, setQuery] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [activePhase, setActivePhase] = useState(analyses[0].id);
  const [completedPhases, setCompletedPhases] = useState<string[]>([]);
  const [results, setResults] = useState<Record<string, string>>({});
  const [provenance, setProvenance] = useState<{ model: string } | null>(null);
  const [error, setError] = useState("");

  async function analyze(event: FormEvent) {
    event.preventDefault();
    const company = companyName.trim();
    const question = query.trim();
    if (!company || !question) { setError("Enter both Company Name and Your Query."); return; }

    const nextRunId = `${Date.now()}${Math.random().toString(36).slice(2)}`.replace(/[^a-zA-Z0-9]/g, "");
    setRunId(nextRunId);
    setLoading(true);
    setStopping(false);
    setError("");
    setCompletedPhases([]);
    setResults({});
    setActivePhase(analyses[0].id);
    setProvenance(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/analyze`, {
        method: "POST",
        headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
        body: JSON.stringify({ company_name: company, query: question, work_id: nextRunId }),
      });
      if (!response.ok) {
        let message = "Analysis failed.";
        try { const data = await response.json(); if (typeof data?.detail === "string") message = data.detail; } catch {}
        throw new Error(message);
      }
      if (!response.body) throw new Error("The analysis stream was not available.");

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
          const lines = block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim());
          if (!lines.length) continue;
          let data: AnalysisEvent;
          try { data = JSON.parse(lines.join("\n")) as AnalysisEvent; } catch { continue; }
          if (data.type === "phase_completed") {
            setRunId(data.run_id);
            setActivePhase(data.phase);
            setCompletedPhases((previous) => previous.includes(data.phase) ? previous : [...previous, data.phase]);
            setResults((previous) => ({ ...previous, [data.phase]: data.raw_analysis }));
            if (data.provenance) setProvenance(data.provenance);
          } else if (data.type === "analysis_completed") {
            setCompletedPhases(data.completed_phases ?? []);
            setLoading(false);
          } else if (data.type === "analysis_cancelled") {
            setCompletedPhases(data.completed_phases ?? []);
            setLoading(false);
          } else if (data.type === "analysis_failed") {
            setError(data.error);
            setLoading(false);
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed.");
      setLoading(false);
    }
  }

  async function stopAnalysis() {
    if (!runId || stopping || !loading) return;
    setStopping(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/analysis/${runId}/stop`, { method: "POST" });
      if (!response.ok) throw new Error("The backend did not accept the stop request.");
      setLoading(false);
    } catch (err) {
      setStopping(false);
      setError(err instanceof Error ? err.message : "Unable to stop the analysis.");
    }
  }

  function reset() {
    setCompanyName(""); setQuery(""); setRunId(null); setLoading(false); setStopping(false);
    setActivePhase(analyses[0].id); setCompletedPhases([]); setResults({}); setProvenance(null); setError("");
  }

  const activeResult = results[activePhase] ?? "";

  return <div className="app-shell">
    <header className="topbar">
      <div><div className="brand">Finance QA</div><div className="tagline">Ask questions about a company’s financials</div></div>
      {runId && <div className="repo-pill">{companyName}</div>}
    </header>

    {!runId ? <main className="landing"><div className="landing-card">
      <div className="eyebrow">FINANCE QA · V1</div>
      <h1>Ask a financial question about a company.</h1>
      <p className="landing-copy">Enter a company name and your question. V1 keeps the existing financial-analysis backend architecture.</p>
      <form onSubmit={analyze} className="repo-form qa-form">
        <label className="qa-field"><span>Company Name</span><input value={companyName} onChange={(event) => setCompanyName(event.target.value)} placeholder="e.g. Infosys" required disabled={loading} /></label>
        <label className="qa-field"><span>Your Query</span><textarea value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. How resilient are the company’s earnings and cash generation?" rows={6} required disabled={loading} /></label>
        <button type="submit" disabled={loading}>{loading ? "Analyzing..." : "Ask Finance QA"}</button>
      </form>
      {error && <div className="error-banner" role="alert">{error}</div>}
      <div className="landing-note">The query is passed to the backend now; dynamic temporary agents and skills will be added in a later iteration.</div>
    </div></main> : <div className="workspace">
      <aside className="sidebar">
        <div className="sidebar-heading">Financial Analysis</div>
        <div className="progress-label">{loading ? `${completedPhases.length} of ${analyses.length} analyses completed` : "Analysis"}</div>
        <nav className="analysis-nav" aria-label="financial analyses">{analyses.map((analysis, index) => {
          const complete = completedPhases.includes(analysis.id);
          return <button key={analysis.id} className={`analysis-tab ${activePhase === analysis.id ? "active" : ""} ${!complete ? "locked" : ""}`} onClick={() => complete && setActivePhase(analysis.id)} disabled={!complete}>
            <span className="analysis-number">{String(index + 1).padStart(2, "0")}</span><span className="analysis-name">{analysis.label}</span><span className={`analysis-status ${complete ? "done" : ""}`}>{complete ? "✓" : "•"}</span>
          </button>;
        })}</nav>
        {runId && completedPhases.length > 0 && <a className="download-button" href={`${API_BASE_URL}/api/analysis/${runId}/download`} download="financial-analysis.zip">Download completed work</a>}
        <button className="new-analysis" onClick={reset} disabled={loading || stopping}>+ New Question</button>
      </aside>
      <main className="content">
        {loading && !activeResult && <section className="progress-screen"><div className="spinner" /><div><div className="eyebrow">ANALYSIS IN PROGRESS</div><h1>Working on your question</h1><p>{completedPhases.length} of {analyses.length} financial analyses have completed.</p><button type="button" onClick={stopAnalysis} disabled={stopping}>{stopping ? "Stopping..." : "Stop analysis"}</button></div></section>}
        {!loading && completedPhases.length === analyses.length && <section className="completion-banner"><div><div className="eyebrow">FINANCE QA COMPLETE</div><h1>Analysis is ready.</h1><p>Review the completed financial analyses for {companyName}.</p></div><div className="completion-mark">✓</div></section>}
        {activeResult && <section className="dossier-content"><div className="eyebrow">STAGE {String(analyses.findIndex((analysis) => analysis.id === activePhase) + 1).padStart(2, "0")}</div><h2>{analyses.find((analysis) => analysis.id === activePhase)?.label ?? "Financial Analysis"}</h2><p className="section-intro">Analysis returned by the existing financial-analysis backend.{provenance ? ` Model: ${provenance.model}` : ""}</p><article className="evidence-card markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{activeResult}</ReactMarkdown></article></section>}
        {!loading && !activeResult && error && <section className="progress-screen"><div><div className="eyebrow">ANALYSIS FAILED</div><h1>The analysis could not continue.</h1><p>{error}</p></div></section>}
      </main>
    </div>}
  </div>;
}