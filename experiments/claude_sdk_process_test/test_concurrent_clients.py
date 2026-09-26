"""Concurrent Claude Agent SDK client experiment.

This experiment is intentionally independent of the ReverseEngineer-SDLC
application. It tests whether independently constructed ClaudeSDKClient
instances create independently running Claude Code subprocesses.

Unlike the first version, this script continuously samples the descendant
process tree while requests are running. Each request is deliberately held
open after receiving its response so short model responses cannot cause the
Claude subprocess to disappear before the measurement occurs.
"""

import asyncio
import os
import sys
from collections.abc import Iterable

import psutil
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient


REQUEST_COUNT = int(os.environ.get("CLAUDE_TEST_REQUESTS", "3"))
MODEL = os.environ.get("OPENROUTER_MODEL")
API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Do not inherit a stale ANTHROPIC_BASE_URL from the shell. This experiment is
# specifically testing OpenRouter's Anthropic-compatible endpoint.
ENDPOINT = "https://openrouter.ai/api"
HOLD_SECONDS = float(os.environ.get("CLAUDE_TEST_HOLD_SECONDS", "10"))
SAMPLE_SECONDS = float(os.environ.get("CLAUDE_TEST_SAMPLE_SECONDS", "0.5"))


def mb(value: int) -> float:
    return value / (1024 * 1024)


def cmdline(process: psutil.Process) -> str:
    try:
        return " ".join(process.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return "<unavailable>"


def descendants(root: psutil.Process) -> Iterable[psutil.Process]:
    try:
        return sorted(root.children(recursive=True), key=lambda p: p.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return []


def _is_claude(process: psutil.Process) -> bool:
    try:
        return process.name().lower() in {"claude.exe", "claude"}
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def snapshot(label: str, verbose: bool = True) -> tuple[int, float]:
    root = psutil.Process(os.getpid())
    children = list(descendants(root))

    total_rss = 0.0
    visible_children: list[tuple[psutil.Process, float]] = []
    for child in children:
        try:
            rss = mb(child.memory_info().rss)
            total_rss += rss
            visible_children.append((child, rss))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    claude_count = sum(1 for process, _ in visible_children if _is_claude(process))

    if verbose:
        print("\n" + "=" * 100)
        print(f"SNAPSHOT: {label}")
        print("=" * 100)
        print(
            f"ROOT pid={root.pid} name={root.name()} "
            f"rss={mb(root.memory_info().rss):.1f} MB"
        )
        if not visible_children:
            print("DESCENDANTS: <none>")
        else:
            for child, rss in visible_children:
                print(
                    f"CHILD pid={child.pid} ppid={child.ppid()} "
                    f"name={child.name()} rss={rss:.1f} MB "
                    f"cmd={cmdline(child)}"
                )
            print(f"DESCENDANT RSS TOTAL={total_rss:.1f} MB")
            print(f"CLAUDE-EXE COUNT={claude_count}")

    return claude_count, total_rss


async def run_one_request(number: int, ready: asyncio.Event) -> str:
    request_prompt = f"Reply with exactly: concurrent-{number}"

    options = ClaudeAgentOptions(
        model=MODEL,
        permission_mode="bypassPermissions",
        allowed_tools=[],
        env={
            "ANTHROPIC_BASE_URL": ENDPOINT,
            "ANTHROPIC_AUTH_TOKEN": API_KEY,
            "ANTHROPIC_API_KEY": "",
            "ANTHROPIC_MODEL": MODEL,
            "ANTHROPIC_SMALL_FAST_MODEL": MODEL,
        },
    )

    async with ClaudeSDKClient(options=options) as client:
        # Signal as soon as this independently constructed client has entered
        # its context. The monitor then samples the process tree continuously.
        ready.set()

        await client.query(request_prompt)
        final_text = ""
        async for message in client.receive_response():
            text = getattr(message, "result", None)
            if text:
                final_text = text

        # Keep the client and its Claude subprocess alive after the model has
        # responded, making the concurrent process state observable.
        await asyncio.sleep(HOLD_SECONDS)
        return final_text


async def monitor(tasks: list[asyncio.Task[str]]) -> tuple[int, float]:
    max_claude_count = 0
    max_rss = 0.0
    sample = 0

    while not all(task.done() for task in tasks):
        sample += 1
        claude_count, total_rss = snapshot(
            f"concurrent monitor sample {sample}",
            verbose=False,
        )
        max_claude_count = max(max_claude_count, claude_count)
        max_rss = max(max_rss, total_rss)
        print(
            f"MONITOR sample={sample} claude_exe_count={claude_count} "
            f"descendant_rss={total_rss:.1f} MB"
        )
        await asyncio.sleep(SAMPLE_SECONDS)

    return max_claude_count, max_rss


async def main() -> None:
    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    if not MODEL:
        raise RuntimeError("OPENROUTER_MODEL is not set")
    if REQUEST_COUNT < 1:
        raise RuntimeError("CLAUDE_TEST_REQUESTS must be at least 1")

    print("Claude Agent SDK concurrent-client process experiment")
    print(f"Python executable: {sys.executable}")
    print(f"Parent PID: {os.getpid()}")
    print(f"Concurrent application-like requests: {REQUEST_COUNT}")
    print(f"Endpoint: {ENDPOINT}")
    print(f"Requested model: {MODEL}")
    print(f"API key present: {'yes' if API_KEY else 'no'} (value intentionally not printed)")
    print(f"Post-response client hold: {HOLD_SECONDS:.1f} seconds")
    print(f"Process sample interval: {SAMPLE_SECONDS:.1f} seconds")

    snapshot("before concurrent clients")

    ready_events = [asyncio.Event() for _ in range(REQUEST_COUNT)]
    tasks = [
        asyncio.create_task(run_one_request(i, ready_events[i - 1]))
        for i in range(1, REQUEST_COUNT + 1)
    ]

    # Wait until every independently constructed client has entered its SDK
    # context, then continuously monitor while they execute.
    await asyncio.gather(*(event.wait() for event in ready_events))
    snapshot("all concurrent clients started")

    max_claude_count, max_rss = await monitor(tasks)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    print("\n" + "=" * 100)
    print("RESULTS")
    print("=" * 100)
    for index, result in enumerate(results, start=1):
        if isinstance(result, Exception):
            print(f"REQUEST {index}: ERROR {type(result).__name__}: {result}")
        else:
            print(f"REQUEST {index}: {result!r}")

    print("\n" + "=" * 100)
    print("CONCURRENCY SUMMARY")
    print("=" * 100)
    print(f"Maximum simultaneously observed claude.exe processes: {max_claude_count}")
    print(f"Maximum observed descendant RSS: {max_rss:.1f} MB")
    print(f"Requested concurrent clients: {REQUEST_COUNT}")

    snapshot("immediately after concurrent clients complete")
    await asyncio.sleep(2)
    snapshot("two seconds after all clients complete")


if __name__ == "__main__":
    asyncio.run(main())
