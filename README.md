# Agentic RAG for financial Q&A and benchmark evaluation

RAG Finance QA is an agentic financial question-answering application built to explore retrieval-augmented generation for financial analysis and benchmark evaluation without conventional vector search based retrieval. 

The current version uses an agent to decide what evidence is needed for a user's financial question, retrieve only the relevant evidence through read-only tools, and produce an evidence-based answer.

The key experiment is **Agentic RAG without a traditional vector-search layer**. Instead of embedding the entire evidence corpus and relying on similarity search, the agent can directly address structured SEC financial data and, when supplied, user documents in a temporary workspace.

This is an evaluation-oriented project rather than a production financial-advice application.

## What is different about this version?

The application started as a codebase-analysis / financial-dossier workflow. The current V1 query path has been simplified into a focused financial QA agent.

The agent:

1. Receives a company and a financial question.
2. Reads the relevant query/financial skill guidance.
3. Determines what evidence is actually needed.
4. Retrieves targeted financial evidence using the available tools.
5. Prefers SEC financial data for reported financial facts.
6. Can read optional user-provided documents directly from the temporary workspace.
7. Distinguishes reported facts, calculations, and analytical inference.
8. Returns a concise answer with relevant periods and figures.

The previous multi-phase financial dossier pipeline is still retained in the codebase for possible future integration; it is not used by the current /api/analyze query path.

## Why benchmark it?

Simple financial QA is increasingly easy for strong general-purpose models, so the interesting question is not simply whether an LLM can answer a finance question.

This project is intended to test whether a relatively small agentic retrieval architecture can reliably solve harder financial QA tasks by choosing and retrieving the right evidence.

Initial experiments include questions from:

- **FinanceBench** — the PatronusAI financial QA benchmark.
- **BigBench Finance / related finance benchmark datasets**.
- Custom difficult financial questions requiring multi-step reasoning over financial statements and numerical evidence.

Some difficult benchmark questions can also expose practical agent limitations such as context limits, token limits, or maximum-turn limits. Those failure modes are part of the evaluation rather than being hidden.

The current results are exploratory. A systematic benchmark run is still needed before making claims about overall accuracy or superiority over other retrieval approaches.

## RAG without vector search

This project does not currently build a vector database for financial evidence.

The retrieval strategy is based on **tool-addressable evidence**:

- SEC/company financial data is downloaded into the run workspace.
- Financial statements and structured data can be retrieved through dedicated tools.
- Targeted XBRL/JSON retrieval can be used when appropriate.
- Optional supporting documents are copied into the temporary workspace.
- The agent can use list_files and read_file to inspect those documents when relevant.

The important distinction is that this is not claiming vector search is obsolete. It is an experiment in whether an agent can perform useful RAG over structured and directly addressable evidence without adding an embedding/vector-search layer.

## Optional supporting documents

Supporting documents are optional.

For benchmark experiments, the intended baseline can be **SEC-only**, allowing the agent to answer from the financial evidence it retrieves itself.

Users can also upload additional documents when testing questions that require information outside the SEC evidence. Uploaded files are:

- limited to 10 files per query;
- limited to 5 MB per file;
- limited to 20 MB combined;
- copied into the run's temporary uploaded-documents/ workspace;
- available to the agent through the existing read-only file tools;
- not embedded into a vector database.

## Providers and models

The backend supports the provider/model configuration implemented by the application. OpenRouter can be used to experiment with different models, which is useful for benchmark comparisons.

The application does not silently switch models when a provider or model fails. Authentication, rate-limit, unavailable-model, and provider errors are surfaced to the user.

Actual performance and token usage depend on the selected model, provider limits, agent instructions, retrieved evidence, and question difficulty.

## Model and API key configuration

The V1 web UI uses **BYOK (Bring Your Own Key)**. Before running a query, the user selects a supported provider, enters a model ID, and supplies that provider's API key.

