"""
Reading and writing the bookings Google Sheet.

A row is a dict of the cell texts, keyed by the header row. Data row number i
(counting from 0) sits on Sheet row i + FIRST_DATA_ROW.
Functions take the worksheet as an argument, so tests can pass a fake one.
"""
from __future__ import annotations

import gspread.utils

from config import COLUMNS

FIRST_DATA_ROW = 2   # row 1 is the header


def read_rows(worksheet) -> tuple[list[str], list[dict]]:
    """Return the header row and every data row, as text."""
    all_values = worksheet.get_all_values()
    if not all_values:
        return [], []
    headers = all_values[0]
    rows = []
    for values in all_values[1:]:
        padded = values + [""] * (len(headers) - len(values))
        rows.append(dict(zip(headers, padded)))
    return headers, rows


def append_row(worksheet, row: dict) -> None:
    """Add a booking at the bottom of the Sheet, in COLUMNS order."""
    worksheet.append_row([row.get(col, "") for col in COLUMNS], value_input_option="RAW")


def update_cells(worksheet, sheet_row: int, updates: dict, headers: list[str]) -> None:
    """Write several cells of one row in a single API call (avoids rate limits)."""
    batch = [
        {
            "range": gspread.utils.rowcol_to_a1(sheet_row, headers.index(column) + 1),
            "values": [["" if value is None else value]],
        }
        for column, value in updates.items()
        if column in headers
    ]
    if batch:
        worksheet.batch_update(batch, value_input_option="RAW")
