"""Biashara HR, employee register and attendance clocking.

Attendance is linked to an authenticated, active company member. GPS coordinates
are optional evidence; no face template or biometric identifier is collected.
Payroll is not calculated or paid by this first-release attendance module.
"""
from __future__ import annotations

import re
import secrets
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, request
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.biashara import services
from backend.jumuiya.biashara.access import resolve_business_access
from backend.jumuiya.biashara.tenant_store import tenant_collection, set_business_tenant_context
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import ok, created


hr_bp = Blueprint("jumuiya_biashara_hr", __name__)
LOCAL_ZONE = ZoneInfo("Africa/Nairobi")


def _now():
    return datetime.now(timezone.utc)


def _id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        raise APIError("A valid employee or attendance ID is required.", 422, "invalid_resource_id")


def _text(value, field, maximum=160, required=False):
    result = str(value or "").strip()
    if required and not result:
        raise APIError(f"{field} is required.", 422, "validation_error")
    if len(result) > maximum:
        raise APIError(f"{field} must be {maximum} characters or fewer.", 422, "validation_error")
    return result


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("A JSON request body is required.", 400, "invalid_json")
    return data


def _serialize_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items() if key != "_id"}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _serialize(document):
    if not document:
        return None
    result = _serialize_value(dict(document))
    result["id"] = str(document.get("_id"))
    return result


def _idempotency_key():
    value = request.headers.get("Idempotency-Key") or request.headers.get("X-Offline-Mutation-Id") or ""
    value = str(value).strip()
    if not value:
        return None
    if len(value) > 160:
        raise APIError("Idempotency key is too long.", 422, "invalid_idempotency_key")
    return value


def _company(permission):
    uid = str(current_user_id())
    business = services._require_business(uid, permission=permission)
    _ensure_indexes(business["id"])
    return uid, business


def _self_employee():
    uid = str(current_user_id())
    business = services._require_business(uid, permission="hr.attendance.self")
    _ensure_indexes(business["id"])
    employees = tenant_collection("jumuiya_biashara_employees", business["id"])
    employee = employees.find_one({"business_id": business["id"], "user_id": uid, "status": "active"})
    if not employee:
        raise APIError(
            "Your login is not linked to an active employee record in this company. Ask HR to link your System ID.",
            403,
            "employee_record_not_linked",
        )
    return uid, business, employee


def _gps(data):
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None and longitude is None:
        return None
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError, OverflowError):
        raise APIError("GPS coordinates must be numeric.", 422, "invalid_gps")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise APIError("GPS coordinates are outside the valid range.", 422, "invalid_gps")
    accuracy = data.get("accuracy_meters")
    if accuracy is not None:
        try:
            accuracy = float(accuracy)
        except (TypeError, ValueError, OverflowError):
            raise APIError("GPS accuracy must be numeric.", 422, "invalid_gps")
        if not 0 < accuracy <= 100000:
            raise APIError("GPS accuracy must be between 0 and 100000 metres.", 422, "invalid_gps")
    return {"latitude": lat, "longitude": lon, "accuracy_meters": accuracy}


def _local_date(moment):
    return moment.astimezone(LOCAL_ZONE).date().isoformat()


def _shift_time(value, field, default):
    raw = str(value or default).strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", raw):
        raise APIError(f"{field} must use HH:MM (24-hour) format.", 422, "invalid_shift")
    return time.fromisoformat(raw)


def _ensure_indexes(business_id):
    employees = tenant_collection("jumuiya_biashara_employees", business_id)
    attendance = tenant_collection("jumuiya_biashara_attendance", business_id)
    employees.create_index(
        [("business_id", ASCENDING), ("system_id", ASCENDING)],
        unique=True, name="uq_biashara_employee_system_id",
    )
    employees.create_index(
        [("business_id", ASCENDING), ("user_id", ASCENDING)],
        unique=True, partialFilterExpression={"user_id": {"$type": "string"}},
        name="uq_biashara_employee_user",
    )
    employees.create_index(
        [("business_id", ASCENDING), ("idempotency_key", ASCENDING)],
        unique=True, partialFilterExpression={"idempotency_key": {"$type": "string"}},
        name="uq_biashara_employee_idempotency",
    )
    attendance.create_index(
        [("business_id", ASCENDING), ("user_id", ASCENDING), ("local_date", DESCENDING)],
        name="ix_biashara_attendance_user_date",
    )
    attendance.create_index(
        [("business_id", ASCENDING), ("user_id", ASCENDING), ("open_shift", ASCENDING)],
        unique=True, partialFilterExpression={"open_shift": True},
        name="uq_biashara_attendance_open_shift",
    )
    attendance.create_index(
        [("business_id", ASCENDING), ("clock_in_idempotency_key", ASCENDING)],
        unique=True, partialFilterExpression={"clock_in_idempotency_key": {"$type": "string"}},
        name="uq_biashara_attendance_clockin_idempotency",
    )
    attendance.create_index(
        [("business_id", ASCENDING), ("clock_out_idempotency_key", ASCENDING)],
        unique=True, partialFilterExpression={"clock_out_idempotency_key": {"$type": "string"}},
        name="uq_biashara_attendance_clockout_idempotency",
    )


