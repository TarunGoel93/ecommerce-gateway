from __future__ import annotations

import csv
import io
import json
import logging
import math
import os
import sys
import threading
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

from scraper_registry import SCRAPERS, run_scraper


ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = Path(
    os.environ.get("FRONTEND_DIR", str(ROOT_DIR.parent / "sale-fox-frontend"))
).resolve()
DATA_DIR = ROOT_DIR / "data"
DIST_DIR = Path(
    os.environ.get("FRONTEND_DIST_DIR", str(FRONTEND_DIR / "dist"))
).resolve()
AUTOMATION_BACKEND_DIR = ROOT_DIR / "automation"
if str(AUTOMATION_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_BACKEND_DIR))

from payment_systems import PAYMENT_METHODS_BY_PLATFORM
from unified_automation import ENGINES, attach_flask_automation_routes

DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=None)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("unified-scraper")

for automation_store in PAYMENT_METHODS_BY_PLATFORM:
    if automation_store not in ENGINES:
        raise RuntimeError(f"No automation engine is registered for {automation_store}.")
    attach_flask_automation_routes(
        app,
        automation_store,
        url_prefix=f"/api/automation/{automation_store}",
    )

jobs: dict[str, dict[str, Any]] = {
    slug: {
        "status": "idle",
        "progress": 0,
        "message": "Ready",
        "query": "",
        "logs": [],
        "error": None,
    }
    for slug in SCRAPERS
}
job_lock = threading.RLock()


def _data_file(slug: str, suffix: str) -> Path:
    return DATA_DIR / slug / f"{slug}_products.{suffix}"


def _read_products(slug: str) -> list[dict[str, Any]]:
    saved_file = _data_file(slug, "json")
    if saved_file.exists():
        with saved_file.open(encoding="utf-8") as file:
            products = json.load(file)
            if not isinstance(products, list):
                raise ValueError(f"Saved {slug} catalog is not a JSON list.")
            return products

    return []


def _save_products(slug: str, products: list[dict[str, Any]]) -> None:
    output_dir = DATA_DIR / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    json_file = _data_file(slug, "json")
    csv_file = _data_file(slug, "csv")
    json_temp = json_file.with_suffix(".json.tmp")
    csv_temp = csv_file.with_suffix(".csv.tmp")

    with json_temp.open("w", encoding="utf-8") as file:
        json.dump(products, file, ensure_ascii=False, indent=2)
    json_temp.replace(json_file)

    columns = list(dict.fromkeys(key for product in products for key in product))
    with csv_temp.open("w", encoding="utf-8", newline="") as file:
        if columns:
            writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for product in products:
                writer.writerow({
                    key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                    for key, value in product.items()
                })
    csv_temp.replace(csv_file)


def _record_progress(slug: str, progress: int, message: str) -> None:
    with job_lock:
        job = jobs[slug]
        job["progress"] = max(0, min(100, int(progress)))
        job["message"] = str(message)
        job["logs"].append(str(message))
        job["logs"] = job["logs"][-100:]


def _run_job(slug: str, payload: dict[str, Any]) -> None:
    try:
        _record_progress(slug, 10, f"Starting {SCRAPERS[slug]['name']} scraper")
        products = run_scraper(
            slug,
            payload,
            progress_callback=lambda progress, message: _record_progress(slug, progress, message),
        )
        _save_products(slug, products)
        with job_lock:
            jobs[slug].update({
                "status": "completed",
                "progress": 100,
                "message": f"Finished: {len(products)} products",
                "error": None,
                "count": len(products),
            })
    except Exception as exc:
        logger.exception("Scrape failed for %s", slug)
        with job_lock:
            jobs[slug].update({
                "status": "error",
                "progress": 100,
                "message": f"Scrape failed: {exc}",
                "error": str(exc),
            })


def _valid_number(value: Any, field: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number.") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite, non-negative number.")
    return number


@app.get("/health")
def health():
    return jsonify({"status": "healthy", "service": "Unified Scraper API"})


@app.get("/api/brands")
def list_brands():
    return jsonify([
        {
            "id": slug,
            "name": config["name"],
            "description": config["description"],
            "status": jobs[slug]["status"],
            "payment_automation": slug in PAYMENT_METHODS_BY_PLATFORM,
        }
        for slug, config in SCRAPERS.items()
    ])


@app.get("/api/payment-systems")
def list_payment_systems():
    return jsonify({
        "stores": [
            {
                "id": slug,
                "name": SCRAPERS[slug]["name"],
                "methods": PAYMENT_METHODS_BY_PLATFORM[slug],
            }
            for slug in PAYMENT_METHODS_BY_PLATFORM
        ]
    })


