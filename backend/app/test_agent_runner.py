import json
import unittest

from app.agent_runner import AgentRunnerError, _parse_structured_phase_output


class ParseStructuredPhaseOutputTests(unittest.TestCase):
    def test_valid_json_returns_documentation(self):
        documentation = "# Business Purpose\n\nThis application documents repositories."
        result = _parse_structured_phase_output(
            '{"phase": "business-purpose", "documentation": "# Business Purpose\\n\\nThis application documents repositories."}',
            "business-purpose",
        )
        self.assertEqual(result, documentation)
        self.assertNotIsInstance(result, dict)

    def test_missing_documentation_raises(self):
        with self.assertRaises(AgentRunnerError):
            _parse_structured_phase_output('{"phase": "business-purpose"}', "business-purpose")

    def test_missing_phase_raises(self):
        with self.assertRaises(AgentRunnerError):
            _parse_structured_phase_output(
                '{"documentation": "hello world"}', "business-purpose"
            )

    def test_empty_documentation_raises(self):
        with self.assertRaises(AgentRunnerError):
            _parse_structured_phase_output(
                '{"phase": "business-purpose", "documentation": "   "}',
                "business-purpose",
            )

    def test_incorrect_phase_raises(self):
        with self.assertRaises(AgentRunnerError):
            _parse_structured_phase_output(
                '{"phase": "features", "documentation": "hello world"}',
                "business-purpose",
            )

    def test_malformed_json_raises(self):
        with self.assertRaises(AgentRunnerError):
            _parse_structured_phase_output('{bad json', "phase")

    def test_invalid_result_shape_raises(self):
        with self.assertRaises(AgentRunnerError):
            _parse_structured_phase_output(
                '[{"phase": "business-purpose", "documentation": "wrong shape"}]',
                "business-purpose",
            )

    def test_markdown_content_is_preserved_exactly(self):
        documentation = (
            "# Business Purpose\n\n"
            "| Area | Detail |\n| --- | --- |\n| Scope | Repository analysis |\n\n"
            "```python\nprint('evidence')\n```\n\n"
            "```mermaid\nflowchart TD\n  A --> B\n```"
        )
        payload = json.dumps(
            {"phase": "business-purpose", "documentation": documentation}
        )
        self.assertEqual(
            _parse_structured_phase_output(payload, "business-purpose"),
            documentation,
        )

    def test_nested_json_event_returns_final_documentation(self):
        documentation = "# Business Purpose\n\nFinal result."
        event_stream = json.dumps(
            {"type": "message.updated", "properties": {"info": {"phase": "business-purpose", "documentation": documentation}}}
        )
        self.assertEqual(
            _parse_structured_phase_output(event_stream, "business-purpose"),
            documentation,
        )

    def test_json_encoded_text_event_returns_documentation(self):
        documentation = "# Business Purpose\n\nEncoded final result."
        event_stream = json.dumps(
            {
                "type": "message.part.updated",
                "properties": {
                    "part": {
                        "type": "text",
                        "text": json.dumps(
                            {"phase": "business-purpose", "documentation": documentation}
                        ),
                    }
                },
            }
        )
        self.assertEqual(
            _parse_structured_phase_output(event_stream, "business-purpose"),
            documentation,
        )

    def test_split_text_events_are_reassembled(self):
        documentation = "# Business Purpose\n\nSplit final result."
        payload = json.dumps({"phase": "business-purpose", "documentation": documentation})
        midpoint = len(payload) // 2
        event_stream = "\n".join(
            json.dumps({"type": "text", "part": {"text": fragment}})
            for fragment in (payload[:midpoint], payload[midpoint:])
        )
        self.assertEqual(
            _parse_structured_phase_output(event_stream, "business-purpose"),
            documentation,
        )


if __name__ == "__main__":
    unittest.main()
