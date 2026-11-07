"""Small same-origin storefront server with SQLite-backed COD orders."""

from __future__ import annotations

import hmac
import io
import json
import logging
import mimetypes
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from wsgiref.simple_server import make_server


ROOT = Path(__file__).resolve().parent
DATABASE = Path(
    os.environ.get(
        "NILEMARKET_DATABASE",
        Path.home() / ".local" / "share" / "epgyt-market" / "orders.sqlite3",
    )
)
DELIVERY_FEE = int(os.environ.get("NILEMARKET_DELIVERY_FEE_EGP", "55"))
ADMIN_TOKEN = os.environ.get("NILEMARKET_ADMIN_TOKEN", "")
STORE_NAME = os.environ.get("STORE_NAME", "Epgyt Market")
STORE_PHONE = os.environ.get("STORE_PHONE", "+201031780616")
STORE_DOMAIN = os.environ.get("STORE_DOMAIN", "EgCart.com")
MAX_REQUEST_BYTES = 32_768
CATALOG_PATH = ROOT / "catalog.json"
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/admin.html": "admin.html",
    "/privacy.html": "privacy.html",
    "/styles.css": "styles.css",
    "/store.js": "store.js",
    "/admin.js": "admin.js",
    "/privacy.js": "privacy.js",
}

def load_catalog(path: Path = CATALOG_PATH) -> list[dict[str, Any]]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        raise ValueError("The product catalog must be a non-empty JSON list.")

    products = {}
    for product in entries:
        if not isinstance(product, dict):
            raise ValueError("Each catalog product must be an object.")
        product_id = product.get("id")
        price = product.get("price")
        if (
            not isinstance(product_id, str)
            or not re.fullmatch(r"[a-z0-9-]{1,60}", product_id)
            or product_id in products
        ):
            raise ValueError("Catalog product IDs must be unique lowercase identifiers.")
        if isinstance(price, bool) or not isinstance(price, int) or not 1 <= price <= 10_000_000:
            raise ValueError(f"Catalog price for {product_id} must be a positive EGP integer.")
        for field in ("name", "category_name"):
            translations = product.get(field)
            if (
                not isinstance(translations, dict)
                or set(translations) != {"ar", "tr", "en"}
                or any(not isinstance(value, str) or not value.strip() for value in translations.values())
            ):
                raise ValueError(f"Catalog {field} for {product_id} needs Arabic, Turkish, and English.")
        if product.get("category") not in {"home", "fashion", "accessories", "beauty"}:
            raise ValueError(f"Catalog category for {product_id} is invalid.")
        if product.get("badge") not in {"", "new", "popular"}:
            raise ValueError(f"Catalog badge for {product_id} is invalid.")
        if not isinstance(product.get("image"), str) or not re.fullmatch(
            r"photo-[A-Za-z0-9-]+", product["image"]
        ):
            raise ValueError(f"Catalog image for {product_id} is invalid.")
        products[product_id] = product
    return list(products.values())


CATALOG = load_catalog()
PRODUCTS = {product["id"]: product for product in CATALOG}

GOVERNORATES = {
    "cairo": "Cairo",
    "giza": "Giza",
    "alexandria": "Alexandria",
    "qalyubia": "Qalyubia",
    "sharqia": "Sharqia",
    "dakahlia": "Dakahlia",
    "gharbia": "Gharbia",
    "monufia": "Monufia",
    "beheira": "Beheira",
    "kafr-el-sheikh": "Kafr El Sheikh",
    "damietta": "Damietta",
    "port-said": "Port Said",
    "ismailia": "Ismailia",
    "suez": "Suez",
    "north-sinai": "North Sinai",
    "south-sinai": "South Sinai",
    "beni-suef": "Beni Suef",
    "fayoum": "Fayoum",
    "minya": "Minya",
    "assiut": "Assiut",
    "sohag": "Sohag",
    "qena": "Qena",
    "luxor": "Luxor",
    "aswan": "Aswan",
    "red-sea": "Red Sea",
    "new-valley": "New Valley",
    "matrouh": "Matrouh",
}

ORDER_STATUSES = {
    "new",
    "confirmed",
    "preparing",
    "shipped",
    "delivered",
    "cancelled",
}


class OrderValidationError(ValueError):
    """Raised when a checkout request does not match the store's requirements."""


