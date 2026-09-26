from app.renderer import render_analysis
import os


DUMMY_RAW_ANALYSIS = """
# Business Purpose Analysis

## Purpose

CareerPro-v2 is a web application intended to help users prepare
career-related documents and application materials.

## Observed Components

The repository contains a frontend and backend structure.

The application includes functionality related to resume preparation,
document generation, and career workflows.

## Evidence

The source analysis identified multiple application components and
configuration files.

## Limitations

This is dummy analysis text used only to test the presentation renderer.
It must not trigger repository exploration or OpenCode execution.
"""


def main():
    provider = "openrouter"
    model = "z-ai/glm-5.3-flash"

    # Paste the same BYOK key that you enter in the frontend here temporarily.
   

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") 

    print("Calling renderer only...")
    print(f"Provider: {provider}")
    print(f"Model: {model}")

    result = render_analysis(
        phase="business-purpose",
        analysis=DUMMY_RAW_ANALYSIS,
        provider=provider,
        model=model,
        api_key=api_key,
        timeout=300,
    )

    print("\n--- RENDERER RESULT ---\n")
    print(result)


if __name__ == "__main__":
    main()