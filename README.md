# RevelaCode Jumuiya Backend — Biashara v1

This is a modular extension to the existing RevelaCode Flask + MongoDB backend.
It does NOT replace the existing Bible, Prophecy, Events, Referential, RevelaAI,
or authentication systems.

## Phase 1
- Shared Jumuiya integration
- Existing-auth bridge
- Biashara business profile
- Products
- Customers
- Orders
- Expenses
- Dashboard metrics
- MongoDB indexes
- API contract
- Basic schema tests

## Register inside existing main.py / app factory

from jumuiya.integration.register import register_jumuiya
register_jumuiya(app)

The auth bridge expects the existing RevelaCode auth middleware to expose the
authenticated user as `g.revelacode_user`. Change only
`jumuiya/integration/auth_bridge.py` if your existing auth uses another context.

API base:
`/api/jumuiya/biashara`

Next modules should be added beside `biashara/`:
`shamba/`, `elimu/`, and `community/`.

Architecture:
ONE RevelaCode frontend + ONE RevelaCode backend + ONE identity + multiple hubs.
