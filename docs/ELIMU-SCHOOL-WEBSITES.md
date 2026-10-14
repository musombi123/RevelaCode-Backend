# Elimu public school websites, themes, inquiries, and custom domains

## What this change adds

This change extends the existing verified-school website implementation. It does not replace school registration or verification data and does not create an independent website per school.

- School-specific website theme draft and published theme saved on the existing school record.
- Theme validation for nine hex colours and enumerated typography/button styles.
- Owner-only theme, domain, and inquiry management in the existing Elimu website settings screen.
- Public website reads only the allowlisted published theme.
- Custom hostnames are registered with the existing Render static-site service via the Render API.
- A hostname is marked active only when Render reports DNS verification and an HTTPS request validates successfully and returns a non-error response.
- The public page resolves an active verified custom hostname to its own published, verified school.
- Public contact inquiries are saved in jumuiya_elimu_public_inquiries, and the verified school owner can review, mark read, archive, and reopen messages. Submission does not email the school automatically.

## Required Render backend environment

Configure these on the RevelaCode backend web service in Render. Never place the API key in the frontend, source control, or a public build.

- RENDER_API_KEY: Render API key with permission to manage custom domains for the frontend static site.
- ELIMU_RENDER_SERVICE_ID: the actual Render service ID for revelacode-frontend.onrender.com (the frontend static site, not the backend API service).
- ELIMU_RENDER_SERVICE_HOSTNAME: optional; the exact *.onrender.com hostname of that same frontend static site. Defaults to revelacode-frontend.onrender.com.

The backend returns a clear HTTP 503 when the required credentials or service ID are not configured. Do not enable custom-domain operation until the ID is checked against the intended static site. After setting environment variables, restart/redeploy the backend so it loads them.

Render API documentation:
- https://render.com/docs/custom-domains
- https://api-docs.render.com/reference/create-custom-domain
- https://api-docs.render.com/reference/refresh-custom-domain

Render provides managed TLS for supported custom domains after successful verification. The application also performs a normal certificate-validating HTTPS request before it labels a domain active.

## Connecting a school's existing domain

1. The school registers and controls the hostname at its preferred registrar.
2. In Elimu → Website Settings → Domains and URLs, add a hostname such as www.example.ac.ke.
3. Follow the returned DNS instruction exactly. For a subdomain, create a CNAME to the exact Render service hostname. For a root/apex domain, use the DNS-provider-supported ALIAS/ANAME/CNAME flattening approach or the Render apex A-record fallback displayed in the UI. Remove conflicting AAAA records.
4. Allow DNS to propagate, then click Verify. The UI distinguishes pending DNS, pending routing/TLS, failure, and active HTTPS.
5. Only active, verified, HTTPS-enabled domains can be selected as primary.

A hostname entry alone is not proof of ownership. The backend will not resolve a public school from an unknown, unverified, inactive, or HTTPS-pending hostname. Unique MongoDB hostname indexing prevents assignment to two schools.

## CORS behavior

Platform origins remain explicitly configured through FRONTEND_ORIGINS. A custom origin is allowed only when the hostname matches an active, verified, HTTPS-enabled domain record and its school is still a published verified real school. Arbitrary origins are not allowed. Requests fail closed if the database check fails.

If a school is unpublished or its domain is made inactive, the backend stops approving that origin for browser requests.

## API routes added

The routes below are relative to the existing Elimu blueprint:

- GET /school/domains — list owner domains and synchronize provider/TLS status.
- POST /school/domains — register a hostname with Render and store its school association.
- POST /school/domains/<id>/verify — request DNS verification and refresh status.
- PATCH /school/domains/<id>/primary — choose an active HTTPS domain as primary.
- DELETE /school/domains/<id> — remove a custom domain from Render and the school registry.
- GET /public/school-domain?hostname=<host> — resolve a published school by active custom host.
- POST /public/inquiries — validate and store a public school inquiry.
- GET /school/inquiries — list inquiries for the authenticated verified school owner.
- PATCH /school/inquiries/<id>/status — change one school-owned inquiry's status.

Website theme saving reuses the existing GET/PATCH /school/website-settings routes with website_theme_draft and publish_website_theme.

## Verification checklist before production acceptance

- Run the frontend production build on the feature branch.
- Run Python compile checks and the backend test suite on the feature branch.
- Test theme draft vs. published configuration using two distinct verified schools.
- Test domain creation with a real Render API key and the actual frontend static-site service ID.
- Test verification with a domain whose DNS is controlled by the tester; confirm it stays inactive before DNS and HTTPS work.
- Test the custom domain from a browser and confirm /, /about, and refreshes load that domain's own public school.
- Test a preflight from a verified custom domain and confirm an unrelated origin remains rejected.
- Submit a contact inquiry and verify it appears only in that school's owner inbox.
- Test cross-school IDs against domain removal, primary selection, inquiry listing, and status updates.
- Check 375px, 430px, 768px, 1024px, 1366px, and 1920px viewports.

External DNS ownership and Render TLS cannot be verified without an actual domain and configured Render credentials. No production domain has been created by this source change.