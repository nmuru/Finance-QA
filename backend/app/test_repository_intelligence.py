from pathlib import Path

from app.phase_intelligence import build_phase_intelligence
from app.repository_intelligence import collect_repository_intelligence


def test_collect_repository_intelligence(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest"},"dependencies":{"react":"19"},"devDependencies":{"typescript":"5"}}',
        encoding="utf-8",
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "page.tsx").write_text(
        "export function HomePage() { return null }\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "home.test.ts").write_text(
        "test('home', () => {})\n",
        encoding="utf-8",
    )
    intelligence = collect_repository_intelligence(tmp_path)
    assert intelligence.file_count == 3
    assert "React" in intelligence.technologies
    assert "TypeScript" in intelligence.technologies
    assert "app/page.tsx" in intelligence.page_files
    assert "tests/home.test.ts" in intelligence.test_files
    assert intelligence.package_scripts["test"] == "vitest"


def test_phase_projection_prefers_phase_relevant_files(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "service.ts").write_text(
        "export function service() { return 1 }\n",
        encoding="utf-8",
    )
    intelligence = collect_repository_intelligence(tmp_path)
    prompt = build_phase_intelligence(intelligence, "low-level-design")
    assert "PHASE-SPECIFIC DETERMINISTIC INTELLIGENCE" in prompt
    assert "lib/service.ts" in prompt
    assert "Use the indexed functions" in prompt
