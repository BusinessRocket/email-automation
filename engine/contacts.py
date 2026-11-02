"""Contact lists: add, import from CSV, unsubscribe."""

import csv
import io
import re

from . import db

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")

# CSV header (lower-cased, letters and digits only) -> our field
HEADER_ALIASES = {
    "email": "email", "emailaddress": "email", "mail": "email",
    "name": "name", "fullname": "name", "contactname": "name", "customername": "name",
    "firstname": "first", "first": "first", "givenname": "first",
    "lastname": "last", "last": "last", "surname": "last", "familyname": "last",
    "phone": "phone", "phonenumber": "phone", "mobile": "phone", "mobilenumber": "phone",
    "cell": "phone", "tel": "phone", "telephone": "phone",
    "suburb": "suburb", "city": "suburb", "town": "suburb", "location": "suburb",
    "tags": "tags", "tag": "tags", "labels": "tags", "segment": "tags",
}


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))


def upsert(conn, business: str, email: str, *, name="", phone="", suburb="",
           tags="", source="") -> str:
    """Add a contact or merge into an existing one. Returns 'added', 'updated' or 'invalid'.

    Existing values are only filled in, never blanked, and an unsubscribed
    contact stays unsubscribed.
    """
    email = email.strip().lower()
    if not valid_email(email):
        return "invalid"
    row = conn.execute("SELECT * FROM contacts WHERE business = ? AND email = ?",
                       (business, email)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO contacts (business, email, name, phone, suburb, tags, source,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (business, email, name.strip(), phone.strip(), suburb.strip(),
             db.store_tags(tags), source, db.now(), db.now()))
        return "added"
    merged = db.store_tags(db.tag_list(row["tags"]) + db.tag_list(db.store_tags(tags)))
    conn.execute(
        "UPDATE contacts SET name = ?, phone = ?, suburb = ?, tags = ?, updated_at = ?"
        " WHERE id = ?",
        (row["name"] or name.strip(), row["phone"] or phone.strip(),
         row["suburb"] or suburb.strip(), merged, db.now(), row["id"]))
    return "updated"


def import_csv(conn, business: str, csv_text: str, extra_tags: str = "",
               source: str = "csv") -> dict:
    """Import contacts from CSV text. Column names are matched loosely
    (Email / E-mail / Email Address, First Name + Last Name, Mobile, Suburb, Tags...)."""
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
    if not reader.fieldnames:
        raise ValueError("the CSV is empty")
    columns = {}
    for header in reader.fieldnames:
        key = HEADER_ALIASES.get(re.sub(r"[^a-z0-9]", "", (header or "").lower()))
        if key and key not in columns.values():
            columns[header] = key
    if "email" not in columns.values():
        raise ValueError(f"no email column found; headers were: {', '.join(reader.fieldnames)}")

    counts = {"added": 0, "updated": 0, "invalid": 0}
    for raw in reader:
        row = {field: (raw.get(header) or "").strip() for header, field in columns.items()}
        name = row.get("name") or " ".join(p for p in (row.get("first"), row.get("last")) if p)
        tags = ",".join(t for t in (row.get("tags", "").replace(";", ","), extra_tags) if t)
        result = upsert(conn, business, row.get("email", ""), name=name,
                        phone=row.get("phone", ""), suburb=row.get("suburb", ""),
                        tags=tags, source=source)
        counts[result] += 1
    conn.commit()
    return counts


def set_status(conn, business: str, email: str, status: str) -> bool:
    cur = conn.execute(
        "UPDATE contacts SET status = ?, updated_at = ? WHERE business = ? AND email = ?"
        " AND status != ?", (status, db.now(), business, email.strip().lower(), status))
    return cur.rowcount > 0
