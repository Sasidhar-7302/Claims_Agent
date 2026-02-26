from app.product_catalog import validate_products_catalog


def test_validate_products_catalog_valid():
    data = {
        "products": [
            {
                "product_id": "HD-TEST-001",
                "name": "Test Dryer",
                "aliases": ["test dryer"],
                "policy_file": "policy_test.txt",
            }
        ]
    }
    errors = validate_products_catalog(data)
    assert errors == []


def test_validate_products_catalog_invalid():
    data = {
        "products": [
            {
                "product_id": "",
                "name": "",
                "aliases": "not-a-list",
                "policy_file": "",
            }
        ]
    }
    errors = validate_products_catalog(data)
    assert len(errors) >= 3

