from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(__file__).resolve().parent / "data"
logger = logging.getLogger("unified-scraper.registry")
_load_lock = threading.RLock()
_loaded_classes: dict[str, type] = {}


SCRAPERS: dict[str, dict[str, str]] = {
    "amazon": {
        "name": "Amazon",
        "description": "Amazon India product search",
        "source": "scrapers/brand_scrapers/amazon/amazon_scraper.py",
        "class": "AmazonScraper",
    },
    "apple": {
        "name": "Apple",
        "description": "Apple Store India catalog",
        "source": "scrapers/brand_scrapers/apple/apple_scraper.py",
        "class": "AppleScraperEngine",
    },
    "croma": {
        "name": "Croma",
        "description": "Croma catalog",
        "source": "scrapers/brand_scrapers/croma/croma_scraper.py",
        "class": "CromaScraper",
    },
    "flipkart": {
        "name": "Flipkart",
        "description": "Flipkart phone catalog",
        "source": "scrapers/brand_scrapers/flipkart/flipkart_scraper.py",
        "class": "FlipkartScraper",
    },
    "jiomart": {
        "name": "JioMart",
        "description": "JioMart phone catalog",
        "source": "scrapers/brand_scrapers/jiomart/jiomart_scraper.py",
        "class": "JioMartScraper",
    },
    "oppo": {
        "name": "Oppo",
        "description": "Oppo India store",
        "source": "scrapers/brand_scrapers/oppo/oppo_scraper.py",
        "class": "OppoScraperEngine",
    },
    "reliance": {
        "name": "Reliance Digital",
        "description": "Reliance Digital phone catalog",
        "source": "scrapers/brand_scrapers/reliance/reliance_scraper.py",
        "class": "RelianceScraper",
    },
    "samsung": {
        "name": "Samsung",
        "description": "Samsung India smartphone catalog",
        "source": "scrapers/brand_scrapers/samsung/samsung_scraper.py",
        "class": "SamsungScraper",
    },
    "vivo": {
        "name": "Vivo",
        "description": "Vivo India store",
        "source": "scrapers/brand_scrapers/vivo/vivo_scraper.py",
        "class": "VivoScraper",
    },
    "xiaomi": {
        "name": "Xiaomi",
        "description": "Xiaomi / Mi Store catalog",
        "source": "scrapers/xiaomi/xiaomi_scraper.py",
        "class": "XiaomiScraperEngine",
    },
}


def _load_class(slug: str) -> type:
    with _load_lock:
        if slug in _loaded_classes:
            return _loaded_classes[slug]

        config = SCRAPERS[slug]
        source = ROOT_DIR / config["source"]
        module_name = f"_unified_scraper_{slug}"
        source_dir = str(source.parent)
        if source_dir not in sys.path:
            sys.path.insert(0, source_dir)

        spec = importlib.util.spec_from_file_location(module_name, source)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load scraper source: {source}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise

        scraper_class = getattr(module, config["class"])
        _loaded_classes[slug] = scraper_class
        return scraper_class


def _callback(progress_callback: Callable[[int, str], None], progress: int, message: str) -> None:
    progress_callback(progress, message)


