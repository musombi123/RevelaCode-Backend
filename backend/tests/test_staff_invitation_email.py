from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from backend.jumuiya.elimu.staff.invitation_email import send_staff_invitation_email


def _configure(monkeypatch, *, sender="RevelaCode Elimu <noreply@revelacode.co.ke>"):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("EMAIL_FROM", sender)
    monkeypatch.setenv("FRONTEND_URL", "https://revelacode.co.ke")


def _payload():
    return {
        "recipient": "teacher@example.com",
        "invitee_name": "Jane Teacher",
        "school_name": "Coast Academy",
        "inviter_name": "School Owner",
        "inviter_email": "owner@example.com",
        "role": "teacher",
        "token": "single-use-invitation-token-123456",
    }


def test_staff_invitation_uses_configured_verified_sender_and_confirms_resend_id(monkeypatch):
    _configure(monkeypatch)
    captured = {}

    class FakeEmails:
        @staticmethod
        def send(message):
            captured["message"] = message
            return {"id": "email_accepted_123"}

    resend = SimpleNamespace(api_key=None, Emails=FakeEmails)
    monkeypatch.setitem(sys.modules, "resend", resend)

    result = send_staff_invitation_email(**_payload())

    assert resend.api_key == "re_test_key"
    assert captured["message"]["from"] == "RevelaCode Elimu <noreply@revelacode.co.ke>"
    assert captured["message"]["to"] == ["teacher@example.com"]
    assert captured["message"]["reply_to"] == ["owner@example.com"]
    assert "https://revelacode.co.ke/elimu-invitation?" in captured["message"]["text"]
    assert result == {
        "provider": "resend",
        "accepted": True,
        "email_id": "email_accepted_123",
    }


def test_staff_invitation_requires_explicit_sender_configuration(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    monkeypatch.setenv("FRONTEND_URL", "https://revelacode.co.ke")

    with pytest.raises(RuntimeError, match="EMAIL_FROM is not configured"):
        send_staff_invitation_email(**_payload())


def test_staff_invitation_does_not_report_success_without_resend_email_id(monkeypatch):
    _configure(monkeypatch)

    class FakeEmails:
        @staticmethod
        def send(_message):
            return {}

    monkeypatch.setitem(sys.modules, "resend", SimpleNamespace(api_key=None, Emails=FakeEmails))

    with pytest.raises(RuntimeError, match="did not return an email ID"):
        send_staff_invitation_email(**_payload())
