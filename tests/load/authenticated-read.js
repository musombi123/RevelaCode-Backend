import http from "k6/http";
import { check, sleep } from "k6";

// Read-only authenticated API profile. Pass an endpoint known to be safe for
// repeated GET requests; never point this profile at mutation endpoints.
const targetVus = Math.max(1, Math.min(10000, Number(__ENV.TARGET_VUS || 250)));
const baseUrl = String(__ENV.BASE_URL || "").replace(/\/$/, "");
const apiPath = String(__ENV.API_PATH || "/health");
const accessToken = String(__ENV.ACCESS_TOKEN || "");
const requestTimeout = String(__ENV.REQUEST_TIMEOUT || "10s");

export const options = {
  stages: [
    { duration: "2m", target: Math.min(25, targetVus) },
    { duration: "3m", target: Math.min(100, targetVus) },
    { duration: "5m", target: targetVus },
    { duration: "2m", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1200", "p(99)<2500"],
  },
};

function tenantHeaders() {
  const raw = String(__ENV.TENANT_HEADERS_JSON || "").trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("TENANT_HEADERS_JSON must be a JSON object");
    }
    return parsed;
  } catch (error) {
    throw new Error("Invalid TENANT_HEADERS_JSON: " + error.message);
  }
}

const extraHeaders = tenantHeaders();

export default function () {
  if (!baseUrl) {
    throw new Error("BASE_URL is required");
  }
  if (!apiPath.startsWith("/") || apiPath.startsWith("//")) {
    throw new Error("API_PATH must be a safe absolute path beginning with one slash");
  }

  const headers = {
    Accept: "application/json",
    ...extraHeaders,
  };
  if (accessToken) {
    headers.Authorization = "Bearer " + accessToken;
  }

  const response = http.get(baseUrl + apiPath, {
    headers,
    timeout: requestTimeout,
    tags: { profile: "authenticated-read", endpoint: apiPath },
  });

  check(response, {
    "status is successful": (r) => r.status >= 200 && r.status < 300,
    "response is JSON": (r) =>
      String(r.headers["Content-Type"] || "").toLowerCase().includes("application/json"),
  });

  sleep(1);
}