def init_database(database: Path = DATABASE) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                governorate TEXT NOT NULL,
                address TEXT NOT NULL,
                privacy_consent INTEGER NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL,
                status TEXT NOT NULL,
                items_json TEXT NOT NULL,
                subtotal INTEGER NOT NULL,
                delivery_fee INTEGER NOT NULL,
                total INTEGER NOT NULL
            )
            """
        )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(orders)").fetchall()
        }
        if "privacy_consent" not in columns:
            connection.execute(
                "ALTER TABLE orders ADD COLUMN privacy_consent INTEGER NOT NULL DEFAULT 0"
            )


def normalize_phone(value: Any) -> str:
    if not isinstance(value, str):
        raise OrderValidationError("Enter a valid Egyptian mobile number.")
    digits = value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    digits = re.sub(r"[\s().-]", "", digits)
    if digits.startswith("+20"):
        digits = "0" + digits[3:]
    elif digits.startswith("0020"):
        digits = "0" + digits[4:]
    if not re.fullmatch(r"01[0125]\d{8}", digits):
        raise OrderValidationError("Enter a valid Egyptian mobile number.")
    return digits


def validate_settings() -> None:
    if not 0 <= DELIVERY_FEE <= 10_000:
        raise ValueError("NILEMARKET_DELIVERY_FEE_EGP must be between 0 and 10000.")
    if ADMIN_TOKEN and len(ADMIN_TOKEN) < 24:
        raise ValueError("NILEMARKET_ADMIN_TOKEN must be at least 24 characters.")
    normalize_phone(STORE_PHONE)
    if not STORE_NAME.strip() or len(STORE_NAME) > 80:
        raise ValueError("STORE_NAME must contain between 1 and 80 characters.")
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", STORE_DOMAIN):
        raise ValueError("STORE_DOMAIN must be a hostname.")


validate_settings()


def _clean_text(value: Any, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise OrderValidationError(f"Enter a valid {field}.")
    cleaned = " ".join(value.split())
    if not minimum <= len(cleaned) <= maximum or any(ord(char) < 32 for char in cleaned):
        raise OrderValidationError(f"Enter a valid {field}.")
    return cleaned


def create_order(payload: Any, database: Path = DATABASE, delivery_fee: int = DELIVERY_FEE) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OrderValidationError("Invalid order details.")
    customer = payload.get("customer")
    if not isinstance(customer, dict):
        raise OrderValidationError("Enter your delivery details.")

    name = _clean_text(customer.get("name"), "full name", 2, 100)
    phone = normalize_phone(customer.get("phone"))
    governorate = customer.get("governorate")
    if not isinstance(governorate, str) or governorate not in GOVERNORATES:
        raise OrderValidationError("Choose a valid Egyptian governorate.")
    address = _clean_text(customer.get("address"), "delivery address", 5, 500)
    if payload.get("privacy_consent") is not True:
        raise OrderValidationError("Accept the privacy policy before placing an order.")
    if payload.get("privacy_consent") is not True:
        raise OrderValidationError("Accept the privacy policy before placing an order.")
    if payload.get("payment_method") != "cod":
        raise OrderValidationError("Cash on delivery is the only available payment method.")

    requested_items = payload.get("items")
    if not isinstance(requested_items, list) or not 1 <= len(requested_items) <= len(PRODUCTS):
        raise OrderValidationError("Your bag is empty or contains too many products.")

    line_items = []
    seen_ids = set()
    for item in requested_items:
        if not isinstance(item, dict):
            raise OrderValidationError("Invalid product in your bag.")
        product_id = item.get("id")
        quantity = item.get("quantity")
        if not isinstance(product_id, str) or product_id not in PRODUCTS or product_id in seen_ids:
            raise OrderValidationError("Your bag contains an unavailable product.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 10:
            raise OrderValidationError("Product quantities must be between 1 and 10.")
        seen_ids.add(product_id)
        product = PRODUCTS[product_id]
        line_items.append(
            {
                "id": product_id,
                "name": product["name"]["en"],
                "names": product["name"],
                "quantity": quantity,
                "unit_price": product["price"],
            }
        )

    if isinstance(delivery_fee, bool) or not isinstance(delivery_fee, int) or not 0 <= delivery_fee <= 10_000:
        raise ValueError("Delivery fee must be an integer between 0 and 10000 EGP.")

    init_database(database)
    subtotal = sum(item["unit_price"] * item["quantity"] for item in line_items)
    order_id = uuid.uuid4().hex[:12].upper()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(database, timeout=10) as connection:
        connection.execute(
            """
            INSERT INTO orders (
                id, created_at, customer_name, phone, governorate, address, privacy_consent,
                payment_method, status, items_json, subtotal, delivery_fee, total
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 'cod', 'new', ?, ?, ?, ?)
            """,
            (
                order_id,
                created_at,
                name,
                phone,
                governorate,
                address,
                json.dumps(line_items, ensure_ascii=False),
                subtotal,
                delivery_fee,
                subtotal + delivery_fee,
            ),
        )
    return {
        "id": order_id,
        "created_at": created_at,
        "items": line_items,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": subtotal + delivery_fee,
        "payment_method": "cod",
    }


def list_orders(database: Path = DATABASE) -> list[dict[str, Any]]:
    init_database(database)
    with sqlite3.connect(database, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, created_at, customer_name, phone, governorate, address,
                   privacy_consent, payment_method, status, items_json, subtotal, delivery_fee, total
            FROM orders ORDER BY created_at DESC, rowid DESC LIMIT 100
            """
        ).fetchall()
    orders = []
    for row in rows:
        order = dict(row)
        order["items"] = json.loads(order.pop("items_json"))
        orders.append(order)
    return orders


def update_order_status(order_id: str, status: Any, database: Path = DATABASE) -> bool:
    if (
        not isinstance(order_id, str)
        or not re.fullmatch(r"[A-F0-9]{12}", order_id)
        or not isinstance(status, str)
        or status not in ORDER_STATUSES
    ):
        raise OrderValidationError("Invalid order or status.")
    with sqlite3.connect(database, timeout=10) as connection:
        cursor = connection.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    return cursor.rowcount == 1


