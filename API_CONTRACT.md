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
