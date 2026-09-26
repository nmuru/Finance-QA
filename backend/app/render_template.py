"""Phase-specific renderer template loading."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_SOURCE = PROJECT_ROOT / ".agents" / "skills"


def load_render_template(phase: str) -> str:
    """Load the presentation template from the skill directory for a phase."""
    phase_name = (phase or "").strip()
    if not phase_name:
        raise ValueError("phase cannot be empty")

    candidate = SKILLS_SOURCE / phase_name / "OUTPUT_TEMPLATE.md"
    if not candidate.is_file():
        raise FileNotFoundError(
            f"No OUTPUT_TEMPLATE.md found for phase '{phase_name}' at '{candidate}'."
        )

    return candidate.read_text(encoding="utf-8", errors="replace")
