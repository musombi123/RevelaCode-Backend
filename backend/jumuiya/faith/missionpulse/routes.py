"""MissionPulse: privacy-aware church mission coordination API.

Uses RevelaCode's existing Jumuiya MongoDB, auth bridge and user identity.
No separate database, identity provider, or AI eligibility decisions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, jsonify, request

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.permissions import (
    current_user_id,
    current_user_roles,
    require_authenticated,
)

missionpulse_bp = Blueprint("missionpulse", __name__)


def _now():
    return datetime.now(timezone.utc)


def _body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _text(value, limit=500):
    return str(value or "").strip()[:limit]


def _coord(value, minimum, maximum):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= maximum else None


def _oid(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        return None


def _json(doc):
    if not doc:
        return None
    result = dict(doc)
    result["_id"] = str(result["_id"])
    for key, value in list(result.items()):
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
    return result


def _is_platform_admin():
    roles = {r.lower() for r in current_user_roles()}
    return bool(roles.intersection({
        "platform_admin", "super_admin", "system_admin",
        "founder", "root_admin",
    }))


def _membership(org_id, roles=None):
    query = {
        "user_id": current_user_id(),
        "org_id": org_id,
        "status": "active",
    }
    if roles:
        query["role"] = {"$in": list(roles)}
    return collection("jumuiya_missionpulse_memberships").find_one(query)


def _require_org(org_id, roles=None):
    if _is_platform_admin():
        return {"role": "platform_admin", "org_id": org_id}
    member = _membership(org_id, roles)
    if not member:
        return None
    return member


def _audit(action, resource, resource_id, org_id, metadata=None):
    collection("jumuiya_missionpulse_audit").insert_one({
        "user_id": current_user_id(),
        "action": action,
        "resource": resource,
        "resource_id": str(resource_id),
        "org_id": org_id,
        "metadata": metadata or {},
        "created_at": _now(),
    })


def _error(message, status=400, code="invalid_request"):
    return jsonify(success=False, error={"code": code, "message": message}), status


@missionpulse_bp.get("/health")
def health():
    return jsonify(success=True, service="MissionPulse", persistence="MongoDB",
                   auth="RevelaCode Jumuiya"), 200


@missionpulse_bp.get("/me")
@require_authenticated
def me():
    memberships = list(collection("jumuiya_missionpulse_memberships").find({
        "user_id": current_user_id(), "status": "active"
    }).limit(100))
    return jsonify(success=True, platform_admin=_is_platform_admin(),
                   memberships=[_json(x) for x in memberships]), 200


@missionpulse_bp.post("/organizations")
@require_authenticated
def create_organization():
    """Create Conference/Field/Church/Department nodes; privileged onboarding only."""
    data = _body()
    org_type = _text(data.get("type"), 30).lower()
    name = _text(data.get("name"), 160)
    parent_id = _text(data.get("parent_id"), 64)
    allowed = {"conference", "field", "district", "church", "department"}
    if org_type not in allowed or not name:
        return _error("A valid organization type and name are required.")
    if not _is_platform_admin():
        if not parent_id or not _require_org(parent_id, {"conference_admin", "field_admin", "church_admin"}):
            return _error("Only an authorized administrator can register this organization.", 403, "forbidden")
    parent = _oid(parent_id) if parent_id else None
    if parent_id and parent is None:
        return _error("Parent organization ID is invalid.")
    if org_type != "conference" and parent is None:
        return _error("This organization type requires a parent organization.")
    if org_type == "conference" and not _is_platform_admin():
        return _error("Conference creation requires platform administrator approval.", 403, "forbidden")
    parent_doc = collection("jumuiya_missionpulse_organizations").find_one({"_id": parent}) if parent else None
    if parent and not parent_doc:
        return _error("Parent organization was not found.", 404, "not_found")
    doc = {
        "type": org_type, "name": name, "parent_id": parent,
        "conference_id": (str((parent_doc or {}).get("conference_id")) if (parent_doc or {}).get("conference_id") else (str(parent) if parent and parent_doc and parent_doc.get("type") == "conference" else None)),
        "county": _text(data.get("county"), 100),
        "town": _text(data.get("town"), 100),
        "latitude": _coord(data.get("latitude"), -90, 90),
        "longitude": _coord(data.get("longitude"), -180, 180),
        "status": "active", "created_by": current_user_id(),
        "created_at": _now(), "updated_at": _now(),
    }
    result = collection("jumuiya_missionpulse_organizations").insert_one(doc)
    if org_type == "conference":
        collection("jumuiya_missionpulse_organizations").update_one({"_id": result.inserted_id}, {"$set": {"conference_id": str(result.inserted_id)}})
        doc["conference_id"] = str(result.inserted_id)
    doc["_id"] = result.inserted_id
    _audit("organization.created", "organization", result.inserted_id, str(doc.get("conference_id") or result.inserted_id))
    return jsonify(success=True, organization=_json(doc)), 201


@missionpulse_bp.post("/memberships")
@require_authenticated
def grant_membership():
    data = _body()
    org_id = _text(data.get("org_id"), 64)
    target_user = _text(data.get("user_id"), 128)
    role = _text(data.get("role"), 50).lower()
    allowed_roles = {
        "conference_admin", "field_admin", "district_coordinator", "church_admin",
        "pastor", "personal_ministries", "dorcas", "health_ministries",
        "youth_ministries", "family_ministries", "education_ministries",
        "case_worker", "volunteer", "report_viewer",
    }
    org_oid = _oid(org_id)
    if not org_oid or not target_user or role not in allowed_roles:
        return _error("Valid org_id, user_id and role are required.")
    org = collection("jumuiya_missionpulse_organizations").find_one({"_id": org_oid, "status": "active"})
    if not org:
        return _error("Organization not found.", 404, "not_found")
    if not _is_platform_admin() and not _require_org(org_id, {"conference_admin", "field_admin", "church_admin"}):
        return _error("You cannot manage memberships for this organization.", 403, "forbidden")
    doc = {
        "org_id": org_id, "user_id": target_user, "role": role,
        "status": "active", "granted_by": current_user_id(),
        "created_at": _now(), "updated_at": _now(),
    }
    collection("jumuiya_missionpulse_memberships").update_one(
        {"org_id": org_id, "user_id": target_user},
        {"$set": doc}, upsert=True,
    )
    _audit("membership.granted", "membership", target_user, str(org.get("conference_id") or org_id), {"role": role})
    return jsonify(success=True, membership=doc), 200


@missionpulse_bp.get("/organizations")
@require_authenticated
def list_organizations():
    org_id = _text(request.args.get("org_id"), 64)
    query = {"status": "active"}
    if org_id:
        if not _require_org(org_id):
            return _error("You cannot view this organization.", 403, "forbidden")
        query["parent_id"] = _oid(org_id)
    elif not _is_platform_admin():
        memberships = list(collection("jumuiya_missionpulse_memberships").find({
            "user_id": current_user_id(), "status": "active"
        }).limit(100))
        ids = [m.get("org_id") for m in memberships]
        query = {"status": "active", "_id": {"$in": [_oid(x) for x in ids if _oid(x)]}}
    docs = list(collection("jumuiya_missionpulse_organizations").find(query).sort("name", 1).limit(300))
    return jsonify(success=True, organizations=[_json(x) for x in docs]), 200


@missionpulse_bp.post("/cases")
@require_authenticated
def create_case():
    data = _body()
    org_id = _text(data.get("church_id"), 64)
    if not _oid(org_id) or not _require_org(org_id, {
        "conference_admin", "field_admin", "district_coordinator", "church_admin",
        "pastor", "personal_ministries", "dorcas", "health_ministries",
        "case_worker",
    }):
        return _error("An authorized church or ministry membership is required.", 403, "forbidden")
    category = _text(data.get("category"), 50).lower()
    allowed = {"basic_needs", "education", "health_referral", "family_support",
               "bible_study", "youth_development", "other"}
    summary = _text(data.get("summary"), 1200)
    if category not in allowed or not summary:
        return _error("A valid category and case summary are required.")
    consent = data.get("consent") is True
    if not consent:
        return _error("Record the person's consent before saving identifiable beneficiary information.")
    now = _now()
    org = collection("jumuiya_missionpulse_organizations").find_one({"_id": _oid(org_id)})
    if not org or org.get("type") != "church":
        return _error("Community cases must belong to a registered local church.", 400, "invalid_church")
    doc = {
        "church_id": org_id, "conference_id": str(org.get("conference_id") or ""),
        "category": category, "summary": summary,
        "beneficiary_name": _text(data.get("beneficiary_name"), 160),
        "beneficiary_contact": _text(data.get("beneficiary_contact"), 80),
        "location_general": _text(data.get("location_general"), 160),
        "consent": True, "status": "new", "priority": _text(data.get("priority"), 20) or "normal",
        "assigned_to": None, "assigned_ministry": None, "due_at": None, "assignment_note": "", "created_by": current_user_id(),
        "created_at": now, "updated_at": now,
    }
    result = collection("jumuiya_missionpulse_cases").insert_one(doc)
    doc["_id"] = result.inserted_id
    _audit("case.created", "case", result.inserted_id, org_id, {"category": category})
    return jsonify(success=True, case=_json(doc)), 201


@missionpulse_bp.get("/cases")
@require_authenticated
def list_cases():
    org_id = _text(request.args.get("church_id"), 64)
    if not org_id or not _require_org(org_id, {
        "conference_admin", "field_admin", "district_coordinator", "church_admin",
        "pastor", "personal_ministries", "dorcas", "health_ministries", "case_worker",
    }):
        return _error("Authorized church access is required.", 403, "forbidden")
    docs = list(collection("jumuiya_missionpulse_cases").find({
        "church_id": org_id
    }).sort("updated_at", -1).limit(200))
    return jsonify(success=True, cases=[_json(x) for x in docs]), 200


@missionpulse_bp.patch("/cases/<case_id>")
@require_authenticated
def update_case(case_id):
    oid = _oid(case_id)
    if not oid:
        return _error("Invalid case ID.")
    cases = collection("jumuiya_missionpulse_cases")
    case = cases.find_one({"_id": oid})
    if not case:
        return _error("Case not found.", 404, "not_found")
    org_id = case.get("church_id")
    if not _require_org(org_id, {
        "conference_admin", "field_admin", "district_coordinator", "church_admin",
        "pastor", "personal_ministries", "dorcas", "health_ministries", "case_worker",
    }):
        return _error("You cannot access this case.", 403, "forbidden")
    data = _body()
    allowed_status = {"new", "reviewed", "assigned", "in_progress", "follow_up_required", "resolved"}
    updates = {}
    if "status" in data:
        status = _text(data["status"], 40).lower()
        if status not in allowed_status:
            return _error("Invalid case status.")
        updates["status"] = status
    if "assigned_to" in data:
        assignee = _text(data["assigned_to"], 128) or None
        if assignee and not collection("jumuiya_missionpulse_memberships").find_one({
            "church_id": org_id, "user_id": assignee, "status": "active"
        }):
            # Memberships are attached to the organization ID, not a separate church_id field.
            if not collection("jumuiya_missionpulse_memberships").find_one({
                "org_id": org_id, "user_id": assignee, "status": "active"
            }):
                return _error("The assigned officer is not an active member of this church.", 400, "invalid_assignee")
        updates["assigned_to"] = assignee
    if "assigned_ministry" in data:
        updates["assigned_ministry"] = _text(data["assigned_ministry"], 80) or None
    if "due_at" in data:
        updates["due_at"] = _text(data["due_at"], 50) or None
    if "assignment_note" in data:
        updates["assignment_note"] = _text(data["assignment_note"], 1000)
    if "follow_up_note" in data:
        note = _text(data["follow_up_note"], 1200)
        if note:
            cases.update_one({"_id": oid}, {"$push": {"follow_ups": {
                "note": note, "created_by": current_user_id(), "created_at": _now()
            }}})
    updates["updated_at"] = _now()
    if updates:
        cases.update_one({"_id": oid}, {"$set": updates})
    _audit("case.updated", "case", case_id, org_id, {"fields": sorted(updates)})
    return jsonify(success=True, case=_json(cases.find_one({"_id": oid}))), 200


@missionpulse_bp.post("/outreach")
@require_authenticated
def create_outreach():
    data = _body()
    org_id = _text(data.get("church_id"), 64)
    if not _oid(org_id) or not _require_org(org_id, {
        "conference_admin", "field_admin", "district_coordinator", "church_admin",
        "pastor", "personal_ministries", "dorcas", "health_ministries",
        "youth_ministries", "family_ministries", "education_ministries",
    }):
        return _error("Authorized church or ministry membership is required.", 403, "forbidden")
    title = _text(data.get("title"), 180)
    if not title:
        return _error("Outreach programme title is required.")
    volunteer_ids = list(dict.fromkeys(
        _text(x, 128) for x in (data.get("volunteer_user_ids") or []) if _text(x, 128)
    ))[:200]
    if volunteer_ids:
        active_ids = {
            item.get("user_id") for item in collection("jumuiya_missionpulse_memberships").find({
                "org_id": org_id, "status": "active", "user_id": {"$in": volunteer_ids}
            }, {"user_id": 1})
        }
        if set(volunteer_ids) - active_ids:
            return _error("Every assigned volunteer must be an active member of this church.", 400, "invalid_volunteer")
    doc = {
        "church_id": org_id, "title": title,
        "programme_type": _text(data.get("programme_type"), 60),
        "description": _text(data.get("description"), 1500),
        "venue_general": _text(data.get("venue_general"), 180),
        "starts_at": _text(data.get("starts_at"), 50),
        "ends_at": _text(data.get("ends_at"), 50),
        "volunteer_user_ids": volunteer_ids,
        "attendance_count": 0, "people_reached": 0, "services_delivered": [],
        "status": "planned", "created_by": current_user_id(),
        "created_at": _now(), "updated_at": _now(),
    }
    result = collection("jumuiya_missionpulse_outreach").insert_one(doc)
    doc["_id"] = result.inserted_id
    _audit("outreach.created", "outreach", result.inserted_id, org_id)
    return jsonify(success=True, outreach=_json(doc)), 201


@missionpulse_bp.get("/outreach")
@require_authenticated
def list_outreach():
    org_id = _text(request.args.get("church_id"), 64)
    if not org_id or not _require_org(org_id):
        return _error("Authorized church access is required.", 403, "forbidden")
    docs = list(collection("jumuiya_missionpulse_outreach").find({
        "church_id": org_id
    }).sort("starts_at", -1).limit(200))
    return jsonify(success=True, programmes=[_json(x) for x in docs]), 200


@missionpulse_bp.patch("/outreach/<programme_id>")
@require_authenticated
def update_outreach(programme_id):
    oid = _oid(programme_id)
    if not oid:
        return _error("Invalid programme ID.")
    programmes = collection("jumuiya_missionpulse_outreach")
    programme = programmes.find_one({"_id": oid})
    if not programme:
        return _error("Programme not found.", 404, "not_found")
    if not _require_org(programme.get("church_id"), {
        "conference_admin", "field_admin", "district_coordinator", "church_admin",
        "pastor", "personal_ministries", "dorcas", "health_ministries",
        "youth_ministries", "family_ministries", "education_ministries",
    }):
        return _error("You cannot update this programme.", 403, "forbidden")
    data = _body()
    updates = {}
    for key, limit in (("status", 30), ("attendance_count", 8), ("people_reached", 8)):
        if key in data:
            value = data[key]
            if key in {"attendance_count", "people_reached"}:
                try:
                    value = max(0, min(int(value), 1000000))
                except (TypeError, ValueError):
                    return _error(key + " must be a non-negative integer.")
            else:
                value = _text(value, limit)
                if value not in {"planned", "in_progress", "completed", "cancelled"}:
                    return _error("Invalid programme status.")
            updates[key] = value
    if "services_delivered" in data and isinstance(data["services_delivered"], list):
        updates["services_delivered"] = [_text(x, 120) for x in data["services_delivered"][:50] if _text(x, 120)]
    updates["updated_at"] = _now()
    programmes.update_one({"_id": oid}, {"$set": updates})
    _audit("outreach.updated", "outreach", programme_id, programme.get("church_id"), {"fields": sorted(updates)})
    return jsonify(success=True, outreach=_json(programmes.find_one({"_id": oid})))


@missionpulse_bp.get("/reports/church/<church_id>")
@require_authenticated
def church_report(church_id):
    if not _require_org(church_id, {
        "conference_admin", "field_admin", "district_coordinator", "church_admin",
        "pastor", "report_viewer",
    }):
        return _error("You cannot view this church report.", 403, "forbidden")
    cases = collection("jumuiya_missionpulse_cases")
    outreach = collection("jumuiya_missionpulse_outreach")
    case_total = cases.count_documents({"church_id": church_id})
    resolved = cases.count_documents({"church_id": church_id, "status": "resolved"})
    programmes = list(outreach.find({"church_id": church_id}, {
        "attendance_count": 1, "people_reached": 1, "status": 1, "services_delivered": 1
    }).limit(1000))
    return jsonify(success=True, report={
        "church_id": church_id, "cases_registered": case_total,
        "cases_resolved": resolved, "cases_open": max(0, case_total - resolved),
        "programmes_planned": len(programmes),
        "programmes_completed": sum(1 for x in programmes if x.get("status") == "completed"),
        "attendance_total": sum(int(x.get("attendance_count") or 0) for x in programmes),
        "people_reached_total": sum(int(x.get("people_reached") or 0) for x in programmes),
    }), 200


@missionpulse_bp.get("/reports/conference/<conference_id>")
@require_authenticated
def conference_report(conference_id):
    if not _is_platform_admin() and not _require_org(conference_id, {"conference_admin", "report_viewer"}):
        return _error("Conference-level reporting access is required.", 403, "forbidden")
    orgs = collection("jumuiya_missionpulse_organizations")
    churches = list(orgs.find({"conference_id": conference_id, "type": "church", "status": "active"}, {"_id": 1}))
    church_ids = [str(x["_id"]) for x in churches]
    cases = collection("jumuiya_missionpulse_cases")
    outreach = collection("jumuiya_missionpulse_outreach")
    case_total = cases.count_documents({"church_id": {"$in": church_ids}})
    resolved = cases.count_documents({"church_id": {"$in": church_ids}, "status": "resolved"})
    programmes = list(outreach.find({"church_id": {"$in": church_ids}}, {
        "attendance_count": 1, "people_reached": 1, "status": 1
    }).limit(10000))
    return jsonify(success=True, report={
        "conference_id": conference_id, "participating_churches": len(church_ids),
        "cases_registered": case_total, "cases_resolved": resolved,
        "cases_open": max(0, case_total - resolved),
        "programmes_planned": len(programmes),
        "programmes_completed": sum(1 for x in programmes if x.get("status") == "completed"),
        "attendance_total": sum(int(x.get("attendance_count") or 0) for x in programmes),
        "people_reached_total": sum(int(x.get("people_reached") or 0) for x in programmes),
        "privacy": "Aggregated counts only; beneficiary details are not exposed.",
    }), 200


@missionpulse_bp.post("/sync")
@require_authenticated
def sync_queue():
    """Idempotent offline outbox replay. Each item must include client_id and kind."""
    data = _body()
    items = data.get("items")
    if not isinstance(items, list) or len(items) > 100:
        return _error("Sync requires an items array containing at most 100 records.")
    results = []
    for item in items:
        if not isinstance(item, dict):
            results.append({"ok": False, "error": "invalid_item"})
            continue
        client_id = _text(item.get("client_id"), 100)
        kind = _text(item.get("kind"), 30)
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        if not client_id or kind not in {"case", "outreach"}:
            results.append({"client_id": client_id, "ok": False, "error": "invalid_item"})
            continue
        receipt = collection("jumuiya_missionpulse_sync_receipts").find_one({
            "user_id": current_user_id(), "client_id": client_id
        })
        if receipt:
            results.append({"client_id": client_id, "ok": True, "duplicate": True, "server_id": receipt.get("server_id")})
            continue
        # Reuse the same validation and authorization paths as online writes.
        org_id = _text(payload.get("church_id"), 64)
        if not _oid(org_id) or not _require_org(org_id):
            results.append({"client_id": client_id, "ok": False, "error": "forbidden_or_invalid_church"})
            continue
        if kind == "case":
            category = _text(payload.get("category"), 50).lower()
            summary = _text(payload.get("summary"), 1200)
            if category not in {"basic_needs", "education", "health_referral", "family_support", "bible_study", "youth_development", "other"} or not summary or payload.get("consent") is not True:
                results.append({"client_id": client_id, "ok": False, "error": "invalid_case_or_missing_consent"})
                continue
            doc = {
                "church_id": org_id, "category": category, "summary": summary,
                "beneficiary_name": _text(payload.get("beneficiary_name"), 160),
                "beneficiary_contact": _text(payload.get("beneficiary_contact"), 80),
                "consent": True, "status": "new", "created_by": current_user_id(),
                "created_at": _now(), "updated_at": _now(), "offline_client_id": client_id,
            }
            result = collection("jumuiya_missionpulse_cases").insert_one(doc)
        else:
            title = _text(payload.get("title"), 180)
            if not title:
                results.append({"client_id": client_id, "ok": False, "error": "missing_title"})
                continue
            doc = {
                "church_id": org_id, "title": title,
                "programme_type": _text(payload.get("programme_type"), 60),
                "description": _text(payload.get("description"), 1500),
                "starts_at": _text(payload.get("starts_at"), 50),
                "status": "planned", "created_by": current_user_id(),
                "created_at": _now(), "updated_at": _now(), "offline_client_id": client_id,
            }
            result = collection("jumuiya_missionpulse_outreach").insert_one(doc)
        collection("jumuiya_missionpulse_sync_receipts").insert_one({
            "user_id": current_user_id(), "client_id": client_id,
            "kind": kind, "server_id": str(result.inserted_id), "created_at": _now(),
        })
        _audit(kind + ".synced", kind, result.inserted_id, org_id, {"client_id": client_id})
        results.append({"client_id": client_id, "ok": True, "duplicate": False, "server_id": str(result.inserted_id)})
    return jsonify(success=True, results=results), 200


@missionpulse_bp.get("/memberships")
@require_authenticated
def list_memberships():
    org_id = _text(request.args.get("org_id"), 64)
    if not org_id or not _require_org(org_id, {"conference_admin", "field_admin", "district_coordinator", "church_admin"}):
        return _error("Organization administrator access is required.", 403, "forbidden")
    docs = list(collection("jumuiya_missionpulse_memberships").find({
        "org_id": org_id, "status": "active"
    }, {"user_id": 1, "role": 1, "created_at": 1}).sort("role", 1).limit(500))
    return jsonify(success=True, members=[_json(x) for x in docs]), 200


@missionpulse_bp.get("/map/<conference_id>")
@require_authenticated
def mission_map(conference_id):
    if not _is_platform_admin() and not _require_org(conference_id, {"conference_admin", "report_viewer"}):
        return _error("Conference-level map access is required.", 403, "forbidden")
    churches = list(collection("jumuiya_missionpulse_organizations").find({
        "conference_id": conference_id, "type": "church", "status": "active",
        "latitude": {"$ne": None}, "longitude": {"$ne": None},
    }, {"name": 1, "county": 1, "town": 1, "latitude": 1, "longitude": 1, "_id": 1}).limit(500))
    pins = []
    for church in churches:
        church_id = str(church["_id"])
        pins.append({
            "church_id": church_id,
            "name": church.get("name"),
            "county": church.get("county"),
            "town": church.get("town"),
            "latitude": church.get("latitude"),
            "longitude": church.get("longitude"),
            "cases_registered": collection("jumuiya_missionpulse_cases").count_documents({"church_id": church_id}),
            "programmes_completed": collection("jumuiya_missionpulse_outreach").count_documents({"church_id": church_id, "status": "completed"}),
        })
    return jsonify(success=True, pins=pins,
                   privacy="Only church locations and aggregated activity are shown; beneficiary locations are never exposed."), 200