def run_scraper(
    slug: str,
    payload: dict[str, Any],
    progress_callback: Callable[[int, str], None],
) -> list[dict[str, Any]]:
    if slug not in SCRAPERS:
        raise ValueError(f"Unknown scraper: {slug}")

    scraper_class = _load_class(slug)
    query = payload["query"]
    pages = payload["pages"]
    pincode = payload["pincode"]
    minimum = payload["min_price"]
    maximum = payload["max_price"]
    in_stock_only = bool(payload.get("in_stock_only", False))
    data_dir = str(DATA_DIR / slug)
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    _callback(progress_callback, 20, f"Loading {SCRAPERS[slug]['name']} engine")

    if slug == "amazon":
        scraper = scraper_class(driver=None, config={"domain": "https://www.amazon.in"})
        results = scraper.scrape_search_results(
            query=query,
            max_pages=pages,
            min_price=minimum,
            max_price=maximum,
            in_stock_only=in_stock_only,
            prime_only=bool(payload.get("prime_only", False)),
            min_rating=payload.get("min_rating"),
            progress_callback=lambda event: _callback(
                progress_callback,
                40,
                event.get("message", event.get("stage", "Scraping Amazon")),
            ),
            deep_scan=bool(payload.get("deep_scan", True)),
            use_turbo=True,
        )
    elif slug == "apple":
        scraper = scraper_class(data_dir=data_dir)
        results = scraper.scrape_catalog(
            query=query,
            pincode=pincode,
            in_stock_only=in_stock_only,
            log_callback=lambda message: _callback(progress_callback, 40, str(message)),
        )
    elif slug == "croma":
        scraper = scraper_class(data_dir=data_dir)
        results = scraper.scrape(
            query=query,
            pages=pages,
            pincode=pincode,
            in_stock_only=in_stock_only,
            progress_callback=lambda _status, progress, message: _callback(progress_callback, progress, message),
        )
    elif slug == "flipkart":
        scraper = scraper_class()
        results = scraper.scrape_catalog(
            query=query,
            pages=pages,
            min_price=minimum,
            max_price=maximum,
            in_stock_only=in_stock_only,
        )
    elif slug == "jiomart":
        scraper = scraper_class(pincode=pincode)
        # Unified API persistence replaces these engines' legacy output locations.
        scraper.save_results = lambda _products: None
        results = scraper.scrape_catalog(
            query=query,
            pages=pages,
            in_stock_only=in_stock_only,
            min_price=minimum,
            max_price=maximum,
        )
    elif slug == "oppo":
        scraper = scraper_class(data_dir=data_dir)
        results = scraper.scrape(
            query=query,
            pincode=pincode,
            in_stock_only=in_stock_only,
            log_callback=lambda message: _callback(progress_callback, 40, str(message)),
        )
    elif slug == "reliance":
        scraper = scraper_class(pincode=pincode, progress_cb=lambda message, progress: _callback(progress_callback, progress, message))
        scraper.save_results = lambda _products: None
        results = scraper.scrape_catalog(
            query=query,
            pages=pages,
            in_stock_only=in_stock_only,
            min_price=minimum,
            max_price=maximum,
        )
    elif slug == "samsung":
        scraper = scraper_class(data_dir=data_dir)
        results = scraper.scrape(
            query=query,
            pages=pages,
            pincode=pincode,
            in_stock_only=in_stock_only,
            progress_callback=lambda **event: _callback(
                progress_callback,
                event.get("progress", 40),
                event.get("message", event.get("status", "Scraping Samsung")),
            ),
        )
    elif slug == "vivo":
        scraper = scraper_class(output_dir=data_dir)
        results = scraper.scrape(
            series_filter=query,
            pincode=pincode,
            progress_callback=lambda progress, message: _callback(progress_callback, progress, message),
        )
    elif slug == "xiaomi":
        scraper = scraper_class(data_dir=data_dir)
        results = scraper.scrape_category(query=query, pincode=pincode, limit=payload.get("limit", 50))
    else:
        raise ValueError(f"No adapter is configured for scraper: {slug}")

    if not isinstance(results, list):
        raise TypeError(f"{SCRAPERS[slug]['name']} scraper returned a non-list result.")
    normalized = []
    for index, product in enumerate(results):
        if not isinstance(product, dict):
            raise TypeError(f"{SCRAPERS[slug]['name']} returned an invalid product at index {index}.")
        normalized.append({**product, "_source_brand": slug, "_source_id": f"{slug}-{index}"})
    _callback(progress_callback, 95, f"Saving {len(normalized)} {SCRAPERS[slug]['name']} products")
    return normalized
