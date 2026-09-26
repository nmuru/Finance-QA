"use client";

export default function SessionExpiredPage() {
  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "32px", background: "#fff", color: "#111" }}>
      <section style={{ width: "100%", maxWidth: "560px", textAlign: "center" }}>
        <h1 style={{ margin: 0, fontSize: "32px" }}>Session Expired</h1>
        <p style={{ margin: "16px 0 24px", lineHeight: 1.6 }}>
          This analysis session has expired. Start a new analysis to continue.
        </p>
        <button
          type="button"
          onClick={() => window.location.replace("/")}
          style={{ padding: "10px 18px", border: "1px solid #111", borderRadius: "6px", background: "#111", color: "#fff", cursor: "pointer" }}
        >
          Start New Analysis
        </button>
      </section>
    </main>
  );
}
