"""Independent Claude Agent SDK process-lifecycle and OpenRouter experiment.

This script intentionally contains no ReverseEngineer-SDLC application code.
It tests two questions together:

1. Does one long-lived ClaudeSDKClient launch child processes that are reused
   across several sequential queries?
2. Can the Claude Agent SDK route those queries to a non-Anthropic model through
   OpenRouter's Anthropic-compatible Messages API?

No API key is stored in this file. Configure the environment before running.
"""

import asyncio
import os
import sys
from typing import Iterable

import psutil
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient


OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL")

PROMPTS = [
    "Reply with exactly: query-one",
    "Reply with exactly: query-two",
    "Reply with exactly: query-three",
]


def _mb(value: int) -> float:
    return value / (1024 * 1024)


def _safe_cmdline(process: psutil.Process) -> str:
    try:
        return " ".join(process.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return "<unavailable>"


def descendants(root: psutil.Process) -> Iterable[psutil.Process]:
    try:
        return sorted(root.children(recursive=True), key=lambda p: p.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return []


def snapshot(label: str) -> None:
    root = psutil.Process(os.getpid())
    print("\n" + "=" * 88)
    print(f"SNAPSHOT: {label}")
    print("=" * 88)
    print(
        f"ROOT  pid={root.pid} name={root.name()} "
        f"rss={_mb(root.memory_info().rss):.1f} MB "
        f"cmd={_safe_cmdline(root)}"
    )

    children = list(descendants(root))
    if not children:
        print("CHILDREN: <none>")
        return

    for child in children:
        try:
            memory = _mb(child.memory_info().rss)
            print(
                f"CHILD pid={child.pid} ppid={child.ppid()} "
                f"name={child.name()} rss={memory:.1f} MB "
                f"cmd={_safe_cmdline(child)}"
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            print(f"CHILD pid={child.pid} <process disappeared or inaccessible>")


async def run_query(client: ClaudeSDKClient, prompt: str, number: int) -> None:
    print(f"\n--- QUERY {number}: {prompt!r} ---")
    await client.query(prompt)

    response_count = 0
    async for message in client.receive_response():
        response_count += 1
        text = getattr(message, "result", None)
        if text:
            print(f"RESULT: {text}")

    print(f"QUERY {number} completed; received {response_count} SDK messages")


async def main() -> None:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Set it in the shell before running this experiment."
        )
    if not OPENROUTER_MODEL:
        raise RuntimeError(
            "OPENROUTER_MODEL is not set. Set it to an exact OpenRouter model ID, "
            "for example a currently available free model ID."
        )

    print("Claude Agent SDK process-lifecycle and OpenRouter experiment")
    print(f"Python executable: {sys.executable}")
    print(f"Python PID: {os.getpid()}")
    print("Endpoint: https://openrouter.ai/api")
    print(f"Requested model: {OPENROUTER_MODEL}")
    print("API key present: yes (value intentionally not printed)")
    print("This process remains alive while all queries execute.")

    snapshot("before client construction")

    # OpenRouter exposes an Anthropic-compatible Messages API at /api/v1/messages.
    # Claude Code / the Agent SDK use the base URL https://openrouter.ai/api, and
    # the model ID is passed through to the configured endpoint.
    options = ClaudeAgentOptions(
        model=OPENROUTER_MODEL,
        permission_mode="bypassPermissions",
        allowed_tools=[],
        env={
            "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
            "ANTHROPIC_AUTH_TOKEN": OPENROUTER_API_KEY,
            # Explicitly blank this to avoid an Anthropic key taking precedence.
            "ANTHROPIC_API_KEY": "",
            "ANTHROPIC_MODEL": OPENROUTER_MODEL,
            "ANTHROPIC_SMALL_FAST_MODEL": OPENROUTER_MODEL,
        },
    )

    async with ClaudeSDKClient(options=options) as client:
        snapshot("after client start, before first query")

        for number, prompt in enumerate(PROMPTS, start=1):
            await run_query(client, prompt, number)
            snapshot(f"after query {number}")

        print("\nKeeping the same client open for 10 seconds for inspection...")
        await asyncio.sleep(10)
        snapshot("same client after 10-second idle period")

    print("\nClaudeSDKClient context has exited.")
    await asyncio.sleep(2)
    snapshot("after client shutdown")


if __name__ == "__main__":
    asyncio.run(main())
