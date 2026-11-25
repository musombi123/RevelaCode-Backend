# RPSVI controlled tester licence — draft terms

**Draft for operational and legal review. Not a legal opinion or a substitute for advice from a qualified Kenyan lawyer.**

## 1. Grant and scope

RevelaCode may issue a named, non-transferable, limited, time-bound permission to perform only the test cases, endpoints, environments and dates written in the tester's assignment. The default and only approved target is the designated RPSVI staging environment.

This licence does not grant permission to access production systems, other users' accounts, personal data, private repositories, infrastructure consoles, cloud control panels or third-party services.

## 2. Allowed activity

Only the activities explicitly assigned are allowed. Examples may include ordinary functional walkthroughs, role/tenant-isolation checks using assigned synthetic accounts, bounded read-only load scripts, and pre-approved failure simulations.

The licence does not grant blanket permission for penetration testing, vulnerability exploitation or stress testing.

## 3. Prohibited activity

Unless a separate written scope expressly permits a narrowly defined test, the tester must not:

- Target production, third-party systems or any hostname not listed in the assignment.
- Run denial-of-service, distributed denial-of-service, flooding, stress or resource-exhaustion attacks.
- Brute-force passwords, MFA, reset tokens or credentials.
- Phish, impersonate staff, conduct social engineering or attempt physical access.
- Exfiltrate, alter or destroy data, or access another tester's account.
- Probe cloud metadata endpoints, internal networks, private IP ranges or unrelated hosts.
- Upload malware, persistence mechanisms or destructive payloads.
- Bypass payment, licensing, entitlement or access controls beyond an assigned non-destructive check.
- Send real emails, SMS, WhatsApp messages, payments or webhooks.
- Share staging credentials, test tokens, vulnerability details or private test evidence publicly.

Stop immediately when unexpected production data, real personal data, service instability or an out-of-scope system is encountered.

## 4. Accounts and data

Use only the assigned staging account and synthetic dataset. Keep credentials private, use MFA when offered, and report suspected credential exposure immediately. Do not copy real data into reports or local files. Delete local test artefacts when the assignment ends unless the coordinator asks that sanitised evidence be retained.

## 5. Responsible disclosure

Report suspected vulnerabilities privately using the official programme channel. Include reproducible evidence without escalating access or collecting unnecessary data. Do not publish the finding until RevelaCode has acknowledged it and both parties have agreed on a safe disclosure process.

RevelaCode should acknowledge receipt, assign a tracking ID and communicate triage status. A report is not automatically a confirmed vulnerability or a guarantee of a particular remediation time.

## 6. Voluntary participation and recognition

Participation is voluntary and unpaid unless a separate written agreement says otherwise. A credential is based on reviewed evidence, not merely registration or the number of hours spent. It is a RevelaCode programme credential, not a government licence or external professional certification.

No employment, partnership, academic credit, compensation or future work is promised by this draft licence.

## 7. Suspension and revocation

RevelaCode may suspend or revoke a tester assignment or credential for out-of-scope activity, unsafe conduct, credential sharing, false evidence, privacy violations or programme closure. A tester may stop participating at any time and should notify the coordinator so accounts and tokens can be disabled.

## 8. Acceptance

The final version must record the tester's legal name or approved display name, unique tester ID, accepted version/date, permitted track, exact staging hostname, assigned scope, start/end dates and coordinator approval. Do not issue access until the final licence and privacy notice have been approved and accepted.
