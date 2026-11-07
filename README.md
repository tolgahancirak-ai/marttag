# Epgyt Market

Responsive Arabic, Turkish, and English storefront for Egypt, with a shopping
bag, cash-on-delivery checkout, order dashboard, and privacy notice.

## Store settings

- Store name: Epgyt Market
- Domain to connect: `EgCart.com`
- WhatsApp: `+20 103 178 0616`
- Cash-on-delivery delivery: 55 EGP
- Products: the current eight sample products and prices are in
  [`catalog.json`](catalog.json). Replace them with real stock before
  advertising the store.

## Deploy to Render

1. In Render, create a Blueprint from this GitHub repository and approve the
   resources in [`render.yaml`](render.yaml). The configuration provisions a
   paid Starter service and a persistent disk; check current Render pricing.
2. Wait for deployment, then check the service URL and its `/healthz` endpoint.
3. Open `/admin.html` and enter the generated `NILEMARKET_ADMIN_TOKEN` from
   Render's private environment settings. Never commit or share the token.
4. In Render's service settings, add `egcart.com` as a custom domain. Add
   `www.egcart.com` too if desired.
5. Copy Render's DNS instructions to the EgCart.com registrar's DNS panel.
   Wait for verification and HTTPS provisioning before sharing the site.

The domain and DNS must be controlled through the registrar account; this
repository cannot create or change those records.

## Local development

```bash
export NILEMARKET_ADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 server.py
```

Open `http://127.0.0.1:8000` for the store and
`http://127.0.0.1:8000/admin.html` for the order dashboard. Override the store
settings with `STORE_NAME`, `STORE_PHONE`, `STORE_DOMAIN`, and
`NILEMARKET_DELIVERY_FEE_EGP`. Orders are stored outside the web root; set
`NILEMARKET_DATABASE` to select a different database path.

## Before accepting real orders

- Replace all sample products, prices, and photos in `catalog.json`.
- Confirm the 55 EGP flat delivery fee with the delivery provider and update
  `NILEMARKET_DELIVERY_FEE_EGP` if required.
- Confirm WhatsApp support and monitor the private order dashboard.
- Arrange order notifications and database backups.
- Have [`privacy.html`](privacy.html) reviewed by an Egypt-based legal
  professional before collecting customer information.

Product photos and web fonts load from external services.
