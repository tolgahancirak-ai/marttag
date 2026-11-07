import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from wsgiref.simple_server import make_server

import pytest

import server as storefront
from server import (
    OrderValidationError,
    create_order,
    list_orders,
    normalize_phone,
    update_order_status,
)


def valid_payload():
    return {
        "customer": {
            "name": "Nadia Hassan",
            "phone": "+20 1012345678",
            "governorate": "cairo",
            "address": "12 Garden City, Cairo",
        },
        "privacy_consent": True,
        "payment_method": "cod",
        "items": [
            {"id": "ceramic-vase", "quantity": 2},
            {"id": "woven-bag", "quantity": 1},
        ],
    }


def test_create_order_uses_server_catalog_and_persists_cod_order(tmp_path):
    database = tmp_path / "orders.sqlite3"

    order = create_order(valid_payload(), database, delivery_fee=75)

    assert order["subtotal"] == 2 * 680 + 950
    assert order["delivery_fee"] == 75
    assert order["total"] == 2 * 680 + 950 + 75
    assert order["payment_method"] == "cod"
    saved = list_orders(database)
    assert len(saved) == 1
    assert saved[0]["id"] == order["id"]
    assert saved[0]["phone"] == "01012345678"
    assert saved[0]["status"] == "new"
    assert saved[0]["items"][0]["unit_price"] == 680


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phone", "010123"),
        ("governorate", "not-a-governorate"),
        ("address", "x"),
    ],
)
def test_create_order_rejects_invalid_delivery_details(tmp_path, field, value):
    payload = valid_payload()
    payload["customer"][field] = value

    with pytest.raises(OrderValidationError):
        create_order(payload, tmp_path / "orders.sqlite3")


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"id": "unknown-product", "quantity": 1}],
        [{"id": "ceramic-vase", "quantity": 0}],
        [{"id": "ceramic-vase", "quantity": 11}],
        [{"id": ["ceramic-vase"], "quantity": 1}],
        [
            {"id": "ceramic-vase", "quantity": 1},
            {"id": "ceramic-vase", "quantity": 1},
        ],
    ],
)
def test_create_order_rejects_invalid_cart(tmp_path, items):
    payload = valid_payload()
    payload["items"] = items

    with pytest.raises(OrderValidationError):
        create_order(payload, tmp_path / "orders.sqlite3")


def test_create_order_rejects_non_cod_payment(tmp_path):
    payload = valid_payload()
    payload["payment_method"] = "card"

    with pytest.raises(OrderValidationError):
        create_order(payload, tmp_path / "orders.sqlite3")


def test_create_order_requires_privacy_consent(tmp_path):
    payload = valid_payload()
    payload["privacy_consent"] = False

    with pytest.raises(OrderValidationError):
        create_order(payload, tmp_path / "orders.sqlite3")


def test_phone_normalization_accepts_egyptian_digits_and_country_code():
    assert normalize_phone("٠١٠١٢٣٤٥٦٧٨") == "01012345678"
    assert normalize_phone("00201012345678") == "01012345678"


def test_admin_can_update_order_status(tmp_path):
    database = tmp_path / "orders.sqlite3"
    order = create_order(valid_payload(), database)

    assert update_order_status(order["id"], "confirmed", database)
    assert list_orders(database)[0]["status"] == "confirmed"
    assert not update_order_status("ABCDEF123456", "shipped", database)


def test_order_status_rejects_invalid_values(tmp_path):
    with pytest.raises(OrderValidationError):
        update_order_status("ABCDEF123456", ["delivered"], tmp_path / "orders.sqlite3")


def test_existing_order_database_is_migrated_for_privacy_consent(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    with storefront.sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE orders (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, customer_name TEXT NOT NULL,
                phone TEXT NOT NULL, governorate TEXT NOT NULL, address TEXT NOT NULL,
                payment_method TEXT NOT NULL, status TEXT NOT NULL, items_json TEXT NOT NULL,
                subtotal INTEGER NOT NULL, delivery_fee INTEGER NOT NULL, total INTEGER NOT NULL
            )
            """
        )

    storefront.init_database(database)

    with storefront.sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(orders)")}
    assert "privacy_consent" in columns


@pytest.fixture
def api_server(tmp_path, monkeypatch):
    database = tmp_path / "orders.sqlite3"
    monkeypatch.setattr(storefront, "DATABASE", database)
    monkeypatch.setattr(storefront, "DELIVERY_FEE", 60)
    monkeypatch.setattr(storefront, "ADMIN_TOKEN", "test-token-that-is-long-enough")
    storefront.init_database(database)
    httpd = make_server("127.0.0.1", 0, storefront.app)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def test_http_api_places_order_and_protects_admin_routes(api_server):
    with urlopen(f"{api_server}/api/config") as response:
        config = json.load(response)
    assert config["delivery_fee"] == 60
    assert len(config["governorates"]) == 27
    assert len(config["products"]) == 8
    assert config["products"][0]["price"] == 680

    with urlopen(f"{api_server}/admin.html") as response:
        assert response.status == 200
        assert response.headers["Content-Security-Policy"]
    with urlopen(f"{api_server}/privacy.html") as response:
        assert response.status == 200
    with urlopen(Request(f"{api_server}/privacy.js", method="HEAD")) as response:
        assert response.status == 200
        assert int(response.headers["Content-Length"]) > 0
    with pytest.raises(HTTPError) as source_error:
        urlopen(f"{api_server}/server.py")
    assert source_error.value.code == 404
    with pytest.raises(HTTPError) as source_head_error:
        urlopen(Request(f"{api_server}/server.py", method="HEAD"))
    assert source_head_error.value.code == 404

    payload = valid_payload()
    request = Request(
        f"{api_server}/api/orders",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request) as response:
        created = json.load(response)["order"]
        assert response.status == 201
    assert created["total"] == 2 * 680 + 950 + 60

    protected_request = Request(f"{api_server}/api/admin/orders")
    with pytest.raises(HTTPError) as error:
        urlopen(protected_request)
    assert error.value.code == 401

    admin_request = Request(
        f"{api_server}/api/admin/orders",
        headers={"Authorization": "Bearer test-token-that-is-long-enough"},
    )
    with urlopen(admin_request) as response:
        orders = json.load(response)["orders"]
    assert orders[0]["id"] == created["id"]

    status_request = Request(
        f"{api_server}/api/admin/orders/{created['id']}",
        data=json.dumps({"status": "confirmed"}).encode(),
        headers={
            "Authorization": "Bearer test-token-that-is-long-enough",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    with urlopen(status_request) as response:
        assert json.load(response)["status"] == "confirmed"