@app.get("/api/products")
def all_products():
    products = []
    for slug in SCRAPERS:
        for index, product in enumerate(_read_products(slug)):
            products.append({**product, "_source_brand": slug, "_source_id": f"{slug}-{index}"})
    return jsonify({"count": len(products), "products": products})


@app.get("/api/brands/<slug>/status")
def get_status(slug: str):
    if slug not in SCRAPERS:
        return jsonify({"error": f"Unknown scraper: {slug}"}), 404
    with job_lock:
        status = dict(jobs[slug])
    status["count"] = len(_read_products(slug))
    return jsonify(status)


@app.post("/api/brands/<slug>/scrape")
def start_scrape(slug: str):
    if slug not in SCRAPERS:
        return jsonify({"error": f"Unknown scraper: {slug}"}), 404
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "The request body must be a JSON object."}), 400
    query = str(payload.get("query", "")).strip()
    if not query:
        return jsonify({"error": "A search query is required."}), 400

    try:
        pages = int(payload.get("pages", 1))
        if not 1 <= pages <= 10:
            raise ValueError("pages must be between 1 and 10.")
        min_price = _valid_number(payload.get("min_price"), "min_price")
        max_price = _valid_number(payload.get("max_price"), "max_price")
        if min_price is not None and max_price is not None and min_price > max_price:
            raise ValueError("min_price cannot exceed max_price.")
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    payload.update({
        "query": query,
        "pages": pages,
        "min_price": min_price,
        "max_price": max_price,
        "pincode": str(payload.get("pincode", "110058")).strip() or "110058",
    })

    with job_lock:
        if jobs[slug]["status"] == "running":
            return jsonify({"error": "A scrape is already running for this store."}), 409
        jobs[slug].update({
            "status": "running",
            "progress": 0,
            "message": "Queued",
            "query": query,
            "logs": [],
            "error": None,
        })

    threading.Thread(target=_run_job, args=(slug, payload), daemon=True).start()
    return jsonify({"status": "started", "message": f"{SCRAPERS[slug]['name']} scrape started."}), 202


@app.get("/api/brands/<slug>/products")
def brand_products(slug: str):
    if slug not in SCRAPERS:
        return jsonify({"error": f"Unknown scraper: {slug}"}), 404
    products = _read_products(slug)
    return jsonify({"count": len(products), "products": products})


@app.get("/api/brands/<slug>/export/<format>")
def export_brand(slug: str, format: str):
    if slug not in SCRAPERS:
        return jsonify({"error": f"Unknown scraper: {slug}"}), 404
    if format not in {"json", "csv"}:
        return jsonify({"error": "Export format must be json or csv."}), 404
    products = _read_products(slug)
    if not products:
        return jsonify({"error": "No products are available to export."}), 404
    _save_products(slug, products)
    export_file = _data_file(slug, format)
    mime_type = "application/json" if format == "json" else "text/csv"
    return send_file(export_file, mimetype=mime_type, as_attachment=True)


@app.get("/api/export/<format>")
def export_all(format: str):
    if format not in {"json", "csv"}:
        return jsonify({"error": "Export format must be json or csv."}), 404
    products = [
        {**product, "_source_brand": slug}
        for slug in SCRAPERS
        for product in _read_products(slug)
    ]
    if not products:
        return jsonify({"error": "No products are available to export."}), 404
    if format == "json":
        payload = json.dumps(products, ensure_ascii=False, indent=2)
        return send_file(
            io.BytesIO(payload.encode("utf-8")),
            mimetype="application/json",
            as_attachment=True,
            download_name="all_products.json",
        )

    columns = list(dict.fromkeys(key for product in products for key in product))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for product in products:
        writer.writerow({
            key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
            for key, value in product.items()
        })
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="all_products.csv",
    )


@app.get("/api/<path:_path>")
def unknown_api_route(_path: str):
    return jsonify({"error": "API route not found."}), 404


@app.get("/")
def frontend_index():
    if not (DIST_DIR / "index.html").is_file():
        return jsonify({"message": "Unified frontend is not built. Run npm run dev in the unified dashboard folder."})
    return send_from_directory(DIST_DIR, "index.html")


@app.get("/<path:path>")
def frontend_asset(path: str):
    requested_path = (DIST_DIR / path).resolve()
    try:
        requested_path.relative_to(DIST_DIR.resolve())
    except ValueError:
        return jsonify({"error": "Not found."}), 404
    if requested_path.is_file():
        return send_from_directory(DIST_DIR, path)
    if (DIST_DIR / "index.html").is_file():
        return send_from_directory(DIST_DIR, "index.html")
    return jsonify({"error": "Not found."}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, threaded=True)
