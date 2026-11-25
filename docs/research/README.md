# RevelaCode research library — backend and platform

**Edition:** Founder and due-diligence research  
**Repository:** `musombi123/RevelaCode-Backend`  
**Evidence snapshot:** 25 November 2026  
**Disclosure:** Internal working research. Review and redact operational details before external distribution.

This library explains the backend and the platform services it owns. It is based on the repository's `main` source and the documentation available at the evidence date. It is not a security certification, financial statement, legal opinion, independent audit, or capacity guarantee.

## Start here

1. [Platform and backend architecture](PLATFORM-AND-BACKEND-ARCHITECTURE.md) — application structure, request flow, identity, data and hub boundaries.
2. [Operations, security and scalability](OPERATIONS-SECURITY-AND-SCALABILITY.md) — deployment topology, security controls, operational risks and the 100K capacity gate.
3. [Investor due diligence and evidence register](INVESTOR-DUE-DILIGENCE.md) — what can be stated, what needs proof, and what an investor may reasonably request.

## How to read status statements

- **Implemented in source:** relevant code or route is present in the inspected repository.
- **Documented design:** the repository describes the intended architecture, but this alone does not prove it is fully live.
- **Partially implemented:** implementation exists but acceptance, integration, migration or operational verification remains.
- **Unverified:** this review did not inspect live production telemetry, execute the whole test suite, or obtain independent evidence.
- **Planned:** a future capability or release gate.

A route, component, workflow or configuration file is evidence of implementation work, not proof that a feature is healthy in production or used by customers.

## Platform summary

RevelaCode is a modular software platform with a shared account/backend foundation and domain-specific experiences. The repository includes the original faith/scripture/study capabilities and the Jumuiya services for Biashara, Shamba, Elimu, Community, shared identity, wallet, marketplace and MissionPulse/Faith services.

The backend's current source is a Flask application. MongoDB is the primary persistence layer. Jumuiya's general collection helper uses the existing RevelaCode database and a `jumuiya_` namespace. Biashara's tenant architecture additionally defines central company identity/membership records and a separate database per company within the existing MongoDB cluster for operational records. These are two related but distinct persistence patterns; neither should be described inaccurately as "one collection for every company".

## Related source

- [Backend README](../../README.md)
- [API contract](../../API_CONTRACT.md)
- [Biashara Core-Zero architecture](../BIASHARA_CORE_ZERO_ARCHITECTURE.md)
- [Biashara roles and permissions](../BIASHARA_MODULES_AND_PERMISSIONS.md)
- [Scalability and reliability programme](../SCALABILITY_RELIABILITY_PROGRAMME.md)
- [Capacity and release gates](../CAPACITY_AND_RELEASE_GATES.md)
- [Platform IP guard](../PLATFORM_IP_GUARD.md)
- [Elimu school websites](../ELIMU-SCHOOL-WEBSITES.md)

## External disclosure rule

Do not place live secrets, customer personal data, unredacted environment files, internal IP allowlists, private incident records, or sensitive endpoint abuse details in an investor pack. Share architecture and evidence with access controls; share credentials through a separate approved secret-management process.
