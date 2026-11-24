import unittest
from unittest.mock import patch

from app import DIST_DIR, app


class UnifiedApiTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_lists_unique_scrapers_and_reads_existing_catalogs(self):
        brands_response = self.client.get("/api/brands")
        catalog_response = self.client.get("/api/products")

        self.assertEqual(brands_response.status_code, 200)
        self.assertEqual(len(brands_response.get_json()), 10)
        self.assertEqual(catalog_response.status_code, 200)
        self.assertGreater(catalog_response.get_json()["count"], 0)
        self.assertTrue(all("_source_brand" in item for item in catalog_response.get_json()["products"]))

    def test_all_scraper_sources_are_backend_local_and_loadable(self):
        from scraper_registry import ROOT_DIR, SCRAPERS, _load_class

        backend_root = ROOT_DIR.resolve()
        for slug, config in SCRAPERS.items():
            with self.subTest(store=slug):
                source = (backend_root / config["source"]).resolve()
                source.relative_to(backend_root)
                self.assertTrue(source.is_file())
                self.assertIsNotNone(_load_class(slug))

    def test_rejects_invalid_scrape_requests(self):
        missing_query = self.client.post("/api/brands/amazon/scrape", json={})
        invalid_pages = self.client.post(
            "/api/brands/amazon/scrape",
            json={"query": "phone", "pages": 11},
        )
        invalid_body = self.client.post("/api/brands/amazon/scrape", json=["phone"])

        self.assertEqual(missing_query.status_code, 400)
        self.assertEqual(invalid_pages.status_code, 400)
        self.assertEqual(invalid_body.status_code, 400)

    def test_unknown_brand_and_api_routes_are_not_served_as_frontend(self):
        unknown_brand = self.client.get("/api/brands/not-a-store/status")
        unknown_api = self.client.get("/api/not-a-route")

        self.assertEqual(unknown_brand.status_code, 404)
        self.assertEqual(unknown_api.status_code, 404)

    def test_payment_systems_and_namespaced_automation_are_available(self):
        systems_response = self.client.get("/api/payment-systems")
        config_response = self.client.get("/api/automation/amazon/config")
        unsupported_response = self.client.get("/api/automation/xiaomi/config")

        self.assertEqual(systems_response.status_code, 200)
        store_ids = {store["id"] for store in systems_response.get_json()["stores"]}
        self.assertIn("amazon", store_ids)
        self.assertIn("vivo", store_ids)
        self.assertNotIn("xiaomi", store_ids)

        self.assertEqual(config_response.status_code, 200)
        config = config_response.get_json()
        self.assertEqual(config["brand"], "Amazon")
        self.assertEqual(config["payment_methods"], ["cod", "upi", "cards"])
        self.assertTrue(all(
            not {"number", "cvv", "expiry", "upi_id", "otp"}.intersection(card)
            for card in config["cards"]
        ))
        self.assertEqual(unsupported_response.status_code, 404)

    def test_bulk_quantity_requires_confirmation_and_enforces_cap(self):
        from unified_automation import ENGINES

        route = "/api/automation/flipkart/start"
        missing_confirmation = self.client.post(
            route,
            json={"product_name": "Test phone", "payment_method": "cod", "quantity": 2},
        )
        over_limit = self.client.post(
            route,
            json={
                "product_name": "Test phone",
                "payment_method": "cod",
                "quantity": 11,
                "confirm_auto_place": True,
            },
        )

        self.assertEqual(missing_confirmation.status_code, 400)
        self.assertIn("Confirm automated", missing_confirmation.get_json()["error"])
        self.assertEqual(over_limit.status_code, 400)
        self.assertIn("1 to 10", over_limit.get_json()["error"])

        with patch("unified_automation.threading.Thread") as thread:
            response = self.client.post(
                route,
                json={
                    "product_name": "Test phone",
                    "payment_method": "cod",
                    "quantity": 10,
                    "confirm_auto_place": True,
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(thread.call_args.kwargs["args"][-2], 10)
        with ENGINES["flipkart"].lock:
            ENGINES["flipkart"].state["status"] = "idle"

    def test_checkout_quantity_is_set_and_verified(self):
        from bulk_quantity import BulkQuantityError, set_checkout_quantity

        class FakeInput:
            id = "quantity"
            tag_name = "input"
            text = ""

            def __init__(self):
                self.value = "1"

            def is_displayed(self):
                return True

            def get_attribute(self, name):
                return self.value if name == "value" else None

            def clear(self):
                self.value = ""

            def send_keys(self, *values):
                self.value = next(value for value in values if str(value).isdigit())

        class FakeDriver:
            def __init__(self, with_control=True):
                self.quantity = FakeInput()
                self.with_control = with_control

            def find_elements(self, _by, _selector):
                return [self.quantity] if self.with_control else []

            def execute_script(self, *_args):
                return None

        driver = FakeDriver()
        with patch("bulk_quantity.time.sleep"):
            self.assertEqual(set_checkout_quantity(driver, "Amazon", 10), 10)
        self.assertEqual(driver.quantity.value, "10")

        with self.assertRaises(BulkQuantityError):
            set_checkout_quantity(FakeDriver(with_control=False), "Amazon", 2)

        with self.assertRaises(ValueError):
            set_checkout_quantity(driver, "Amazon", 11)

    def test_bulk_quantity_is_routed_to_all_checkout_stores(self):
        from unified_automation import ENGINES

        stores = (
            "amazon",
            "apple",
            "croma",
            "flipkart",
            "jiomart",
            "reliance",
            "samsung",
            "vivo",
        )
        for store in stores:
            with self.subTest(store=store):
                engine = ENGINES[store]
                with engine.lock:
                    engine.state["status"] = "idle"
                payment_method = "cards" if store == "apple" else "cod"
                payload = {
                    "product_name": "Test phone",
                    "payment_method": payment_method,
                    "quantity": 2,
                    "confirm_auto_place": True,
                }
                with patch("unified_automation.threading.Thread") as thread:
                    with patch("unified_automation.get_configured_card", return_value={}):
                        response = self.client.post(f"/api/automation/{store}/start", json=payload)

                self.assertEqual(response.status_code, 202)
                args = thread.call_args.kwargs["args"]
                routed_quantity = args[-2] if store == "flipkart" else args[-1]
                self.assertEqual(routed_quantity, 2)
                with engine.lock:
                    engine.state["status"] = "idle"

    def test_final_action_matching_does_not_confuse_payment_options(self):
        from payment_systems.base_payment import BasePaymentSystem

        class FakeButton:
            def __init__(self, text):
                self.text = text

            def is_displayed(self):
                return True

            def is_enabled(self):
                return True

        class FakeDriver:
            def __init__(self, buttons):
                self.buttons = buttons

            def find_elements(self, _by, _selector):
                return self.buttons

        system = BasePaymentSystem("Store")
        with patch.object(system, "click_element_hard", return_value=True) as click:
            with self.assertRaises(RuntimeError):
                system.click_final_action(FakeDriver([FakeButton("Pay on Delivery")]), ["pay now"])
            self.assertEqual(
                system.click_final_action(FakeDriver([FakeButton("Pay Now ₹1,000")]), ["pay now"]),
                "pay now",
            )
        self.assertEqual(click.call_count, 1)
    def test_order_confirmation_does_not_invent_order_ids_or_match_summaries(self):
        from payment_systems.base_payment import BasePaymentSystem

        class FakeDriver:
            current_url = "https://store.example/checkout"

            def __init__(self, page_source):
                self.page_source = page_source

        with patch("payment_systems.base_payment.time.sleep"):
            with patch("payment_systems.base_payment.time.time", side_effect=[0, 0]):
                confirmed, order_id = BasePaymentSystem("Store").watch_order_confirmation(
                    FakeDriver("<main>Your order has been placed.</main>"),
                    timeout=1,
                )
            with patch("payment_systems.base_payment.time.time", side_effect=[0, 0, 2]):
                summary_confirmed, _ = BasePaymentSystem("Store").watch_order_confirmation(
                    FakeDriver("<main>Order summary and delivery by tomorrow.</main>"),
                    timeout=1,
                )

        self.assertTrue(confirmed)
        self.assertIsNone(order_id)
        self.assertFalse(summary_confirmed)

    def test_production_frontend_is_served_when_built(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        if (DIST_DIR / "index.html").is_file():
            self.assertIn("<div id=\"root\"></div>", response.get_data(as_text=True))
        else:
            self.assertIn("frontend is not built", response.get_data(as_text=True))
        response.close()

    def test_xiaomi_adapter_uses_existing_catalog_without_network(self):
        from scraper_registry import run_scraper

        payload = {
            "query": "All",
            "pages": 1,
            "pincode": "110058",
            "min_price": None,
            "max_price": None,
            "in_stock_only": False,
        }
        products = run_scraper("xiaomi", payload, lambda _progress, _message: None)

        self.assertGreater(len(products), 0)
        self.assertTrue(all(product["_source_brand"] == "xiaomi" for product in products))

    def test_all_registered_scraper_engines_load(self):
        from scraper_registry import SCRAPERS, _load_class

        for slug in SCRAPERS:
            with self.subTest(scraper=slug):
                self.assertTrue(_load_class(slug).__name__)


if __name__ == "__main__":
    unittest.main()
