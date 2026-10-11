
"""Safe monetary calculations for the revenue engine."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from backend.revenue.constants import (
    CURRENCY_DEFAULT,
    MAX_CURRENCY_AMOUNT,
    ZERO_MONEY,
)

CENT = Decimal("0.01")


class MoneyValidationError(ValueError):
    """Raised when a monetary value is invalid."""


def to_money(value, *, allow_zero=True):
    """Convert a value to a validated, two-decimal monetary amount."""
    if isinstance(value, bool) or value is None:
        raise MoneyValidationError("A valid monetary amount is required.")

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise MoneyValidationError("The monetary amount is invalid.") from None

    if not amount.is_finite():
        raise MoneyValidationError("The monetary amount must be finite.")

    if amount < ZERO_MONEY:
        raise MoneyValidationError("Negative monetary amounts are not allowed.")

    if not allow_zero and amount == ZERO_MONEY:
        raise MoneyValidationError("The monetary amount must be greater than zero.")

    if amount > MAX_CURRENCY_AMOUNT:
        raise MoneyValidationError("The monetary amount exceeds the allowed limit.")

    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_percentage_fee(amount, percentage):
    """Calculate a platform fee in percentage points, e.g. 1 means 1%."""
    gross = to_money(amount)

    try:
        rate = Decimal(str(percentage))
    except (InvalidOperation, ValueError, TypeError):
        raise MoneyValidationError("The fee percentage is invalid.") from None

    if not rate.is_finite() or rate < 0 or rate > 100:
        raise MoneyValidationError(
            "The fee percentage must be between 0 and 100."
        )

    fee = (gross * rate / Decimal("100")).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )

    return {
        "currency": CURRENCY_DEFAULT,
        "gross_amount": f"{gross:.2f}",
        "fee_percentage": f"{rate.normalize()}",
        "platform_fee": f"{fee:.2f}",
        "seller_amount_before_other_charges": f"{gross - fee:.2f}",
    }