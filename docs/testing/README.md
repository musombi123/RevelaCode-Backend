# RevelaCode Public System Verification Initiative (RPSVI)

**Programme status: preparation — not yet open for public enrolment**

RPSVI is RevelaCode's controlled programme for validating functional correctness, tenant isolation, security controls, reliability, API performance and the RevelaAI integration. Its volunteer track is the **RevelaCode Verified System Tester Programme**.

## Objectives

1. Prepare an isolated staging environment with synthetic data.
2. Establish a controlled tester application, scope/licence, reporting process and credential register.
3. Verify baseline performance before tuning.
4. Increase workload progressively under an approved test plan.
5. Benchmark the actual provider and model used by RevelaAI.
6. Publish evidence-based reports, including known limitations.

## Documents

- [Staging environment and data isolation](STAGING_ENVIRONMENT.md)
- [Volunteer programme and enrolment](VOLUNTEER_PROGRAMME.md)
- [Controlled tester licence and rules](TESTER_LICENCE.md)
- [Test-case catalogue](TEST_CASE_CATALOG.md)
- [Capacity test plan and release gates](CAPACITY_TEST_PLAN.md)
- [RevelaAI model benchmark plan](AI_BENCHMARK_PLAN.md)

## Current blockers before enrolment

- A dedicated staging API service and a separate staging MongoDB database have not been provisioned or verified.
- Staging-only secrets and synthetic user/tenant accounts have not been created.
- The current worker runs a daily pipeline capable of sending notifications. Do not add a staging worker until external effects are disabled or sandboxed.
- Volunteer application, identity/consent handling, private issue intake and credential verification need an owner and operational process.
- No baseline or 100,000-concurrent-user result has been measured.

## Safety boundary

The current load scripts are read-only and require both `BASE_URL` and `EXPECTED_STAGING_HOST`. They reject known production hosts and require an exact hostname match. The authenticated profile also requires a staging token and is capped at 1,000 virtual users per single generator. Higher concurrency requires a separately designed distributed test.

**Never use production user data, production credentials, or production payment/email/WhatsApp integrations for RPSVI.** Do not publish vulnerabilities, bearer tokens, personal information or internal service credentials.

## Evidence and status vocabulary

Use these labels in all reports:

- **Measured:** captured from an identified build, environment and repeatable test.
- **Passed:** all stated acceptance thresholds were met in that test.
- **Failed:** one or more stated thresholds or correctness assertions failed.
- **Not measured:** no valid result exists yet.
- **Target:** desired threshold, not an observed result.
- **Estimated:** an assumption or model, not a test result.

Registration as a volunteer is not certification. A tester credential is issued only for a category whose required evidence has been reviewed and accepted.
