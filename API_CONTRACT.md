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


## Premium Biashara storefront settings

The authenticated GET /api/jumuiya/biashara/website and PUT /api/jumuiya/biashara/website endpoints additionally support:

- logo_url and hero_image_url: HTTPS media URLs or compressed data:image/png, data:image/jpeg, or data:image/webp base64 image data from the Website Studio uploader. Embedded images are limited to 450,000 characters per image.
- hero_video_url: optional HTTPS YouTube, Vimeo, or direct video URL.
- hero_slides: up to 8 objects containing image_url, video_url, title, subtitle, and alt. Each slide must contain an image or video URL.
- gallery_items: up to 12 objects containing type (image or video), url, caption, and alt.
- social_links: HTTPS profile URLs for the supported profile names (facebook, instagram, messenger, tiktok, youtube, x, linkedin, telegram, pinterest, snapchat, threads, whatsapp_channel, reddit, discord, twitch, bluesky, mastodon, github, medium, wechat, vk, rumble, line, signal, website, and other).
- announcement, footer_message, show_gallery, and show_social_links.
- custom_domain: bare domain name only, e.g. shop.example.com.

domain_status is server-managed and cannot be supplied by a client. Saving a new custom_domain records pending_platform_setup; this is a setup request, not proof of ownership or a live domain. DNS verification, hosting-level domain mapping, routing, and TLS/SSL must be configured by the platform before the domain can serve the storefront. The /b/<slug> address remains the public path until that platform work is complete.

The existing verification requirement remains in force: website settings are only accessible to an active, platform-verified business owner, and the public website only returns data for an active, verified business whose website has been published.
