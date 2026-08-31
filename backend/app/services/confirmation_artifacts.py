from __future__ import annotations

import re
from pathlib import Path


def build_ics_body(
    *,
    uid: str,
    title: str,
    start_at_utc: str,
    end_at_utc: str,
    description: str | None,
    location: str | None,
    organizer_email: str | None,
) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SYZY//Social Scheduling//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{escape_ics(uid)}",
        f"DTSTAMP:{start_at_utc}",
        f"DTSTART:{start_at_utc}",
        f"DTEND:{end_at_utc}",
        f"SUMMARY:{escape_ics(title)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{escape_ics(description)}")
    if location:
        lines.append(f"LOCATION:{escape_ics(location)}")
    if organizer_email:
        lines.append(f"ORGANIZER:mailto:{escape_ics(organizer_email)}")
    lines.extend(["END:VEVENT", "END:VCALENDAR", ""])
    return "\r\n".join(lines)


def escape_ics(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", r"\n")
    )


def artifact_filename(title: str, request_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower() or "event"
    return f"{slug}-{request_id}.ics"


def ensure_artifact_dir(base_dir: str | Path) -> Path:
    path = Path(base_dir)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path
