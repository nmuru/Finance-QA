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
  const [companyName, setCompanyName] = useState("");
  const [query, setQuery] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function askQuestion(event: FormEvent) {
    event.preventDefault();

    const company = companyName.trim();
    const question = query.trim();

    if (!company || !question) {
      setError("Enter both Company Name and Your Query.");
      return;
    }

    setLoading(true);
    setAnswer("");
    setError("");

    try {
      const formData = new FormData();
      formData.append("company_name", company);
      formData.append("query", question);
      files.forEach((file) => formData.append("files", file));

      const response = await fetch(`${API_BASE_URL}/api/analyze`, {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
        },
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
          <div className="tagline">Ask questions about a company’s financials</div>
        </div>
      </header>

      <main className="landing">
        <div className="landing-card">
          <div className="eyebrow">FINANCE QA</div>
          <h1>Ask a financial question about a company.</h1>

          <form onSubmit={askQuestion} className="repo-form qa-form">
            <label className="qa-field">
              <span>Company Name</span>
              <input
                value={companyName}
                onChange={(event) => setCompanyName(event.target.value)}
                placeholder="e.g. Infosys"
                required
                disabled={loading}
              />
            </label>

            <label className="qa-field">
              <span>Your Query</span>
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="e.g. How resilient are the company’s earnings and cash generation?"
                rows={6}
                required
                disabled={loading}
              />
            </label>

            <label className="qa-field">
              <span>Supporting Documents <small>(optional)</small></span>
              <input
                type="file"
                multiple
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setFiles(Array.from(event.target.files ?? []))
                }
                disabled={loading}
              />
              {files.length > 0 && (
                <small>{files.length} file{files.length === 1 ? "" : "s"} selected</small>
              )}
            </label>

            <button type="submit" disabled={loading}>
              {loading ? "Answering..." : "Ask Finance QA"}
            </button>
          </form>

          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}

          {answer && (
            <section className="answer-panel">
              <div className="eyebrow">ANSWER</div>
              <h2>{companyName}</h2>
              <div className="answer-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown></div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
