# RevelaCode platform and backend architecture

**Evidence snapshot:** 25 November 2026  
**Primary source:** `main.py`, `backend/db.py`, `backend/jumuiya/integration/register.py`, `backend/jumuiya/core/database.py`, `backend/ai_gateway/`, `render.yaml`, and the linked architecture documents.

## 1. System overview

RevelaCode separates user-facing applications from authoritative business logic and data access.

```text
Web / Android clients
       |
       v
RevelaCode React frontend
       |
       | HTTPS API requests + authenticated session
       v
RevelaCode Flask backend (Gunicorn on Render)
       |
       +--> Authentication / account / MFA / compliance
       |
       +--> Study, scripture and platform routes
       |
       +--> Jumuiya integration
       |      +--> Shared identity, notifications, wallet, marketplace
       |      +--> Biashara services
       |      +--> Shamba services
       |      +--> Elimu services
       |      +--> Community and World Events
       |      +--> MissionPulse / Faith
       |
       +--> Revenue engine
       |
       +--> Internal, user-scoped RevelaAI context gateway
       |
       v
MongoDB persistence
       |
       +--> Core RevelaCode collections
       +--> Jumuiya-prefixed collections
       +--> Biashara tenant databases in the same MongoDB cluster
```

This is a logical view, not a deployment diagram for every third-party dependency. It describes the code boundaries found in the repository, not measured request volume or production service health.

## 2. Application composition

The backend entry point is `main.py`. It creates a Flask application, configures logging and CORS, installs request/security middleware, initializes the database, and registers route blueprints.

The main registration groups include:

- Core account and authentication routes, MFA, compliance, user data, account management, account documents and history.
- Jumuiya platform registration, including its identity bridge and domain modules.
- Revenue routes.
- The internal RevelaAI context gateway.
- Study routes and compatibility aliases for existing clients.

A helper dynamically imports selected non-critical blueprints and logs registration failures. Study registration and the Jumuiya/revenue registration paths contain stricter failure handling. Therefore, registration logs and deployment smoke tests remain important evidence when diagnosing a production boot.

## 3. Identity and authorization

The inspected backend uses JWT-based authentication. The auth gate reads the signing secret from deployment configuration and validates authenticated requests. The Jumuiya integration bridge adapts an existing RevelaCode authenticated identity into the request context used by Jumuiya.

Jumuiya permission helpers read the authenticated user from Flask's request context (`g.jumuiya_user`) and provide authenticated-user and role checks. Biashara's architecture specifies a server-side membership and permission model: the role selected in a UI is not authority by itself.

Important design principles:

- A client-supplied user, school, business or tenant identifier is a selector, not proof of authorization.
- Sensitive reads and writes must be scoped to the authenticated user's active ownership or membership.
- UI-hidden actions are not a substitute for backend authorization.
- Platform-admin authority is separate from ordinary business membership roles.
- Tenant boundaries need explicit negative tests, not just successful-owner tests.

The presence of authorization helpers does not by itself prove every route has been reviewed. The scalability programme still identifies route-by-route authorization and tenant-isolation verification as outstanding audit work.

## 4. Persistence model

### 4.1 Core database connection

`backend/db.py` reads `MONGO_URI` and an optional database name (default `revelacode`), constructs a PyMongo `MongoClient`, performs a ping, and exposes a database handle. Pool and timeout settings are environment-configurable.

The same module initializes several core collections, including users, scriptures, admin actions, support tickets, legal documents, notifications and domains.

### 4.2 Jumuiya collection namespace

`backend/jumuiya/core/database.py` obtains the existing RevelaCode database through `backend.db.get_db()`. Its general collection helper rejects names that do not begin with `jumuiya_`. Index definitions are centralized in that module.

This keeps Jumuiya's general platform records within the existing database boundary and uses a namespace to avoid accidental collection-name overlap.

### 4.3 Biashara tenant data

The Biashara Core-Zero architecture describes an additional tenant-specific pattern:

