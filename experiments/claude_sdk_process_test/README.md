# Claude Agent SDK process and OpenRouter experiment

This experiment is independent of the ReverseEngineer-SDLC application. It answers two architectural questions together: whether the Claude Agent SDK launches and reuses a Claude Code subprocess, and whether the same SDK can route to a non-Anthropic model through OpenRouter.

The script starts one long-lived `ClaudeSDKClient`, records the current process tree before and after the client starts, sends three sequential queries through the same client, and records the process tree after every query. It then exits the client context and records the process tree again.

The model is deliberately not hard-coded. Set `OPENROUTER_MODEL` to an exact model ID available in your OpenRouter account, including a free-model ID if desired. This makes the experiment explicitly test a non-Anthropic model instead of silently falling back to a Claude default.

The experiment configures the Agent SDK with OpenRouter's Anthropic-compatible endpoint and passes the OpenRouter API key to the CLI subprocess using `ANTHROPIC_AUTH_TOKEN`. It also explicitly clears `ANTHROPIC_API_KEY` to prevent an Anthropic credential from taking precedence.

## Install

```powershell
pip install claude-agent-sdk psutil
```

## Configure PowerShell

Do not put the API key in the Python source file. Set it in the current shell:

```powershell
$env:OPENROUTER_API_KEY = "your-openrouter-key"
$env:OPENROUTER_MODEL = "your-exact-openrouter-model-id"
```

Use the OpenRouter model catalog to obtain the exact current model ID. If testing a free model, include the exact free-model suffix if OpenRouter lists one for that model.

## Run

```powershell
python experiments\claude_sdk_process_test\test_process_lifecycle.py
```

The important comparison is the snapshot labelled `after client start` versus the snapshots after query 1, 2, and 3. If the same child-process PID remains present across all three queries, that is evidence that one SDK client reuses one subprocess rather than starting a new subprocess for every query. If additional processes appear for each query or remain after client shutdown, that will also be visible.

A successful run is also evidence that the Agent SDK has actually sent requests through OpenRouter rather than directly to Anthropic. Verify this independently in the OpenRouter activity dashboard while running the experiment.

This routing mechanism is based on OpenRouter's documented Anthropic-compatible API and its documented Claude Code integration. Non-Anthropic model use through this path should still be treated as an integration experiment rather than equivalent to first-party Anthropic support.
