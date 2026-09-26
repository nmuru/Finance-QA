from pathlib import Path

from app.agent_runner import _format_skill_resources, _resolve_skill_resources


def test_resolve_skill_resources_includes_existing_template_and_output_content(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    skill_dir = project_root / ".agents" / "skills" / "business-requirements"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("skill", encoding="utf-8")
    (skill_dir / "OUTPUT_TEMPLATE.md").write_text("template", encoding="utf-8")
    output_dir = tmp_path / "output-content" / "run-123"
    output_dir.mkdir(parents=True)

    monkeypatch.setattr("app.agent_runner.SKILLS_SOURCE", project_root / ".agents" / "skills")

    resources = _resolve_skill_resources("business-requirements", output_dir)

    assert resources["skill"] == str(skill_dir / "SKILL.md")
    assert resources["artifacts"]["output_template"] == str(skill_dir / "OUTPUT_TEMPLATE.md")
    assert resources["artifacts"]["output_content"] == str(output_dir.resolve())
    assert "list_previous_phase_outputs" in resources["tools"]["output_content"]
    assert "read_previous_phase_output" in resources["tools"]["output_content"]


def test_resolve_skill_resources_omits_missing_optional_artifacts(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    skill_dir = project_root / ".agents" / "skills" / "business-requirements"
    skill_dir.mkdir(parents=True)
    output_dir = tmp_path / "output-content" / "run-123"
    output_dir.mkdir(parents=True)

    monkeypatch.setattr("app.agent_runner.SKILLS_SOURCE", project_root / ".agents" / "skills")

    resources = _resolve_skill_resources("business-requirements", output_dir)

    assert resources["skill"] == str(skill_dir / "SKILL.md")
    assert "output_template" not in resources["artifacts"]
    assert "output_content" in resources["artifacts"]


def test_format_skill_resources_exposes_paths_not_content():
    resources = {
        "skill": ".agents/skills/business-requirements/SKILL.md",
        "artifacts": {
            "output_template": ".agents/skills/business-requirements/OUTPUT_TEMPLATE.md",
            "output_content": "output-content/run-123",
        },
        "tools": {
            "repository": ["list_files", "read_file", "search_repository"],
            "output_content": ["list_previous_phase_outputs", "read_previous_phase_output"],
        },
    }

    context = _format_skill_resources(resources)

    assert ".agents/skills/business-requirements/OUTPUT_TEMPLATE.md" in context
    assert "output-content/run-123" in context
    assert "list_previous_phase_outputs" in context
    assert "template" not in context.lower().split("OUTPUT_TEMPLATE.md", 1)[-1]


def test_discover_skill_metadata_supports_both_filename_conventions(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    skill_dir = project_root / ".agents" / "skills" / "revenue-earnings-engine"
    skill_dir.mkdir(parents=True)

    (skill_dir / "revenue_analysis_SKILL.md").write_text(
        "---\nname: revenue-analysis\ndescription: Revenue analysis\n---\n\nFull skill body that must not be loaded.",
        encoding="utf-8",
    )
    (skill_dir / "SKILL_margin_analysis.md").write_text(
        "---\nname: margin-analysis\ndescription: Margin analysis\n---\n\nAnother full skill body.",
        encoding="utf-8",
    )
    (skill_dir / "notes.md").write_text("Not a skill.", encoding="utf-8")

    monkeypatch.setattr("app.agent_runner.SKILLS_SOURCE", project_root / ".agents" / "skills")

    from app.agent_runner import _discover_skill_metadata, _format_skill_metadata

    skills = _discover_skill_metadata("revenue-earnings-engine")
    context = _format_skill_metadata(skills)

    assert [item["file"] for item in skills] == [
        "SKILL_margin_analysis.md",
        "revenue_analysis_SKILL.md",
    ]
    assert "name: revenue-analysis" in context
    assert "name: margin-analysis" in context
    assert "Full skill body" not in context
    assert "Another full skill body" not in context
