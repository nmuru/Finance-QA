
"use client";

import { FormEvent, useEffect, useId, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function MermaidDiagram({ chart }: { chart: string }) {
  const id = useId().replace(/:/g, "");
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    async function renderDiagram() {
      try {
        const { default: mermaid } = await import("mermaid");
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "default" });
        const cleaned = chart.trim().replace(/^```mermaid\s*/i, "").replace(/```$/i, "").trim();
        const parsed = await mermaid.parse(cleaned);
        if (!parsed) throw new Error("Mermaid could not parse the diagram.");
        const { svg: renderedSvg } = await mermaid.render(`mermaid-${id}`, cleaned);
        if (!cancelled) { setSvg(renderedSvg); setError(""); }
      } catch (err) {
        if (!cancelled) { setSvg(""); setError(err instanceof Error ? err.message : "Unable to render Mermaid diagram."); }
      }
    }
    renderDiagram();
    return () => { cancelled = true; };
  }, [chart, id]);
  if (error) return <div className="mermaid-error"><div>Diagram could not be rendered. Mermaid source is shown below.</div><pre className="markdown-code-block"><code>{chart}</code></pre></div>;
  if (!svg) return <div className="mermaid-loading">Rendering diagram...</div>;
  return <div className="mermaid-diagram" dangerouslySetInnerHTML={{ __html: svg }} />;
}

type Phase = { id: string; label: string; shortLabel: string };
type AnalysisResult = {
  company_name: string;
  revenue_earnings_engine: string;
  financial_resilience: string;
  capital_cash_deployment: string;
  accounting_signals_anomalies: string;
};
type Failure = { phase: string; phase_name: string; error_type: string; error: string };
type AnalysisEvent =
  | { type: "phase_completed"; phase: string; phase_name: string; raw_analysis: string; raw_path: string; run_id: string; provenance?: { model: string } }
  | { type: "analysis_completed"; company_name: string; run_id: string; completed_phases: string[]; failed_phases?: Failure[] }
  | { type: "analysis_cancelled"; company_name: string; run_id: string; completed_phases: string[]; failed_phases?: Failure[] }
  | { type: "analysis_failed"; company_name: string; run_id?: string; error: string };
type RunStatus = { run_id: string; status: string; company_name: string; selected_phases: string[]; completed_phases: string[]; failures: Failure[]; active_phase: string | null; results: Record<string, string> };
type StoredWorkspace = { runId: string; companyName: string; selectedPhases: string[]; completedPhases: string[]; activePhase: string; status: string; provenance: { model: string } | null; mode: "parallel" | "sequence" };

const analyses: Phase[] = [
  { id: "revenue-earnings-engine", label: "Revenue & Earnings Engine", shortLabel: "Earnings Engine" },
  { id: "financial-resilience", label: "Financial Resilience", shortLabel: "Resilience" },
  { id: "capital-cash-deployment", label: "Capital & Cash Deployment", shortLabel: "Capital & Cash" },
  { id: "accounting-signals-anomalies", label: "Accounting Signals & Anomalies", shortLabel: "Signals" },
];

const defaultSelectedPhases = analyses.map((analysis) => analysis.id);
const analysisResultMap: Record<Phase["id"], keyof AnalysisResult> = {
  "revenue-earnings-engine": "revenue_earnings_engine",
  "financial-resilience": "financial_resilience",
  "capital-cash-deployment": "capital_cash_deployment",
  "accounting-signals-anomalies": "accounting_signals_anomalies",
};

// const API_BASE_URL = "http://localhost:8000";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEMO_RUN_ID = "financial-demo";
const DEMOS = {
  infy: { folder: "infy-demo", label: "INFY SEC Demo", title: "INFY financial dossier" },
  ibm: { folder: "ibm-demo", label: "IBM SEC Demo", title: "IBM financial dossier" },
} as const;
const providers = [
  { id: "openrouter", label: "OpenRouter", placeholder: "e.g. openai/gpt-5, anthropic/claude-sonnet-4" },
  { id: "openai", label: "OpenAI", placeholder: "e.g. gpt-5" },
];

const STORAGE_KEY = "financial-analysis:v1-workspace";

