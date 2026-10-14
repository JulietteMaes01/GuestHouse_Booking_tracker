"""An in-memory stand-in for the gspread worksheet, used by tests and tools."""


class FakeWorksheet:
    """Serves fixed rows the way gspread does, and records every write."""

    def __init__(self, records, values):
        self.records = records   # what get_all_records() returns (numbers converted)
        self.values = values     # what get_all_values() returns (header + raw strings)
        self.writes = []

    @classmethod
    def from_rows(cls, headers, rows):
        """Build from a list of {column: value} dicts; missing columns are blank."""
        records = [{col: row.get(col, "") for col in headers} for row in rows]
        values = [list(headers)] + [[str(rec[col]) for col in headers] for rec in records]
        return cls(records, values)

    def get_all_records(self):
        return [dict(r) for r in self.records]

    def get_all_values(self):
        return [list(v) for v in self.values]

    def append_row(self, values, value_input_option=None):
        self.writes.append(("append_row", values))

    def update_cell(self, row, col, value):
        self.writes.append(("update_cell", row, col, value))

    def batch_update(self, data, value_input_option=None):
        self.writes.append(("batch_update", data))
