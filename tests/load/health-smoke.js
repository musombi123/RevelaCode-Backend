import http from "k6/http";
import { check } from "k6";

// Safe, read-only smoke/load profile. Point BASE_URL at a staging deployment.
// Do not aim this at production without an approved test window.
const baseUrl = (__ENV.BASE_URL || "").replace(/\/$/, "");
if (!baseUrl) {
  throw new Error("Set BASE_URL to the staging API origin.");
}

export const options = {
  stages: [
    { duration: "30s", target: 10 },
    { duration: "1m", target: 25 },
    { duration: "1m", target: 50 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1000", "p(99)<2000"],
  },
};

export default function () {
  const response = http.get(`${baseUrl}/health`, {
    headers: { Accept: "application/json" },
    tags: { endpoint: "health" },
    timeout: "10s",
  });
  check(response, {
    "health returns 200": (r) => r.status === 200,
    "health body is JSON": (r) =>
      (r.headers["Content-Type"] || "").includes("application/json"),
  });
}
