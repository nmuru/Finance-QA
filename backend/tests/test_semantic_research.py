from __future__ import annotations

from dataclasses import dataclass

from .repository_intelligence import RepositoryIntelligence


@dataclass
class FakeMessage:
    content: object = None
    reasoning: str | None = None


@dataclass
class FakeChoice:
    message: FakeMessage
    finish_reason: str | None = None


@dataclass
class FakeResponse:
    choices: list[FakeChoice]


def make_intelligence() -> RepositoryIntelligence:
    return RepositoryIntelligence(
        schema_version="1",
        root="/repo",
        file_count=1,
        files=["README.md"],
        directories=[],
        languages={},
        technologies=[],
        technology_evidence=[],
        package_scripts={},
        dependencies={},
        dev_dependencies={},
        env_variables=[],
        env_variable_evidence=[],
        routes=[],
        page_files=[],
        api_routes=[],
        entry_points=[],
        test_files=[],
        config_files=[],
        ci_files=[],
        documentation_files=["README.md"],
        documentation_excerpts={"README.md": "A product description."},
        integration_files=[],
        dependency_edges=[],
        source_files=[],
        parse_summary={},
    )


def test_extract_string_content(monkeypatch):
    from app import semantic_research

    response = FakeResponse([FakeChoice(FakeMessage(content="brief"), "stop")])
    assert semantic_research._extract_message_content(response) == "brief"


def test_extract_list_content(monkeypatch):
    from app import semantic_research

    response = FakeResponse([FakeChoice(FakeMessage(content=[{"type": "output_text", "text": "a"}, {"text": "b"}]), "stop")])
    assert semantic_research._extract_message_content(response) == "ab"


def test_reasoning_only_fails_closed(monkeypatch):
    from app import semantic_research

    async def fake_create(*args, **kwargs):
        return FakeResponse([FakeChoice(FakeMessage(content=None, reasoning="internal reasoning"), "length")])

    class FakeCompletions:
        create = fake_create

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(semantic_research, "AsyncOpenAI", FakeClient)

    import pytest

    with pytest.raises(RuntimeError, match="reasoning but no final answer"):
        semantic_research.run_repository_research(
            intelligence=make_intelligence(),
            provider="openrouter",
            model="openrouter/free",
            api_key="test-key",
        )


def test_write_research_artifact(tmp_path):
    from app import semantic_research

    path = tmp_path / "research.md"
    semantic_research.write_research_artifact(path, kind="phase", phase="business-purpose", content="brief")
    text = path.read_text(encoding="utf-8")
    assert "Research schema: 2" in text
    assert "Material claims must be verified" in text
    assert text.endswith("brief\n")
