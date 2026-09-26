from pathlib import Path
import time
import os


import requests

from app.renderer import render_analysis


SOURCE_DIR = Path(
    r"C:\ReverseEngineer-SDLC\ReverseEngineer-SDLC-OpenCode-v2"
    r"\ReverseEngineer-SDLC\backend\output-content"
    r"\ec68ea08c3104bd5913ac0a91776ec2a"
)

DESTINATION_DIR = Path(
    r"C:\ReverseEngineer-SDLC\ReverseEngineer-SDLC-OpenCode-v2"
    r"\ReverseEngineer-SDLC\frontend\public\vercel-demo"
)


PROVIDER = "openrouter"
MODEL = "openrouter/free"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") 

PHASES = [
    "business-purpose",
    "features",
    "business-requirements",
    "technology-architecture",
    "design-pattern",
    "software-requirements",
    "high-level-design",
    "low-level-design",
    "implementation-detail",
    "testing-harness",
    "future-directions",
]


MAX_RETRIES = 5
RETRY_BASE_SECONDS = 30
WAIT_BETWEEN_PHASES = 20


def is_complete(destination_file: Path) -> bool:
    return (
        destination_file.exists()
        and destination_file.is_file()
        and destination_file.stat().st_size > 0
    )


def get_status_code(exc: Exception):
    if isinstance(exc, requests.exceptions.HTTPError):
        if exc.response is not None:
            return exc.response.status_code
    return None


def main():
    DESTINATION_DIR.mkdir(parents=True, exist_ok=True)

    for phase in PHASES:
        source_file = SOURCE_DIR / phase / "opencode-output.md"
        destination_file = DESTINATION_DIR / f"{phase}.md"

        if not source_file.exists():
            print(f"SKIPPING: source not found: {source_file}")
            continue

        # Preserve work already completed successfully.
        if is_complete(destination_file):
            print(f"ALREADY COMPLETE: {phase}")
            continue

        print(f"\nRendering phase: {phase}")

        raw_analysis = source_file.read_text(
            encoding="utf-8",
            errors="replace",
        )

        success = False

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                rendered_result = render_analysis(
                    phase=phase,
                    analysis=raw_analysis,
                    provider=PROVIDER,
                    model=MODEL,
                    api_key=API_KEY,
                )

                if not rendered_result or not rendered_result.strip():
                    raise RuntimeError(
                        f"Renderer returned an empty result for {phase}"
                    )

                destination_file.write_text(
                    rendered_result,
                    encoding="utf-8",
                )

                print(f"SUCCESS: {destination_file}")
                success = True
                break

            except Exception as exc:
                status_code = get_status_code(exc)

                if status_code == 429 and attempt < MAX_RETRIES:
                    wait_seconds = RETRY_BASE_SECONDS * attempt

                    print(
                        f"RATE LIMITED for {phase}. "
                        f"Waiting {wait_seconds} seconds before retry "
                        f"{attempt + 1}/{MAX_RETRIES}..."
                    )

                    time.sleep(wait_seconds)
                    continue

                print(f"FAILED: {phase}")
                print(exc)
                break

        if success:
            print(
                f"Waiting {WAIT_BETWEEN_PHASES} seconds before the next phase..."
            )
            time.sleep(WAIT_BETWEEN_PHASES)


if __name__ == "__main__":
    main()
