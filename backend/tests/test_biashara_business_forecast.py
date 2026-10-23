from datetime import datetime, timedelta, timezone

from backend.jumuiya.biashara.intelligence.service import forecast_business_data


AS_OF = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def _sale(day, amount, quantity=1):
    return {
        "created_at": datetime.fromisoformat(day).replace(tzinfo=timezone.utc),
        "amount": amount,
        "items": [{"product_id": "p-1", "quantity": quantity, "unit_price": 90}],
    }


def test_business_forecast_uses_recorded_sales_and_produces_horizon():
    sales = [
        _sale("2026-10-18", 450, 2),
        _sale("2026-10-20", 680, 3),
        _sale("2026-10-22", 740, 4),
        _sale("2026-10-24", 880, 5),
    ]
    products = [{
        "_id": "p-1",
        "name": "Desk lamp",
        "category": "Home",
        "price": 90,
        "cost_price": 75,
        "stock_quantity": 12,
        "low_stock_threshold": 5,
        "currency": "KES",
    }]

    result = forecast_business_data(
        sales,
        products,
        forecast_days=7,
        target_margin_percent=25,
        currency="KES",
        as_of=AS_OF,
    )

    assert result["revenue"]["available"] is True
    assert result["revenue"]["projected_total"] > 0
    assert len(result["revenue"]["daily_forecast"]) == 7
    assert result["actual_last_7_days"] == 2750
    assert result["products"][0]["demand"]["available"] is True
    assert len(result["products"][0]["demand"]["daily_forecast"]) == 7
    assert result["products"][0]["recommended_price"] == 100
    assert result["products"][0]["pricing_status"] == "below_target_margin"
    assert result["products"][0]["gross_margin_percent"] == 16.67


def test_business_forecast_does_not_invent_revenue_without_enough_history():
    result = forecast_business_data(
        [_sale("2026-10-23", 300, 2)],
        [{
            "_id": "p-1",
            "name": "Desk lamp",
            "price": 90,
            "cost_price": 75,
            "stock_quantity": 10,
        }],
        forecast_days=7,
        as_of=AS_OF,
    )

    assert result["revenue"]["available"] is False
    assert result["revenue"]["projected_total"] is None
    assert result["revenue"]["daily_forecast"] == []
    assert result["products"][0]["demand"]["available"] is False
    assert "three different days" in result["revenue"]["reason"]


def test_business_forecast_supports_custom_margin_and_marks_low_stock():
    result = forecast_business_data(
        [],
        [{
            "_id": "p-1",
            "name": "Desk lamp",
            "price": 100,
            "cost_price": 60,
            "stock_quantity": 2,
            "low_stock_threshold": 5,
        }],
        target_margin_percent=40,
        as_of=AS_OF,
    )

    product = result["products"][0]
    assert product["recommended_price"] == 100
    assert product["target_gross_margin_percent"] == 40
    assert product["low_stock"] is True
    assert product["pricing_status"] == "target_met"
