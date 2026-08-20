# RevelaCode Jumuiya Backend


Jumuiya is an ecosystem platform built **inside the existing RevelaCode Flask + MongoDB backend**.


It does not replace or create a separate backend for RevelaCode's existing services.


Existing RevelaCode functionality remains intact, including:


- Bible
- Prophecy
- Events
- Referential
- Study
- RevelaAI
- Existing authentication
- Existing notifications
- Existing MongoDB infrastructure


Jumuiya adds modular ecosystem hubs on top of the same backend.


---


# Architecture


```text
                    REVELACODE PLATFORM
                           │
              ┌────────────┴────────────┐
              │                         │
        Existing Services            JUMUIYA
              │                         │
     ┌────────┼────────┐       ┌────────┼────────┐
     │        │        │       │        │        │
   Bible   Prophecy  Study  Biashara  Shamba   Elimu
                                │        │        │
                                └────┬───┴────┬───┘
                                     │
                              Shared Ecosystem
                                     │
                         ┌───────────┼───────────┐
                         │           │           │
                    Marketplace   Wallet     Community
Core principle

ONE backend + ONE database + ONE identity + MULTIPLE hubs

Jumuiya does not create:

a second authentication system
a second MongoDB connection
a second user database
a second notification platform
Backend Structure
backend/
│
├── main.py
├── db.py
│
├── user_profile/
│   ├── auth_gate.py
│   └── user_data.py
│
└── jumuiya/
    │
    ├── core/
    │   ├── database.py
    │   ├── permissions.py
    │   ├── errors.py
    │   ├── responses.py
    │   ├── identity.py
    │   ├── pagination.py
    │   └── audit.py
    │
    ├── integration/
    │   ├── auth_bridge.py
    │   └── register.py
    │
    ├── identity/
    │   ├── models.py
    │   ├── routes.py
    │   └── services.py
    │
    ├── wallet/
    │   ├── models.py
    │   ├── routes.py
    │   └── services.py
    │
    ├── marketplace/
    │   ├── models.py
    │   ├── routes.py
    │   └── services.py
    │
    ├── biashara/
    │   ├── models.py
    │   ├── schemas.py
    │   ├── routes.py
    │   └── services.py
    │
    ├── shamba/
    │   ├── models.py
    │   ├── schemas.py
    │   ├── routes.py
    │   └── services.py
    │
    ├── elimu/
    │   ├── models.py
    │   ├── schemas.py
    │   ├── routes.py
    │   └── services.py
    │
    └── community/
        ├── models.py
        ├── routes.py
        └── services.py
Database Architecture

Jumuiya uses the existing RevelaCode MongoDB connection from:

backend/db.py

It does not create another MongoDB client.

Jumuiya collections use the mandatory:

jumuiya_

namespace.

Example:

users
scriptures
notifications
domains


jumuiya_profiles
jumuiya_businesses
jumuiya_products
jumuiya_customers
jumuiya_orders
jumuiya_sales
jumuiya_expenses
jumuiya_inventory_movements


jumuiya_farmers
jumuiya_farms
jumuiya_crops
jumuiya_harvests


jumuiya_education_profiles
jumuiya_schools
jumuiya_classes
jumuiya_lessons


jumuiya_marketplace_listings
jumuiya_transactions
jumuiya_community_posts
jumuiya_audit_logs
Authentication

RevelaCode remains the source of truth for authentication.

The existing login endpoint creates an access token:

Authorization: Bearer <access-token>

The Jumuiya authentication bridge:

backend/jumuiya/integration/auth_bridge.py

validates the token and creates the normalized:

g.jumuiya_user

identity.

The normalized identity is shared by all hubs.

RevelaCode users._id
        │
        ▼
       JWT
        │
        ▼
Jumuiya Auth Bridge
        │
        ▼
g.jumuiya_user
        │
        ├── Biashara
        ├── Shamba
        ├── Elimu
        ├── Marketplace
        ├── Wallet
        └── Community
Registration

Jumuiya is registered from the existing:

backend/main.py

using:

from backend.jumuiya.integration.register import register_jumuiya


register_jumuiya(app)

The registration layer is responsible for:

Jumuiya database indexes
Jumuiya error handlers
Authentication bridge
Identity routes
Wallet routes
Marketplace routes
Biashara routes
Shamba routes
Elimu routes
Community routes
API Structure

All Jumuiya APIs live under:

/api/jumuiya
Identity
GET /api/jumuiya/identity/me
PUT /api/jumuiya/identity/profile
Wallet
GET /api/jumuiya/wallet/ledger

Payment-provider integration will be added separately. Wallet ledger records must not be manufactured directly by untrusted clients.

Marketplace
GET    /api/jumuiya/marketplace/listings
POST   /api/jumuiya/marketplace/listings
DELETE /api/jumuiya/marketplace/listings/<id>
Biashara
GET    /api/jumuiya/biashara/health


GET    /api/jumuiya/biashara/business
POST   /api/jumuiya/biashara/business


GET    /api/jumuiya/biashara/products
POST   /api/jumuiya/biashara/products
PUT    /api/jumuiya/biashara/products/<id>
DELETE /api/jumuiya/biashara/products/<id>


GET    /api/jumuiya/biashara/inventory/low-stock
POST   /api/jumuiya/biashara/inventory/<id>/adjust


GET    /api/jumuiya/biashara/customers
POST   /api/jumuiya/biashara/customers


GET    /api/jumuiya/biashara/orders
POST   /api/jumuiya/biashara/orders
GET    /api/jumuiya/biashara/orders/<id>
PATCH  /api/jumuiya/biashara/orders/<id>/status


GET    /api/jumuiya/biashara/expenses
POST   /api/jumuiya/biashara/expenses


POST   /api/jumuiya/biashara/sales


GET    /api/jumuiya/biashara/dashboard
Shamba
GET    /api/jumuiya/shamba/health


GET    /api/jumuiya/shamba/farmer
POST   /api/jumuiya/shamba/farmer


GET    /api/jumuiya/shamba/farms
POST   /api/jumuiya/shamba/farms


GET    /api/jumuiya/shamba/farms/<id>
PUT    /api/jumuiya/shamba/farms/<id>
DELETE /api/jumuiya/shamba/farms/<id>


GET    /api/jumuiya/shamba/farms/<id>/crops
POST   /api/jumuiya/shamba/farms/<id>/crops


GET    /api/jumuiya/shamba/farms/<id>/activities
POST   /api/jumuiya/shamba/farms/<id>/activities


GET    /api/jumuiya/shamba/farms/<id>/harvests
POST   /api/jumuiya/shamba/farms/<id>/harvests


GET    /api/jumuiya/shamba/dashboard
Elimu
GET  /api/jumuiya/elimu/health


GET  /api/jumuiya/elimu/profile
POST /api/jumuiya/elimu/profile


GET  /api/jumuiya/elimu/school
POST /api/jumuiya/elimu/school


GET  /api/jumuiya/elimu/classes
POST /api/jumuiya/elimu/classes


GET  /api/jumuiya/elimu/lessons
POST /api/jumuiya/elimu/lessons


GET  /api/jumuiya/elimu/assignments
POST /api/jumuiya/elimu/assignments


GET  /api/jumuiya/elimu/fees
POST /api/jumuiya/elimu/fees


GET  /api/jumuiya/elimu/cbc/projects
POST /api/jumuiya/elimu/cbc/projects


GET /api/jumuiya/elimu/dashboard
Community
GET    /api/jumuiya/community/feed


POST   /api/jumuiya/community/posts
PUT    /api/jumuiya/community/posts/<id>
DELETE /api/jumuiya/community/posts/<id>


GET    /api/jumuiya/community/posts/<id>/comments
POST   /api/jumuiya/community/posts/<id>/comments


POST   /api/jumuiya/community/posts/<id>/react
Hubs
Biashara

Business operating hub for:

Business profiles
Products
Customers
Orders
Inventory
Sales
Expenses
Business analytics
Shamba

Agriculture hub for:

Farmer profiles
Farms
Crops
Farm activities
Harvests
Agricultural records
Future market-price services
Future farmer-to-buyer connections
Elimu

Education hub for:

Students
Parents
Teachers
Schools
Classes
Lessons
Assignments
Fees
CBC projects
Future assessment and reporting systems
Community

Cross-hub social layer for:

Posts
Comments
Reactions
Announcements
Jobs
Lost & found
Community information
Cross-hub communication
Cross-Hub Connections

Jumuiya is designed so the hubs can work together.

Shamba → Marketplace
Farmer
  ↓
Harvest
  ↓
Marketplace listing
  ↓
Buyer
Biashara → Marketplace
Business
  ↓
Product/service
  ↓
Marketplace
  ↓
Buyer
Elimu → Marketplace
School / Parent
  ↓
Education-related goods/services
  ↓
Marketplace
All Hubs → Wallet
Biashara
      ↘
Shamba  → Wallet / Transactions
      ↗
Elimu
All Hubs → Community
Biashara ─┐
Shamba ───┼──→ Community
Elimu ────┘
Notifications

RevelaCode already has an existing notification system.

Jumuiya does not create a second notification engine.

Jumuiya events should eventually feed the existing RevelaCode notification infrastructure.

Examples:

Biashara → New order
Shamba   → Harvest reminder
Elimu    → Assignment due
Wallet   → Payment confirmed
Marketplace → Listing sold
Community → New comment
Development Status
Core              ✅
Identity          ✅
Wallet foundation ✅
Marketplace       ✅
Biashara          ✅ foundation
Shamba            ✅ foundation
Elimu             ✅ foundation
Community         ✅ foundation
Auth bridge       ✅
Registration      ✅
Frontend           ⏳
Payment gateway    ⏳
Production testing ⏳
Development Philosophy

Jumuiya is built as a modular extension of RevelaCode.

Each hub owns its domain logic:

Biashara → business logic
Shamba   → agriculture logic
Elimu    → education logic

Shared platform capabilities remain in:

core/
identity/
wallet/
marketplace/
integration/

The hubs should not create duplicate authentication, duplicate databases, or duplicate infrastructure.

Deployment

Jumuiya runs through the existing RevelaCode Flask application.

The production entry point remains:

backend/main.py

No separate Jumuiya server is required.

The same deployment therefore serves:

RevelaCode
+
Jumuiya

from one backend.

Long-Term Vision
                 REVELACODE
                     │
                 ONE IDENTITY
                     │
          ┌──────────┼──────────┐
          │          │          │
       BIASHARA    SHAMBA     ELIMU
          │          │          │
          └──────────┼──────────┘
                     │
              MARKETPLACE
                     │
                  WALLET
                     │
                COMMUNITY

One platform. One identity. One backend. Multiple ecosystems.

Jumuiya is designed to allow people, businesses, farmers, schools, parents, teachers, buyers and communities to interact through a common digital ecosystem while preserving the existing RevelaCode platform.