@hr_bp.get("/hr/employees")
@require_authenticated
def list_employees():
    uid, business = _company("hr.view")
    _ensure_indexes(business["id"])
    rows = tenant_collection("jumuiya_biashara_employees", business["id"]).find(
        {"business_id": business["id"], "status": {"$ne": "deleted"}}
    ).sort("created_at", DESCENDING).limit(500)
    return ok([_serialize(row) for row in rows])


@hr_bp.post("/hr/employees")
@require_authenticated
def create_employee():
    uid, business = _company("hr.employees.manage")
    data = _body()
    name = _text(data.get("name"), "Employee name", 160, required=True)
    phone = _text(data.get("phone"), "Phone", 32, required=True)
    email = _text(data.get("email"), "Email", 254)
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise APIError("Enter a valid employee email address.", 422, "invalid_email")
    role = _text(data.get("role") or "employee", "Company role", 48).lower().replace("-", "_").replace(" ", "_")
    allowed_roles = {
        "employee", "sales_agent", "store_keeper", "factory_floor_lead",
        "accountant", "hr_manager", "operations_manager", "manager",
    }
    if role not in allowed_roles:
        raise APIError("Select a valid employee role. Executive and administrator roles cannot be assigned through HR.", 422, "invalid_employee_role")
    linked_user_id = _text(data.get("user_id"), "User ID", 160)
    idempotency_key = _idempotency_key()
    employees = tenant_collection("jumuiya_biashara_employees", business["id"])
    if idempotency_key:
        existing = employees.find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
        if existing:
            return ok(_serialize(existing), "This employee registration was already recorded.")
    if linked_user_id:
        member = resolve_business_access(linked_user_id, business["id"])
        if not member:
            raise APIError("The linked account must first accept an invitation to this company.", 422, "employee_membership_required")
        if member.get("is_owner") or str(member.get("role") or "") in {"ceo", "director", "admin", "owner"}:
            raise APIError("Executive accounts cannot be reassigned as ordinary employee records.", 422, "employee_role_conflict")

    start_time = _shift_time(data.get("shift_start"), "shift_start", "08:00")
    end_time = _shift_time(data.get("shift_end"), "shift_end", "17:00")
    try:
        grace = int(data.get("late_grace_minutes", 10))
    except (TypeError, ValueError):
        raise APIError("late_grace_minutes must be an integer.", 422, "invalid_shift")
    if not 0 <= grace <= 240:
        raise APIError("late_grace_minutes must be between 0 and 240.", 422, "invalid_shift")
    now = _now()
    system_id = "RC-" + secrets.token_hex(4).upper()
    employee = {
        "_id": ObjectId(),
        "business_id": business["id"],
        "system_id": system_id,
        "user_id": linked_user_id or None,
        "name": name,
        "phone": phone,
        "email": email,
        "department": _text(data.get("department"), "Department", 100),
        "job_title": _text(data.get("job_title"), "Job title", 120),
        "role": role,
        "idempotency_key": idempotency_key,
        "shift_start": start_time.strftime("%H:%M"),
        "shift_end": end_time.strftime("%H:%M"),
        "late_grace_minutes": grace,
        "status": "active",
        "created_by_user_id": uid,
        "created_at": now,
        "updated_at": now,
    }
    try:
        employees.insert_one(employee)
    except DuplicateKeyError:
        if idempotency_key:
            existing = employees.find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
            if existing:
                return ok(_serialize(existing), "This employee registration was already recorded.")
        raise APIError("This account is already linked to an employee or the System ID collided. Retry the registration.", 409, "employee_already_registered")
    return created(_serialize(employee), "Employee registered. Share the System ID through your approved onboarding process.")