def _json_response(status: str, payload: Any) -> tuple[str, bytes]:
    return status, json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _request_json(environ: dict[str, Any]) -> Any:
    if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
        raise OrderValidationError("Send order details as JSON.")
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError as error:
        raise OrderValidationError("Invalid request length.") from error
    if not 0 < length <= MAX_REQUEST_BYTES:
        raise OrderValidationError("Request is empty or too large.")
    try:
        return json.loads(environ["wsgi.input"].read(length).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OrderValidationError("Invalid JSON request.") from error


def _admin_authorized(environ: dict[str, Any]) -> bool:
    if not ADMIN_TOKEN:
        return False
    scheme, _, token = environ.get("HTTP_AUTHORIZATION", "").partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(
        token.encode("utf-8"), ADMIN_TOKEN.encode("utf-8")
    )


def application(environ: dict[str, Any], start_response: Any) -> list[bytes]:
    """WSGI application used by Gunicorn in production and wsgiref locally."""
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = urlsplit(environ.get("PATH_INFO", "/")).path
    status = "200 OK"
    content_type = "application/json; charset=utf-8"
    cache_control = "no-store"
    body = b""

    try:
        if method in {"GET", "HEAD"} and path == "/healthz":
            body = b'{"ok":true}'
        elif method == "GET" and path == "/api/config":
            body = json.dumps(
                {
                    "currency": "EGP",
                    "delivery_fee": DELIVERY_FEE,
                    "cod_enabled": True,
                    "governorates": list(GOVERNORATES),
                    "store_name": STORE_NAME,
                    "store_phone": STORE_PHONE,
                    "store_whatsapp": re.sub(r"\D", "", STORE_PHONE),
                    "store_domain": STORE_DOMAIN,
                    "products": CATALOG,
                }
            ).encode()
        elif method == "GET" and path == "/api/admin/orders":
            if not ADMIN_TOKEN:
                status, body = _json_response(
                    "503 Service Unavailable", {"error": "Admin access is not configured."}
                )
            elif not _admin_authorized(environ):
                status, body = _json_response(
                    "401 Unauthorized", {"error": "Admin authentication required."}
                )
            else:
                body = json.dumps({"orders": list_orders(DATABASE)}, ensure_ascii=False).encode()
        elif method == "POST" and path == "/api/orders":
            try:
                order = create_order(_request_json(environ), DATABASE, DELIVERY_FEE)
            except OrderValidationError as error:
                status, body = _json_response("400 Bad Request", {"error": str(error)})
            else:
                status, body = _json_response("201 Created", {"order": order})
        elif method == "PATCH" and re.fullmatch(r"/api/admin/orders/[A-F0-9]{12}", path):
            if not ADMIN_TOKEN:
                status, body = _json_response(
                    "503 Service Unavailable", {"error": "Admin access is not configured."}
                )
            elif not _admin_authorized(environ):
                status, body = _json_response(
                    "401 Unauthorized", {"error": "Admin authentication required."}
                )
            else:
                order_id = path.rsplit("/", 1)[-1]
                try:
                    payload = _request_json(environ)
                    if not isinstance(payload, dict):
                        raise OrderValidationError("Invalid order status.")
                    order_status = payload.get("status")
                    updated = update_order_status(order_id, order_status, DATABASE)
                except OrderValidationError as error:
                    status, body = _json_response("400 Bad Request", {"error": str(error)})
                else:
                    if updated:
                        body = json.dumps({"id": order_id, "status": order_status}).encode()
                    else:
                        status, body = _json_response(
                            "404 Not Found", {"error": "Order not found."}
                        )
        elif method in {"GET", "HEAD"} and path in STATIC_FILES:
            file_path = ROOT / STATIC_FILES[path]
            body = file_path.read_bytes()
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            cache_control = "public, max-age=300"
        elif path == "/robots.txt":
            status, body = "404 Not Found", b"Not found."
            content_type = "text/plain; charset=utf-8"
        else:
            status, body = _json_response("404 Not Found", {"error": "Not found."})
    except (OSError, sqlite3.Error):
        logging.exception("Store request failed for %s %s", method, path)
        status, body = _json_response("500 Internal Server Error", {"error": "Store request failed."})

    content_length = len(body)
    if method == "HEAD":
        body = b""
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(content_length)),
        ("Cache-Control", cache_control),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
        (
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' https://images.unsplash.com data:; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self'; "
            "connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        ),
    ]
    if environ.get("HTTP_X_FORWARDED_PROTO") == "https":
        headers.append(("Strict-Transport-Security", "max-age=31536000; includeSubDomains"))
    start_response(status, headers)
    return [body]


app = application


def main() -> None:
    init_database()
    host = os.environ.get("NILEMARKET_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", os.environ.get("NILEMARKET_PORT", "8000")))
    server = make_server(host, port, app)
    print(f"{STORE_NAME} is serving on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nShutting down {STORE_NAME}.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
