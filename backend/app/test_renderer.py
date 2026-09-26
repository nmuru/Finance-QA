"""
Standalone renderer test.

Run from the backend directory:

    python -m app.test_renderer

The main() guard is required on Windows because renderer.py uses
multiprocessing with the "spawn" start method.
"""

from pathlib import Path

from .renderer import render_analysis

import os


# ---------------------------------------------------------------------------
# Set these three paths to the existing files you want to test.
# Raw strings are used so Windows backslashes are handled correctly.
# ---------------------------------------------------------------------------

analysis = Path(
    r"C:\ReverseEngineer-SDLC-v2\ReverseEngineer-SDLC\SDLC-Reverse-Engineer\backend\output-content\e04b5878e50f4026a6d7920ef009a345\business-requirements\agent-output.md"
).read_text(encoding="utf-8")

template = Path(
    r"C:\ReverseEngineer-SDLC-v2\ReverseEngineer-SDLC\SDLC-Reverse-Engineer\backend\.agents\skills\business-requirements\OUTPUT_TEMPLATE.md"
).read_text(encoding="utf-8")

OUTPUT_PATH = Path(
    r"C:\ReverseEngineer-SDLC-v2\ReverseEngineer-SDLC\SDLC-Reverse-Engineer\backend\renderer-output.md"
)




def main() -> None:
     
    result = render_analysis(
        phase="business-requirements",
        analysis=analysis,
        template=template,
        provider="openrouter",
        model="openrouter/free",
        api_key=os.environ["OPENROUTER_API_KEY"],
        timeout=300,
    )

    OUTPUT_PATH.write_text(result, encoding="utf-8")

    print(f"Renderer output written to: {OUTPUT_PATH}")
    print(f"Output characters: {len(result):,}")


if __name__ == "__main__":
    main()
