# Jumuiya Revenue Engine: payment-provider setup

The Revenue Engine uses the existing RevelaCode backend identity and Mongo database. It does not create a wallet or a separate database. The paid-subscription path writes a confirmed transaction to `jumuiya_revenue_transactions`, the payment event to `jumuiya_revenue_payment_events`, the checkout to `jumuiya_revenue_mpesa_checkouts`, and the subscription to `jumuiya_revenue_subscriptions`. Hub trials remain in `jumuiya_revenue_trials`.

## M-Pesa Daraja environment

Set these in the **RevelaCode-Backend** deployment environment, never in the frontend or RevelaAI:

| Variable | Purpose |
|---|---|
| `MPESA_ENV` | `sandbox` for tests or `production` for live payments |
| `MPESA_CONSUMER_KEY` | Daraja app consumer key |
| `MPESA_CONSUMER_SECRET` | Daraja app consumer secret |
| `MPESA_SHORTCODE` | Registered PayBill/Till shortcode |
| `MPESA_PASSKEY` | STK Push passkey supplied for the shortcode |
| `MPESA_CALLBACK_URL` | Public HTTPS URL ending in `/api/revenue/providers/mpesa/callback` |
| `MPESA_TRANSACTION_TYPE` | Optional: `CustomerPayBillOnline` by default or `CustomerBuyGoodsOnline` |
| `MPESA_PARTY_B` | Optional: destination shortcode; defaults to `MPESA_SHORTCODE` |

Use the exact values supplied by Safaricom for the registered Daraja application and shortcode. Do not use sandbox credentials with production mode or expose keys in the browser. A real payment can be collected once production credentials, callback reachability and the matching registered short code are configured.

The backend reports checkout readiness at `GET /api/revenue/admin/billing/status` and in the public plans response. Readiness only means the required environment values are present; it does **not** prove a live Daraja payment has succeeded.

## Checkout and confirmation

1. An authenticated client calls `POST /api/revenue/checkout` with only `plan_code` and a Kenyan `phone`, plus an `Idempotency-Key` header. The amount is taken from the backend plan catalogue.
2. The backend creates a tracked checkout record before calling Daraja STK Push.
3. The callback is treated as a notification. The backend queries the same Daraja `CheckoutRequestID`; only a final successful result for that checkout can activate a subscription.
4. Subscription activation and the confirmed revenue transaction are idempotent. A retry repairs a missing transaction-history entry where an earlier successful activation was already recorded.
5. An authenticated customer can inspect `GET /api/revenue/checkout/{checkoutRequestId}` or call `POST /api/revenue/checkout/{checkoutRequestId}/refresh` to reconcile a pending result.

A browser redirect, an unsigned callback body, an STK initiation response, or a pending query is not proof of payment. If Daraja returns no final `ResultCode`, checkout remains awaiting verification; it must not grant access.

## Trial and entitlement behavior

Each authenticated user can start one 30-day trial for each supported hub: Shamba, Biashara, Elimu, Community, Smart AI, Marketplace and Faith. Trial starts are recorded once per user/hub. Essential features remain free. The backend entitlement service checks the active trial or a current paid subscription for designated premium capabilities.

RevelaAI consults the same RevelaCode backend for image generation, document analysis, voice, Live Vision and persistent memory. A billing-service outage blocks these premium operations but does not block ordinary free text chat.

## Plan publication and current limits

Plans default to `proposed`; those are not approved public prices. A platform administrator must review and publish a monthly or yearly hub plan before it becomes eligible for checkout. The admin Revenue Center exposes the plan status and verified payment totals.

This release does not claim that automatic renewals, payment refunds, advertising campaign fulfilment, marketplace seller settlement/commissions, or stored-value wallet funding are enabled. Monthly/yearly subscription checkout is the supported Daraja flow. These other revenue lines require their respective fulfillment, accounting and reconciliation contracts before charging customers.

The general signed provider endpoint `POST /api/revenue/providers/verified-payment` is separately available to trusted adapters. It requires `REVENUE_PROVIDER_WEBHOOK_SECRET` (at least 32 characters) and a matching `X-Revenue-Signature: sha256=<HMAC-SHA256(raw request body)>`. Its caller must verify payment with the provider before signing the canonical event. Daraja's direct integration uses its own server-side status query.
