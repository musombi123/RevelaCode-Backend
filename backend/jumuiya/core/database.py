# backend/jumuiya/core/database.py

from __future__ import annotations

from pymongo import ASCENDING, DESCENDING

from backend.db import get_db


# =========================================================
# JUMUIYA COLLECTION PREFIX
# =========================================================

JUMUIYA_PREFIX = "jumuiya_"


# =========================================================
# DATABASE / COLLECTION
# =========================================================

def collection(name: str):
    """
    Return a Jumuiya collection from the existing RevelaCode
    MongoDB database.

    Jumuiya uses the SAME MongoDB database as RevelaCode,
    while keeping its own collections under the `jumuiya_`
    namespace.
    """

    if not isinstance(name, str):
        raise ValueError(
            "Collection name must be text."
        )

    name = name.strip()

    if not name:
        raise ValueError(
            "Collection name is required."
        )

    if not name.startswith(
        JUMUIYA_PREFIX
    ):
        raise ValueError(
            "Jumuiya collections must use "
            "the 'jumuiya_' prefix."
        )

    return get_db()[name]


# =========================================================
# INDEX DEFINITIONS
# =========================================================
#
# Keeping definitions in one place makes ensure_indexes()
# auditable and prevents accidental duplicate declarations.
#
# Important integrity indexes:
#   - one profile per user
#   - one school per owner
#   - one student admission number per school
#   - one attendance record per student per date
#   - one unique Community reaction per user/post
#
# Query indexes are intentionally scoped by their tenant /
# ownership fields first because Jumuiya is multi-domain.
# =========================================================

