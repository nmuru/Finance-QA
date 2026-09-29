"use client";

import { ChangeEvent, FormEvent, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type QueryEvent =
  | {
      type: "query_answered";
      company_name: string;
      query: string;
      run_id: string;
      answer: string;
      provenance?: { model: string };
    }
  | { type: "analysis_failed"; error: string }
  | { type: "analysis_cancelled"; run_id: string };

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [companyName, setCompanyName] = useState("AAPL");
  const [query, setQuery] = useState(
    "What was Apple's capital allocation efficiency (dividend + buyback) as percentage of net income for 2024?",
  );
  const [provider, setProvider] = useState("openrouter");
  const [model, setModel] = useState("openrouter/free");
  const [apiKey, setApiKey] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [answer, setAnswer] = useState("");
  const [usedModel, setUsedModel] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function handleProviderChange(nextProvider: string) {
    setProvider(nextProvider);
    if (nextProvider === "openrouter" && !model.trim()) {
      setModel("openrouter/free");
    } else if (nextProvider === "openai" && model === "openrouter/free") {
      setModel("");
    }
  }

  async function askQuestion(event: FormEvent) {
    event.preventDefault();

    const company = companyName.trim();
    const question = query.trim();
    const selectedModel = model.trim();
    const selectedApiKey = apiKey.trim();

    if (!company || !question) {
      setError("Enter both a company and a financial question.");
      return;
    }
    if (!selectedModel) {
      setError("Enter the model ID you want to use.");
      return;
    }
    if (!selectedApiKey) {
      setError("Enter your API key to run this request.");
      return;
    }

    setLoading(true);
    setAnswer("");
    setUsedModel("");
    setError("");

    try {
      const formData = new FormData();
      formData.append("company_name", company);
      formData.append("query", question);
      formData.append("provider", provider);
      formData.append("model", selectedModel);
      formData.append("api_key", selectedApiKey);
      files.forEach((file) => formData.append("files", file));

      const response = await fetch(`${API_BASE_URL}/api/analyze`, {
        method: "POST",
        headers: { Accept: "text/event-stream" },
        body: formData,
      });

      if (!response.ok) {
        let message = "Unable to answer the query.";
        try {
          const data = await response.json();
          if (typeof data?.detail === "string") message = data.detail;
        } catch {}
        throw new Error(message);
      }

      if (!response.body) throw new Error("The answer stream was not available.");

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
          const lines = block
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim());

          if (!lines.length) continue;

          let data: QueryEvent;
          try {
            data = JSON.parse(lines.join("\n")) as QueryEvent;
          } catch {
            continue;
          }

          if (data.type === "query_answered") {
            setAnswer(data.answer);
            setUsedModel(data.provenance?.model || selectedModel);
            setLoading(false);
          } else if (data.type === "analysis_failed") {
            setError(data.error);
            setLoading(false);
          } else if (data.type === "analysis_cancelled") {
            setError("The query was cancelled.");
            setLoading(false);
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to answer the query.");
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="brand">Finance QA</div>
          <div className="tagline">Agentic RAG for financial questions</div>
        </div>
        <div className="byok-badge">BYOK · Bring Your Own Key</div>
      </header>

      <main className="landing">
        <div className="landing-card qa-card">
          <div className="hero-row">
            <div>
              <div className="eyebrow">FINANCE QA</div>
              <h1>Ask a financial question. Let the agent find the evidence.</h1>
              <p className="landing-copy">
                Finance QA retrieves targeted financial evidence, works through the question, and returns a concise answer with the relevant figures and periods.
              </p>
            </div>
          </div>

          <form onSubmit={askQuestion} className="qa-form">
            <div className="section-heading">
              <span>AI provider</span>
              <small>Use your own API key, or leave it blank to use the hosted default.</small>
            </div>

            <div className="provider-grid">
              <label className="qa-field">
                <span>Provider</span>
                <select
                  value={provider}
                  onChange={(event) => handleProviderChange(event.target.value)}
                  disabled={loading}
                >
                  <option value="openrouter">OpenRouter</option>
                  <option value="openai">OpenAI</option>
                </select>
              </label>

              <label className="qa-field">
                <span>Model</span>
                <input
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  placeholder="e.g. openrouter/free"
                  autoComplete="off"
                  disabled={loading}
                />
              </label>
            </div>

            <label className="qa-field">
              <span>API Key</span>
              <input
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="Paste your provider API key"
                autoComplete="new-password"
                spellCheck={false}
                disabled={loading}
              />
              <small className="field-note">
                Sent over HTTPS with this request. Finance QA does not save it.
              </small>
            </label>

            <div className="section-heading query-heading">
              <span>Financial question</span>
              <small>Company and question are required.</small>
            </div>

            <div className="provider-grid">
              <label className="qa-field">
                <span>Company</span>
                <input
                  value={companyName}
                  onChange={(event) => setCompanyName(event.target.value)}
                  placeholder="e.g. AAPL"
                  required
                  disabled={loading}
                />
              </label>

              <label className="qa-field">
                <span>Supporting documents <small>(optional)</small></span>
                <input
                  className="file-input"
                  type="file"
                  multiple
                  onChange={(event: ChangeEvent<HTMLInputElement>) =>
                    setFiles(Array.from(event.target.files ?? []))
                  }
                  disabled={loading}
                />
              </label>
            </div>

            <label className="qa-field">
              <span>Your query</span>
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ask about revenue, margins, cash flow, capital allocation, valuation, or another financial topic."
                rows={6}
                required
                disabled={loading}
              />
            </label>

            {files.length > 0 && (
              <div className="file-summary">
                <span>{files.length} document{files.length === 1 ? "" : "s"} selected</span>
                <span>{files.map((file) => file.name).join(" · ")}</span>
              </div>
            )}

            {error && (
              <div className="error-banner" role="alert">
                {error}
              </div>
            )}

            <div className="form-footer">
              <div className="privacy-note">
                <strong>Your key, your spend.</strong>
                <span>Set limits directly with your provider.</span>
              </div>
              <button type="submit" className="primary-action" disabled={loading}>
                {loading ? "Researching..." : "Ask Finance QA"}
              </button>
            </div>
          </form>

          {answer && (
            <section className="answer-panel">
              <div className="answer-header">
                <div>
                  <div className="eyebrow">ANSWER</div>
                  <h2>{companyName}</h2>
                </div>
                <div className="model-chip">{provider} · {usedModel || model}</div>
              </div>
              <div className="answer-content markdown-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
