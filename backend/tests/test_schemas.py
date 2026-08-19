import pytest
from jumuiya.biashara.schemas import business_payload, product_payload, customer_payload, order_payload, expense_payload

def test_business_requires_name():
    with pytest.raises(ValueError): business_payload({})

def test_product_requires_name():
    with pytest.raises(ValueError): product_payload({"price":10})

def test_customer_requires_name():
    with pytest.raises(ValueError): customer_payload({})

def test_order_requires_items():
    with pytest.raises(ValueError): order_payload({"items":[]})

def test_expense_requires_title():
    with pytest.raises(ValueError): expense_payload({"amount":100})
