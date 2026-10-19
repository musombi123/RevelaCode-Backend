from datetime import datetime, timedelta, timezone

from backend.jumuiya.elimu.staff.models import invitation_is_expired


def test_invitation_expiry_handles_naive_mongodb_utc_datetime():
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    assert invitation_is_expired(
        {"expires_at": datetime(2026, 10, 19, 11, 59, 59)},
        current_time=now,
    )
    assert not invitation_is_expired(
        {"expires_at": datetime(2026, 10, 19, 12, 0, 1)},
        current_time=now,
    )


def test_invitation_expiry_handles_timezone_aware_datetimes():
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    assert invitation_is_expired(
        {"expires_at": now - timedelta(seconds=1)},
        current_time=now,
    )
    assert not invitation_is_expired(
        {"expires_at": now + timedelta(seconds=1)},
        current_time=now,
    )


def test_invitation_expiry_handles_naive_current_time():
    now = datetime(2026, 10, 19, 12, 0, 0)
    assert not invitation_is_expired(
        {"expires_at": datetime(2026, 10, 19, 12, 0, 1, tzinfo=timezone.utc)},
        current_time=now,
    )