Currently supported providers are:

- **OpenRouter**
- **OpenAI**

The API key is sent with the active request over HTTPS, held in memory while that request runs, and is not written to Finance QA's database, workspace, provenance, or frontend storage. Provider spending limits remain under the user's provider account.

For OpenRouter, a convenient model value for testing is:

    openrouter/free

The backend still retains its environment configuration for legacy/internal agent paths, but the public V1 `/api/analyze` endpoint uses the provider, model, and API key supplied with each request.


## Local development

This project is currently intended to run locally. It is **not deployed on Vercel**.

A local setup is preferable for the current benchmark/evaluation stage because it makes the model, provider, prompts, tools, retrieved evidence, and runtime behavior easier to inspect and reproduce.

### Requirements

Install:

- **Git**
- **Python 3.11+**
- **Node.js 20.9+**
- An API key for the AI provider/model you want to use
- An **EDGAR identity** for SEC access

Set your EDGAR identity before starting the backend:

    set EDGAR_IDENTITY=Your Name your.email@example.com

Use your own name and email address rather than the example above.

### Quick start on Windows

Clone the repository:

    git clone https://github.com/nmuru/Finance-QA.git
    cd Finance-QA

Then start the application:

    set EDGAR_IDENTITY=Your Name your.email@example.com
    start.bat

The frontend normally runs at:

**http://localhost:3000**

The backend normally runs at:

**http://localhost:8000**

Enter the company and financial question in the application. Configure the model and API key in the backend environment as described above.

### Manual startup

If start.bat contains paths specific to the author's machine or does not work on your system, start the services manually.

Create the backend environment and install dependencies:

    cd backend
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt

Start the backend in one terminal:

    cd backend
    set EDGAR_IDENTITY=Your Name your.email@example.com
    .venv\Scripts\python.exe -m uvicorn app.main:app --reload

In a second terminal, install and start the frontend:

    cd frontend
    npm install
    npm run dev

Open:

**http://localhost:3000**

## Typical benchmark workflow

For a reproducible benchmark experiment:

1. Start the application locally.
2. Use the benchmark question as the query.
3. Provide the corresponding company.
4. Leave supporting documents empty when testing the SEC-only baseline.
5. Record the final answer and any execution failure.
6. Repeat with the same model/configuration across the benchmark set.
7. Compare accuracy as well as failure modes such as context overflow, token limits, and maximum agent turns.

The goal is to evaluate the retrieval-and-agent architecture, not just whether a particular model can answer an isolated question.

## Architecture

At a high level:

    User
      |
      v
    Next.js UI
      |
      v
    FastAPI /api/analyze
      |
      v
    Query Agent
      |
      +---- Query / Financial Skills
      |
      +---- SEC Financial Tools
      |
      +---- Structured XBRL / JSON Retrieval
      |
      +---- Optional Uploaded Documents
      |          |
      |          +---- list_files
      |          +---- read_file
      |
      v
    Evidence-based Financial Answer

There is no vector database in this path.

The retrieval mechanism is instead driven by the agent's evidence requirements and the available tools.

## Current limitations

This is a research/demo and benchmark-oriented implementation.

Important limitations include:

- benchmark coverage is still being expanded;
- systematic accuracy measurements have not yet been published;
- difficult questions can exceed model context or token limits;
- agent runs can reach maximum-turn limits;
- different models may behave very differently on the same question;
- SEC evidence may be insufficient for questions requiring information outside reported filings;
- uploaded documents are supplemental evidence rather than a fully indexed document corpus.

These limitations are useful evaluation signals rather than reasons to hide failed runs.

## Project status

The current focus is:

**Agentic RAG + financial tools + benchmark evaluation**

The next stage is to run larger benchmark sets systematically and investigate where the agent succeeds, where it fails, and which retrieval/agent strategies improve reproducibility and accuracy.

Repository:

https://github.com/nmuru/Finance-QA
