# RevelaCode investor due diligence and evidence register

**Edition:** Founder study and due-diligence preparation  
**Evidence snapshot:** 25 November 2026  
**Status:** Working document; not an offering memorandum or audited business record.

## 1. Investment thesis to test

RevelaCode is developing a shared digital platform that brings several domain-specific workflows into one user and service ecosystem: faith and study, education, agriculture, business operations and community. The intended value proposition is reduced fragmentation for users and institutions that need multiple digital services, supported by a reusable identity, API and operational foundation.

That is a thesis to validate with customer evidence. It is not yet proof of product-market fit, paid adoption, defensible market share or recurring revenue.

## 2. Product portfolio visible in the backend

| Area | Backend evidence | Diligence question |
|---|---|---|
| Core account / identity | JWT auth gate, account routes and Jumuiya auth bridge | Are sessions, recovery and MFA flows tested end-to-end? |
| Study / scripture / Faith | Study blueprint, Bible/scripture domain data, MissionPulse route | Which content is licensed, original or user-supplied? |
| Elimu | School, staff, parent/student portal, finance, reports, automation and website routes | Which schools are paying, in pilot or only test tenants? |
| Biashara | Sales, orders, inventory, finance, HR, factory, quality and analytics modules | Which workflows are generally available and which integrations are still in setup? |
| Shamba | Farmer/farm-related routes and workflows | What is the validated user value and field adoption? |
| Community | Feed, messaging, groups, notifications and discovery modules | What are retention, moderation and safety metrics? |
| Shared services | Identity, wallet, marketplace, notifications and integration routes | Which are live, reconciled and actively used? |

The backend README and route registration show the breadth of the intended platform. They do not provide customer counts or independently verified adoption.

## 3. Business model evidence required

Potential monetization surfaces appear in the product architecture (subscriptions, premium hub access, payments, business services, storage or publishing integrations in related products). Before stating them as established revenue streams, provide:

- the approved price list and effective date;
- signed customer contracts or subscription records;
- paid invoice/payment records and refund treatment;
- M-Pesa settlement and reconciliation evidence;
- gross/net revenue calculations and tax treatment;
- churn, renewal and collection rates;
- cost of service per customer and contribution margin.

Do not equate an enabled pricing screen, a payment intent, a pending checkout or a test transaction with collected revenue.

## 4. Financial and operating pack

An investor or institutional partner may reasonably request:

1. Company registration and ownership records (where applicable).
2. Founder and contributor roles, IP assignment and contractor agreements.
3. Bank/mobile-money statements and management accounts.
4. Revenue by product, customer and period.
5. Hosting, database, domain, email, AI and third-party service costs.
6. Twelve- to twenty-four-month cash-flow forecast with assumptions.
7. Customer pipeline, pilots, signed agreements and renewal evidence.
8. Product roadmap, staffing plan and use of funds.
9. Tax, data-protection and regulatory review where relevant.
10. Cap table, share-class details and any existing obligations before any equity discussion.

If a record does not exist yet, mark it as not prepared; do not backfill fictional history.

## 5. Market research that must be conducted separately

Market size must be researched for each customer segment and geography. Avoid adding unrelated total addressable markets (TAMs) together into one attractive number.

For each segment, collect:

- clearly defined target buyer and user;
- number of organizations/accounts in the chosen geography;
- current alternatives and incumbent workflows;
- willingness-to-pay interviews or pilot conversion evidence;
- procurement and sales cycle;
- connectivity, device, payment and support constraints;
- competitor pricing, product capabilities and distribution;
- bottom-up reachable market calculation.

Use dated, cited public sources and identify estimates. Do not present assumptions as Kenyan market facts without source support.

## 6. Security, privacy and operational due diligence

Expected requests include:

- system and data-flow diagrams;
- data inventory and retention schedule;
- privacy notice and consent flows;
- role and tenant authorization design;
- incident response and breach handling;
- access control and credential rotation;
- backup and disaster recovery;
- penetration test or security assessment;
- dependency/SBOM and open-source licence register;
- uptime and performance reports;
- service-provider and processor agreements.

Sensitive production records should be shared through a restricted data room with redaction and least-privilege access.

## 7. Intellectual property and licensing

The repositories contain a mixture of proprietary project code, open-source frontend code (the Frontend repository retains its MIT licence), third-party libraries, external services and downloaded assets. An investor review should therefore distinguish:

- ownership of original source code and authored materials;
- contributors' written IP assignment or licence agreements;
- the MIT-licensed frontend and obligations for redistributed copies;
- proprietary backend and other repository licensing notices;
- dependency licences;
- content, map, media, font and asset licences;
- trademarks, product names and company registrations;
- third-party API terms and data rights.

A repository licence alone does not prove that all contributor-created code, logos, content or uploaded assets are owned by the company. Obtain written assignments and keep provenance records.

## 8. Risk register

| Risk | Why it matters | Evidence / mitigation needed |
|---|---|---|
| Broad product scope | Multiple hubs increase support, QA and delivery cost | Stage launches; show product-level adoption and maintenance cost |
| Scale not benchmarked | Architecture settings do not prove concurrency | Run representative staged load tests and publish results |
| Tenant isolation | Cross-company/school data leakage would be severe | Negative authorization and tenant-query tests |
| Payment reconciliation | Payment initiation is not equivalent to an audited ledger | Immutable ledger, signed callback validation, reconciliation process |
| Background job duplication | Multiple workers can duplicate scheduled tasks | Distributed leases, idempotency and retry/dead-letter controls |
| Third-party service reliance | Service downtime or cost changes can disrupt features | Dependency map, fallback behavior and cost model |
| Privacy and child-related data | Education products may process sensitive learner data | Data mapping, legal review, retention, consent and access controls |
| IP provenance | External assets and contributor code may carry obligations | Signed contributor agreements and asset/licence register |
| Product readiness | Feature code may be ahead of end-to-end acceptance | Release gates, human playtests, customer acceptance records |

## 9. Founder questions to master

Be able to answer each without relying on a slide:

1. What exact user problem does RevelaCode solve first?
2. Who is the first paying customer and decision-maker?
3. Why would a school, farmer, business or institution choose this over its current process?
4. Which module is already used outside founder-controlled testing?
5. What is the cost to serve one active customer each month?
6. Which workflows are live, in pilot, experimental or planned?
7. How do you prevent one school or company from accessing another's records?
8. What happens when MongoDB, Render, email, payments or the network is unavailable?
9. What is your measured capacity and what test produced that number?
10. What intellectual property is owned, licensed or still awaiting assignment?
11. What milestones would an investment actually fund?
12. What evidence would make you stop or change the current roadmap?

## 10. Evidence status at this snapshot

**Available in source:** backend code, route registration, API contracts, database abstractions, security/scalability plans, deployment configuration and tests.

**Not established by this repository review:** audited financial statements, independently confirmed customer/revenue figures, market-size calculation, customer retention, contractual partnerships, external security certification, production SLA, or 100K-concurrency benchmark.

The investor data room should contain actual source records for these items, or identify them as not yet available.
