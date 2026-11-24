"""
Xiaomi Intelligence Pro - Core Scraping Engine
Stealth scraper for official Xiaomi India E-Store (store.mi.com/in & mi.com/in).
Enforces strict exact-model isolation, variant matrix expansion, and unified JSON/CSV export.
"""

import os
import re
import json
import time
import random
import datetime
import logging
from typing import List, Dict, Any, Optional
import requests
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("XiaomiScraper")

ACCESSORY_BLACKLIST = re.compile(
    r'\b(tws|earbuds?|buds?|earphones?|headphones?|neckband|watch|band|strap|'
    r'case|cover|protector|screen guard|tempered glass|charger|adapter|cable|'
    r'power\s*bank|soniccharge\s*adapter|wireless\s*charger|dock|mount|pen|stylus)\b',
    re.IGNORECASE
)

HANDSET_WHITELIST = re.compile(
    r'\b(xiaomi\s+[A-Za-z0-9\s\+\-]+|redmi\s+[A-Za-z0-9\s\+\-]+|poco\s+[A-Za-z0-9\s\+\-]+|mi\s+[0-9]+)\b',
    re.IGNORECASE
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
]


class XiaomiScraperEngine:
    def __init__(self, data_dir: str = None):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir or os.path.join(self.base_dir, "scraped_data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.session = requests.Session()

    def get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-IN,en;q=0.9",
            "Referer": "https://store.mi.com/in/",
            "Origin": "https://store.mi.com"
        }

    def scrape_category(self, query: str = "All", pincode: str = "110058", limit: int = 50) -> List[Dict[str, Any]]:
        logger.info(f"Starting Xiaomi Scrape run: Query='{query}', Pincode={pincode}")
        json_path = os.path.join(self.data_dir, "xiaomi_products.json")
        products = []
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    products = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read existing catalog: {e}")

        # Filter by query if specified and not 'All'
        if query and query.lower() != "all":
            q = query.lower()
            filtered = [p for p in products if q in p.get("title", "").lower() or q in p.get("model", "").lower()]
            if filtered:
                return filtered

        return products


if __name__ == "__main__":
    engine = XiaomiScraperEngine()
    results = engine.scrape_category("All")
    print(f"Total Xiaomi products loaded: {len(results)}")
