"""Load presentation skills and phase-specific document templates."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_SOURCE = PROJECT_ROOT / ".agents" / "skills"
TEMPLATE_FILENAME = "OUTPUT_TEMPLATE.md"
UNDERSTAND_SKILL_FILENAME = "explain-phase-skill.md"


def load_phase_template(phase: str) -> str:
    """Load the presentation template belonging to a phase."""
    phase_name = (phase or "").strip()
    if not phase_name:
        raise ValueError("phase cannot be empty")
    template_path = SKILLS_SOURCE / phase_name / TEMPLATE_FILENAME
    if not template_path.is_file():
        raise FileNotFoundError(f"No {TEMPLATE_FILENAME} found for phase '{phase_name}' at '{template_path}'.")
    template = template_path.read_text(encoding="utf-8").strip()
    if not template:
        raise ValueError(f"{TEMPLATE_FILENAME} is empty for phase '{phase_name}'.")
    return template


def load_explain_phase_skill() -> str:
    """Load the single common skill used by the understand objective."""
    skill_path = SKILLS_SOURCE / UNDERSTAND_SKILL_FILENAME
    if not skill_path.is_file():
        raise FileNotFoundError(f"No {UNDERSTAND_SKILL_FILENAME} found at '{skill_path}'.")
    skill = skill_path.read_text(encoding="utf-8").strip()
    if not skill:
        raise ValueError(f"{UNDERSTAND_SKILL_FILENAME} is empty.")
    return skill
