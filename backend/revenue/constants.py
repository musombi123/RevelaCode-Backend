"""Shared constants for the Jumuiya OS Revenue Engine."""

from decimal import Decimal

CURRENCY_DEFAULT = "KES"

# These streams are request/intent categories, not proof that a payment
# provider has collected money. Billing remains disabled until payment
# verification and settlement are implemented.
SUPPORTED_REVENUE_STREAMS = frozenset({
    "shamba",
    "elimu",
    "biashara",
    "community",
    "marketplace",
    "smart_ai",
    "faith",
    "advertising",
    "transaction_fees",
})

PAYMENT_STATUSES = frozenset({
    "pending",
    "processing",
    "succeeded",
    "failed",
    "cancelled",
    "refunded",
    "partially_refunded",
})

SUBSCRIPTION_STATUSES = frozenset({
    "pending",
    "active",
    "past_due",
    "cancelled",
    "expired",
})

LEDGER_ENTRY_TYPES = frozenset({
    "customer_payment",
    "platform_revenue",
    "seller_payable",
    "refund",
    "payment_provider_fee",
    "tax_payable",
    "operating_expense",
    "settlement",
    "adjustment",
})

# Decimal avoids binary floating-point errors in monetary calculations.
ZERO_MONEY = Decimal("0.00")

# These are application limits, not subscription prices.
MAX_CURRENCY_AMOUNT = Decimal("999999999.99")
MAX_IDEMPOTENCY_KEY_LENGTH = 128
