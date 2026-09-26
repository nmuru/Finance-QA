"""
Prompt contracts for the presentation-stage LLM.

The analysis stage produces the content for one phase.
The rendering stage turns that completed phase content into either the
standard document or an explanatory essay.
"""

from textwrap import dedent


RENDER_SYSTEM_PROMPT = dedent(
    """
    You are a document writer.

    Produce the requested software reverse-engineering documentation using
    the provided document template.

    Use the template as the format and structure for the document.

    Use the provided phase content as the source of the document's content.

    Do not invent facts, information, findings, requirements, or conclusions.

    If the phase content does not contain information for a section of the
    template, skip that section rather than inventing content.

    Preserve the meaning and factual content of the phase content.

    Return only the completed document.
    """
).strip()


UNDERSTAND_SYSTEM_PROMPT = dedent(
    """
    You are an expert software engineer explaining an existing software
    system to a software developer who is completely new to the codebase.

    You will receive one completed reverse-engineering phase document and the
    common explain-phase skill.

    Explain the subject covered by that phase only.

    The phase document is the source of truth. Do not invent facts, infer
    information from other phases, or expand the explanation into a
    whole-codebase overview.

    Write a clear, concise explanatory essay that makes the subject of this
    phase understandable to a developer who has no prior knowledge of this
    repository.

    Return only the completed explanatory document.
    """
).strip()


def build_render_prompt(phase: str, analysis: str, template: str) -> tuple[str, str]:
    """Build the standard document-rendering prompts for one phase."""
    phase_name = phase.replace("-", " ").strip().title()

    if not template or not template.strip():
        raise ValueError(f"No render template was provided for phase '{phase}'.")

    user_prompt = dedent(
        f"""
        You need to produce a {phase_name} documentation in the format
        specified by the template below.

        Start with the template and create the document according to its
        structure, headings, ordering, and formatting.

        You can take the content of the document from the provided
        {phase}.md content below.

        Do not invent content.

        If information required by a template section is not available in
        the {phase}.md content, skip that section.

        Do not add information from your own knowledge.

        --- BEGIN TEMPLATE ---
        {template}
        --- END TEMPLATE ---

        --- BEGIN {phase.upper()}.MD CONTENT ---
        {analysis}
        --- END {phase.upper()}.MD CONTENT ---

        Produce only the completed {phase_name} document.
        """
    ).strip()

    return RENDER_SYSTEM_PROMPT, user_prompt


def build_understand_prompt(phase: str, analysis: str, skill: str) -> tuple[str, str]:
    """Build the explanatory essay prompts for one completed phase."""
    phase_name = phase.replace("-", " ").strip().title()

    if not skill or not skill.strip():
        raise ValueError("Explain-phase skill cannot be empty.")

    user_prompt = dedent(
        f"""
        Explain the subject of the completed {phase_name} phase for a
        software developer who is completely new to this codebase.

        The output must explain this phase only. Do not create a holistic
        explanation of the entire repository and do not use information from
        other phases.

        Use the common skill below as the writing and reasoning instructions.
        Use the supplied phase document as the factual source.

        --- BEGIN EXPLAIN-PHASE SKILL ---
        {skill}
        --- END EXPLAIN-PHASE SKILL ---

        --- BEGIN {phase.upper()}.MD CONTENT ---
        {analysis}
        --- END {phase.upper()}.MD CONTENT ---

        Produce only the completed explanatory document.
        """
    ).strip()

    return UNDERSTAND_SYSTEM_PROMPT, user_prompt
