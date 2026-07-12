"""
Parses an uploaded Excel/CSV file into a list of {name, phone, pg_name,
location, email} dicts, auto-detecting which column is which by header text.
"""
import csv
import io
from typing import List

import openpyxl

# Header text (lowercased, punctuation-stripped) we'll accept for each field.
HEADER_ALIASES = {
    "name": ["name", "fullname", "contactname", "leadname", "ownername"],
    "phone": ["phone", "no", "number", "mobile", "mobileno", "contactno",
              "phonenumber", "whatsapp", "whatsappno"],
    "pg_name": ["pgname", "pg", "propertyname", "hostelname", "property"],
    "location": ["location", "address", "area", "city"],
    "email": ["email", "mail", "emailaddress", "emailid"],
}


def _clean_header(h: str) -> str:
    return "".join(ch for ch in str(h or "").lower() if ch.isalnum())


def _match_field(header: str) -> str | None:
    cleaned = _clean_header(header)
    for field, aliases in HEADER_ALIASES.items():
        if cleaned in aliases:
            return field
    return None


def _rows_from_excel(content: bytes) -> tuple[list, list]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter, [])
    rows = list(rows_iter)
    return list(header), rows


def _rows_from_csv(content: bytes) -> tuple[list, list]:
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], []
    return rows[0], rows[1:]


def parse_leads_file(content: bytes, filename: str) -> List[dict]:
    """Returns a list of dicts with keys: name, phone, pg_name, location, email
    (missing/unrecognized columns simply come back as None for that field)."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        header, rows = _rows_from_excel(content)
    else:
        header, rows = _rows_from_csv(content)

    # Map column index -> field name, for every header we recognize.
    col_map = {}
    for idx, col_name in enumerate(header):
        field = _match_field(col_name)
        if field:
            col_map[idx] = field

    leads = []
    for row in rows:
        if row is None or all(cell in (None, "") for cell in row):
            continue
        lead = {"name": None, "phone": None, "pg_name": None, "location": None, "email": None}
        for idx, field in col_map.items():
            if idx < len(row) and row[idx] not in (None, ""):
                lead[field] = str(row[idx]).strip()
        leads.append(lead)
    return leads
