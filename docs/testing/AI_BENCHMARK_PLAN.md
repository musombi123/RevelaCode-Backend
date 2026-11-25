# RevelaAI integration and model benchmark plan

## Separate the service layers

- RevelaCode Backend owns platform authentication, tenant-aware business APIs and the shared MongoDB system of record.
- RevelaAI owns AI orchestration, provider selection, model calls and AI tool routing.
- The external model provider performs inference.

A successful health response proves service health only. A configured model name proves configuration only. To verify a model call, capture the actual provider and model returned by the authenticated generation path for a synthetic staging user.

## Preflight

- Use a staging RevelaAI gateway and staging service-to-service key.
- Keep provider keys server-side and never include them in client bundles, test scripts or logs.
- Use a dedicated synthetic staging identity accepted by RevelaAI's existing authentication bridge.
- Set a strict per-run request budget and provider spend limit.
- Do not run automated benchmark prompts against production.
- Confirm the exact production entrypoint and deployment commit before creating a staging equivalent.
- The current non-streaming `/api/chat` route persists turns. Use a dedicated test account and bounded sessions.

## What to measure

| Metric | Meaning |
|---|---|
| Provider and actual model | Final provider/model reported by the completed request |
| Fallback | Whether the completed request used a fallback path |
| Time to response headers / waiting | Server-observed wait for the non-streaming response; not true token TTFT |
| End-to-end duration | Full request duration from load generator |
| Input/output tokens | Actual usage metadata, only if provider returns it |
| Error/timeout rate | Provider and gateway failures |
| Quality score | Blind rubric score from fixed, versioned test prompts |
| Cost per successful task | Based on measured token use and the applicable provider price sheet/version |

True time-to-first-token requires a streaming benchmark that records the first streamed token event. Do not label non-streaming response waiting time as TTFT.

## Benchmark suite

Use a small, fixed set of prompts spanning general explanation, code reasoning, Elimu tutoring, Shamba agricultural guidance, Biashara analysis and grounded research. Define expected answer properties and safety constraints before running. Avoid personal, confidential or real customer data.

For every run record:
- Prompt suite version and prompt ID.
- RevelaAI build SHA and gateway environment.
- Provider and actual model from each response.
- Whether a fallback occurred.
- Request duration, response waiting duration and status.
- Token usage and pricing basis if available.
- Human quality score and reviewer notes.

Do not compare models using one prompt or a single run. Run multiple repetitions under comparable conditions and separate cold starts from warm steady-state measurements.

## Provider routing verification

The authenticated chat response currently returns provider/model metadata for generated answers and indicates fallback status. The root and health/capabilities routes report configured active provider/model, which is useful for preflight but is not proof of a successful inference.

Count a provider call as **verified inference** only when:
- The request reached the intended staging route.
- The response is successful.
- Provider and actual model are present and not a policy/manifest response.
- The result is not an unlabelled fallback.
- The request ID, build and timing evidence are captured.

Record direct rule/manifest responses separately from model-generated responses.

## Initial benchmark safety cap

The first k6 AI benchmark should use no more than 3 virtual users and 3 requests per user (9 total requests). Increase only after cost, quotas, rate limits and provider latency have been reviewed. A live-model benchmark consumes paid/free provider quota and should be explicitly enabled by the operator.

## Model selection

Do not define "best model" as the highest parameter count or fastest single response. Compare quality, latency, reliability, fallback frequency, context handling and cost per successfully completed task. Different RevelaCode hubs may need different models. Select per workload only after repeatable evidence.
