"""OpenAI Agents SDK concurrent process-overhead experiment.

This experiment mirrors the Claude Agent SDK concurrent-client experiment,
but uses the OpenAI Agents SDK with OpenRouter's OpenAI-compatible endpoint.

The purpose is specifically to determine whether concurrent agent runs spawn
heavyweight local agent/CLI subprocesses. It continuously inspects the Python
process tree while several independent agent runs execute concurrently.
"""

import asyncio
import os
import sys

import psutil
from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    set_tracing_disabled,
)
from openai import AsyncOpenAI


REQUEST_COUNT = int(os.environ.get("OPENAI_AGENT_TEST_REQUESTS", "3"))
MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
API_KEY = os.environ.get("OPENROUTER_API_KEY")
ENDPOINT = "https://openrouter.ai/api/v1"
SAMPLE_SECONDS = float(os.environ.get("OPENAI_AGENT_TEST_SAMPLE_SECONDS", "0.5"))


def mb(value: int) -> float:
    return value / (1024 * 1024)


def cmdline(process: psutil.Process) -> str:
    try:
        return " ".join(process.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return "<unavailable>"


def snapshot(label: str, verbose: bool = True) -> tuple[int, float]:
    root = psutil.Process(os.getpid())
    try:
        descendants = sorted(root.children(recursive=True), key=lambda p: p.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        descendants = []

    total_rss = 0.0
    visible = []
    for child in descendants:
        try:
            rss = mb(child.memory_info().rss)
            total_rss += rss
            visible.append((child, rss))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if verbose:
        print("\n" + "=" * 100)
        print(f"SNAPSHOT: {label}")
        print("=" * 100)
        print(f"ROOT pid={root.pid} name={root.name()} rss={mb(root.memory_info().rss):.1f} MB")
        if not visible:
            print("DESCENDANTS: <none>")
        else:
            for child, rss in visible:
                print(
                    f"CHILD pid={child.pid} ppid={child.ppid()} "
                    f"name={child.name()} rss={rss:.1f} MB cmd={cmdline(child)}"
                )
            print(f"DESCENDANT RSS TOTAL={total_rss:.1f} MB")

    return len(visible), total_rss


async def run_one_agent(number: int, started: asyncio.Event) -> str:
    # A separate Agent object represents the same architectural pattern as
    # separate application requests, while still using one Python process.
    client = AsyncOpenAI(api_key=API_KEY, base_url=ENDPOINT)
    model = OpenAIChatCompletionsModel(model=MODEL, openai_client=client)

    agent = Agent(
        name=f"ConcurrentAgent{number}",
        instructions="Reply with exactly the requested text and nothing else.",
        model=model,
    )

    started.set()
    result = await Runner.run(agent, f"Reply with exactly: openai-concurrent-{number}")
    await client.close()
    return str(result.final_output)


async def monitor(tasks: list[asyncio.Task[str]]) -> tuple[int, float]:
    max_child_count = 0
    max_rss = 0.0
    sample = 0

    while not all(task.done() for task in tasks):
        sample += 1
        child_count, total_rss = snapshot(f"monitor sample {sample}", verbose=False)
        max_child_count = max(max_child_count, child_count)
        max_rss = max(max_rss, total_rss)
        print(
            f"MONITOR sample={sample} descendant_processes={child_count} "
            f"descendant_rss={total_rss:.1f} MB"
        )
        await asyncio.sleep(SAMPLE_SECONDS)

    return max_child_count, max_rss


async def main() -> None:
    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    if REQUEST_COUNT < 1:
        raise RuntimeError("OPENAI_AGENT_TEST_REQUESTS must be at least 1")

    # OpenRouter is being used for model traffic, so disable OpenAI tracing to
    # avoid requiring an unrelated OpenAI platform API key.
    set_tracing_disabled(disabled=True)

    print("OpenAI Agents SDK concurrent process-overhead experiment")
    print(f"Python executable: {sys.executable}")
    print(f"Parent PID: {os.getpid()}")
    print(f"Concurrent application-like requests: {REQUEST_COUNT}")
    print(f"Endpoint: {ENDPOINT}")
    print(f"Requested model: {MODEL}")
    print(f"API key present: {'yes' if API_KEY else 'no'} (value intentionally not printed)")
    print(f"Process sample interval: {SAMPLE_SECONDS:.1f} seconds")

    snapshot("before concurrent agent runs")

    started_events = [asyncio.Event() for _ in range(REQUEST_COUNT)]
    tasks = [
        asyncio.create_task(run_one_agent(i, started_events[i - 1]))
        for i in range(1, REQUEST_COUNT + 1)
    ]

    await asyncio.gather(*(event.wait() for event in started_events))
    snapshot("all concurrent agent runs started")

    max_child_count, max_rss = await monitor(tasks)
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
    print(f"Maximum simultaneously observed descendant processes: {max_child_count}")
    print(f"Maximum observed descendant RSS: {max_rss:.1f} MB")
    print(f"Requested concurrent agents: {REQUEST_COUNT}")

    snapshot("immediately after concurrent agent runs complete")
    await asyncio.sleep(2)
    snapshot("two seconds after all agent runs complete")


if __name__ == "__main__":
    asyncio.run(main())
