"""Preview/apply the Biashara owner-membership migration.

Run from repository root:
    python -m backend.scripts.migrate_biashara_memberships --dry-run
    python -m backend.scripts.migrate_biashara_memberships --apply
    python -m backend.scripts.migrate_biashara_memberships --plan-rollback

MONGO_URI must point at the intended environment. Dry run is the default.
"""
from __future__ import annotations

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Safely backfill Biashara owner memberships.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Create/repair owner membership rows.")
    mode.add_argument("--plan-rollback", action="store_true", help="Report possible reversals without performing them.")
    parser.add_argument("--limit", type=int, default=500, help="Maximum businesses/records inspected (1–5000).")
    args = parser.parse_args()

    try:
        from backend.jumuiya.biashara.tenancy import migration

        if args.plan_rollback:
            report = migration.plan_owner_membership_rollback(limit=args.limit)
        else:
            if args.apply:
                # Apply the repository's declared indexes first. This includes
                # the unique (business_id, user_id) membership key and the new
                # non-unique owner lookup index.
                from backend.jumuiya.core.database import ensure_indexes
                ensure_indexes()
            report = migration.run_owner_membership_migration(
                dry_run=not args.apply,
                limit=args.limit,
            )
        print(json.dumps(report, indent=2, default=str))
        return 0
    except Exception as error:
        print(
            json.dumps({
                "status": "error",
                "error_type": type(error).__name__,
                "message": str(error),
                "hint": "No ownership was guessed. Verify MONGO_URI and inspect the deployment logs before retrying.",
            }, indent=2),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