INDEX_DEFINITIONS = {
    # -----------------------------------------------------
    # SHARED JUMUIYA CORE
    # -----------------------------------------------------

    "jumuiya_profiles": [
        (
            [
                ("user_id", ASCENDING),
            ],
            {"unique": True, "name": "uq_jumuiya_profiles_user"},
        ),
    ],

    "jumuiya_transactions": [
        (
            [
                ("user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_jumuiya_transactions_user_created"},
        ),
    ],

    "jumuiya_roles": [
        (
            [
                ("user_id", ASCENDING),
                ("role", ASCENDING),
            ],
            {"unique": True, "name": "uq_jumuiya_roles_user_role"},
        ),
    ],

    "jumuiya_notifications": [
        (
            [
                ("user_id", ASCENDING),
                ("read", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_jumuiya_notifications_user_read_created"},
        ),
        (
            [
                ("user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_jumuiya_notifications_user_created"},
        ),
    ],

    "jumuiya_business_website_inquiries": [
        (
            [
                ("business_id", ASCENDING),
                ("owner_user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_biashara_website_inquiries_owner_created"},
        ),
    ],

    "jumuiya_audit_logs": [
        (
            [
                ("user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_jumuiya_audit_user_created"},
        ),
        (
            [
                ("resource", ASCENDING),
                ("resource_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_jumuiya_audit_resource_created"},
        ),
        (
            [
                ("action", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_jumuiya_audit_action_created"},
        ),
    ],

    # -----------------------------------------------------
    # COMMUNITY
    # -----------------------------------------------------

    "jumuiya_community_posts": [
        (
            [
                ("status", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_posts_status_created"},
        ),
        (
            [
                ("category", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_posts_category_created"},
        ),
        (
            [
                ("hub", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_posts_hub_created"},
        ),
        (
            [
                ("author_user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_posts_author_created"},
        ),
        (
            [
                ("status", ASCENDING),
                ("hub", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_posts_status_hub_created"},
        ),
        (
            [
                ("status", ASCENDING),
                ("type", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_posts_status_type_created"},
        ),
        (
            [
                ("status", ASCENDING),
                ("location", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_posts_status_location_created"},
        ),
    ],

    "jumuiya_community_comments": [
        (
            [
                ("post_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_comments_post_created"},
        ),
        (
            [
                ("author_user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_comments_author_created"},
        ),
    ],

    "jumuiya_community_reactions": [
        (
            [
                ("post_id", ASCENDING),
                ("user_id", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_community_reactions_post_user",
            },
        ),
        (
            [
                ("user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_reactions_user_created"},
        ),
    ],

    "jumuiya_community_groups": [
        (
            [
                ("status", ASCENDING),
                ("category", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_groups_status_category_created"},
        ),
        (
            [
                ("status", ASCENDING),
                ("featured", DESCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_groups_status_featured_created"},
        ),
        (
            [
                ("status", ASCENDING),
                ("member_user_ids", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_groups_member_created"},
        ),
        (
            [
                ("created_by_user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_community_groups_creator_created"},
        ),
    ],

    # -----------------------------------------------------
    # MARKETPLACE
    # -----------------------------------------------------

    "jumuiya_marketplace_listings": [
        (
            [
                ("status", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_marketplace_listings_status_created"},
        ),
        (
            [
                ("hub", ASCENDING),
                ("category", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_marketplace_listings_hub_category_created"},
        ),
        (
            [
                ("seller_user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_marketplace_listings_seller_created"},
        ),
    ],

    # -----------------------------------------------------
    # BIASHARA
    # -----------------------------------------------------

    "jumuiya_businesses": [
        (
            [
                ("owner_user_id", ASCENDING),
                ("created_at", ASCENDING),
            ],
            {
                "name": "ix_businesses_owner_created",
            },
        ),
        (
            [
                ("slug", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_businesses_slug",
            },
        ),
        (
            [
                ("county", ASCENDING),
                ("category", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_businesses_county_category_status"},
        ),
    ],

    "jumuiya_business_memberships": [
        (
            [("business_id", ASCENDING), ("user_id", ASCENDING)],
            {"unique": True, "name": "uq_biashara_membership_business_user"},
        ),
        (
            [("user_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
            {"name": "ix_biashara_membership_user_status"},
        ),
        (
            [("business_id", ASCENDING), ("status", ASCENDING), ("role", ASCENDING)],
            {"name": "ix_biashara_membership_business_status_role"},
        ),
    ],

    "jumuiya_products": [
        (
            [
                ("business_id", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_products_business_status"},
        ),
        (
            [
                ("business_id", ASCENDING),
                ("category", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_products_business_category_status"},
        ),
        (
            [
                ("business_id", ASCENDING),
                ("sku", ASCENDING),
            ],
            {"name": "ix_products_business_sku"},
        ),
    ],

    "jumuiya_customers": [
        (
            [
                ("business_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_customers_business_created"},
        ),
    ],

    "jumuiya_orders": [
        (
            [
                ("business_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_orders_business_created"},
        ),
        (
            [
                ("business_id", ASCENDING),
                ("status", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_orders_business_status_created"},
        ),
        (
            [
                ("business_id", ASCENDING),
                ("idempotency_key", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_orders_business_idempotency",
                "partialFilterExpression": {"idempotency_key": {"$type": "string"}},
            },
        ),
    ],

    "jumuiya_sales": [
        (
            [
                ("business_id", ASCENDING),
                ("sold_at", DESCENDING),
            ],
            {"name": "ix_sales_business_sold"},
        ),
        (
            [
                ("business_id", ASCENDING),
                ("idempotency_key", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_sales_business_idempotency",
                "partialFilterExpression": {"idempotency_key": {"$type": "string"}},
            },
        ),
        (
            [
                ("business_id", ASCENDING),
                ("order_id", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_sales_canonical_order",
                # Historical sales stay untouched; this invariant applies only
                # to sales written through the canonical order lifecycle.
                "partialFilterExpression": {
                    "canonical_order_sale": True,
                    "order_id": {"$type": "string"},
                },
            },
        ),
    ],

    "jumuiya_outbox_events": [
        (
            [
                ("business_id", ASCENDING),
                ("event_id", ASCENDING),
            ],
            {"unique": True, "name": "uq_biashara_outbox_business_event"},
        ),
        (
            [
                ("business_id", ASCENDING),
                ("state", ASCENDING),
                ("next_attempt_at", ASCENDING),
                ("created_at", ASCENDING),
            ],
            {"name": "ix_biashara_outbox_due_events"},
        ),
        (
            [
                ("business_id", ASCENDING),
                ("entity_type", ASCENDING),
                ("entity_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_biashara_outbox_entity_history"},
        ),
    ],

    "jumuiya_automation_rules": [
        (
            [("business_id", ASCENDING), ("trigger_event", ASCENDING), ("enabled", ASCENDING), ("created_at", DESCENDING)],
            {"name": "ix_biashara_automation_rules_trigger"},
        ),
    ],

    "jumuiya_automation_runs": [
        (
            [("business_id", ASCENDING), ("run_key", ASCENDING)],
            {"unique": True, "name": "uq_biashara_automation_run_key"},
        ),
        (
            [("business_id", ASCENDING), ("created_at", DESCENDING)],
            {"name": "ix_biashara_automation_runs_created"},
        ),
        (
            [("business_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
            {"name": "ix_biashara_automation_runs_status"},
        ),
    ],

    "jumuiya_automation_tasks": [
        (
            [("business_id", ASCENDING), ("task_key", ASCENDING)],
            {"unique": True, "name": "uq_biashara_automation_task_key"},
        ),
        (
            [("business_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
            {"name": "ix_biashara_automation_tasks_status"},
        ),
        (
            [("business_id", ASCENDING), ("task_type", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
            {"name": "ix_biashara_automation_tasks_type_status"},
        ),
    ],

    "jumuiya_invoices": [
        (
            [("business_id", ASCENDING), ("invoice_number", ASCENDING)],
            {
                "unique": True,
                "name": "uq_biashara_invoice_number",
                "partialFilterExpression": {"invoice_number": {"$type": "string"}},
            },
        ),
        (
            [("business_id", ASCENDING), ("idempotency_key", ASCENDING)],
            {
                "unique": True,
                "name": "uq_biashara_invoice_idempotency",
                "partialFilterExpression": {"idempotency_key": {"$type": "string"}},
            },
        ),
        (
            [("business_id", ASCENDING), ("source_order_id", ASCENDING)],
            {
                "unique": True,
                "name": "uq_biashara_invoice_order",
                "partialFilterExpression": {
                    "canonical_order_invoice": True,
                    "source_order_id": {"$type": "string"},
                },
            },
        ),
        (
            [("business_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
            {"name": "ix_biashara_invoices_status_created"},
        ),
    ],

    "jumuiya_payments": [
        (
            [("business_id", ASCENDING), ("idempotency_key", ASCENDING)],
            {
                "unique": True,
                "name": "uq_biashara_payment_idempotency",
                "partialFilterExpression": {"idempotency_key": {"$type": "string"}},
            },
        ),
        (
            [("business_id", ASCENDING), ("invoice_id", ASCENDING), ("created_at", DESCENDING)],
            {"name": "ix_biashara_payments_invoice_created"},
        ),
        (
            [("business_id", ASCENDING), ("payment_status", ASCENDING), ("created_at", DESCENDING)],
            {"name": "ix_biashara_payments_status_created"},
        ),
    ],

    "jumuiya_finance_counters": [
        (
            [("business_id", ASCENDING), ("sequence_name", ASCENDING), ("year", ASCENDING)],
            {"unique": True, "name": "uq_biashara_finance_counter"},
        ),
    ],

    "jumuiya_journal_entries": [
        (
            [("business_id", ASCENDING), ("source_key", ASCENDING)],
            {"unique": True, "name": "uq_biashara_journal_source"},
        ),
        (
            [("business_id", ASCENDING), ("effective_at", DESCENDING)],
            {"name": "ix_biashara_journal_effective"},
        ),
        (
            [("business_id", ASCENDING), ("source_type", ASCENDING), ("effective_at", DESCENDING)],
            {"name": "ix_biashara_journal_source_type"},
        ),
        (
            [("business_id", ASCENDING), ("currency", ASCENDING), ("status", ASCENDING), ("effective_at", DESCENDING)],
            {"name": "ix_biashara_journal_currency_status"},
        ),
    ],

    "jumuiya_expenses": [
        (
            [
                ("business_id", ASCENDING),
                ("spent_at", DESCENDING),
            ],
            {"name": "ix_expenses_business_spent"},
        ),
        (
            [
                ("business_id", ASCENDING),
                ("idempotency_key", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_biashara_expense_idempotency",
                "partialFilterExpression": {"idempotency_key": {"$type": "string"}},
            },
        ),
    ],

    "jumuiya_inventory_movements": [
        (
            [
                ("business_id", ASCENDING),
                ("product_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_inventory_business_product_created"},
        ),
        (
            [
                ("business_id", ASCENDING),
                ("idempotency_key", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_inventory_business_idempotency",
                "partialFilterExpression": {"idempotency_key": {"$type": "string"}},
            },
        ),
    ],

    # -----------------------------------------------------
    # SHAMBA
    # -----------------------------------------------------

    "jumuiya_farmers": [
        (
            [
                ("user_id", ASCENDING),
            ],
            {"unique": True, "name": "uq_farmers_user"},
        ),
    ],

    "jumuiya_farms": [
        (
            [
                ("owner_user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_farms_owner_created"},
        ),
        (
            [
                ("county", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_farms_county_status"},
        ),
    ],

    "jumuiya_crops": [
        (
            [
                ("farm_id", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_crops_farm_status"},
        ),
        (
            [
                ("owner_user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_crops_owner_created"},
        ),
    ],

    "jumuiya_farm_activities": [
        (
            [
                ("farm_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_farm_activities_farm_created"},
        ),
    ],

    "jumuiya_harvests": [
        (
            [
                ("farm_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_harvests_farm_created"},
        ),
        (
            [
                ("owner_user_id", ASCENDING),
                ("market_status", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_harvests_owner_market_created"},
        ),
    ],

    "jumuiya_market_prices": [
        (
            [
                ("crop", ASCENDING),
                ("county", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_market_prices_crop_county_created"},
        ),
    ],

    # =====================================================
    # ELIMU
    # =====================================================

    "jumuiya_education_profiles": [
        (
            [
                ("user_id", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_education_profiles_user",
            },
        ),
        (
            [
                ("profile_type", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_education_profiles_type_status"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_education_profiles_school_status"},
        ),
    ],

    "jumuiya_schools": [
        (
            [
                ("owner_user_id", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_schools_owner",
            },
        ),
        (
            [
                ("county", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_schools_county_status"},
        ),
        (
            [
                ("status", ASCENDING),
                ("updated_at", DESCENDING),
            ],
            {"name": "ix_schools_status_updated"},
        ),
    ],

    "jumuiya_classes": [
        (
            [
                ("school_id", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_classes_school_status"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("academic_year", ASCENDING),
                ("level", ASCENDING),
                ("name", ASCENDING),
            ],
            {"name": "ix_classes_school_year_level_name"},
        ),
    ],

    "jumuiya_students": [
        (
            [
                ("school_id", ASCENDING),
                ("admission_number", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_students_school_admission",
            },
        ),
        (
            [
                ("school_id", ASCENDING),
                ("status", ASCENDING),
                ("class_name", ASCENDING),
            ],
            {"name": "ix_students_school_status_class"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("class_id", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_students_school_class_status"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("full_name", ASCENDING),
            ],
            {"name": "ix_students_school_name"},
        ),
        (
            [
                ("student_user_id", ASCENDING),
            ],
            {"name": "ix_students_user"},
        ),
    ],

    "jumuiya_lessons": [
        (
            [
                ("school_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_lessons_school_created"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("subject", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_lessons_school_subject_created"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("class_name", ASCENDING),
                ("academic_year", ASCENDING),
                ("term", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_lessons_school_class_year_term_created"},
        ),
        (
            [
                ("subject", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_lessons_subject_created"},
        ),
    ],

    "jumuiya_assignments": [
        (
            [
                ("school_id", ASCENDING),
                ("class_name", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_assignments_school_class_created"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("subject", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_assignments_school_subject_created"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("due_date", ASCENDING),
            ],
            {"name": "ix_assignments_school_due"},
        ),
    ],

    "jumuiya_attendance": [
        (
            [
                ("school_id", ASCENDING),
                ("student_id", ASCENDING),
                ("date", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_attendance_school_student_date",
            },
        ),
        (
            [
                ("school_id", ASCENDING),
                ("class_name", ASCENDING),
                ("date", DESCENDING),
            ],
            {"name": "ix_attendance_school_class_date"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("date", DESCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_attendance_school_date_status"},
        ),
        (
            [
                ("student_id", ASCENDING),
                ("date", DESCENDING),
            ],
            {"name": "ix_attendance_student_date"},
        ),
    ],

    "jumuiya_assessments": [
        (
            [
                ("school_id", ASCENDING),
                ("student_id", ASCENDING),
                ("academic_year", ASCENDING),
                ("term", ASCENDING),
                ("subject", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_assessments_student_period_subject"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("student_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_assessments_school_student_created"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("class_name", ASCENDING),
                ("subject", ASCENDING),
                ("academic_year", ASCENDING),
                ("term", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_assessments_class_subject_period_created"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("assessment_type", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_assessments_type_created"},
        ),
    ],

    "jumuiya_fees": [
        (
            [
                ("school_id", ASCENDING),
                ("student_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_fees_school_student_created"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("status", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_fees_school_status_created"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("academic_year", ASCENDING),
                ("term", ASCENDING),
                ("status", ASCENDING),
            ],
            {"name": "ix_fees_school_period_status"},
        ),
        (
            [
                ("student_user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_fees_student_user_created"},
        ),
        (
            [
                ("payment_reference", ASCENDING),
            ],
            {
                "unique": True,
                "sparse": True,
                "name": "uq_fees_payment_reference",
            },
        ),
    ],

    "jumuiya_cbc_projects": [
        (
            [
                ("school_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_cbc_school_created"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("student_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_cbc_school_student_created"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("status", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_cbc_school_status_created"},
        ),
        (
            [
                ("student_user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {"name": "ix_cbc_student_user_created"},
        ),
    ],

    "jumuiya_school_events": [
        (
            [
                ("school_id", ASCENDING),
                ("start_date", ASCENDING),
            ],
            {"name": "ix_events_school_start"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("calendar_year", ASCENDING),
                ("start_date", ASCENDING),
            ],
            {"name": "ix_events_school_calendar_start"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("is_annual", ASCENDING),
                ("start_date", ASCENDING),
            ],
            {"name": "ix_events_school_annual_start"},
        ),
        (
            [
                ("school_id", ASCENDING),
                ("event_type", ASCENDING),
                ("status", ASCENDING),
                ("start_date", ASCENDING),
            ],
            {"name": "ix_events_school_type_status_start"},
        ),
    ],

    "jumuiya_elimu_media": [
        (
            [
                ("school_id", ASCENDING),
                ("is_published", ASCENDING),
                ("sort_order", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {
                "name": "ix_elimu_media_school_published_order"
            },
        ),
        (
            [
                ("school_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {
                "name": "ix_elimu_media_school_created"
            },
        ),
        (
            [
                ("public_id", ASCENDING),
            ],
            {
                "unique": True,
                "name": "uq_elimu_media_public_id"
            },
        ),
    ],
}


# =========================================================
# INDEX CREATION
# =========================================================

def _index_key_tuple(keys):
    return tuple(
        (str(field), int(direction))
        for field, direction in keys
    )


def _index_options_signature(info):
    """
    Keep only options that materially affect index compatibility.
    The index name is intentionally excluded.
    """

    return {
        key: info.get(key)
        for key in (
            "unique",
            "sparse",
            "expireAfterSeconds",
            "hidden",
            "partialFilterExpression",
        )
        if key in info
    }


def _ensure_collection_indexes(
    db,
    collection_name: str,
    definitions,
):
    """
    Create a collection's indexes without breaking an existing
    deployment simply because an older index has a different name.

    Equivalent existing indexes are reused.

    When an existing index has the same key pattern but materially
    different options, it is replaced with the requested index.
    This is especially important for the Elimu attendance uniqueness
    guarantee.

    A unique replacement can still fail when existing data contains
    duplicates. That failure is intentional: silently keeping a
    non-unique index would weaken data integrity.
    """

    target = db[collection_name]

    existing = list(
        target.list_indexes()
    )

    by_name = {
        item.get("name"): item
        for item in existing
    }

    by_keys = {}

    for item in existing:
        if item.get("name") == "_id_":
            continue

        keys = tuple(
            (str(field), int(direction))
            for field, direction in item.get(
                "key",
                {},
            ).items()
        )

        by_keys.setdefault(
            keys,
            [],
        ).append(item)

    applied = []

    for keys, requested_options in definitions:
        requested_options = dict(
            requested_options
        )

        requested_name = requested_options.get(
            "name"
        )

        requested_signature = {
            key: requested_options.get(key)
            for key in (
                "unique",
                "sparse",
                "expireAfterSeconds",
                "hidden",
                "partialFilterExpression",
            )
            if key in requested_options
        }

        key_signature = _index_key_tuple(
            keys
        )

        # -------------------------------------------------
        # 1. Explicitly named index already exists.
        # -------------------------------------------------

        if requested_name in by_name:
            existing_info = by_name[
                requested_name
            ]

            existing_signature = _index_options_signature(
                existing_info
            )

            if (
                _index_key_tuple(
                    list(
                        existing_info.get(
                            "key",
                            {},
                        ).items()
                    )
                )
                != key_signature
                or existing_signature != requested_signature
            ):
                target.drop_index(
                    requested_name
                )

                # Refresh the in-memory maps after the drop.
                existing = list(
                    target.list_indexes()
                )
                by_name = {
                    item.get("name"): item
                    for item in existing
                }

                by_keys = {}

                for item in existing:
                    if item.get("name") == "_id_":
                        continue

                    current_keys = tuple(
                        (
                            str(field),
                            int(direction),
                        )
                        for field, direction
                        in item.get(
                            "key",
                            {},
                        ).items()
                    )

                    by_keys.setdefault(
                        current_keys,
                        [],
                    ).append(item)

            else:
                applied.append(
                    requested_name
                )
                continue

        # -------------------------------------------------
        # 2. Reuse an equivalent older index.
        # -------------------------------------------------

        equivalent = None

        for existing_info in by_keys.get(
            key_signature,
            [],
        ):
            if (
                _index_options_signature(
                    existing_info
                )
                == requested_signature
            ):
                equivalent = existing_info
                break

        if equivalent:
            applied.append(
                equivalent.get(
                    "name"
                )
            )
            continue

        # -------------------------------------------------
        # 3. A same-key index exists with incompatible
        #    options. Replace it.
        # -------------------------------------------------

        same_key_indexes = by_keys.get(
            key_signature,
            [],
        )

        for existing_info in same_key_indexes:
            existing_name = existing_info.get(
                "name"
            )

            if existing_name:
                target.drop_index(
                    existing_name
                )

        # Recreate requested index.
        created_name = target.create_index(
            keys,
            **requested_options,
        )

        applied.append(
            created_name
        )

        # Keep the local maps current for later definitions
        # in the same collection.
        refreshed = list(
            target.list_indexes()
        )

        by_name = {
            item.get("name"): item
            for item in refreshed
        }

        by_keys = {}

        for item in refreshed:
            if item.get("name") == "_id_":
                continue

            current_keys = tuple(
                (
                    str(field),
                    int(direction),
                )
                for field, direction
                in item.get(
                    "key",
                    {},
                ).items()
            )

            by_keys.setdefault(
                current_keys,
                [],
            ).append(item)

    return applied


def ensure_indexes():
    """
    Create all indexes required by the Jumuiya platform.

    Jumuiya shares the existing RevelaCode MongoDB
    connection/database.

    Returns:
        True after all index declarations have been applied.
    """

    db = get_db()

    for collection_name, definitions in INDEX_DEFINITIONS.items():
        _ensure_collection_indexes(
            db,
            collection_name,
            definitions,
        )

    return True


# =========================================================
# OPTIONAL INSPECTION
# =========================================================

def index_manifest():
    """
    Return a serializable description of the expected index
    contract.

    Useful for diagnostics, tests and deployment verification
    without opening a second MongoDB connection.
    """

    return {
        collection_name: [
            {
                "keys": list(keys),
                "options": dict(options),
            }
            for keys, options in definitions
        ]
        for collection_name, definitions
        in INDEX_DEFINITIONS.items()
    }
