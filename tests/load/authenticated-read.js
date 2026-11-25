import http from "k6/http";
import { check, fail, sleep } from "k6";
import { requireStagingBaseUrl } from "./lib/staging-target.js";

const baseUrl = requireStagingBaseUrl();
const apiPath = String(__ENV.API_PATH || "").trim();
const accessToken = String(__ENV.ACCESS_TOKEN || "").trim();
const requestTimeout = String(__ENV.REQUEST_TIMEOUT || "10s");
const targetVus = Number(__ENV.TARGET_VUS || 25);

if (!apiPath || !apiPath.startsWith("/") || apiPath.startsWith("//")) {
  fail("API_PATH must be a reviewed read-only path beginning with one slash.");
}
if (!accessToken) {
  fail("ACCESS_TOKEN is required. Use a dedicated synthetic staging account.");
}
if (!Number.isInteger(targetVus) || targetVus < 1 || targetVus > 1000) {
  fail("TARGET_VUS must be an integer from 1 to 1000 for a single-generator run.");
}

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
    fail("Invalid TENANT_HEADERS_JSON: " + error.message);
  }
  return {};
}

const extraHeaders = tenantHeaders();

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

export default function () {
  const headers = {
    Accept: "application/json",
    Authorization: "Bearer " + accessToken,
    ...extraHeaders,
  };

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
