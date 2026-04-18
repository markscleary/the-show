"""Tests for the signed-link HTTP server."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

import pytest

SECRET = "test-link-secret"


def _make_token(matter_id: int, action: str, expiry_ts: int, secret: str = SECRET) -> str:
    msg = f"{matter_id}:{action}:{expiry_ts}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    payload = f"{msg}:{sig}"
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


@pytest.fixture
def client(monkeypatch, queue_db):
    monkeypatch.setenv("URGENT_EMAIL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("URGENT_WHATSAPP_VERIFY_TOKEN", "my-verify-token")
    import urgent_contact.link_server as ls
    ls.app.config["TESTING"] = True
    with ls.app.test_client() as c:
        yield c


# ──────────────────────────────────────────────────────────────────────────────
# GET /respond — email link handler
# ──────────────────────────────────────────────────────────────────────────────

def test_valid_token_returns_200(client, queue_db):
    expiry = int(time.time()) + 3600
    token = _make_token(1, "APPROVE", expiry)
    resp = client.get(f"/respond?token={token}&handle=mark%40example.com")
    assert resp.status_code == 200
    assert b"Response recorded" in resp.data


def test_valid_token_writes_to_queue(client, queue_db):
    import urllib.parse
    import urgent_contact.link_queue as lq
    expiry = int(time.time()) + 3600
    token = _make_token(7, "REJECT", expiry)
    handle = "user@example.com"
    client.get(f"/respond?token={token}&handle={urllib.parse.quote(handle)}")
    rows = lq.read_link_responses(handle)
    assert len(rows) == 1
    assert rows[0]["action"] == "REJECT"
    assert rows[0]["matter_id"] == 7


def test_all_valid_actions_accepted(client, queue_db):
    expiry = int(time.time()) + 3600
    for action in ("APPROVE", "REJECT", "STOP", "CONTINUE"):
        token = _make_token(1, action, expiry)
        resp = client.get(f"/respond?token={token}&handle=u%40x.com")
        assert resp.status_code == 200, f"{action} failed with {resp.status_code}"


def test_expired_token_returns_400(client):
    expiry = int(time.time()) - 10  # already expired
    token = _make_token(1, "APPROVE", expiry)
    resp = client.get(f"/respond?token={token}&handle=u%40x.com")
    assert resp.status_code == 400


def test_wrong_hmac_returns_400(client):
    expiry = int(time.time()) + 3600
    token = _make_token(1, "APPROVE", expiry, secret="wrong-secret")
    resp = client.get(f"/respond?token={token}&handle=u%40x.com")
    assert resp.status_code == 400


def test_missing_token_returns_400(client):
    resp = client.get("/respond?handle=u%40x.com")
    assert resp.status_code == 400


def test_missing_handle_returns_400(client):
    expiry = int(time.time()) + 3600
    token = _make_token(1, "APPROVE", expiry)
    resp = client.get(f"/respond?token={token}")
    assert resp.status_code == 400


def test_malformed_token_returns_400(client):
    resp = client.get("/respond?token=notavalidtoken&handle=u%40x.com")
    assert resp.status_code == 400


def test_error_page_reveals_no_detail(client):
    # Error page should not leak reason (expired vs bad sig)
    resp = client.get("/respond?token=bad&handle=u%40x.com")
    body = resp.data.decode()
    assert "expired" not in body.lower() or "longer valid" in body.lower()
    assert "signature" not in body.lower()
    assert "hmac" not in body.lower()


# ──────────────────────────────────────────────────────────────────────────────
# GET /whatsapp-webhook — Meta verification
# ──────────────────────────────────────────────────────────────────────────────

def test_whatsapp_verify_correct_token(client):
    resp = client.get(
        "/whatsapp-webhook"
        "?hub.mode=subscribe&hub.verify_token=my-verify-token&hub.challenge=testchallenge"
    )
    assert resp.status_code == 200
    assert resp.data == b"testchallenge"


def test_whatsapp_verify_wrong_token(client):
    resp = client.get(
        "/whatsapp-webhook"
        "?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=testchallenge"
    )
    assert resp.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# POST /whatsapp-webhook — inbound messages
# ──────────────────────────────────────────────────────────────────────────────

def test_whatsapp_webhook_queues_message(client, queue_db):
    import urgent_contact.link_queue as lq
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"from": "+61412345678", "text": {"body": "APPROVE 654321"}}
                            ]
                        }
                    }
                ]
            }
        ]
    }
    resp = client.post("/whatsapp-webhook", json=payload)
    assert resp.status_code == 200
    rows = lq.read_whatsapp_responses("+61412345678")
    assert len(rows) == 1
    assert rows[0]["body"] == "APPROVE 654321"


def test_whatsapp_webhook_bad_payload_returns_200(client):
    # Bad payloads must not crash the server
    resp = client.post("/whatsapp-webhook", data="not-json", content_type="text/plain")
    assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# POST /twilio-webhook — inbound SMS
# ──────────────────────────────────────────────────────────────────────────────

def test_twilio_webhook_queues_sms(client, queue_db):
    import urgent_contact.link_queue as lq
    resp = client.post(
        "/twilio-webhook",
        data={"From": "+61412345678", "To": "+15005550006", "Body": "APPROVE 000000"},
    )
    assert resp.status_code == 200
    assert b"Response" in resp.data  # TwiML
    rows = lq.read_sms_responses("+61412345678")
    assert len(rows) == 1
    assert rows[0]["body"] == "APPROVE 000000"


def test_twilio_webhook_empty_body_is_ok(client):
    resp = client.post("/twilio-webhook", data={})
    assert resp.status_code == 200
