from datetime import date

from backend.jumuiya.elimu.finance_routes import (
    _elimu_mpesa_callback_url,
    _normalize_whatsapp_phone,
    _whatsapp_phone_variants,
)
from backend.jumuiya.elimu.intelligence_routes import (
    _fees_for_student,
    _index_fees,
    _risk_for_student,
)


def test_normalizes_common_kenyan_guardian_phone_formats():
    assert _normalize_whatsapp_phone("0712 345 678") == "+254712345678"
    assert _normalize_whatsapp_phone("+254 712-345-678") == "+254712345678"
    assert _normalize_whatsapp_phone("712345678") == "+254712345678"
    assert _normalize_whatsapp_phone("not-a-phone") == ""


def test_phone_variants_include_national_and_international_forms():
    variants = set(_whatsapp_phone_variants("+254712345678"))
    assert "+254712345678" in variants
    assert "254712345678" in variants
    assert "0712345678" in variants
    assert "712345678" in variants


def test_fee_index_matches_student_id_and_admission_number_without_cross_matching():
    students = [
        {"student_id": "STU-001", "amount": 1000, "amount_paid": 200, "fee_type": "Tuition"},
        {"student_id": "", "admission_number": "ADM-002", "amount": 500, "amount_paid": 0, "fee_type": "Lunch"},
        {"student_id": "STU-OTHER", "admission_number": "ADM-001", "amount": 999, "amount_paid": 0, "fee_type": "Other"},
    ]
    indexed = _index_fees(students)
    matched = _fees_for_student(
        {"_id": "STU-001", "admission_number": "ADM-001"},
        indexed,
    )
    assert [item["fee_type"] for item in matched] == ["Tuition"]


def test_fee_risk_returns_explainable_high_signal_for_repeat_overdue_arrears():
    student = {
        "_id": "STU-001",
        "admission_number": "ADM-001",
        "full_name": "Test Student",
        "class_name": "Grade 6",
    }
    fees = [
        {
            "student_id": "STU-001",
            "amount": 1000,
            "amount_paid": 0,
            "status": "overdue",
            "due_date": "2026-01-01",
            "academic_year": "2025",
            "term": "Term 1",
            "fee_type": "Tuition",
        },
        {
            "student_id": "STU-001",
            "amount": 500,
            "amount_paid": 0,
            "status": "overdue",
            "due_date": "2026-02-01",
            "academic_year": "2025",
            "term": "Term 2",
            "fee_type": "Lunch",
        },
    ]
    result = _risk_for_student(student, fees, date(2026, 10, 29))
    assert result["risk_band"] == "high"
    assert result["risk_score"] == 90
    assert result["balance"] == 1500
    assert result["terms_observed"] == 2
    assert result["confidence"] == "low"
    assert result["reasons"]


def test_fee_risk_marks_missing_fee_history_as_insufficient_data():
    result = _risk_for_student(
        {"_id": "STU-002", "full_name": "No Records"},
        [],
        date(2026, 10, 29),
    )
    assert result["risk_band"] == "insufficient_data"
    assert result["risk_score"] is None
    assert result["confidence"] == "insufficient"


def test_elimu_callback_url_requires_the_dedicated_public_https_path(monkeypatch):
    monkeypatch.setenv(
        "ELIMU_MPESA_CALLBACK_URL",
        "https://revelacode-backend.onrender.com/api/jumuiya/elimu/finance/mpesa/callback",
    )
    assert _elimu_mpesa_callback_url().endswith("/api/jumuiya/elimu/finance/mpesa/callback")

    monkeypatch.setenv(
        "ELIMU_MPESA_CALLBACK_URL",
        "https://revelacode-backend.onrender.com/api/revenue/providers/mpesa/callback",
    )
    assert _elimu_mpesa_callback_url() == ""