@hr_bp.patch("/hr/employees/<employee_id>")
@require_authenticated
def update_employee(employee_id):
    uid, business = _company("hr.employees.manage")
    data = _body()
    allowed = {"name", "phone", "email", "department", "job_title", "role", "user_id", "shift_start", "shift_end", "late_grace_minutes", "status"}
    update = {}
    for field in allowed:
        if field not in data:
            continue
        if field in {"name", "phone"}:
            update[field] = _text(data[field], field.replace("_", " ").title(), 160, required=True)
        elif field in {"email", "department", "job_title"}:
            update[field] = _text(data[field], field.replace("_", " ").title(), 254 if field == "email" else 120)
        elif field == "user_id":
            value = _text(data[field], "User ID", 160)
            if value:
                member = resolve_business_access(value, business["id"])
                if not member:
                    raise APIError("The linked account must first accept an invitation to this company.", 422, "employee_membership_required")
                if member.get("is_owner") or str(member.get("role") or "") in {"ceo", "director", "admin", "owner"}:
                    raise APIError("Executive accounts cannot be linked as ordinary employees.", 422, "employee_role_conflict")
            update[field] = value or None
        elif field == "role":
            value = _text(data[field], "Role", 48).lower().replace("-", "_").replace(" ", "_")
            if value not in {"employee", "sales_agent", "store_keeper", "factory_floor_lead", "accountant", "hr_manager", "operations_manager", "manager"}:
                raise APIError("This role cannot be assigned through HR.", 422, "invalid_employee_role")
            update[field] = value
        elif field in {"shift_start", "shift_end"}:
            update[field] = _shift_time(data[field], field, "08:00").strftime("%H:%M")
        elif field == "late_grace_minutes":
            try:
                number = int(data[field])
            except (TypeError, ValueError):
                raise APIError("late_grace_minutes must be an integer.", 422, "invalid_shift")
            if not 0 <= number <= 240:
                raise APIError("late_grace_minutes must be between 0 and 240.", 422, "invalid_shift")
            update[field] = number
        elif field == "status":
            status = str(data[field] or "").strip().lower()
            if status not in {"active", "inactive"}:
                raise APIError("Employee status must be active or inactive.", 422, "invalid_employee_status")
            update[field] = status
    if not update:
        raise APIError("No supported employee fields were provided.", 422, "empty_update")
    update["updated_at"] = _now()
    employees = tenant_collection("jumuiya_biashara_employees", business["id"])
    result = employees.update_one(
        {"_id": _id(employee_id), "business_id": business["id"]},
        {"$set": update},
    )
    if not result.matched_count:
        raise APIError("Employee record was not found in this company.", 404, "employee_not_found")
    return ok(_serialize(employees.find_one({"_id": _id(employee_id), "business_id": business["id"]})), "Employee record updated.")


@hr_bp.get("/hr/attendance")
@require_authenticated
def list_attendance():
    uid, business = _company("hr.attendance.view")
    query = {"business_id": business["id"]}
    employee_id = str(request.args.get("employee_id") or "").strip()
    day = str(request.args.get("date") or "").strip()
    if employee_id:
        employee = tenant_collection("jumuiya_biashara_employees", business["id"]).find_one(
            {"_id": _id(employee_id), "business_id": business["id"]}
        )
        if not employee:
            raise APIError("Employee not found.", 404, "employee_not_found")
        query["user_id"] = employee.get("user_id")
    if day:
        try:
            date.fromisoformat(day)
        except ValueError:
            raise APIError("date must use YYYY-MM-DD.", 422, "invalid_date")
        query["local_date"] = day
    rows = tenant_collection("jumuiya_biashara_attendance", business["id"]).find(query).sort(
        "clock_in_at", DESCENDING
    ).limit(500)
    return ok([_serialize(row) for row in rows])


