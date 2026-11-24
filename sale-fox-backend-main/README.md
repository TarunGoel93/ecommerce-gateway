# Sale-Fox Unified Backend

This directory is the standalone backend repository root. It contains the Flask API, scraper
registry and engines, checkout automation, and store-specific payment integrations.

## Layout

- `app.py` and `scraper_registry.py`: the shared API and scraper routing.
- `automation/`: checkout flows, quantity verification, and payment systems.
- `scrapers/brand_scrapers/`: Amazon, Apple, Croma, Flipkart, JioMart, Oppo, Reliance Digital,
  Samsung, and Vivo scraper engines.
- `scrapers/xiaomi/`: Xiaomi scraper engine.
- `data/`: current product catalogs and runtime scrape output.
- `legacy/`: previous standalone server implementations and their deployment files; the unified
  API does not launch these servers.

The unified API no longer reads scraper code from `sale-fox-frontend/`,
`Scrapers-And-Payment-System/`, or `xiaomi scraper/`. Those workspace folders are not required to
run this backend.

## Requirements and startup

Install the Python requirements and Chromium, then start the API:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

The API listens on `http://127.0.0.1:5050` by default. Set `HOST` or `PORT` to override the bind
address or port. Start the frontend separately from the `sale-fox-frontend/` directory with `npm ci`
and `npm run dev`; Vite forwards `/api` requests to the API. `FRONTEND_DIR` can point the API to
the frontend checkout, and `FRONTEND_DIST_DIR` can override its production build directory.

## API overview

- `GET /health`
- `GET /api/brands`, `/api/products`, `/api/payment-systems`
- `GET /api/brands/<store>/status`
- `POST /api/brands/<store>/scrape`
- `GET /api/automation/<store>/config` and `/status`
- `POST /api/automation/<store>/start`, `/stop`, `/submit-otp`, and `/import-cards`

Scraping is configured for ten stores: Amazon, Apple, Croma, Flipkart, JioMart, Oppo, Reliance
Digital, Samsung, Vivo, and Xiaomi. Checkout automation is configured for Amazon, Apple, Croma,
Flipkart, JioMart, Reliance Digital, Samsung, and Vivo.

Checkout can submit a real order. Bulk checkout supports quantities 1–10 and requires explicit
confirmation for quantities above one. Do not start checkout unless you intend to place the order.
OTP, bank 3-D Secure, and UPI authentication remain interactive.

## Local configuration and data

Automation settings are optional. Put them in a local `.env` file in this backend directory, or
export them before starting the API. The automation module loads this `.env` file at startup.

- `AUTOMATION_PROFILE_ROOT`: browser profiles directory. Defaults to
  `~/.sale-fox/chrome-profiles`.
- `AUTOMATION_CARDS_FILE`: path to a private JSON file containing a list of cards. Each card
  should have `number`, `expiry`, and `cvv`; optional `label` and `brand` fields are supported.
- `AUTOMATION_CUSTOMER_NAME`, `AUTOMATION_CUSTOMER_FIRST_NAME`,
  `AUTOMATION_CUSTOMER_LAST_NAME`, `AUTOMATION_CUSTOMER_PHONE`,
  `AUTOMATION_CUSTOMER_EMAIL`, `AUTOMATION_CUSTOMER_ADDRESS`, `AUTOMATION_CUSTOMER_HOUSE`,
  `AUTOMATION_CUSTOMER_STREET`, `AUTOMATION_CUSTOMER_CITY`, `AUTOMATION_CUSTOMER_STATE`,
  `AUTOMATION_CUSTOMER_PINCODE`, `AUTOMATION_CUSTOMER_LANDMARK`, and `AUTOMATION_GST_NUMBER`:
  optional checkout details. A signed-in browser profile may already have the required details.
- `AUTOMATION_ORDERS_FILE`: optional Flipkart order-history CSV path. Defaults to
  `~/.sale-fox/orders.csv`.
- `AUTOMATION_NOTIFICATION_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, and `SMTP_PASS`:
  optional email notification settings.

Never commit `.env`, card files, browser profiles, or personal customer details. Keep card files
outside the repository and restrict access to them.

Scrape results are written under `data/`. The backend `.gitignore` excludes `.env`, browser
profiles, Python caches, and legacy scraper output.

The old `legacy/amazon-node/Dockerfile` is only for the archived Node.js Amazon scraper; it does not
build this unified Flask backend.

## Tests

From this directory, run:

```bash
./.venv/bin/python -m unittest test_app.py
```