- Company profile, ownership, membership, invitations, tenant registry and verified company domains remain central.
- Each company receives a database within the existing MongoDB cluster, named from a one-way hash prefix derived from the business ID.
- Operational records such as products, orders, inventory movements, production batches, quality checks, staff records and related finance operations are routed to the verified company database.
- Tenant provisioning is leased/idempotent; source records are not deleted as part of legacy copy.

This is a documented architecture and source-owned implementation area. For external diligence, demonstrate the active provisioning and query path in a controlled staging tenant, including cross-company denial tests. Do not disclose actual tenant IDs or database names.

## 5. Domain modules

### Biashara

Biashara is intended as a business operations launcher on the shared Core-Zero service foundation, not a second operating system. Its documented module families include sales, customers, orders, inventory, suppliers, purchasing, finance, invoices, expenses, HR, attendance, payroll preparation, production, machines, quality, website, integrations, automations and synchronization.

Its company templates include general, retail shop, hardware, factory, salon, professional services and a school/Elimu launcher. Templates change workflow navigation and defaults; they must not grant backend permissions.

**Financial accuracy note:** the API contract explicitly describes sales/expense totals as operational metrics, not yet a legally auditable accounting ledger. Live payments require an immutable transaction ledger and M-Pesa reconciliation. eTIMS and payment surfaces must be described according to their actual integration readiness, not as a guarantee of regulatory or tax compliance.

### Shamba

Shamba routes and services are registered under the Jumuiya backend. The research inventory should distinguish farmer/profile onboarding, farm records, crops/activities, market, buyers/orders, weather and diagnostic/insight surfaces. The exact production status of each workflow should be verified against the relevant route, tests and live service before being marketed as generally available.

### Elimu

Elimu routes are registered as a Jumuiya domain module. The repository includes school verification, staff, inventory, library, finance, reports, timetable, portal, automation, lifecycle and synchronization areas. Public school websites and custom domains use verified-school and active-HTTPS checks. A hostname submission is not itself proof of ownership or a live domain.

School inquiries are stored for the verified school owner to review; the public website documentation says submission does not automatically email the school.

### Community and Faith

Community routes include posts, groups, messaging, discovery, notifications and World Events. MissionPulse is registered under the Faith route family. Study and scripture remain part of the original RevelaCode backend scope. As with other modules, route and test presence should not be presented as proof of broad active adoption.

## 6. RevelaAI integration boundary

RevelaCode owns the platform identity, permissions and source-of-truth domain data. Its internal AI gateway is a controlled service-to-service boundary for RevelaAI to request user-scoped context. The inspected gateway states that it does not expose MongoDB directly and delegates retrieval to existing platform services.

The gateway validates the requesting AI service and scopes the returned context to a user. Domain context includes general, Biashara, Shamba, Elimu, Community, study, scripture, technology and programming.

RevelaAI's model/provider orchestration is a separate system and must be documented in its own dossier. This RevelaCode document does not claim that the gateway itself is a model or AI inference engine.

## 7. API and integration principles

- Flask routes remain the platform API surface.
- Existing response shapes and authentication contracts are compatibility constraints.
- M-Pesa, email, OAuth, WhatsApp and external market-data integrations have separate credentials and callback flows.
- Webhook and payment mutation paths should be idempotent and auditable.
- Offline sync needs stable mutation IDs and conflict-resolution rules.
- Custom-domain CORS approval is based on an explicit origin allowlist or server-verified active domain records; credentialed wildcard CORS is not the intended design.

## 8. What must be demonstrated in diligence

1. A request traced from React client to authenticated Flask route and then to its scoped data store.
2. One successful and one denied cross-school or cross-company request.
3. A payment test showing idempotency, callback verification, ledger allocation and reconciliation—or a clear statement of the steps not yet implemented.
4. The operational state of scheduled jobs and the background worker.
5. The current staging and production deployment revisions.
6. A route inventory showing authentication, role, tenant scope, validation and tests.
7. Backup/restore evidence and database index review.

A diagram is an explanation of intended control flow. Demonstration logs, test reports and deployment records are the evidence that the deployed system follows it.