@hr_bp.post("/hr/attendance/clock-in")
@require_authenticated
def clock_in():
    uid, business, employee = _self_employee()
    data = _body()
    attendance = tenant_collection("jumuiya_biashara_attendance", business["id"])
    idempotency_key = _idempotency_key()
    if idempotency_key:
        previous = attendance.find_one({"business_id": business["id"], "clock_in_idempotency_key": idempotency_key})
        if previous:
            return ok(_serialize(previous), "This clock-in was already recorded.")
    existing = attendance.find_one({"business_id": business["id"], "user_id": uid, "open_shift": True})
    if existing:
        raise APIError("You are already clocked in. Clock out before starting another shift.", 409, "shift_already_open")
    now = _now()
    local = now.astimezone(LOCAL_ZONE)
    scheduled = _shift_time(employee.get("shift_start"), "shift_start", "08:00")
    scheduled_local = datetime.combine(local.date(), scheduled, tzinfo=LOCAL_ZONE)
    late_minutes = max(0, int((local - scheduled_local).total_seconds() // 60) - int(employee.get("late_grace_minutes", 10) or 0))
    gps = _gps(data)
    record = {
        "_id": ObjectId(),
        "business_id": business["id"],
        "employee_id": str(employee["_id"]),
        "user_id": uid,
        "system_id": employee["system_id"],
        "employee_name": employee["name"],
        "local_date": local.date().isoformat(),
        "clock_in_at": now,
        "clock_in_gps": gps,
        "clock_in_idempotency_key": idempotency_key,
        "late_minutes": late_minutes,
        "clock_out_at": None,
        "clock_out_gps": None,
        "worked_minutes": None,
        "overtime_minutes": None,
        "open_shift": True,
        "created_at": now,
        "updated_at": now,
    }
    try:
        attendance.insert_one(record)
    except DuplicateKeyError:
        if idempotency_key:
            previous = attendance.find_one({"business_id": business["id"], "clock_in_idempotency_key": idempotency_key})
            if previous:
                return ok(_serialize(previous), "This clock-in was already recorded.")
        raise APIError("You are already clocked in on another device.", 409, "shift_already_open")
    return created(_serialize(record), "Clock-in recorded.")


@hr_bp.post("/hr/attendance/clock-out")
@require_authenticated
def clock_out():
    uid, business, employee = _self_employee()
    attendance = tenant_collection("jumuiya_biashara_attendance", business["id"])
    idempotency_key = _idempotency_key()
    if idempotency_key:
        previous = attendance.find_one({"business_id": business["id"], "clock_out_idempotency_key": idempotency_key})
        if previous:
            return ok(_serialize(previous), "This clock-out was already recorded.")
    record = attendance.find_one({"business_id": business["id"], "user_id": uid, "open_shift": True})
    if not record:
        raise APIError("There is no open shift to clock out.", 409, "no_open_shift")
    data = request.get_json(silent=True) or {}
    now = _now()
    gps = _gps(data)
    clock_in = record["clock_in_at"]
    worked_minutes = max(0, int((now - clock_in).total_seconds() // 60))
    local_start = clock_in.astimezone(LOCAL_ZONE)
    shift_start = _shift_time(employee.get("shift_start"), "shift_start", "08:00")
    shift_end = _shift_time(employee.get("shift_end"), "shift_end", "17:00")
    shift_start_dt = datetime.combine(local_start.date(), shift_start, tzinfo=LOCAL_ZONE)
    shift_end_dt = datetime.combine(local_start.date(), shift_end, tzinfo=LOCAL_ZONE)
    if shift_end_dt <= shift_start_dt:
        shift_end_dt += timedelta(days=1)
    planned_minutes = max(0, int((shift_end_dt - shift_start_dt).total_seconds() // 60))
    overtime_minutes = max(0, worked_minutes - planned_minutes)
    result = attendance.update_one(
        {"_id": record["_id"], "business_id": business["id"], "user_id": uid, "open_shift": True},
        {"$set": {
            "clock_out_at": now,
            "clock_out_gps": gps,
            "clock_out_idempotency_key": idempotency_key,
            "worked_minutes": worked_minutes,
            "overtime_minutes": overtime_minutes,
            "open_shift": False,
            "updated_at": now,
        }},
    )
    if not result.modified_count:
        if idempotency_key:
            previous = attendance.find_one({"business_id": business["id"], "clock_out_idempotency_key": idempotency_key})
            if previous:
                return ok(_serialize(previous), "This clock-out was already recorded.")
        raise APIError("The shift was changed by another request. Refresh attendance and try again.", 409, "shift_state_conflict")
    return ok(_serialize(attendance.find_one({"_id": record["_id"], "business_id": business["id"]})), "Clock-out recorded.")


@hr_bp.get("/hr/attendance/me")
@require_authenticated
def my_attendance():
    uid, business, employee = _self_employee()
    recent = tenant_collection("jumuiya_biashara_attendance", business["id"]).find(
        {"business_id": business["id"], "user_id": uid}
    ).sort("clock_in_at", DESCENDING).limit(30)
    recent_rows = list(recent)
    open_shift = next((row for row in recent_rows if row.get("open_shift")), None)
    return ok({"employee": _serialize(employee), "open_shift": _serialize(open_shift), "recent": [_serialize(row) for row in recent_rows]})