function emptyResult(companyName = ""): AnalysisResult {
  return { company_name: companyName, revenue_earnings_engine: "", financial_resilience: "", capital_cash_deployment: "", accounting_signals_anomalies: "" };
}
function makeRunId() { return (typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`).replace(/[^a-zA-Z0-9]/g, ""); }

export default function Home() {
  const [companyName, setCompanyName] = useState("");
  const [provider, setProvider] = useState("openrouter");
  const [model, setModel] = useState("openrouter/free");
  const [apiKey, setApiKey] = useState("");
  const [mode, setMode] = useState<"parallel" | "sequence">("parallel");
  const [showApiKey, setShowApiKey] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analysisStarted, setAnalysisStarted] = useState(false);
  const [analysisComplete, setAnalysisComplete] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [activePhase, setActivePhase] = useState("revenue-earnings-engine");
  const [completedPhases, setCompletedPhases] = useState<string[]>([]);
  const [completionMessages, setCompletionMessages] = useState<string[]>([]);
  const [selectedPhases, setSelectedPhases] = useState<string[]>(defaultSelectedPhases);
  const [selectionView, setSelectionView] = useState<"setup" | null>(null);
  const [isDemo, setIsDemo] = useState(true);
  const [demoFolder, setDemoFolder] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [error, setError] = useState("");
  const [failedPhases, setFailedPhases] = useState<string[]>([]);
  const [provenance, setProvenance] = useState<{ model: string } | null>(null);
  const [restored, setRestored] = useState(false);
  const continuationStartingRef = useRef(false);
  const viewedCompletedPhaseRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function restoreWorkspace() {
      try {
        window.localStorage.removeItem(STORAGE_KEY);
        const raw = window.sessionStorage.getItem(STORAGE_KEY);
        if (!raw) { setRestored(true); return; }
        const stored = JSON.parse(raw) as StoredWorkspace;
        if (!stored.runId || stored.runId === DEMO_RUN_ID) { window.sessionStorage.removeItem(STORAGE_KEY); setRestored(true); return; }
        const storedCompleted = stored.completedPhases ?? [];
        const storedSelected = (stored.selectedPhases?.length ? stored.selectedPhases : defaultSelectedPhases).filter((analysis) => !storedCompleted.includes(analysis));
        setCompanyName(stored.companyName); setRunId(stored.runId); setSelectedPhases(storedSelected); setMode(stored.mode ?? "parallel");
        setCompletedPhases(storedCompleted); setActivePhase(stored.activePhase || storedCompleted[storedCompleted.length - 1] || storedSelected[0] || analyses[0].id);
        setAnalysisStarted(true); setIsDemo(false); setProvenance(stored.provenance ?? null);
        const response = await fetch(`${API_BASE_URL}/api/analysis/${stored.runId}/status`, { cache: "no-store" });
        if (!response.ok) throw new Error("Saved analysis state is no longer available on the backend.");
        const status = await response.json() as RunStatus;
        if (cancelled) return;
        applyStatus(status);
      } catch (err) {
        if (!cancelled) { window.sessionStorage.removeItem(STORAGE_KEY); setError(err instanceof Error ? err.message : "Unable to restore the previous analysis."); }
      } finally { if (!cancelled) setRestored(true); }
    }
    restoreWorkspace();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!analysisStarted || isDemo || !runId || !restored || analysisComplete || stopped) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/analysis/${runId}/status`, { cache: "no-store" });
        if (!response.ok) return;
        const status = await response.json() as RunStatus;
        if (!cancelled && !continuationStartingRef.current) applyStatus(status);
      } catch { /* SSE is primary during the original request; polling is the refresh fallback. */ }
    };
    poll();
    const timer = window.setInterval(poll, 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [analysisStarted, isDemo, runId, restored, analysisComplete, stopped]);

  useEffect(() => {
    if (!analysisStarted || isDemo || !runId) return;
    const snapshot: StoredWorkspace = { runId, companyName, selectedPhases, completedPhases, activePhase, status: stopped ? "cancelled" : analysisComplete ? "completed" : stopping ? "cancelling" : "running", provenance, mode };
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  }, [analysisStarted, isDemo, runId, companyName, selectedPhases, completedPhases, activePhase, stopped, analysisComplete, stopping, provenance, mode]);

  function applyStatus(status: RunStatus) {
    const backendCompleted = status.completed_phases ?? [];
    const completed = Array.from(new Set([...completedPhases, ...backendCompleted]));
    const backendSelected = status.selected_phases?.length ? status.selected_phases : defaultSelectedPhases;
    const selected = backendSelected.filter((analysis) => !completed.includes(analysis));
    const viewedCompletedPhase = viewedCompletedPhaseRef.current;
    const nextActive = viewedCompletedPhase && completed.includes(viewedCompletedPhase) ? viewedCompletedPhase : status.active_phase || selected[0] || activePhase || completed[completed.length - 1] || analyses[0].id;
    setRunId(status.run_id); setCompanyName(status.company_name); setSelectedPhases(selected);
    setCompletedPhases(completed); setActivePhase(nextActive);
    setFailedPhases((status.failures ?? []).map((failure) => failure.phase));
    setAnalysisResult((previous) => {
      const next = { ...(previous ?? emptyResult(status.company_name)), company_name: status.company_name };
      for (const [analysis, content] of Object.entries(status.results ?? {})) { const key = analysisResultMap[analysis as Phase["id"]]; if (key) next[key] = content; }
      return next;
    });
    if (status.status === "completed") { setAnalysisComplete(true); setLoading(false); setStopping(false); setStopped(false); }
    else if (status.status === "cancelled") { setAnalysisComplete(false); setLoading(false); setStopping(false); setStopped(true); }
    else if (status.status === "failed") { setAnalysisComplete(false); setLoading(false); setStopping(false); setError("The analysis could not continue."); }
    else { setAnalysisComplete(false); setLoading(true); if (status.status === "cancelling") setStopping(true); }
  }

  async function viewDemo(folder: string, demoCompanyName: string) {
    viewedCompletedPhaseRef.current = null;
    setError("");
    setCompanyName(demoCompanyName);
    setDemoFolder(folder);
    setRunId(DEMO_RUN_ID);
    setIsDemo(true);
    setAnalysisStarted(true);
    setAnalysisComplete(true);
    setStopped(false);
    setCompletedPhases(analyses.map((analysis) => analysis.id));
    setActivePhase(analyses[0].id);
    setSelectionView(null);
    setFailedPhases([]);
    setProvenance(null);
    setAnalysisResult(emptyResult(demoCompanyName));
  }

  async function analyze(event: FormEvent) {
    event.preventDefault();
    const analysesToRun = selectedPhases.filter((analysis) => !completedPhases.includes(analysis));
    if (!provider || !model.trim() || !apiKey.trim()) { setError("Enter an AI provider, model, and API key before starting."); return; }
    if (!companyName.trim() || analysesToRun.length === 0) { setError("Enter a company name and select at least one new financial analysis before starting."); return; }
    viewedCompletedPhaseRef.current = null;
    continuationStartingRef.current = Boolean(runId && !isDemo);
    const nextRunId = runId && !isDemo ? runId : makeRunId();
    setRunId(nextRunId); setLoading(true); setStopping(false); setStopped(false); setIsDemo(false); setAnalysisStarted(true); setSelectionView(null); setAnalysisComplete(false); setError(""); setFailedPhases([]);
    setCompletionMessages([]); setActivePhase(analysesToRun[0]);
    setCompletedPhases((previous) => isDemo ? [] : previous);
    setSelectedPhases(analysesToRun);
    setAnalysisResult(isDemo ? emptyResult(companyName) : (analysisResult ?? emptyResult(companyName)));

    try {
      const response = await fetch(`${API_BASE_URL}/api/analyze`, {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          company_name: companyName,
          selected_phases: analysesToRun,
          work_id: nextRunId,
          provider,
          model,
          api_key: apiKey,
          mode,
        }),
      });

      if (!response.ok) {
        let message = "Analysis failed.";

        try {
          const data = await response.json();

          if (typeof data?.detail === "string") {
            message = data.detail;
          }
        } catch {}

        throw new Error(message);
      }

      if (!response.body) {
        throw new Error("The analysis stream was not available.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const eventBlock of events) {
          const dataLines = eventBlock
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim());

          if (!dataLines.length) {
            continue;
          }

          let eventData: AnalysisEvent;

          try {
            eventData = JSON.parse(dataLines.join("\n")) as AnalysisEvent;
          } catch {
            continue;
          }

          if (eventData.type === "phase_completed") {
            setRunId(eventData.run_id);

            setProvenance(
              eventData.provenance
                ? { model: eventData.provenance.model }
                : { model }
            );

            setCompletionMessages((previous) =>
              previous.includes(eventData.phase_name)
                ? previous
                : [...previous, `${eventData.phase_name} analysis completed`]
            );

            const resultKey =
              analysisResultMap[eventData.phase as Phase["id"]];

            if (resultKey) {
              setAnalysisResult((previous) => ({
                ...(previous ?? emptyResult(companyName)),
                company_name: companyName,
                [resultKey]: eventData.raw_analysis,
              }));

              setCompletedPhases((previous) =>
                previous.includes(eventData.phase)
                  ? previous
                  : [...previous, eventData.phase]
              );

              setSelectedPhases((previous) =>
                previous.filter((id) => id !== eventData.phase)
              );

              setActivePhase(eventData.phase);
            }
          } else if (eventData.type === "analysis_completed") {
            const failures = eventData.failed_phases ?? [];

            setRunId(eventData.run_id);
            setAnalysisComplete(true);
            setLoading(false);
            setStopping(false);
            setStopped(false);
            setFailedPhases(
              failures.map((failure) => failure.phase)
            );

            if (failures.length) {
              setError(
                `${failures.length} selected analysis${
                  failures.length === 1 ? "" : "s"
                } could not be completed.`
              );
            }
          } else if (eventData.type === "analysis_cancelled") {
            setRunId(eventData.run_id);
            setAnalysisComplete(false);
            setLoading(false);
            setStopping(false);
            setStopped(true);
            setCompletedPhases(eventData.completed_phases ?? []);
            setFailedPhases(
              (eventData.failed_phases ?? []).map(
                (failure) => failure.phase
              )
            );
            setSelectedPhases((previous) =>
              previous.filter(
                (id) =>
                  !(eventData.completed_phases ?? []).includes(id)
              )
            );
          } else if (eventData.type === "analysis_failed") {
            setError(eventData.error);
            setAnalysisComplete(false);
            setLoading(false);
            setStopping(false);
          }
        }
      }
    } catch (err) {
      if (!stopped) {
        setError(err instanceof Error ? err.message : "Analysis failed.");
        setAnalysisComplete(false);
        setLoading(false);
      }
    } finally {
      continuationStartingRef.current = false;
    }
  }

  async function stopAnalysis() {
    if (!runId || stopping || !loading) return;
    if (!window.confirm("Stop this analysis? No further analyses will be started. Completed results will remain available.")) return;
    setStopping(true); setError("");
    try { const response = await fetch(`${API_BASE_URL}/api/analysis/${runId}/stop`, { method: "POST" }); if (!response.ok) throw new Error("The backend did not accept the stop request."); const status = await response.json() as RunStatus; applyStatus(status); }
    catch (err) { setStopping(false); setError(err instanceof Error ? err.message : "Unable to stop the analysis."); }
  }

  function resetAnalysis() {
    viewedCompletedPhaseRef.current = null;
    window.sessionStorage.removeItem(STORAGE_KEY); setAnalysisStarted(false); setIsDemo(false); setDemoFolder(null); setAnalysisComplete(false); setCompletedPhases([]); setCompletionMessages([]); setCompanyName(""); setRunId(null); setProvider("openrouter"); setModel("openrouter/free"); setApiKey(""); setMode("parallel"); setShowApiKey(false); setSelectedPhases(defaultSelectedPhases); setSelectionView(null); setActivePhase(analyses[0].id); setAnalysisResult(null); setError(""); setLoading(false); setStopping(false); setStopped(false); setFailedPhases([]); setProvenance(null); continuationStartingRef.current = false;
  }

  const activePhaseDefinition = analyses.find((analysis) => analysis.id === activePhase) ?? analyses[0];
  const activeResultKey = analysisResultMap[activePhaseDefinition.id];
  const activeResult = analysisResult && activeResultKey ? analysisResult[activeResultKey] : "";
  const denominator = analyses.length;
  const progressText = `${completedPhases.length} of ${denominator} analyses have completed. You can read completed analyses while the remaining analyses continue running.`;

  return <div className="app-shell">
    <header className="topbar"><div><div className="brand">Financial Dossier</div><div className="tagline">SEC Company Facts → Financial Intelligence Dossier</div></div>{analysisStarted && companyName && <div className="repo-pill" title={companyName}>{companyName.replace(/^https?:\/\//, "")}</div>}</header>
    {!analysisStarted ? <main className="landing"><div className="landing-card"><div className="eyebrow">AI FINANCIAL ANALYSIS</div><h1>Turn SEC company facts into a financial intelligence dossier.</h1><p className="landing-copy">Submit a SEC Company Name to progressively analyze earnings quality, financial resilience, capital deployment, and accounting signals from structured SEC XBRL data.</p>
      
      

      <div className="demo-links" style={{ marginTop: 20 }}>
        <span>Example:</span>
        <button
          type="button"
          className="demo-link"
          onClick={() => viewDemo(DEMOS.infy.folder, "INFY")}
          disabled={loading}
        >
          {DEMOS.infy.label}
        </button>
        <button
          type="button"
          className="demo-link"
          onClick={() => viewDemo(DEMOS.ibm.folder, "IBM")}
          disabled={loading}
        >
          IBM SEC Demo
        </button>
      </div>


      {/* <p style={{ marginTop: 20 }}>
        <a
          className="guide-link"
          href="/guide-and-tips.html"
          target="_blank"
          rel="noreferrer"
        >
          Guide & Tips
        </a>
      </p>     */}




      <fieldset className="analysis-selection" style={{ marginTop: 28 }}><legend>AI model</legend><div style={{ display: "grid", gap: 14 }}><label style={{ display: "grid", gap: 7 }}><span style={{ fontSize: 13, fontWeight: 700 }}>Provider</span><select value={provider} onChange={(event) => setProvider(event.target.value)} disabled={loading} aria-label="AI provider" style={{ width: "100%", padding: "12px 13px", border: "1px solid #cfd4da", borderRadius: 9, outline: "none", color: "var(--text)", background: "white" }}>{providers.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label style={{ display: "grid", gap: 7 }}><span style={{ fontSize: 13, fontWeight: 700 }}>Model</span><input value={model} onChange={(event) => setModel(event.target.value)} placeholder={providers.find((item) => item.id === provider)?.placeholder} disabled={loading} required aria-label="AI model" autoComplete="off" style={{ width: "100%", padding: "12px 13px", border: "1px solid #cfd4da", borderRadius: 9, outline: "none", color: "var(--text)", background: "white" }} /></label><label style={{ display: "grid", gap: 7 }}><span style={{ fontSize: 13, fontWeight: 700 }}>API key</span><div style={{ display: "flex", gap: 8 }}><input value={apiKey} onChange={(event) => setApiKey(event.target.value)} type={showApiKey ? "text" : "password"} placeholder="Enter your API key" disabled={loading} required aria-label="AI provider API key" autoComplete="off" style={{ minWidth: 0, flex: 1, padding: "12px 13px", border: "1px solid #cfd4da", borderRadius: 9, outline: "none", color: "var(--text)", background: "white" }} /><button type="button" onClick={() => setShowApiKey((value) => !value)} disabled={loading}>{showApiKey ? "Hide" : "Show"}</button></div></label><p style={{ margin: 0, color: "var(--muted)", fontSize: 12 }}>Your API key is used for this analysis request and is not saved by this frontend.</p></div></fieldset>

      {/* <fieldset className="analysis-selection" style={{ marginTop: 18 }}><legend>Financial analysis objective</legend><div style={{ display: "grid", gap: 10 }}><label className="analysis-option" style={{ alignItems: "flex-start" }}><input type="radio" name="objective" value="document" checked={objective === "document"} onChange={() => setObjective("document")} disabled={loading} /><span><strong>Document</strong><br /><span style={{ color: "var(--muted)", fontSize: 12 }}>Extract decision-useful financial signals from SEC structured data.</span></span></label><label className="analysis-option" style={{ alignItems: "flex-start" }}><input type="radio" name="objective" value="understand" checked={objective === "understand"} onChange={() => setObjective("understand")} disabled={loading} /><span><strong>Understand</strong><br /><span style={{ color: "var(--muted)", fontSize: 12 }}>Explain each completed analysis with evidence, trends, and caveats.</span></span></label></div></fieldset> */}

      <fieldset className="analysis-selection" style={{ marginTop: 18 }}><legend>Analysis mode</legend><div style={{ display: "grid", gap: 10 }}><label className="analysis-option" style={{ alignItems: "flex-start" }} title="Parallel completes analyses faster. Sequential runs analyses one after another, allowing later analyses to use the results of earlier analyses."><input type="radio" name="analysis-mode" value="parallel" checked={mode === "parallel"} onChange={() => setMode("parallel")} disabled={loading} /><span><strong>Parallel</strong><br /><span style={{ color: "var(--muted)", fontSize: 12 }}>Runs analyses in parallel.</span></span></label><label className="analysis-option" style={{ alignItems: "flex-start" }} title="Parallel completes analyses faster. Sequential runs analyses one after another, allowing later analyses to use the results of earlier analyses."><input type="radio" name="analysis-mode" value="sequence" checked={mode === "sequence"} onChange={() => setMode("sequence")} disabled={loading} /><span><strong>Sequential</strong><br /><span style={{ color: "var(--muted)", fontSize: 12 }}>Runs analyses one after another; later analyses can use earlier analysis results.</span></span></label></div></fieldset>

      <form onSubmit={analyze} className="repo-form"><input value={companyName} onChange={(event) => setCompanyName(event.target.value)} placeholder="Company name or SEC Company Facts JSON URL" type="text" required aria-label="Company name or SEC Company Facts JSON URL" /><button type="submit" disabled={loading}>{loading ? "Analyzing..." : "Analyze"}</button></form>
      <fieldset className="analysis-selection"><legend>Select analyses</legend><div className="analysis-selection-grid">{analyses.map((analysis) => <label key={analysis.id} className="analysis-option"><input type="checkbox" checked={selectedPhases.includes(analysis.id)} onChange={() => setSelectedPhases((previous) => previous.includes(analysis.id) ? previous.filter((id) => id !== analysis.id) : [...previous, analysis.id])} disabled={loading} /><span>{analysis.label}</span></label>)}</div></fieldset>
      {error && <div className="error-banner" role="alert">{error}</div>}<div className="landing-note">Analysis is performed by the backend financial analysis pipeline.</div>
    </div></main> : <div className="workspace">
      <aside className="sidebar"><div className="sidebar-heading">financial analysis Dossier</div><div className="progress-label">{loading ? progressText : analysisComplete ? "Analysis complete" : stopped ? `${completedPhases.length} of ${denominator} analyses completed before stop` : error ? "Analysis failed" : "Analysis"}</div><nav className="analysis-nav" aria-label="analyses"><button className={`analysis-tab selection-tab ${selectionView === "setup" ? "active" : ""}`} onClick={() => { viewedCompletedPhaseRef.current = null; setSelectionView("setup"); }}><span className="analysis-number">00</span><span className="analysis-name">Select Analyses</span><span className="analysis-status">•</span></button>{analyses.map((analysis, index) => { const complete = completedPhases.includes(analysis.id); return <button key={analysis.id} className={`analysis-tab ${activePhase === analysis.id ? "active" : ""} ${!complete ? "locked" : ""}`} onClick={() => { if (complete) { viewedCompletedPhaseRef.current = analysis.id; setSelectionView(null); setActivePhase(analysis.id); } }} disabled={!complete}><span className="analysis-number">{String(index + 1).padStart(2, "0")}</span><span className="analysis-name">{analysis.label}</span><span className={`analysis-status ${complete ? "done" : ""}`}>{complete ? "✓" : "•"}</span></button>; })}</nav>{runId && !isDemo && completedPhases.length > 0 && <a className="download-button" href={`${API_BASE_URL}/api/analysis/${runId}/download`} download="financial-analysis.zip">Download completed work</a>}<button className="new-analysis" onClick={resetAnalysis} disabled={loading || stopping}>+ New repository</button></aside>
      <main className="content">
        {selectionView === "setup" ? <section className="selection-panel"><div className="eyebrow">ANALYSIS SETUP</div><h1>Continue analysis</h1><p className="section-intro">Select additional analyses to run in this repository workspace. Completed analyses remain readable here and are not rerunnable in V1. To rerun a completed analysis, open a new browser tab/workspace.</p><fieldset className="analysis-selection"><legend>Run analyses</legend><div className="analysis-selection-grid">{analyses.map((analysis) => { const complete = completedPhases.includes(analysis.id); return <label key={analysis.id} className="analysis-option"><input type="checkbox" checked={!complete && selectedPhases.includes(analysis.id)} onChange={() => setSelectedPhases((previous) => previous.includes(analysis.id) ? previous.filter((id) => id !== analysis.id) : [...previous, analysis.id])} disabled={loading || stopping || complete} /><span>{analysis.label}{complete ? " (completed)" : ""}</span></label>; })}</div></fieldset><form onSubmit={analyze} className="repo-form"><input value={companyName} onChange={(event) => setCompanyName(event.target.value)} placeholder="Company name or SEC Company Facts JSON URL" type="text" required aria-label="Company name or SEC Company Facts JSON URL" disabled={true} readOnly /><button type="submit" disabled={loading || stopping}>{loading ? "Running..." : "Run selected analyses"}</button></form>{error && <div className="error-banner" role="alert">{error}</div>}</section>
        : isDemo ? <><section className="completion-banner"><div><div className="eyebrow">EXAMPLE DOCUMENTATION</div><h1>{companyName === "INFY" ? DEMOS.infy.title : DEMOS.ibm.title}</h1><p>Browse the pre-generated twelve-analysis reverse-engineering documentation.</p></div><div className="completion-mark">✓</div></section><section className="dossier-content"><div className="eyebrow">STAGE {String(analyses.findIndex((analysis) => analysis.id === activePhase) + 1).padStart(2, "0")}</div><h2>{activePhaseDefinition.label}</h2><p className="section-intro">Pre-generated financial analysis documentation for {companyName === "INFY" ? "INFY" : "IBM"}.</p><article className="evidence-card markdown-content">{demoFolder ? <iframe key={`${demoFolder}/${activePhase}.html`} src={`/${demoFolder}/${activePhase}.html`} title={`${companyName} ${activePhaseDefinition.label}`} style={{ width: "100%", minHeight: "900px", border: 0, display: "block", background: "white" }} /> : <div className="mermaid-loading">Loading demo documentation...</div>}</article></section></>
        : <>{loading && <section className="progress-screen"><div className="spinner"/><div><div className="eyebrow">ANALYSIS IN PROGRESS</div><h1>Results are arriving progressively</h1><p>{progressText}</p>{stopping ? <p style={{ fontWeight: 700 }}>Stop requested. Waiting for the current backend work to unwind safely.</p> : <button type="button" onClick={stopAnalysis} disabled={stopping} style={{ minHeight: 42, padding: "0 16px", border: "1px solid #b42318", borderRadius: 8, background: "white", color: "#b42318", fontWeight: 700 }}>{stopping ? "Stopping analysis..." : "Stop analysis"}</button>}{completionMessages.length > 0 && <div className="completion-messages" aria-live="polite">{completionMessages.map((message) => <div key={message}>{message}</div>)}</div>}</div></section>}
          {stopped && <section className="completion-banner" style={{ borderColor: "#ead9c5", background: "#fffaf3" }}><div><div className="eyebrow">ANALYSIS STOPPED</div><h1>The analysis was stopped by the user.</h1><p>{completedPhases.length} of {denominator} analyses completed before stop.</p><button type="button" onClick={resetAnalysis} style={{ marginTop: 14, minHeight: 42, padding: "0 16px", border: 0, borderRadius: 8, background: "var(--accent)", color: "white", fontWeight: 700 }}>Back to Main Page</button></div></section>}
          {analysisComplete && <section className="completion-banner"><div><div className="eyebrow">REVERSE ENGINEERING COMPLETE</div><h1>Your financial dossier is ready.</h1><p>Visit the individual analysis tabs on the left to explore the Financial Dossier.</p></div><div className="completion-mark">✓</div>{runId && <a className="download-button" href={`${API_BASE_URL}/api/analysis/${runId}/download`} download="financial-analysis.zip">Download ZIP</a>}</section>}
          {activeResult && <section className="dossier-content"><div className="eyebrow">STAGE {String(analyses.findIndex((analysis) => analysis.id === activePhase) + 1).padStart(2, "0")}</div><h2>{activePhaseDefinition.label}</h2><p className="section-intro">Analysis returned by the backend financial analysis pipeline for this financial analysis.{provenance ? ` Model: ${provenance.model}` : ""}</p><article className="evidence-card markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code({ className, children, ...props }) { if (/language-mermaid/.test(className || "")) return <MermaidDiagram chart={String(children).replace(/\n$/, "")} />; return <code className={className} {...props}>{children}</code>; } }}>{activeResult}</ReactMarkdown></article></section>}
          {!loading && !stopped && !analysisComplete && !activeResult && error && <section className="progress-screen"><div><div className="eyebrow">ANALYSIS FAILED</div><h1>The analysis could not continue.</h1><p>{error}</p></div></section>}
        </>}
      </main>
    </div>}
  </div>;
}
