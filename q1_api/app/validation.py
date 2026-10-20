"""CSV validation returns per-row problems, rather than aborting the batch."""
import csv
import io
import re
from datetime import date

FIELDS = ("case_ref", "applicant_name", "id_number", "dob", "issue_date", "image_ref")


def parse_csv(payload):
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    try:
        names = reader.fieldnames
    except csv.Error as exc:
        raise ValueError("Malformed CSV header") from exc
    if not names or len(set(names)) != len(names):
        raise ValueError("CSV header is missing or contains duplicate columns")
    missing = set(FIELDS) - set(names)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(sorted(missing)))
    accepted, rejected, seen = [], [], set()
    try:
        for raw in reader:
            number = reader.line_num  # Physical line at the end of this CSV record.
            row = {key: (raw.get(key) or "").strip() for key in FIELDS}
            errors = []
            if None in raw:
                errors.append("Too many columns")
            for key, value in row.items():
                if not value:
                    errors.append(f"{key} is required")
            for key in ("dob", "issue_date"):
                if row[key]:
                    try:
                        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[key]):
                            raise ValueError
                        date.fromisoformat(row[key])
                    except ValueError:
                        errors.append(f"{key} must be a valid YYYY-MM-DD date")
            if not errors:
                dob = date.fromisoformat(row["dob"])
                issue_date = date.fromisoformat(row["issue_date"])

                if dob > issue_date:
                    errors.append("issue_date must not be earlier than dob")
            # The first occurrence reserves the reference, including invalid rows.
            if row["case_ref"] in seen:
                errors.append("Duplicate case_ref within this upload")
            if row["case_ref"]:
                seen.add(row["case_ref"])
            if errors:
                rejected.append({"row": number, "case_ref": row["case_ref"], "reasons": errors})
            else:
                accepted.append({**row, "row_number": number})
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV near line {reader.line_num}") from exc
    return accepted, rejected
