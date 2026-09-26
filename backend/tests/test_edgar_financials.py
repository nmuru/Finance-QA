import unittest

from app.edgar_financials import _statement_records


class _ViewStatement:
    def __init__(self):
        self.calls = []

    def to_dataframe(self, view=None):
        self.calls.append(view)
        return _DataFrame()


class _FactsStatement:
    def __init__(self):
        self.calls = 0

    def to_dataframe(self):
        self.calls += 1
        return _DataFrame()


class _DataFrame:
    columns = ["label", "2024"]

    def reset_index(self, drop=True):
        return self

    def to_dict(self, orient="records"):
        return [{"label": "Revenue", "2024": 100}]


class StatementRecordsTests(unittest.TestCase):
    def test_standard_statement_passes_view(self):
        statement = _ViewStatement()
        result = _statement_records(statement, "standard")
        self.assertEqual(statement.calls, ["standard"])
        self.assertEqual(result["rows"], [{"label": "Revenue", "2024": 100}])

    def test_facts_statement_uses_no_view_argument(self):
        statement = _FactsStatement()
        result = _statement_records(statement, None)
        self.assertEqual(statement.calls, 1)
        self.assertEqual(result["rows"], [{"label": "Revenue", "2024": 100}])


if __name__ == "__main__":
    unittest.main()
