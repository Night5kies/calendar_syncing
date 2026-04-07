from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx


@dataclass
class FlowState:
    request_id: str
    share_token: str
    participant_name: str


def request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected_status: int = 200,
    json: dict | None = None,
) -> dict:
    response = client.request(method, path, json=json)
    if response.status_code != expected_status:
        raise AssertionError(
            f"{method} {path} returned {response.status_code}, expected {expected_status}: {response.text}"
        )
    return response.json()


def create_request(client: httpx.Client) -> FlowState:
    deadline = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "title": "Reminder flow smoke test",
        "duration_min": 60,
        "timezone": "America/New_York",
        "event_type": "meal",
        "notes": "Created by reminder test script",
        "response_deadline": deadline.isoformat(),
        "reminders_enabled": True,
    }
    created = request(client, "POST", "/v1/requests", json=payload)
    request_id = created["id"]

    participants = [
        {"display_name": "Alex", "email": "alex@example.com"},
        {"display_name": "Jules", "phone": "555-222-0101"},
    ]
    for participant in participants:
        request(client, "POST", f"/v1/requests/{request_id}/participants", json=participant)

    starts = [
        datetime.now(timezone.utc) + timedelta(days=2, hours=18),
        datetime.now(timezone.utc) + timedelta(days=3, hours=19),
        datetime.now(timezone.utc) + timedelta(days=4, hours=17),
    ]
    for index, start_at in enumerate(starts, start=1):
        request(
            client,
            "POST",
            f"/v1/requests/{request_id}/proposals",
            json={"rank": index, "start_at": start_at.isoformat()},
        )

    share = request(client, "POST", f"/v1/share/{request_id}")
    return FlowState(
        request_id=request_id,
        share_token=share["token"],
        participant_name="Alex",
    )


def assert_initial_state(client: httpx.Client, state: FlowState) -> None:
    detail = request(client, "GET", f"/v1/requests/{state.request_id}")
    assert detail["reminders"]["enabled"] is True
    assert detail["reminders"]["response_deadline"] is not None
    assert detail["reminders"]["sent_count"] == 0
    assert detail["progress"]["responded_count"] == 0
    assert detail["progress"]["outstanding_count"] == 2
    assert len(detail["outstanding_participants"]) == 2
    print("Initial reminder state looks correct.")


def assert_manual_ping(client: httpx.Client, state: FlowState) -> None:
    ping = request(client, "POST", f"/v1/requests/{state.request_id}/reminders/ping")
    assert ping["sent_count"] == 2
    assert ping["outstanding_count"] == 2

    detail = request(client, "GET", f"/v1/requests/{state.request_id}")
    assert detail["reminders"]["sent_count"] == 2
    assert detail["reminders"]["last_reminded_at"] is not None
    assert len(detail["reminders"]["history"]) == 2
    print("Manual ping queued reminders for both non-responders.")


def submit_one_response(client: httpx.Client, state: FlowState) -> None:
    share = request(client, "GET", f"/v1/share/public/{state.share_token}")
    proposal_id = share["request"]["proposals"][0]["id"]

    request(
        client,
        "POST",
        f"/v1/share/public/{state.share_token}/responses",
        json={
            "display_name": state.participant_name,
            "guest_key": "script-guest-alex",
            "proposal_id": proposal_id,
            "choice": "picked",
            "email": "alex@example.com",
        },
    )

    detail = request(client, "GET", f"/v1/requests/{state.request_id}")
    assert detail["progress"]["responded_count"] == 1
    assert detail["progress"]["outstanding_count"] == 1
    assert len(detail["outstanding_participants"]) == 1
    remaining = detail["outstanding_participants"][0]
    assert remaining["display_name"] == "Jules"
    print("Attendee response removed one participant from the outstanding list.")


def assert_second_ping(client: httpx.Client, state: FlowState) -> None:
    ping = request(client, "POST", f"/v1/requests/{state.request_id}/reminders/ping")
    assert ping["sent_count"] == 1
    assert ping["outstanding_count"] == 1

    detail = request(client, "GET", f"/v1/requests/{state.request_id}")
    assert detail["reminders"]["sent_count"] == 3
    assert len(detail["reminders"]["history"]) == 3
    print("Second ping only queued a reminder for the remaining non-responder.")


def finalize_and_fetch_artifact(client: httpx.Client, state: FlowState) -> None:
    detail = request(client, "GET", f"/v1/requests/{state.request_id}")
    proposal_id = detail["proposals"][0]["id"]
    request(
        client,
        "POST",
        f"/v1/requests/{state.request_id}/finalize",
        json={"proposal_id": proposal_id},
    )
    detail = request(client, "GET", f"/v1/requests/{state.request_id}")
    assert detail["status"] == "confirmed"
    assert detail["confirmed_event"] is not None
    artifact_url = detail["confirmed_event"]["artifact_url"]
    assert artifact_url is not None

    artifact_response = client.get(f"/v1/requests/{state.request_id}/artifact.ics")
    if artifact_response.status_code != 200:
        raise AssertionError(
            f"GET artifact returned {artifact_response.status_code}: {artifact_response.text}"
        )
    assert "BEGIN:VCALENDAR" in artifact_response.text
    print("Finalize flow produced a confirmation artifact.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test the reminder flow against a running backend.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Backend base URL. Default: http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--bearer-token",
        default=None,
        help="Optional bearer token. Omit this in local dev when allow_dev_auth is enabled.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    headers = {}
    if args.bearer_token:
        headers["Authorization"] = f"Bearer {args.bearer_token}"

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=20.0) as client:
        try:
            state = create_request(client)
            print(f"Created request {state.request_id}")
            assert_initial_state(client, state)
            assert_manual_ping(client, state)
            submit_one_response(client, state)
            assert_second_ping(client, state)
            finalize_and_fetch_artifact(client, state)
        except Exception as exc:
            print(f"Reminder flow test failed: {exc}", file=sys.stderr)
            return 1

    print("Reminder flow test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
