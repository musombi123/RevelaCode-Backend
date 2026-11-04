"""Admin-only sample records for the Jumuiya ecosystem.

These fixtures are deliberately stored in a dedicated collection. They are
never inserted into tenant collections, public Community feeds, user accounts,
school ledgers, wallets, or live business/farm operations.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.jumuiya.core.database import collection

SAMPLE_DATA_VERSION = 1
SAMPLE_COLLECTION = "jumuiya_admin_sample_records"

HUB_LABELS = {
    "community": "Community Center",
    "shamba": "Shamba",
    "biashara": "Biashara",
    "elimu": "Elimu",
    "marketplace": "Marketplace",
    "faith": "Faith & MissionPulse",
    "shared": "Shared Jumuiya Services",
}

# Stable IDs make seeding safe to run more than once. All names and figures
# below are fictional training examples; contact details are intentionally
# omitted and no sample identity can authenticate to the platform.
_SAMPLE_FIXTURES: tuple[dict[str, Any], ...] = (
    # COMMUNITY CENTER
    {
        "sample_id": "community.group.coast-technology-makers",
        "hub": "community", "module": "Groups", "record_type": "group",
        "title": "Coast Technology Makers",
        "summary": "A public learning group for local developers, designers, and technology students.",
        "status": "active", "location": "Mombasa, Kenya",
        "details": {"group_type": "professional", "visibility": "public", "members": 128, "join_mode": "open", "topics": ["software", "AI", "design"]},
    },
    {
        "sample_id": "community.group.coastal-farmers-network",
        "hub": "community", "module": "Groups", "record_type": "group",
        "title": "Coastal Farmers Network",
        "summary": "A peer group sharing crop practices, market information, and climate-smart farming knowledge.",
        "status": "active", "location": "Kilifi County",
        "details": {"group_type": "agriculture", "visibility": "discoverable", "members": 342, "join_mode": "request", "topics": ["maize", "cassava", "horticulture"]},
    },
    {
        "sample_id": "community.post.digital-skills-clinic",
        "hub": "community", "module": "Pulse Feed", "record_type": "post",
        "title": "Free digital skills clinic this Saturday",
        "summary": "A sample announcement inviting members to a practical session on online safety and digital productivity.",
        "status": "published", "location": "Mombasa, Kenya",
        "details": {"author_label": "Community Learning Team (sample)", "type": "announcement", "category": "technology", "likes": 24, "comments": 8, "shares": 3},
    },
    {
        "sample_id": "community.thread.market-access-help",
        "hub": "community", "module": "Threads", "record_type": "thread",
        "title": "How can small farmers reach reliable buyers?",
        "summary": "A sample help discussion connecting Shamba farmers with Biashara buyers and marketplace guidance.",
        "status": "open", "location": "Coast Region",
        "details": {"thread_type": "help", "replies": 16, "participants": 9, "linked_hubs": ["shamba", "biashara", "marketplace"]},
    },
    {
        "sample_id": "community.event.community-connect-day",
        "hub": "community", "module": "Events", "record_type": "event",
        "title": "Jumuiya Community Connect Day",
        "summary": "A sample cross-hub showcase for learning, local businesses, farmers, and community projects.",
        "status": "scheduled", "location": "Mombasa, Kenya",
        "details": {"event_date": "2026-12-05", "capacity": 180, "registrations": 64, "visibility": "public"},
    },
    {
        "sample_id": "community.moderation.sample-report",
        "hub": "community", "module": "Trust & Moderation", "record_type": "moderation_report",
        "title": "Sample marketplace misinformation report",
        "summary": "A training moderation case showing how reports are queued, reviewed, and resolved.",
        "status": "reviewing", "location": "Community-wide",
        "details": {"report_type": "misinformation", "priority": "normal", "assigned_to": "Sample Moderator", "resolution_target": "Review source evidence before action"},
    },
    {
        "sample_id": "community.member.directory-example",
        "hub": "community", "module": "Member Directory", "record_type": "member",
        "title": "Community Contributor 001",
        "summary": "A fictional member profile for demonstrating directory and trust-state administration.",
        "status": "basic", "location": "Mombasa County",
        "details": {"member_ref": "SAMPLE-MEMBER-001", "interests": ["technology", "community projects"], "contributions": 12, "trust_level": "basic"},
    },

    # SHAMBA
    {
        "sample_id": "shamba.farmer.coast-grower",
        "hub": "shamba", "module": "Farmer Profiles", "record_type": "farmer",
        "title": "Sample Farmer Amina",
        "summary": "A fictional farmer profile with a completed farm profile and pending ownership review.",
        "status": "pending", "location": "Kilifi County, Kenya",
        "details": {"farmer_ref": "SAMPLE-FARMER-001", "farm_count": 2, "experience_years": 6, "primary_crops": ["maize", "cassava", "cowpeas"], "profile_completed": True},
    },
    {
        "sample_id": "shamba.farm.mwangaza",
        "hub": "shamba", "module": "Farms", "record_type": "farm",
        "title": "Mwangaza Demonstration Farm",
        "summary": "A sample mixed farm showing acreage, soil, water-source, and verification fields.",
        "status": "pending_verification", "location": "Kilifi County, Kenya",
        "details": {"farm_ref": "SAMPLE-FARM-001", "size_acres": 4.5, "soil_type": "sandy loam", "water_source": "rain-fed and water tank", "farming_type": "mixed"},
    },
    {
        "sample_id": "shamba.crop.maize-season",
        "hub": "shamba", "module": "Crops", "record_type": "crop",
        "title": "Maize — Short Rains Season",
        "summary": "A sample crop record with planting, expected yield, crop health, and input costs.",
        "status": "growing", "location": "Kilifi County, Kenya",
        "details": {"crop_ref": "SAMPLE-CROP-001", "area_acres": 2, "expected_yield_kg": 2400, "health_status": "healthy", "estimated_cost_kes": 18500},
    },
    {
        "sample_id": "shamba.activity.soil-preparation",
        "hub": "shamba", "module": "Farm Activities", "record_type": "activity",
        "title": "Land preparation and compost application",
        "summary": "A sample operational activity linked to the Mwangaza demonstration farm.",
        "status": "completed", "location": "Kilifi County, Kenya",
        "details": {"activity_type": "ploughing", "cost_kes": 4200, "quantity": 2, "unit": "acres", "payment_status": "paid"},
    },
    {
        "sample_id": "shamba.harvest.maize-lot",
        "hub": "shamba", "module": "Harvests", "record_type": "harvest",
        "title": "Maize Harvest Lot A",
        "summary": "A sample harvest with quantity, grade, asking price, and marketplace readiness.",
        "status": "available", "location": "Kilifi County, Kenya",
        "details": {"quantity_kg": 850, "quality": "Grade A", "asking_price_kes_per_kg": 48, "sold_quantity_kg": 0, "market_status": "available"},
    },

    # BIASHARA
    {
        "sample_id": "biashara.business.coast-supplies",
        "hub": "biashara", "module": "Business Profiles", "record_type": "business",
        "title": "Coast Farm & General Supplies",
        "summary": "A fictional retail/agro-dealer business with a complete profile awaiting verification.",
        "status": "pending_verification", "location": "Mombasa County, Kenya",
        "details": {"business_ref": "SAMPLE-BIZ-001", "category": "agrovet and retail", "currency": "KES", "profile_complete": True, "verification_status": "pending"},
    },
    {
        "sample_id": "biashara.product.maize-seed",
        "hub": "biashara", "module": "Products & Stock", "record_type": "product",
        "title": "Certified Maize Seed — 2 kg",
        "summary": "A sample inventory item with a SKU, selling price, and reorder threshold.",
        "status": "active", "location": "Mombasa County, Kenya",
        "details": {"sku": "SAMPLE-SEED-002", "quantity_on_hand": 48, "reorder_level": 12, "selling_price_kes": 780, "unit": "packet"},
    },
    {
        "sample_id": "biashara.customer.community-coop",
        "hub": "biashara", "module": "Customers", "record_type": "customer",
        "title": "Coastal Growers Cooperative",
        "summary": "A fictional wholesale customer record for demonstrating customer management.",
        "status": "active", "location": "Kilifi County, Kenya",
        "details": {"customer_ref": "SAMPLE-CUSTOMER-001", "customer_type": "organization", "orders_count": 4, "credit_limit_kes": 25000},
    },
    {
        "sample_id": "biashara.order.sample-104",
        "hub": "biashara", "module": "Orders", "record_type": "order",
        "title": "Sample Order #104",
        "summary": "A sample order showing line items, fulfillment state, and total value.",
        "status": "processing", "location": "Mombasa County, Kenya",
        "details": {"order_ref": "SAMPLE-ORDER-104", "items": 3, "total_kes": 12600, "payment_status": "paid", "fulfilment": "packing"},
    },
    {
        "sample_id": "biashara.sale.counter-sale",
        "hub": "biashara", "module": "Sales & Finance", "record_type": "sale",
        "title": "Sample Counter Sale",
        "summary": "A fictional sale record used to demonstrate sales totals and payment reconciliation screens.",
        "status": "paid", "location": "Mombasa County, Kenya",
        "details": {"receipt_ref": "SAMPLE-RCPT-0081", "subtotal_kes": 5400, "tax_kes": 0, "total_kes": 5400, "payment_method": "cash"},
    },
    {
        "sample_id": "biashara.expense.transport",
        "hub": "biashara", "module": "Expenses", "record_type": "expense",
        "title": "Sample Delivery Expense",
        "summary": "A sample operating expense categorized for transport and delivery.",
        "status": "recorded", "location": "Mombasa County, Kenya",
        "details": {"category": "transport", "amount_kes": 950, "currency": "KES", "approval_status": "approved"},
    },
    {
        "sample_id": "biashara.service.delivery",
        "hub": "biashara", "module": "Services", "record_type": "service",
        "title": "Local Delivery Service",
        "summary": "A sample service catalogue entry with a clear delivery scope.",
        "status": "active", "location": "Mombasa County, Kenya",
        "details": {"service_ref": "SAMPLE-SERVICE-001", "price_from_kes": 250, "availability": "same-day subject to route"},
    },

    # ELIMU
    {
        "sample_id": "elimu.school.mwangaza-academy",
        "hub": "elimu", "module": "Schools", "record_type": "school",
        "title": "Mwangaza Community Academy",
        "summary": "A fictional school profile for displaying school registration and verification workflows.",
        "status": "pending", "location": "Mombasa County, Kenya",
        "details": {"school_ref": "SAMPLE-SCHOOL-001", "school_type": "primary", "principal_label": "Sample Principal", "verification_status": "pending", "is_demo": True},
    },
    {
        "sample_id": "elimu.class.grade-six-blue",
        "hub": "elimu", "module": "Classes", "record_type": "class",
        "title": "Grade 6 Blue",
        "summary": "A sample class group with a teacher allocation and active learner count.",
        "status": "active", "location": "Mombasa County, Kenya",
        "details": {"class_ref": "SAMPLE-CLASS-006B", "level": "Grade 6", "stream": "Blue", "learner_count": 32, "academic_year": "2026"},
    },
    {
        "sample_id": "elimu.student.learner-001",
        "hub": "elimu", "module": "Students", "record_type": "student",
        "title": "Sample Learner 001",
        "summary": "A fictional learner record with a sample admission reference.",
        "status": "active", "location": "Mombasa County, Kenya",
        "details": {"admission_ref": "SAMPLE-ADM-001", "class_name": "Grade 6 Blue", "guardian_ref": "SAMPLE-GUARDIAN-001"},
    },
    {
        "sample_id": "elimu.staff.teacher-001",
        "hub": "elimu", "module": "Staff", "record_type": "staff",
        "title": "Sample Mathematics Teacher",
        "summary": "A fictional staff profile for teacher and HR workspace previews.",
        "status": "active", "location": "Mombasa County, Kenya",
        "details": {"staff_ref": "SAMPLE-STAFF-001", "role": "teacher", "subjects": ["Mathematics", "Science"], "employment_type": "full_time"},
    },
    {
        "sample_id": "elimu.attendance.grade-six",
        "hub": "elimu", "module": "Attendance", "record_type": "attendance",
        "title": "Grade 6 Attendance — Sample Day",
        "summary": "A sample daily roll call summary for the Grade 6 Blue class.",
        "status": "recorded", "location": "Mombasa County, Kenya",
        "details": {"date": "2026-11-03", "present": 29, "absent": 2, "late": 1, "total": 32},
    },
    {
        "sample_id": "elimu.fee.term-two",
        "hub": "elimu", "module": "Fees & Finance", "record_type": "fee",
        "title": "Term 2 Sample Fee Balance",
        "summary": "A fictional votehead summary for demonstrating school fee balances.",
        "status": "partially_paid", "location": "Mombasa County, Kenya",
        "details": {"student_ref": "SAMPLE-ADM-001", "billed_kes": 18500, "paid_kes": 12000, "balance_kes": 6500, "term": "Term 2 2026"},
    },
    {
        "sample_id": "elimu.assessment.maths-midterm",
        "hub": "elimu", "module": "Assessments", "record_type": "assessment",
        "title": "Mathematics Mid-Term Assessment",
        "summary": "A sample assessment result for demonstrating class performance reporting.",
        "status": "published", "location": "Mombasa County, Kenya",
        "details": {"subject": "Mathematics", "score": 78, "maximum_score": 100, "grade": "B", "term": "Term 2 2026"},
    },
    {
        "sample_id": "elimu.lesson.fractions",
        "hub": "elimu", "module": "Learning", "record_type": "lesson",
        "title": "Fractions and Equivalent Values",
        "summary": "A sample lesson plan with a learning objective and classroom activity.",
        "status": "published", "location": "Mombasa County, Kenya",
        "details": {"subject": "Mathematics", "class_name": "Grade 6 Blue", "duration_minutes": 40, "learning_area": "Number"},
    },
    {
        "sample_id": "elimu.event.parent-day",
        "hub": "elimu", "module": "School Calendar", "record_type": "event",
        "title": "Sample Parent Engagement Day",
        "summary": "A sample school calendar event for parent and teacher engagement.",
        "status": "scheduled", "location": "Mombasa County, Kenya",
        "details": {"event_date": "2026-11-20", "event_type": "parent_meeting", "expected_attendees": 90},
    },

    # MARKETPLACE
    {
        "sample_id": "marketplace.listing.maize-grain",
        "hub": "marketplace", "module": "Listings", "record_type": "listing",
        "title": "Dry Maize Grain — 850 kg",
        "summary": "A sample marketplace listing connected conceptually to the Shamba harvest workflow.",
        "status": "active", "location": "Kilifi County, Kenya",
        "details": {"listing_ref": "SAMPLE-LISTING-001", "quantity": 850, "unit": "kg", "asking_price_kes_per_kg": 48, "seller_hub": "shamba"},
    },
    {
        "sample_id": "marketplace.request.maize-buyer",
        "hub": "marketplace", "module": "Buyer Requests", "record_type": "buyer_request",
        "title": "Buyer Request — Maize Grain",
        "summary": "A sample buyer request showing quantity, quality requirements, and delivery region.",
        "status": "open", "location": "Mombasa County, Kenya",
        "details": {"request_ref": "SAMPLE-BUY-001", "quantity_kg": 500, "quality": "dry and clean", "budget_kes_per_kg": 52},
    },

    # FAITH / MISSIONPULSE
    {
        "sample_id": "faith.organization.coastal-fellowship",
        "hub": "faith", "module": "MissionPulse", "record_type": "organization",
        "title": "Coastal Community Fellowship",
        "summary": "A fictional faith organization for previewing MissionPulse organization administration.",
        "status": "active", "location": "Mombasa County, Kenya",
        "details": {"organization_ref": "SAMPLE-ORG-001", "organization_type": "church", "members": 86, "teams": 5},
    },
    {
        "sample_id": "faith.outreach.community-care",
        "hub": "faith", "module": "Outreach", "record_type": "outreach",
        "title": "Community Care Outreach",
        "summary": "A sample outreach activity with volunteer and beneficiary planning figures.",
        "status": "scheduled", "location": "Mombasa County, Kenya",
        "details": {"outreach_ref": "SAMPLE-OUTREACH-001", "starts_on": "2026-11-21", "volunteers": 14, "planned_beneficiaries": 60},
    },

    # SHARED SERVICES
    {
        "sample_id": "shared.identity.profile",
        "hub": "shared", "module": "Identity", "record_type": "identity_profile",
        "title": "Sample Jumuiya Member Profile",
        "summary": "A fictional profile demonstrating cross-hub identity fields without creating an account.",
        "status": "sample", "location": "Coast Region, Kenya",
        "details": {"profile_ref": "SAMPLE-PROFILE-001", "active_hubs": ["community", "shamba"], "account_created": False},
    },
    {
        "sample_id": "shared.wallet.transaction",
        "hub": "shared", "module": "Wallet", "record_type": "wallet_transaction",
        "title": "Sample Wallet Credit",
        "summary": "A non-financial training record; no M-Pesa request or money movement was performed.",
        "status": "illustrative", "location": "Kenya",
        "details": {"transaction_ref": "SAMPLE-WALLET-001", "amount_kes": 1500, "transaction_type": "credit", "provider": "sample_only", "settled": False},
    },
    {
        "sample_id": "shared.notifications.sample",
        "hub": "shared", "module": "Notifications", "record_type": "notification",
        "title": "Sample School Fee Reminder",
        "summary": "A fictional notification preview for the shared notification centre.",
        "status": "unread", "location": "Platform-wide",
        "details": {"notification_ref": "SAMPLE-NOTICE-001", "channel": "in_app", "target_hub": "elimu", "delivery_attempted": False},
    },
    {
        "sample_id": "shared.audit.activity",
        "hub": "shared", "module": "Audit & Activity", "record_type": "audit_event",
        "title": "Sample Admin Review Activity",
        "summary": "An illustrative audit event showing the kind of activity platform administrators can inspect.",
        "status": "sample", "location": "Platform-wide",
        "details": {"event_ref": "SAMPLE-AUDIT-001", "action": "sample.review.opened", "actor_label": "Sample Administrator", "real_user_action": False},
    },
)

def sample_fixtures() -> list[dict[str, Any]]:
    """Return fresh fixture dictionaries for safe callers and tests."""
    return [dict(item, details=dict(item["details"])) for item in _SAMPLE_FIXTURES]


def seed_sample_records() -> dict[str, Any]:
    """Idempotently upsert sample fixtures into the isolated admin collection."""
    target = collection(SAMPLE_COLLECTION)
    now = datetime.now(timezone.utc)
    inserted = 0
    updated = 0

    for fixture in _SAMPLE_FIXTURES:
        document = {
            **fixture,
            "details": dict(fixture["details"]),
            "is_sample": True,
            "seed_managed": True,
            "seed_version": SAMPLE_DATA_VERSION,
            "sample_label": "SAMPLE DATA — NOT A LIVE CUSTOMER RECORD",
            "created_at": now,
            "updated_at": now,
        }
        result = target.update_one(
            {"sample_id": fixture["sample_id"]},
            {
                "$set": document,
                "$setOnInsert": {"first_seeded_at": now},
            },
            upsert=True,
        )
        if result.upserted_id is not None:
            inserted += 1
        elif result.modified_count:
            updated += 1

    counts = {
        hub: target.count_documents({
            "seed_managed": True,
            "hub": hub,
        })
        for hub in HUB_LABELS
    }

    return {
        "inserted": inserted,
        "updated": updated,
        "total": sum(counts.values()),
        "counts_by_hub": counts,
        "version": SAMPLE_DATA_VERSION,
        "collection": SAMPLE_COLLECTION,
    }
