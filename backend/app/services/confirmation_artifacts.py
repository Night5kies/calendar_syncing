from __future__ import annotations

import re
from datetime import datetime, timezone
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
    attendees: list[str] | None = None,
    sequence: int = 0,
    dtstamp_utc: str | None = None,
    method: str | None = None,
) -> str:
    """Build an RFC 5545 VCALENDAR for a confirmed event.

    `method` defaults to REQUEST when there are attendees (which is what the
    confirmation email's MIME part declares, and what makes Gmail/Outlook show
    RSVP controls) and PUBLISH otherwise. The two must agree: a body saying
    PUBLISH inside a `method=REQUEST` part is rejected by some clients.
    """
    attendee_list = [email for email in (attendees or []) if email]
    resolved_method = method or ("REQUEST" if attendee_list else "PUBLISH")
    # DTSTAMP is when the *file* was produced, not when the event starts.
    # Reusing DTSTART made every re-issue look identical, so clients treated an
    # updated invite as a duplicate of the original.
    stamp = dtstamp_utc or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SYZY//Social Scheduling//EN",
        "CALSCALE:GREGORIAN",
        f"METHOD:{resolved_method}",
        "BEGIN:VEVENT",
        f"UID:{escape_ics(uid)}",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{start_at_utc}",
        f"DTEND:{end_at_utc}",
        f"SEQUENCE:{max(0, int(sequence))}",
        f"SUMMARY:{escape_ics(title)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{escape_ics(description)}")
    if location:
        lines.append(f"LOCATION:{escape_ics(location)}")
    if organizer_email:
        lines.append(f"ORGANIZER:mailto:{escape_ics(organizer_email)}")
    for email in attendee_list:
        lines.append(
            "ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;"
            f"RSVP=TRUE:mailto:{escape_ics(email)}"
        )
    lines.extend(["STATUS:CONFIRMED", "END:VEVENT", "END:VCALENDAR", ""])
    return "\r\n".join(fold_line(line) for line in lines)


def fold_line(line: str) -> str:
    """Fold a content line to 75 octets per RFC 5545 section 3.1."""
    if not line:
        return line
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks: list[str] = []
    remaining = encoded
    limit = 75
    while len(remaining) > limit:
        cut = limit
        # Never split a multi-byte character across the fold.
        while cut > 0 and (remaining[cut] & 0xC0) == 0x80:
            cut -= 1
        chunks.append(remaining[:cut].decode("utf-8"))
        remaining = remaining[cut:]
        # Continuation lines start with a space, which costs one octet.
        limit = 74
    if remaining:
        chunks.append(remaining.decode("utf-8"))
    return "\r\n ".join(chunks)


def escape_ics(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\r\n", r"\n")
        .replace("\r", r"\n")
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
