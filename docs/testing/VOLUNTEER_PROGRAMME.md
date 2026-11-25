# RevelaCode Verified System Tester Programme

## Purpose

The RevelaCode Verified System Tester Programme is the volunteer participation arm of the RevelaCode Public System Verification Initiative (RPSVI). Participants help validate the platform under a written scope and receive recognition only for work that is completed and reviewed.

This programme is not a promise of employment, income, admission, academic credit or external professional accreditation. Any such arrangement requires a separate written agreement with the relevant institution or organisation.

## Participation tracks

1. **Functional tester:** user journeys, role permissions, usability defects, data correctness and mobile/browser compatibility.
2. **Security tester:** approved authentication, authorisation, tenant-isolation, input-validation and session tests in staging only.
3. **Performance tester:** approved k6 profiles, test-run monitoring, result capture and repeatability. High-load tests are run only by designated leads using approved distributed infrastructure.
4. **Reliability tester:** controlled restarts, dependency timeouts, retry/idempotency and recovery tests in staging.
5. **AI integration tester:** provider/model metadata, fallback behaviour, latency, response validity and fixed evaluation prompts.

## Admission workflow

1. Applicant submits name, contact method, experience/learning goals, preferred track and availability through the official RevelaCode application channel.
2. Programme coordinator verifies contact and obtains explicit acceptance of the licence, privacy notice and testing rules.
3. Applicant completes the short orientation and confidentiality/responsible-disclosure acknowledgement.
4. Coordinator assigns a unique tester ID, track, staging account, scope, test cases and validity dates.
5. Tester records findings through the approved private reporting channel.
6. A reviewer reproduces each finding, records severity and accepts or rejects the evidence.
7. Credential status is updated only after the category's completion requirements are met.

Do not collect national ID numbers, passwords, private keys or unnecessary sensitive personal information. Restrict access to applicant contact data and publish a tester's name only with explicit consent.

## Credential levels

| Credential | Requirements |
|---|---|
| Registered Tester | Application accepted, orientation completed, licence accepted and a test scope assigned |
| Verified Functional Tester | Assigned functional suite completed; evidence and retests reviewed |
| Verified Security Tester | Security orientation completed; authorised scope followed; at least one complete security test cycle and evidence review accepted |
| Verified Performance Tester | Approved performance plan executed by an authorised lead; raw summary and environment metadata reviewed |
| Verified Reliability Tester | Assigned failure/recovery cases executed and evidence reviewed |
| Verified AI Integration Tester | Fixed AI benchmark cases completed with provider/model and latency evidence reviewed |
| Lead Tester | Repeated high-quality contributions, reviewer training and written appointment by programme owner |

A registered tester is not automatically a verified system tester. A certificate must specify exactly which track and level were earned.

## Credential verification record

Each issued credential should have a unique, non-secret verification ID and a public verification page containing only:

- Credential ID and level.
- Display name, only with the participant's consent.
- Issue date and expiry/review date.
- Verified test category/categories.
- Current status: active, expired, suspended or revoked.
- Issuing programme and a way to report suspected misuse.

Do not expose the tester's email, private test account, internal reports or vulnerability details.

## Evidence quality

A useful submission includes:

- Tester ID and assigned case ID.
- Environment and tested build/commit SHA.
- Timestamp with timezone.
- Preconditions and exact reproducible steps.
- Expected and actual outcome.
- Request ID or sanitised logs where available.
- Screenshots/video with personal data and tokens removed.
- Severity rationale and impact.
- Whether the issue is repeatable and how often.

Do not submit credentials, bearer tokens, personal data, raw database exports or public exploit instructions.

## Cohort rollout

- **Pilot cohort:** functional and security testers on low-risk staging flows.
- **Second cohort:** broader hub coverage after pilot feedback and tenant isolation checks.
- **Performance cohort:** only after the staging host, monitoring, capacity budget and stop controls are signed off.
- **Distributed capacity cohort:** named performance leads only; volunteers do not independently launch large traffic generators.

## Programme governance

The programme owner appoints a test lead, security triage reviewer and credential reviewer. One person may hold multiple roles in the pilot, but changes to permissions and credential issuance must be auditable.

The programme must publish its scope, test window, contact channel, rules, credential criteria and privacy notice before accepting external applications.
