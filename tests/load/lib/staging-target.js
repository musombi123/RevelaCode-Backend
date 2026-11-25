import { fail } from "k6";

const PRODUCTION_HOSTS = new Set([
  "revelacode.co.ke",
  "www.revelacode.co.ke",
  "revelacode-backend.onrender.com",
  "revelacode-api.onrender.com",
]);

export function requireStagingBaseUrl() {
  const baseUrl = String(__ENV.BASE_URL || "").trim().replace(/\/+$/, "");
  const expectedHost = String(__ENV.EXPECTED_STAGING_HOST || "").trim().toLowerCase();

  if (!baseUrl) {
    fail("BASE_URL is required.");
  }
  if (!expectedHost) {
    fail("EXPECTED_STAGING_HOST is required; testing is disabled until the exact staging host is approved.");
  }

  const match = baseUrl.match(/^https:\/\/([^/?#:]+)(?::\d+)?(?:\/|$)/i);
  if (!match) {
    fail("Only an HTTPS staging origin is allowed.");
  }

  const actualHost = match[1].toLowerCase();
  if (PRODUCTION_HOSTS.has(actualHost)) {
    fail("Production hosts are forbidden by this load-test profile.");
  }
  if (actualHost !== expectedHost) {
    fail("BASE_URL hostname must exactly match EXPECTED_STAGING_HOST.");
  }

  return baseUrl;
}
