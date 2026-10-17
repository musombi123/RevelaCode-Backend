# Biashara API

Base: /api/jumuiya/biashara

GET  /health
GET  /business
POST /business

GET  /products
POST /products
PUT  /products/{id}

GET  /customers
POST /customers

GET  /orders
POST /orders

POST /expenses

GET  /dashboard

Business body:
{
  "name":"Mama Njeri Shop",
  "description":"General retail shop",
  "phone":"07XXXXXXXX",
  "location":"Kongowea",
  "county":"Mombasa",
  "category":"Retail"
}

Product body:
{
  "name":"Exercise Book",
  "category":"Stationery",
  "sku":"EX-096",
  "price":80,
  "stock_quantity":50,
  "unit":"piece",
  "currency":"KES"
}

Order body:
{
  "customer_id":"optional-id",
  "items":[
    {"product_id":"product-id","name":"Exercise Book","quantity":2,"unit_price":80}
  ],
  "total_amount":160,
  "currency":"KES"
}

Expense body:
{
  "title":"Transport",
  "category":"Operations",
  "amount":300,
  "currency":"KES"
}

NOTE:
Dashboard sales/expense totals are operational metrics, NOT yet a legally
auditable accounting ledger. Live payments require an immutable transaction
ledger and M-Pesa reconciliation layer.

## Business verification and workspace access

Business profile creation is an application, not immediate workspace activation.

- `GET /api/jumuiya/biashara/business` returns the owner's current business application/profile so the frontend can display its verification status.
- `POST /api/jumuiya/biashara/business` creates an application with `status: "pending_verification"` and `verification_status: "pending"`. Client-supplied status or verification fields are ignored.
- Until a platform administrator approves the application, business workspace services return `403 business_verification_required`. A business is granted workspace access only when both `status: "active"` and `verification_status: "verified"` are set server-side.
- The public business website is returned only when the business is active, verified, and its website has been published.

Platform administrator endpoints (JWT authentication plus an authorized platform-admin role required):

`GET /api/jumuiya/admin/businesses?status=pending&page=1&limit=100`

Lists applications waiting for review, including applications that need information and legacy active records that predate verification.

`PATCH /api/jumuiya/admin/businesses/{business_id}/verification`

Request body for approval:

```json
{
  "decision": "approve",
  "notes": "",
  "checks": {
    "business_details_checked": true,
    "owner_contact_checked": true
  }
}
```

Supported decisions are `approve`, `reject`, and `needs_information`. Approval requires both checks to be explicitly `true`. Rejection and requests for information require non-empty `notes`. The review decision, reviewer, timestamp, checks, and notes are recorded in the business verification history.

Updating a rejected or unapproved application resubmits it for review. Changes to verified business identity/contact/location fields return the business to pending review and disable workspace access until it is approved again.
