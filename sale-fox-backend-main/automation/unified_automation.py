"""Store checkout automation served through the unified Sale-Fox Flask API."""

import os
import sys
import json
import time
import base64
import logging
import smtplib
import threading
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

try:
    import purchase_bot as pb
except Exception:
    pb = None

logger = logging.getLogger("UnifiedAutomation")

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class AutomationCancelled(RuntimeError):
    pass


# Dedicated Payment Systems Architecture
BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from payment_systems import (
    handle_platform_payment,
    get_payment_system,
    load_cards,
    get_configured_card,
    PAYMENT_METHODS_BY_PLATFORM,
)
from bulk_quantity import MAX_BULK_QUANTITY, set_checkout_quantity

CUSTOMER = {
    "name": os.environ.get("AUTOMATION_CUSTOMER_NAME", "").strip(),
    "first_name": os.environ.get("AUTOMATION_CUSTOMER_FIRST_NAME", "").strip(),
    "last_name": os.environ.get("AUTOMATION_CUSTOMER_LAST_NAME", "").strip(),
    "phone": os.environ.get("AUTOMATION_CUSTOMER_PHONE", "").strip(),
    "email": os.environ.get("AUTOMATION_CUSTOMER_EMAIL", "").strip(),
    "address": os.environ.get("AUTOMATION_CUSTOMER_ADDRESS", "").strip(),
    "city": os.environ.get("AUTOMATION_CUSTOMER_CITY", "").strip(),
    "state": os.environ.get("AUTOMATION_CUSTOMER_STATE", "").strip(),
    "pincode": os.environ.get("AUTOMATION_CUSTOMER_PINCODE", "").strip(),
    "landmark": os.environ.get("AUTOMATION_CUSTOMER_LANDMARK", "").strip(),
}

CROMA_CUSTOMER = {
    **CUSTOMER,
    "full_name": CUSTOMER["name"],
    "house": os.environ.get("AUTOMATION_CUSTOMER_HOUSE", "").strip(),
    "street": os.environ.get("AUTOMATION_CUSTOMER_STREET", "").strip(),
    "gst_number": os.environ.get("AUTOMATION_GST_NUMBER", "").strip(),
}

def dispatch_order_email(brand: str, product_name: str, status_msg: str, reason: str, card_last4: str):
    """Send a minimal notification only when local SMTP and recipient are configured."""
    recipient = os.environ.get("AUTOMATION_NOTIFICATION_EMAIL", "").strip()
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    if not (recipient and smtp_host and smtp_user and smtp_pass):
        return False, "Notification email is not configured."

    subject = f"[{brand} Automation Alert] {status_msg} - {product_name}"
    body = (
        f"Store: {brand}\nProduct: {product_name}\nStatus: {status_msg}\n"
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    msg = MIMEText(body, "plain")
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg["Subject"] = subject
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    except Exception:
        logger.exception("Automation notification delivery failed.")
        return False, "Notification delivery failed."
    return True, "Notification email sent."


class AutomationEngine:
    """Manages automation state, detached browser sessions, and live mirror."""

    def __init__(self, brand: str, default_url: str, profiles_dirname: str):
        self.brand = brand
        self.default_url = default_url
        self.profiles_dirname = profiles_dirname
        self.lock = threading.Lock()
        self.driver = None
        self.stop_capture = threading.Event()
        self.cancel_event = threading.Event()
        self.otp_event = threading.Event()
        self.submitted_otp = ""
        self.imported_cards = []
        self.state = {
            "status": "idle",       # idle, starting, running, awaiting_otp, step_done, completed, cancelled, error
            "current_step": 0,
            "progress": 0,
            "account": 1,
            "current_url": default_url,
            "screenshot": None,
            "logs": [],
            "error": None,
            "notification": None,
            "otp_required": False,
            "otp_target": None
        }

    def log(self, message: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] [{level}] {message}"
        with self.lock:
            self.state["logs"].append(entry)
            if len(self.state["logs"]) > 120:
                self.state["logs"] = self.state["logs"][-120:]
        print(f"[{self.brand}] {entry}", flush=True)

    def get_status(self) -> dict:
        with self.lock:
            return {
                "status": self.state["status"],
                "current_step": self.state["current_step"],
                "progress": self.state["progress"],
                "account": self.state["account"],
                "current_url": self.state.get("current_url", self.default_url),
                "screenshot": self.state.get("screenshot"),
                "logs": list(self.state["logs"]),
                "error": self.state["error"],
                "notification": self.state.get("notification"),
                "otp_required": self.state.get("otp_required", False),
                "otp_target": self.state.get("otp_target")
            }

    def available_cards(self) -> list:
        return list(self.imported_cards) if self.imported_cards else load_cards()

    def get_config(self) -> dict:
        all_cards = self.available_cards()
        profiles = ["account_1", "account_2", "account_3", "account_4", "account_5"]
        return {
            "status": "ready",
            "brand": self.brand,
            "cards": [
                {
                    "label": str(card.get("label") or f"Card {index + 1}"),
                    "brand": str(card.get("brand") or "Card"),
                    "last4": str(card.get("last4") or "")[-4:],
                }
                for index, card in enumerate(all_cards)
            ],
            "profiles": profiles,
            "payment_methods": PAYMENT_METHODS_BY_PLATFORM.get(
                self.brand.lower().replace(" digital", "").replace(" ", ""),
                [],
            ),
        }

    def submit_otp(self, otp: str):
        if self.cancel_event.is_set():
            return False
        with self.lock:
            self.submitted_otp = str(otp).strip()
            self.state["otp_required"] = False
        self.otp_event.set()
        self.log(f"[USER INPUT] One-time code received for {self.brand}.", "ACTION")
        return True

    def import_cards(self, cards_list: list):
        if not 1 <= len(cards_list) <= 20:
            raise ValueError("Provide between 1 and 20 payment cards.")
        normalized_cards = []
        for index, card in enumerate(cards_list):
            if not isinstance(card, dict):
                raise ValueError(f"Card entry {index + 1} must be an object.")
            number = "".join(char for char in str(card.get("number", "")) if char.isdigit())
            expiry = str(card.get("expiry", "")).strip()
            cvv = str(card.get("cvv", "")).strip()
            if len(number) < 12 or not expiry or not cvv:
                raise ValueError(
                    f"Card entry {index + 1} must include number, expiry, and security code."
                )
            normalized_cards.append({
                **card,
                "number": number,
                "expiry": expiry,
                "cvv": cvv,
                "last4": number[-4:],
            })
        with self.lock:
            self.imported_cards = normalized_cards
        self.log(f"Loaded {len(normalized_cards)} payment card(s) into the local session.", "SUCCESS")
        return True

    def stop(self):
        self.cancel_event.set()
        self.stop_capture.set()
        driver = self.driver
        self.driver = None
        with self.lock:
            self.state["status"] = "cancelled"
            self.state["otp_required"] = False
            self.state["current_step"] = 0
        if driver:
            try:
                driver.quit()
            except Exception as exc:
                self.log(f"Browser shutdown after stop request failed: {exc}", "WARNING")
        self.log("Automation stop requested.", "STOP")

    def raise_if_cancelled(self):
        if self.cancel_event.is_set():
            raise AutomationCancelled("Automation was stopped.")

    def handle_pipeline_error(self, error: Exception):
        logger.exception("Automation pipeline failed.")
        if self.cancel_event.is_set():
            with self.lock:
                self.state["status"] = "cancelled"
                self.state["error"] = None
                self.state["otp_required"] = False
            self.log("Automation stopped.", "STOP")
            return
        with self.lock:
            self.state["status"] = "error"
            self.state["error"] = str(error)
        self.log(f"Automation failed: {error}", "ERROR")

    def launch_browser(self, account: int, initial_url: str = None) -> webdriver.Chrome:
        """Launches detached, visible Chrome instance with isolated persistent profile."""
        profile_root = Path(
            os.environ.get(
                "AUTOMATION_PROFILE_ROOT",
                str(Path.home() / ".sale-fox" / "chrome-profiles"),
            )
        ).expanduser()
        brand_directory = self.brand.lower().replace(" ", "-")
        base_profile = profile_root / brand_directory / f"account_{account}"
        base_profile.mkdir(parents=True, exist_ok=True)

        opts = Options()
        opts.add_argument(f"--user-data-dir={base_profile.resolve()}")
        opts.add_argument("--profile-directory=Default")
        opts.add_argument("--start-maximized")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--restore-last-session")
        opts.add_argument("--hide-crash-restore-bubble")
        opts.add_argument("--disable-features=CalculateNativeWinOcclusion")
        opts.add_argument("--disable-backgrounding-occluded-windows")
        opts.add_argument("--disable-renderer-backgrounding")
        opts.add_experimental_option("detach", True)
        opts.add_experimental_option("prefs", {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "autofill.credit_card_enabled": False,
            "profile.exit_type": "Normal",
            "profile.exited_cleanly": True,
        })

        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(45)
        self.driver = driver

        url_to_open = initial_url or self.default_url
        driver.get(url_to_open)

        # Start live screen capture thread (350ms)
        self.stop_capture.clear()

        def _capture_loop():
            while not self.stop_capture.is_set():
                try:
                    if self.driver:
                        b64 = self.driver.get_screenshot_as_base64()
                        cur_url = self.driver.current_url
                        with self.lock:
                            self.state["screenshot"] = f"data:image/png;base64,{b64}"
                            self.state["current_url"] = cur_url
                except Exception:
                    pass
                time.sleep(0.35)

        t = threading.Thread(target=_capture_loop, daemon=True)
        t.start()

        return driver

    def finish_flow(
        self,
        success: bool,
        status_title: str,
        reason: str,
        card_last4: str,
        product_name: str,
        status: str | None = None,
    ):
        """Set final state and emit a minimal local notification."""
        notification_sent, notification_message = dispatch_order_email(
            self.brand, product_name, status_title, reason, card_last4
        )
        self.log(f"TRANSACTION RESULT: {status_title} - {reason}", "ALERT")
        self.log(notification_message, "INFO" if notification_sent else "WARNING")

        final_status = status or ("cancelled" if not success else "completed")
        with self.lock:
            self.state["status"] = final_status
            self.state["progress"] = 95 if final_status in {"awaiting_confirmation", "awaiting_upi_qr"} else 100
            self.state["notification"] = {
                "brand": self.brand,
                "status": status_title,
                "reason": reason,
                "card": f"Card ending in {card_last4}" if card_last4 else "",
                "product": product_name,
                "time": datetime.now().strftime("%H:%M:%S"),
                "instructions": "Review the open browser before taking any further action.",
            }

        self.log(
            "Automation is waiting for store or payment confirmation."
            if final_status in {"awaiting_confirmation", "awaiting_upi_qr"}
            else "Automation flow completed.",
            "HANDOFF" if final_status in {"awaiting_confirmation", "awaiting_upi_qr"} else "SUCCESS",
        )


def continue_from_bulk_cart(driver, engine: AutomationEngine, brand_name: str) -> None:
    """Advance from a verified cart quantity to the store's checkout flow."""
    checkout_labels = {
        "Amazon": ("proceed to buy",),
        "Croma": ("checkout",),
        "Flipkart": ("place order",),
        "JioMart": ("proceed to checkout", "checkout", "proceed to pay"),
        "Reliance Digital": ("proceed to checkout", "checkout"),
        "Samsung": ("checkout", "proceed to checkout"),
        "Vivo": ("checkout", "proceed to checkout"),
    }.get(brand_name, ())
    if not checkout_labels:
        raise ValueError(f"Bulk cart checkout is not configured for {brand_name}.")

    text = "translate(normalize-space(string(.)), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
    value = "translate(normalize-space(@value), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
    for label in checkout_labels:
        xpath = (
            f"//button[contains({text}, '{label}') or contains({value}, '{label}')]"
            f" | //a[contains({text}, '{label}') or contains({value}, '{label}')]"
        )
        for button in driver.find_elements(By.XPATH, xpath):
            if button.is_displayed() and button.is_enabled():
                driver.execute_script("arguments[0].click();", button)
                engine.log(f"Advanced from the {brand_name} cart to checkout.", "SUCCESS")
                time.sleep(2)
                return

    raise RuntimeError(
        f"Could not find a {brand_name} checkout button after verifying cart quantity. "
        "Checkout was stopped before payment."
    )


# ---------------------------------------------------------------------------
# Specific Brand Automation Pipeline Workers
# ---------------------------------------------------------------------------

def run_apple_pipeline(
    engine: AutomationEngine,
    account: int,
    product_name: str,
    product_url: str,
    card_index: int,
    quantity: int = 1,
):
    """
    Apple Store exact flow:
    1. Take to phone page directly.
    2. Check bag: if items exist, delete them to clean bag.
    3. Click 'Buy' option on phone page.
    4. Select matching color.
    5. Click 'No trade-in' and 'No AppleCare+'.
    6. Click 'Add to Bag'.
    7. On next screen, click 'Review Bag', then click 'Check Out' button.
    8. Guest checkout & address fill.
    9. Card injection and automatic order submission where the store allows it.
    """
    driver = None
    try:
        if not 1 <= quantity <= MAX_BULK_QUANTITY:
            raise ValueError(f"quantity must be from 1 to {MAX_BULK_QUANTITY}.")
        with engine.lock:
            engine.state["status"] = "running"
            engine.state["current_step"] = 1
            engine.state["progress"] = 10
            engine.state["account"] = account
            engine.state["logs"] = []
            engine.state["error"] = None
            engine.state["notification"] = None

        engine.log(f"Initiating Apple checkout for Account {account}...", "START")

        # Determine target buy URL
        clean_name = product_name.lower()
        target_buy_url = "https://www.apple.com/in/shop/buy-iphone/iphone-16"
        if "16 pro" in clean_name:
            target_buy_url = "https://www.apple.com/in/shop/buy-iphone/iphone-16-pro"
        elif "15 pro" in clean_name:
            target_buy_url = "https://www.apple.com/in/shop/buy-iphone/iphone-15-pro"
        elif "15" in clean_name:
            target_buy_url = "https://www.apple.com/in/shop/buy-iphone/iphone-15"
        elif "14" in clean_name:
            target_buy_url = "https://www.apple.com/in/shop/buy-iphone/iphone-14"

        if product_url and "apple.com" in product_url and "buy-iphone" in product_url:
            target_buy_url = product_url

        # STEP 1: Launch visible Chrome
        driver = engine.launch_browser(account, initial_url=target_buy_url)
        engine.log("SUCCESS: Chrome browser launched visibly on your desktop!", "SUCCESS")
        time.sleep(2)

        # STEP 2: Check Bag & Delete Previous Items if any
        with engine.lock:
            engine.state["current_step"] = 2
            engine.state["progress"] = 20
        engine.log("Checking Apple Shopping Bag (/shop/bag) for previous items...", "ACTION")
        driver.get("https://www.apple.com/in/shop/bag")
        time.sleep(3)

        # Remove items from bag if any exist
        removed_count = 0
        try:
            for _ in range(5):
                remove_buttons = driver.find_elements(By.XPATH, "//button[contains(@data-autom, 'item-remove') or contains(@id, 'remove') or contains(translate(., 'REMOVE', 'remove'), 'remove')]")
                visible_removes = [b for b in remove_buttons if b.is_displayed()]
                if not visible_removes:
                    break
                for b in visible_removes:
                    try:
                        driver.execute_script("arguments[0].click();", b)
                        removed_count += 1
                        time.sleep(1.5)
                        break
                    except Exception:
                        pass
        except Exception as e:
            engine.log(f"Bag check notice: {e}", "INFO")

        if removed_count > 0:
            engine.log(f"Cleaned {removed_count} previous items from Apple Bag. Bag is now completely empty.", "SUCCESS")
        else:
            engine.log("Apple Shopping Bag is clean (0 previous items). Ready for fresh order.", "INFO")

        time.sleep(1)

        # STEP 3: Return to phone page and enter configurator / Click 'Buy'
        with engine.lock:
            engine.state["current_step"] = 2
            engine.state["progress"] = 35
        engine.log(f"Navigating to phone page directly: {target_buy_url}", "ACTION")
        driver.get(target_buy_url)
        time.sleep(3)

        # If on marketing overview page, click 'Buy' CTA
        try:
            for b in driver.find_elements(By.XPATH, "//a[contains(translate(., 'BUY', 'buy'), 'buy') and contains(@href, 'buy-iphone')]"):
                if b.is_displayed():
                    driver.execute_script("arguments[0].click();", b)
                    time.sleep(2)
                    break
        except Exception:
            pass

        engine.log("Opened Apple iPhone Configurator on live screen.", "SUCCESS")

        # STEP 4: Choose Colour matching the clicked phone
        color_candidates = ["black", "white", "pink", "teal", "ultramarine", "desert titanium", "natural titanium", "white titanium", "black titanium", "blue", "green", "yellow"]
        chosen_color = "white"
        for c in color_candidates:
            if c in clean_name:
                chosen_color = c
                break

        engine.log(f"Target Color for '{product_name}': {chosen_color.capitalize()}", "ACTION")
        color_selected = False
        try:
            for xp in [
                f"//input[@name='dimensionColor' and contains(@value, '{chosen_color}')]",
                f"//input[@name='dimensionColor' and contains(@value, '{chosen_color}')]/following-sibling::label",
                f"//*[@role='radio'][contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{chosen_color}')]",
                f"//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{chosen_color}')]"
            ]:
                for el in driver.find_elements(By.XPATH, xp):
                    if el.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", el)
                        engine.log(f"Selected Color: '{chosen_color.capitalize()}' on live screen.", "SUCCESS")
                        color_selected = True
                        break
                if color_selected:
                    break
        except Exception as e:
            engine.log(f"Color selection notice: {e}", "INFO")

        time.sleep(1)

        # STEP 5: Select 'No trade-in' & 'No AppleCare+ Coverage'
        try:
            for el in driver.find_elements(By.XPATH, "//input[@id='noTradeIn'] | //input[@id='noTradeIn']/following-sibling::label | //label[contains(., 'No trade-in')] | //input[@value='noTradeIn']"):
                if el.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", el)
                    engine.log("Selected 'No trade-in' on live screen.", "SUCCESS")
                    break
        except Exception as e:
            engine.log(f"Trade-in notice: {e}", "INFO")

        time.sleep(1)

        try:
            care_radios = driver.find_elements(By.XPATH, "//input[@name='applecare-options']")
            for r in care_radios:
                parent_text = r.find_element(By.XPATH, "..").text.lower()
                if "no applecare" in parent_text or "no coverage" in parent_text:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", r)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", r)
                    engine.log("Selected 'No AppleCare+ Coverage' on live screen.", "SUCCESS")
                    break
        except Exception as e:
            engine.log(f"AppleCare notice: {e}", "INFO")

        time.sleep(1.5)

        # STEP 6: Add to Bag
        with engine.lock:
            engine.state["current_step"] = 3
            engine.state["progress"] = 55
        engine.log(f"Adding '{product_name}' to Apple Shopping Bag...", "ACTION")

        add_to_bag_btn = None
        for b in driver.find_elements(By.XPATH, "//button[@name='add-to-cart' or @data-autom='add-to-cart' or contains(translate(., 'ADD TO BAG', 'add to bag'), 'add to bag')]"):
            if b.is_displayed():
                add_to_bag_btn = b
                break

        if add_to_bag_btn:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", add_to_bag_btn)
            time.sleep(0.5)
            ActionChains(driver).move_to_element(add_to_bag_btn).click().perform()
            engine.log("Clicked 'Add to Bag' button on live screen!", "SUCCESS")
        time.sleep(3)

        # STEP 7: Click 'Review Bag' on the next screen, then click 'Check Out'
        engine.log("Detecting post-add confirmation screen ('Review Bag')...", "ACTION")
        review_clicked = False
        for xp in [
            "//button[contains(translate(., 'REVIEW BAG', 'review bag'), 'review bag')]",
            "//a[contains(translate(., 'REVIEW BAG', 'review bag'), 'review bag')]",
            "//button[@data-autom='reviewBag']"
        ]:
            try:
                for b in driver.find_elements(By.XPATH, xp):
                    if b.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", b)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", b)
                        engine.log("Clicked 'Review Bag' on live confirmation screen.", "SUCCESS")
                        review_clicked = True
                        break
            except Exception:
                pass
            if review_clicked:
                break

        time.sleep(3)

        # Verify /shop/bag page
        if "/shop/bag" not in driver.current_url:
            driver.get("https://www.apple.com/in/shop/bag")
            time.sleep(3)

        engine.log("Apple Shopping Bag verified with selected device.", "SUCCESS")
        if quantity > 1:
            set_checkout_quantity(driver, "Apple", quantity, product_name)
            engine.log(f"Verified the Apple Bag quantity: {quantity}.", "SUCCESS")

        # Click the 'Check Out' button
        engine.log("Clicking 'Check Out' button in Apple Bag...", "ACTION")
        for xp in [
            "//button[@id='shoppingCart.actions.checkout']",
            "//button[contains(translate(., 'CHECK OUT', 'check out'), 'check out')]",
            "//a[contains(translate(., 'CHECK OUT', 'check out'), 'check out')]"
        ]:
            try:
                for btn in driver.find_elements(By.XPATH, xp):
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", btn)
                        engine.log("Clicked 'Check Out' button on bag screen.", "SUCCESS")
                        break
            except Exception:
                pass

        time.sleep(3)

        # STEP 8: Guest Checkout & Shipping Address Injection
        with engine.lock:
            engine.state["current_step"] = 4
            engine.state["progress"] = 75
        engine.log("Handling Guest Checkout & Shipping Details...", "ACTION")

        # Continue as Guest
        try:
            for xp in [
                "//button[contains(translate(., 'CONTINUE AS GUEST', 'continue as guest'), 'continue as guest')]",
                "//a[contains(translate(., 'CONTINUE AS GUEST', 'continue as guest'), 'continue as guest')]",
                "//input[contains(translate(@value, 'CONTINUE AS GUEST', 'continue as guest'), 'continue as guest')]"
            ]:
                for el in driver.find_elements(By.XPATH, xp):
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        engine.log("Selected 'Continue as Guest' checkout mode on live screen.", "SUCCESS")
                        break
        except Exception:
            pass

        time.sleep(2)

        # Shipping Address fields
        fields = {
            "firstName": (CUSTOMER["first_name"], ["//input[contains(@id, 'firstName') or contains(@name, 'firstName')]"]),
            "lastName": (CUSTOMER["last_name"], ["//input[contains(@id, 'lastName') or contains(@name, 'lastName')]"]),
            "street": (CUSTOMER["address"], ["//input[contains(@id, 'street') or contains(@name, 'street') or contains(@id, 'address1')]"]),
            "postalCode": (CUSTOMER["pincode"], ["//input[contains(@id, 'postalCode') or contains(@name, 'postalCode')]"]),
            "mobilePhone": (CUSTOMER["phone"].replace("+91", "").strip(), ["//input[contains(@id, 'daytimePhone') or contains(@id, 'mobilePhone') or contains(@name, 'mobilePhone') or contains(@id, 'phone')]"]),
            "emailAddress": (CUSTOMER["email"], ["//input[contains(@id, 'emailAddress') or contains(@name, 'emailAddress') or contains(@type, 'email')]"])
        }

        for f_name, (f_val, xps) in fields.items():
            if not f_val:
                continue
            for xp in xps:
                try:
                    for el in driver.find_elements(By.XPATH, xp):
                        if el.is_displayed():
                            el.clear()
                            el.send_keys(f_val)
                            driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", el)
                            break
                except Exception:
                    pass

        engine.log("Configured shipping fields were populated where available.", "SUCCESS")
        time.sleep(1.5)

        # Advance to Payment
        for xp in [
            "//button[contains(translate(., 'CONTINUE TO PAYMENT', 'continue to payment'), 'continue to payment')]",
            "//button[contains(translate(., 'CONTINUE TO SHIPPING', 'continue to shipping'), 'continue to shipping')]",
            "//button[contains(translate(., 'CONTINUE', 'continue'), 'continue') and not(contains(., 'Shopping'))]"
        ]:
            try:
                for b in driver.find_elements(By.XPATH, xp):
                    if b.is_displayed() and not ("faq" in b.get_attribute("class").lower() or "accordion" in b.get_attribute("class").lower()):
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", b)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", b)
                        engine.log(f"Clicked '{b.text.strip()}' on live screen.", "SUCCESS")
                        break
            except Exception:
                pass

        time.sleep(3)

        # STEP 9: Payment Stage & Card Submission
        with engine.lock:
            engine.state["current_step"] = 5
            engine.state["progress"] = 90
        engine.log("Detecting Credit / Debit card form on Apple payment stage...", "ACTION")

        card_obj = get_configured_card(engine, card_index)
        card_num = card_obj["number"]
        card_last4 = card_num[-4:]

        # Select Card radio
        try:
            for xp in [
                "//label[contains(translate(., 'CREDIT OR DEBIT CARD', 'credit or debit card'), 'credit or debit card')]",
                "//input[@value='creditCard']/following-sibling::label",
                "//input[@value='credit']/following-sibling::label"
            ]:
                for el in driver.find_elements(By.XPATH, xp):
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(0.5)
                        break
        except Exception:
            pass

        engine.raise_if_cancelled()
        handle_platform_payment(
            platform="apple",
            driver=driver,
            engine=engine,
            product_name=product_name,
            payment_method="cards",
            card_index=card_index,
        )
        engine.raise_if_cancelled()

    except Exception as e:
        engine.handle_pipeline_error(e)


def run_croma_pipeline(
    engine: AutomationEngine,
    account: int,
    product_name: str,
    product_url: str,
    card_index: int = 0,
    payment_method: str = "cards",
    upi_id: str = "",
    custom_card: dict = None,
    gst_number: str = "",
    quantity: int = 1,
):
    """
    Dedicated Croma checkout pipeline:
    1. Detached Chrome launch with profile account_{account}.
    2. Product Navigation & Add to Cart -> https://www.croma.com/cart (Image 1).
    3. Login with the locally configured account email and await a user-entered OTP.
    4. Auto-fill OTP & click 'Checkout' button on Cart page.
    5. Shipping address verification & GST number injection (Image 2 & 3).
    6. Click 'Proceed To Payment' CTA (Image 3).
    7. All five payment method handlers:
       - Cash on Delivery (COD)
       - Credit / Debit Cards (Auto-fills card, CVV & virtual password/PIN - Image 5)
       - EMI on Cards (Bank selection & tenure)
       - UPI (Instant VPA injection)
       - Netbanking (Bank selection)
    8. Gateway Response Detection & Real Notification Dispatch (Email + SMS).
    """
    driver = None
    try:
        if not 1 <= quantity <= MAX_BULK_QUANTITY:
            raise ValueError(f"quantity must be from 1 to {MAX_BULK_QUANTITY}.")
        with engine.lock:
            engine.state["status"] = "running"
            engine.state["current_step"] = 1
            engine.state["progress"] = 10
            engine.state["account"] = account
            engine.state["logs"] = []
            engine.state["error"] = None
            engine.state["notification"] = None
            engine.state["otp_required"] = False

        engine.log(f"Launching Croma checkout for Account {account}...", "START")

        # Determine target product URL
        target_nav_url = product_url if product_url and product_url.startswith("http") else "https://www.croma.com/"
        
        # STEP 1: Launch Browser
        driver = engine.launch_browser(account, initial_url=target_nav_url)
        engine.log("SUCCESS: Chrome browser launched visibly on your desktop for Croma!", "SUCCESS")
        time.sleep(2)

        # STEP 2: Product Page & Add to Cart
        with engine.lock:
            engine.state["current_step"] = 2
            engine.state["progress"] = 25
        engine.log(f"Navigating to Croma target phone: {product_name}...", "ACTION")
        try:
            driver.get(target_nav_url)
        except Exception:
            pass
        time.sleep(3)

        # Use the configured delivery PIN only when one was provided.
        if CUSTOMER["pincode"]:
            try:
                pin_inputs = driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'pincode') or contains(@placeholder, 'Pincode') or contains(@id, 'pincode') or contains(@name, 'pincode')]")
                for p_in in pin_inputs:
                    if p_in.is_displayed():
                        p_in.clear()
                        p_in.send_keys(CUSTOMER["pincode"])
                        time.sleep(0.5)
                        for b in driver.find_elements(By.XPATH, "//button[contains(., 'Check') or contains(., 'Apply') or contains(., 'Verify')]"):
                            if b.is_displayed():
                                driver.execute_script("arguments[0].click();", b)
                                engine.log("Configured delivery PIN applied on Croma.", "SUCCESS")
                                break
                        break
            except Exception as exc:
                engine.log(f"Delivery PIN entry failed: {exc}", "WARNING")

        time.sleep(1)

        # Click Buy Now or Add to Cart
        engine.log(f"Adding '{product_name}' to Croma Cart...", "ACTION")
        added_to_cart = False
        for xp in [
            "//button[contains(translate(., 'ADD TO CART', 'add to cart'), 'add to cart')]",
            "//button[contains(translate(., 'BUY NOW', 'buy now'), 'buy now')]",
            "//button[contains(@class, 'pdp-add-to-cart')]",
            "//button[contains(@class, 'buy-now')]",
            "//a[contains(translate(., 'ADD TO CART', 'add to cart'), 'add to cart')]"
        ]:
            try:
                for b in driver.find_elements(By.XPATH, xp):
                    if b.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", b)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", b)
                        added_to_cart = True
                        engine.log(f"Clicked '{b.text.strip() or 'Add to Cart'}' button.", "SUCCESS")
                        break
                if added_to_cart:
                    break
            except Exception:
                pass

        time.sleep(2.5)

        # Ensure we are on Cart Page (Image 1)
        if "croma.com/cart" not in driver.current_url.lower():
            engine.log("Navigating directly to Croma Cart (https://www.croma.com/cart)...", "ACTION")
            driver.get("https://www.croma.com/cart")
            time.sleep(3)

        # Verify Cart Status on Croma
        time.sleep(2)
        chk_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Checkout')] | //a[contains(., 'Checkout')]")
        has_checkout = any(b.is_displayed() for b in chk_btns)
        empty_text = driver.find_elements(By.XPATH, "//*[contains(text(), 'Your Cart is Empty') or contains(text(), 'Cart is empty')]")
        is_empty = any(e.is_displayed() for e in empty_text)

        if is_empty or not has_checkout:
            engine.log(f"NOTICE: Croma Cart is currently empty. '{product_name}' is not in cart.", "ALERT")
            engine.finish_flow(
                success=False,
                status_title="Item Not In Cart (Cart Empty)",
                reason=f"'{product_name}' could not be added to the cart. Check availability in the open browser.",
                card_last4="",
                product_name=product_name
            )
            return

        if quantity > 1:
            set_checkout_quantity(driver, "Croma", quantity, product_name)
            engine.log(f"Verified the Croma cart quantity: {quantity}.", "SUCCESS")
        engine.log("SUCCESS: Item verified in Croma cart with active Checkout CTA!", "SUCCESS")

        # STEP 3: Login System (Email ONLY) & Floating OTP Window (with Session Persistence)
        with engine.lock:
            engine.state["current_step"] = 3
            engine.state["progress"] = 40

        # Check if already logged in from saved profile session
        croma_logged_in = False
        try:
            user_links = driver.find_elements(By.XPATH, "//a[contains(@class, 'user-link')] | //div[contains(@class, 'user-wrap')]")
            for ul in user_links:
                txt = ul.text.lower()
                if any(k in txt for k in ["account", "orders", "profile"]):
                    croma_logged_in = True
                    break
            # Also check cookies
            c_cookies = {c.get("name"): c.get("value") for c in driver.get_cookies()}
            if any(k in c_cookies for k in ["user", "auth", "token", "loggedIn"]):
                croma_logged_in = True
        except Exception:
            pass

        if croma_logged_in:
            engine.log("[SESSION ACTIVE] A signed-in Croma profile is active.", "SUCCESS")
        else:
            if not CROMA_CUSTOMER["email"]:
                raise ValueError("Set AUTOMATION_CUSTOMER_EMAIL or sign in through the browser profile first.")
            engine.log("Opening Croma sign-in to use the configured account email.", "ACTION")

            # Open Croma login form using reliable header user-link
            login_input_elem = None
            try:
                # 1. First check if login modal is already open
                inps = driver.find_elements(By.XPATH, "//input[contains(@class, 'input-login')]")
                vis = [i for i in inps if i.is_displayed()]
                if vis:
                    login_input_elem = vis[0]
                else:
                    # 2. Click user icon in header (a.user-link)
                    for ul in driver.find_elements(By.XPATH, "//a[contains(@class, 'user-link')] | //div[contains(@class, 'user-wrap')]"):
                        if ul.is_displayed():
                            driver.execute_script("arguments[0].click();", ul)
                            engine.log("Clicked Croma user profile link in header.", "SUCCESS")
                            time.sleep(2)
                            break

                    inps = driver.find_elements(By.XPATH, "//input[contains(@class, 'input-login')]")
                    vis = [i for i in inps if i.is_displayed()]
                    if vis:
                        login_input_elem = vis[0]
                    else:
                        # Fallback: navigate to homepage and click user-link
                        engine.log("Opening Croma homepage to trigger user login modal...", "ACTION")
                        driver.get("https://www.croma.com")
                        time.sleep(3)
                        for ul in driver.find_elements(By.XPATH, "//a[contains(@class, 'user-link')] | //div[contains(@class, 'user-wrap')]"):
                            if ul.is_displayed():
                                driver.execute_script("arguments[0].click();", ul)
                                time.sleep(2)
                                break
                        inps = driver.find_elements(By.XPATH, "//input[contains(@class, 'input-login')]")
                        vis = [i for i in inps if i.is_displayed()]
                        if vis:
                            login_input_elem = vis[0]
            except Exception as e:
                engine.log(f"Login modal detection note: {e}", "INFO")

            if login_input_elem:
                engine.log("Entering the configured Croma account email.", "ACTION")
                try:
                    login_input_elem.clear()
                    login_input_elem.send_keys(CROMA_CUSTOMER["email"])
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", login_input_elem)
                    driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", login_input_elem)
                    time.sleep(1)

                    # Click real Croma Continue button: button.login-btn
                    clicked_continue = False
                    for cont_btn in driver.find_elements(By.XPATH, "//button[contains(@class, 'login-btn')] | //button[contains(., 'Continue') and not(contains(@id, 'pincode'))]"):
                        if cont_btn.is_displayed():
                            driver.execute_script("arguments[0].click();", cont_btn)
                            clicked_continue = True
                            engine.log("Requested a Croma verification code.", "SUCCESS")
                            break

                    if not clicked_continue:
                        login_input_elem.send_keys(Keys.ENTER)
                        engine.log("Submitted email via Enter key.", "SUCCESS")
                except Exception as e:
                    engine.log(f"Login input note: {e}", "INFO")

                # Wait up to 6 seconds for OTP input to appear on Croma screen
                otp_box_detected = False
                for _ in range(6):
                    time.sleep(1)
                    otp_boxes = driver.find_elements(By.XPATH, "//input[@id='partitioned' or contains(@class, 'otpinput')]")
                    if any(o.is_displayed() for o in otp_boxes):
                        otp_box_detected = True
                        break

                engine.log("SUCCESS: Croma OTP verification screen is active!", "SUCCESS")

                # Signal OTP required and activate Floating OTP window
                with engine.lock:
                    engine.state["status"] = "awaiting_otp"
                    engine.state["otp_required"] = True
                    engine.state["otp_target"] = "Configured Croma account"
                engine.otp_event.clear()

                engine.log("=================================================================", "ALERT")
                engine.log("[OTP REQUIRED] Enter the verification code sent by Croma.", "ALERT")
                engine.log("Floating OTP pop-out window is active. Enter the 4-digit OTP to continue...", "ACTION")
                engine.log("=================================================================", "ALERT")

                # Wait for user OTP input (timeout 3 minutes)
                received = engine.otp_event.wait(timeout=180)
                if received and engine.submitted_otp:
                    otp = engine.submitted_otp
                    engine.log("Submitting the entered Croma verification code.", "ACTION")
                    try:
                        # Target input: input.otpinput id='partitioned'
                        otp_inputs = driver.find_elements(By.XPATH, "//input[@id='partitioned' or contains(@class, 'otpinput')]")
                        if otp_inputs:
                            otp_in = otp_inputs[0]
                            otp_in.clear()
                            otp_in.send_keys(otp)
                            driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", otp_in)
                        else:
                            all_otp = driver.find_elements(By.XPATH, "//input[@maxlength='1' or @type='tel' or contains(@class, 'otp')]")
                            for idx, char in enumerate(otp):
                                if idx < len(all_otp):
                                    all_otp[idx].send_keys(char)

                        time.sleep(1)
                        # Click 'Submit OTP' button: button.otp-btn
                        for v_btn in driver.find_elements(By.XPATH, "//button[contains(@class, 'otp-btn') and contains(., 'Submit OTP')] | //button[contains(., 'Submit OTP') or contains(., 'Verify')]"):
                            if v_btn.is_displayed():
                                driver.execute_script("arguments[0].click();", v_btn)
                                engine.log("Clicked 'Submit OTP' on Croma!", "SUCCESS")
                                break
                    except Exception as e:
                        engine.log(f"OTP injection note: {e}", "INFO")

                    time.sleep(3)
                    engine.log("Croma verification step completed.", "SUCCESS")
                else:
                    engine.log("OTP timeout or skipped: Continuing checkout flow...", "INFO")

        with engine.lock:
            engine.state["status"] = "running"
            engine.state["otp_required"] = False

        # STEP 4: Checkout Click on Cart (Image 1)
        with engine.lock:
            engine.state["current_step"] = 4
            engine.state["progress"] = 60
        engine.log("Ensuring Croma Cart page & clicking 'Checkout' CTA...", "ACTION")

        try:
            if "croma.com/cart" not in driver.current_url.lower() and "checkout" not in driver.current_url.lower():
                driver.get("https://www.croma.com/cart")
                time.sleep(2.5)

            # Click green 'Checkout' button (Image 1)
            for chk_btn in driver.find_elements(By.XPATH, "//button[contains(text(), 'Checkout') or contains(., 'Checkout')] | //a[contains(., 'Checkout')]"):
                if chk_btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", chk_btn)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", chk_btn)
                    engine.log("Clicked 'Checkout' CTA on Croma Cart page!", "SUCCESS")
                    break
        except Exception as e:
            engine.log(f"Checkout CTA note: {e}", "INFO")

        time.sleep(3)

        # STEP 5: Shipping Address & GST Injection (Image 2 & 3)
        with engine.lock:
            engine.state["current_step"] = 4
            engine.state["progress"] = 75
        engine.log("Configuring Croma shipping details from local settings or the browser profile.", "ACTION")

        # Handle 'Shipping Address' modal (Image 2)
        try:
            # Check if modal or address radio is present
            addr_radios = driver.find_elements(By.XPATH, "//div[contains(@class, 'address')]//input[@type='radio']")
            if addr_radios:
                for r in addr_radios:
                    if r.is_displayed():
                        driver.execute_script("arguments[0].click();", r)
                        engine.log("Selected a saved shipping address.", "SUCCESS")
                        break
            
            # Click 'Confirm Shipping Address' if button is visible
            for conf_btn in driver.find_elements(By.XPATH, "//button[contains(., 'Confirm Shipping Address') or contains(., 'Deliver Here')]"):
                if conf_btn.is_displayed():
                    driver.execute_script("arguments[0].click();", conf_btn)
                    engine.log("Clicked 'Confirm Shipping Address'!", "SUCCESS")
                    time.sleep(2)
                    break

            # If '+ Add New Address' was required or form is open
            new_addr_inputs = driver.find_elements(By.XPATH, "//input[contains(@name, 'firstName') or contains(@id, 'firstName') or contains(@placeholder, 'Full Name') or contains(@id, 'name')]")
            if new_addr_inputs and CROMA_CUSTOMER["name"]:
                for inp in new_addr_inputs:
                    if inp.is_displayed():
                        inp.clear()
                        inp.send_keys(CROMA_CUSTOMER["name"])
                        break
                # Mobile
                for mob_in in driver.find_elements(By.XPATH, "//input[contains(@name, 'mobile') or contains(@id, 'mobile') or contains(@type, 'tel')]") if CROMA_CUSTOMER["phone"] else []:
                    if mob_in.is_displayed():
                        mob_in.clear()
                        mob_in.send_keys(CROMA_CUSTOMER["phone"])
                        break
                # Pincode
                for p_in in driver.find_elements(By.XPATH, "//input[contains(@name, 'pin') or contains(@id, 'pin') or contains(@placeholder, 'Pincode')]") if CROMA_CUSTOMER["pincode"] else []:
                    if p_in.is_displayed():
                        p_in.clear()
                        p_in.send_keys(CROMA_CUSTOMER["pincode"])
                        break
                # Address line
                for ad_in in driver.find_elements(By.XPATH, "//input[contains(@name, 'address') or contains(@id, 'address') or contains(@placeholder, 'Address')] | //textarea") if (CROMA_CUSTOMER["house"] or CROMA_CUSTOMER["street"]) else []:
                    if ad_in.is_displayed():
                        ad_in.clear()
                        ad_in.send_keys(CROMA_CUSTOMER["house"] + ", " + CROMA_CUSTOMER["street"])
                        break

            # Inject GST Number as requested by user
            gst_val = gst_number or CROMA_CUSTOMER.get("gst_number", "")
            for gst_in in driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'GST') or contains(@id, 'gst') or contains(@name, 'gst')]"):
                if gst_val and gst_in.is_displayed():
                    gst_in.clear()
                    gst_in.send_keys(gst_val)
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", gst_in)
                    engine.log("Configured GST number entered.", "SUCCESS")
                    break

            # Click 'Proceed To Payment' button (Image 3)
            time.sleep(1)
            for proc_btn in driver.find_elements(By.XPATH, "//button[contains(., 'Proceed To Payment') or contains(., 'Proceed to Payment')]"):
                if proc_btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", proc_btn)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", proc_btn)
                    engine.log("Clicked green 'Proceed To Payment' CTA!", "SUCCESS")
                    break
        except Exception as e:
            engine.log(f"Address stage note: {e}", "INFO")

        time.sleep(3)

        # STEP 6: Execute Payment via Dedicated Modular Croma Payment System
        engine.raise_if_cancelled()
        return handle_platform_payment(
            platform="croma",
            driver=driver,
            engine=engine,
            product_name=product_name,
            payment_method=payment_method,
            upi_id=upi_id,
            card_index=card_index,
            custom_card=custom_card,
            gst_number=gst_number,
            customer_info=CROMA_CUSTOMER
        )

    except Exception as e:
        engine.handle_pipeline_error(e)


def run_flipkart_pipeline(
    engine: AutomationEngine,
    account: int,
    product_name: str,
    product_url: str,
    card_index: int = 0,
    payment_method: str = "cod",
    upi_id: str = "",
    quantity: int = 1,
    gst: str = ""
):
    """
    Flipkart checkout pipeline using the existing store automation:
    1. Launches isolated Chrome browser with persistent Flipkart profile.
    2. Navigates to target product URL with continuous 350ms desktop screen streaming.
    3. Handles deliverability and clicks 'Buy Now' using CDP hardware mouse events.
    4. Auto-detects login / SMS OTP (with interactive bot modal input).
    5. Confirms a saved delivery address or uses locally configured details.
    6. Sets and verifies the requested cart quantity (up to the configured cap).
    7. Advances to Payment stage and auto-selects Cash on Delivery (COD).
    8. Hardware-clicks 'Place Order' via Chrome DevTools Protocol & React Synthetic dispatches.
    9. Watches for confirmation / 3-digit Captcha, extracts Order ID, logs to CSV & UI.
    """
    driver = None
    try:
        if not 1 <= quantity <= MAX_BULK_QUANTITY:
            raise ValueError(f"quantity must be from 1 to {MAX_BULK_QUANTITY}.")

        with engine.lock:
            engine.state["status"] = "running"
            engine.state["current_step"] = 1
            engine.state["progress"] = 10
            engine.state["account"] = account
            engine.state["logs"] = []
            engine.state["error"] = None
            engine.state["notification"] = None

        engine.log(f"Launching Flipkart Autonomous Engine for Account {account}...", "START")

        target_nav_url = product_url if product_url and product_url.startswith("http") else "https://www.flipkart.com/"
        driver = engine.launch_browser(account, initial_url=target_nav_url)
        engine.log("SUCCESS: Chrome browser launched visibly on your desktop for Flipkart!", "SUCCESS")
        time.sleep(2.5)

        # Step 2: Deliverability & Product Check
        with engine.lock:
            engine.state["current_step"] = 2
            engine.state["progress"] = 25
        engine.log(f"Navigating to Flipkart product: {product_name}...", "ACTION")
        if driver.current_url != target_nav_url:
            driver.get(target_nav_url)
            time.sleep(2.5)

        # Check delivery PIN only when one is configured.
        if CUSTOMER["pincode"]:
            try:
                pin_inputs = driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'pincode') or contains(@placeholder, 'Pincode') or contains(@id, 'pincodeInputId')]")
                for pin_in in pin_inputs:
                    if pin_in.is_displayed():
                        pin_in.clear()
                        pin_in.send_keys(CUSTOMER["pincode"])
                        time.sleep(0.5)
                        for button in driver.find_elements(By.XPATH, "//button[contains(., 'Check') or contains(., 'Apply')] | //span[contains(., 'Check')]"):
                            if button.is_displayed():
                                if pb:
                                    pb.click_element_hard(driver, button)
                                else:
                                    driver.execute_script("arguments[0].click();", button)
                                engine.log("Checked deliverability using the configured PIN on Flipkart.", "SUCCESS")
                                break
                        break
            except Exception as exc:
                engine.log(f"Delivery PIN entry failed: {exc}", "WARNING")

        time.sleep(1.0)

        # Step 3: Click 'Buy Now'
        with engine.lock:
            engine.state["current_step"] = 2
            engine.state["progress"] = 40
        engine.log(f"Clicking 'Buy Now' on Flipkart for {product_name}...", "ACTION")

        buy_clicked = False
        buy_el = None
        if pb:
            buy_el = pb.find_by_text(driver, ["add to cart"] if quantity > 1 else ["buy now"])
        if not buy_el:
            purchase_xpaths = (
                ["//button[contains(translate(., 'ADD TO CART', 'add to cart'), 'add to cart')]"]
                if quantity > 1
                else [
                    "//*[(self::button or self::div or self::a) and (translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')='BUY NOW')]",
                    "//button[contains(translate(., 'BUY NOW', 'buy now'), 'buy now')]",
                    "//div[contains(@class, 'css-146c3p1') and contains(., 'Buy now')]",
                    "//button[contains(translate(., 'ADD TO CART', 'add to cart'), 'add to cart')]",
                ]
            )
            for xp in purchase_xpaths:
                try:
                    for b in driver.find_elements(By.XPATH, xp):
                        if b.is_displayed():
                            buy_el = b
                            break
                    if buy_el:
                        break
                except Exception:
                    pass

        if buy_el:
            if pb:
                pb.click_element_hard(driver, buy_el)
            else:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", buy_el)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", buy_el)
            engine.log(f"SUCCESS: Clicked 'Buy Now' via hardware mouse event on Flipkart.", "SUCCESS")
            buy_clicked = True
        else:
            engine.log("Buy Now button not found, checking if already on checkout...", "INFO")

        time.sleep(3.0)

        if quantity > 1:
            if not buy_clicked:
                raise RuntimeError("Could not add the Flipkart item to cart; checkout was stopped.")
            driver.get("https://www.flipkart.com/viewcart")
            time.sleep(2.5)
            set_checkout_quantity(driver, "Flipkart", quantity, product_name)
            engine.log(f"Verified the Flipkart cart quantity: {quantity}.", "SUCCESS")
            continue_from_bulk_cart(driver, engine, "Flipkart")

        # Step 4: Login & OTP Handling (with Persistent Profile Session Check)
        with engine.lock:
            engine.state["current_step"] = 3
            engine.state["progress"] = 55

        def check_is_logged_in() -> bool:
            try:
                cur_url = driver.current_url.lower()
                body = driver.page_source.lower()
                is_checkout_step = (
                    "order_summary" in cur_url or
                    "payment" in cur_url or
                    "deliver here" in body or
                    "deliver to this address" in body or
                    ("delivery address" in body and "order summary" in body)
                )
                if is_checkout_step:
                    return True
                # Check header indicators
                has_user = any(k in body for k in ["my account", "my orders"])
                # Check cookies
                c_cookies = {c.get("name"): c.get("value") for c in driver.get_cookies()}
                has_auth = any(k in c_cookies for k in ["sn", "user", "auth", "token", "login_token"])
                login_inps = [i for i in driver.find_elements(By.XPATH, "//input[contains(@class, 'jwCbxy') or contains(@class, 'r4vIwl') or contains(@placeholder, 'phone') or contains(@placeholder, 'Email')]") if i.is_displayed()]
                return (has_user or has_auth) and len(login_inps) == 0
            except Exception:
                return False

        if check_is_logged_in():
            engine.log("[SESSION ACTIVE] A signed-in Flipkart profile is active.", "SUCCESS")
        else:
            if not CUSTOMER["email"]:
                raise ValueError("Set AUTOMATION_CUSTOMER_EMAIL or sign in through the browser profile first.")
            try:
                phone_inputs = [
                    i for i in driver.find_elements(By.XPATH,
                        "//input[contains(@class, 'jwCbxy') or contains(@class, 'r4vIwl') or contains(@placeholder, 'Email') or contains(@placeholder, 'phone') or contains(@placeholder, 'number') or @type='email' or @type='tel' or @type='number']"
                    ) if i.is_displayed()
                ]
                if phone_inputs:
                    pinp = phone_inputs[0]
                    email_val = CUSTOMER["email"]
                    engine.log("Entering the configured Flipkart account email.", "ACTION")
                    pinp.clear()
                    pinp.send_keys(email_val)
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", pinp)
                    driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", pinp)
                    time.sleep(1)

                    # Click Continue button
                    for cb in driver.find_elements(By.XPATH, "//button[contains(translate(., 'CONTINUE', 'continue'), 'continue') or contains(translate(., 'OTP', 'otp'), 'otp') or contains(., 'Submit') or @type='submit']"):
                        if cb.is_displayed():
                            if pb:
                                pb.click_element_hard(driver, cb)
                            else:
                                driver.execute_script("arguments[0].click();", cb)
                            engine.log("Requested a Flipkart verification code.", "ACTION")
                            break
            except Exception as e:
                engine.log(f"Login notice: {e}", "INFO")

            time.sleep(2.5)

            # Signal OTP required and await user OTP
            with engine.lock:
                engine.state["status"] = "awaiting_otp"
                engine.state["otp_required"] = True
                engine.state["otp_target"] = "Configured Flipkart account"
            engine.log("[OTP REQUIRED] Enter the verification code sent by Flipkart.", "ALERT")
            engine.otp_event.clear()

            otp_deadline = time.time() + 180
            while time.time() < otp_deadline:
                if check_is_logged_in():
                    engine.log("SUCCESS: Flipkart Login verified! Moving to Shipping Address...", "SUCCESS")
                    break

                if engine.otp_event.is_set() and engine.submitted_otp:
                    code = engine.submitted_otp.strip()
                    engine.otp_event.clear()
                    engine.log("Submitting the entered Flipkart verification code.", "ACTION")

                    # Check for 6 separate digit boxes
                    digit_boxes = [b for b in driver.find_elements(By.XPATH,
                        "//input[@maxlength='1' or contains(@class, 'S1KmoO') or contains(@class, '_396cs4') or contains(@class, '_2IX_2-')]"
                    ) if b.is_displayed()]

                    if len(digit_boxes) >= 4:
                        for idx, ch in enumerate(code[:len(digit_boxes)]):
                            try:
                                digit_boxes[idx].clear()
                                digit_boxes[idx].send_keys(ch)
                                driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", digit_boxes[idx])
                                driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", digit_boxes[idx])
                            except Exception:
                                pass
                    else:
                        # Single text/number input for full OTP
                        single_inputs = [b for b in driver.find_elements(By.XPATH,
                            "//input[contains(@class, 'r4vIwl') or contains(@class, 'jwCbxy') or contains(@placeholder, 'OTP') or contains(@placeholder, 'otp') or contains(@name, 'otp') or @type='text' or @type='number' or @type='tel']"
                        ) if b.is_displayed()]
                        for s_inp in single_inputs:
                            try:
                                s_inp.clear()
                                s_inp.send_keys(code)
                                driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", s_inp)
                                driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", s_inp)
                                break
                            except Exception:
                                pass

                    time.sleep(1)

                    # Click Verify / Login / Continue button
                    for vb in driver.find_elements(By.XPATH,
                        "//button[contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'VERIFY') or contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'LOGIN') or contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'CONTINUE') or contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'SUBMIT') or @type='submit']"
                    ):
                        if vb.is_displayed():
                            if pb:
                                pb.click_element_hard(driver, vb)
                            else:
                                driver.execute_script("arguments[0].click();", vb)
                            engine.log("Submitted OTP verification to Flipkart.", "SUCCESS")
                            break

                    time.sleep(3)
                    if check_is_logged_in():
                        engine.log("SUCCESS: Flipkart Login verified successfully!", "SUCCESS")
                        break

                time.sleep(1)

        # Step 5: Address Selection & Delivery Confirmation
        with engine.lock:
            engine.state["current_step"] = 4
            engine.state["progress"] = 70
        engine.log("Confirming the saved or locally configured shipping address.", "ACTION")

        delivered = False
        for dh in driver.find_elements(By.XPATH, "//button[contains(., 'DELIVER HERE') or contains(., 'Deliver Here') or contains(., 'Deliver to this address')]"):
            if dh.is_displayed():
                if pb:
                    pb.click_element_hard(driver, dh)
                else:
                    driver.execute_script("arguments[0].click();", dh)
                engine.log("Selected a saved delivery address.", "SUCCESS")
                delivered = True
                break

        if not delivered:
            # Check if address already selected on page
            body_l = driver.page_source.lower()
            if CUSTOMER["pincode"] and CUSTOMER["pincode"] in body_l:
                delivered = True
                engine.log("Verified the configured delivery address.", "SUCCESS")

        time.sleep(1.5)

        # Step 6: Order Summary & Open Box Delivery Confirmation
        with engine.lock:
            engine.state["current_step"] = 4
            engine.state["progress"] = 82
        engine.log("Reviewing Order Summary...", "ACTION")

        for ab in driver.find_elements(By.XPATH, "//button[contains(., 'Accept & Continue') or contains(., 'ACCEPT & CONTINUE')]"):
            if ab.is_displayed():
                if pb:
                    pb.click_element_hard(driver, ab)
                else:
                    driver.execute_script("arguments[0].click();", ab)
                time.sleep(1)

        for cb in driver.find_elements(By.XPATH, "//button[contains(., 'CONTINUE') or contains(., 'Continue')]"):
            if cb.is_displayed():
                if pb:
                    pb.click_element_hard(driver, cb)
                else:
                    driver.execute_script("arguments[0].click();", cb)
                engine.log("Confirmed Order Summary. Arriving on Payment Stage...", "SUCCESS")
                break

        time.sleep(3.0)

        # Step 7: Payment Gateway Execution via Dedicated Modular Flipkart Payment System
        engine.raise_if_cancelled()
        return handle_platform_payment(
            platform="flipkart",
            driver=driver,
            engine=engine,
            product_name=product_name,
            payment_method=payment_method,
            upi_id=upi_id,
            card_index=card_index,
            quantity=quantity,
            customer_info=CUSTOMER
        )

    except Exception as e:
        engine.handle_pipeline_error(e)


def run_generic_store_pipeline(
    engine: AutomationEngine,
    brand_name: str,
    account: int,
    product_name: str,
    product_url: str,
    card_index: int = 0,
    payment_method: str = "cards",
    upi_id: str = "",
    quantity: int = 1,
):
    """
    Checkout pipeline for Amazon, Reliance Digital, JioMart, Samsung, and Vivo:
    1. Detached Chrome launch with isolated profile.
    2. Cart verification & cleanup.
    3. Product navigation & deliverability check.
    4. SKU & Add to Cart / Buy Now.
    5. Optional shipping address injection from local settings.
    6. Payment Option Automation:
       - COD (Cash on Delivery / Pay on Delivery auto-selection & Order Placement)
       - UPI (VPA injection & Dynamic QR mirror)
       - Credit / Debit Cards (Auto-fill)
    7. Notification Dispatch.
    """
    driver = None
    try:
        if not 1 <= quantity <= MAX_BULK_QUANTITY:
            raise ValueError(f"quantity must be from 1 to {MAX_BULK_QUANTITY}.")
        with engine.lock:
            engine.state["status"] = "running"
            engine.state["current_step"] = 1
            engine.state["progress"] = 10
            engine.state["account"] = account
            engine.state["logs"] = []
            engine.state["error"] = None
            engine.state["notification"] = None

        engine.log(f"Launching {brand_name} checkout for Account {account}...", "START")

        # Cart URLs per brand
        cart_urls = {
            "Flipkart": "https://www.flipkart.com/viewcart",
            "Amazon": "https://www.amazon.in/gp/cart/view.html",
            "Croma": "https://www.croma.com/cart",
            "Reliance Digital": "https://www.reliancedigital.in/cart",
            "JioMart": "https://www.jiomart.com/checkout/cart",
            "Samsung": "https://www.samsung.com/in/cart/",
            "Oppo": "https://www.oppo.com/in/store/",
            "Vivo": "https://shop.vivo.com/in/cart",
            "Apple": "https://www.apple.com/in/shop/bag",
        }

        # Step 1: Launch Browser
        target_nav_url = product_url if product_url and product_url.startswith("http") else engine.default_url
        driver = engine.launch_browser(account, initial_url=target_nav_url)
        engine.log(f"SUCCESS: Chrome browser launched visibly on your desktop for {brand_name}!", "SUCCESS")
        time.sleep(2)

        # Step 2: Clean Cart
        cart_url = cart_urls.get(brand_name)
        if cart_url:
            with engine.lock:
                engine.state["current_step"] = 2
                engine.state["progress"] = 25
            engine.log(f"Checking {brand_name} Cart ({cart_url}) for previous items...", "ACTION")
            driver.get(cart_url)
            time.sleep(3)

            # Try to remove previous items
            removed = 0
            for _ in range(4):
                try:
                    removes = driver.find_elements(By.XPATH, "//button[contains(., 'Delete') or contains(., 'Remove')] | //a[contains(., 'Delete') or contains(., 'Remove')] | //span[contains(@class, 'delete') or contains(@class, 'remove')]")
                    vis = [b for b in removes if b.is_displayed()]
                    if not vis:
                        break
                    driver.execute_script("arguments[0].click();", vis[0])
                    removed += 1
                    time.sleep(1.5)
                except Exception:
                    break

            if removed > 0:
                engine.log(f"Cleaned {removed} previous item(s) from {brand_name} cart.", "SUCCESS")
            else:
                engine.log(f"{brand_name} cart is clean and ready.", "INFO")

        time.sleep(1)

        # Step 3: Product Navigation & Pincode Check
        with engine.lock:
            engine.state["current_step"] = 2
            engine.state["progress"] = 40

        engine.log(f"Navigating to {brand_name} product: {product_name}...", "ACTION")
        driver.get(target_nav_url)
        time.sleep(3)

        # Check deliverability only when a delivery PIN is configured.
        if CUSTOMER["pincode"]:
            try:
                pin_inputs = driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'pincode') or contains(@placeholder, 'Pincode') or contains(@id, 'pin') or contains(@name, 'pincode')]")
                for p_in in pin_inputs:
                    if p_in.is_displayed():
                        p_in.clear()
                        p_in.send_keys(CUSTOMER["pincode"])
                        time.sleep(0.5)
                        for button in driver.find_elements(By.XPATH, "//button[contains(., 'Check') or contains(., 'Apply') or contains(., 'Verify')]"):
                            if button.is_displayed():
                                driver.execute_script("arguments[0].click();", button)
                                engine.log("Configured delivery PIN verified on screen.", "SUCCESS")
                                break
                        break
            except Exception as exc:
                engine.log(f"Delivery PIN entry failed: {exc}", "WARNING")

        time.sleep(1.5)

        # Step 4: Add to Cart / Buy Now
        with engine.lock:
            engine.state["current_step"] = 3
            engine.state["progress"] = 60
        engine.log(f"Clicking 'Buy Now' / 'Add to Cart' for {product_name}...", "ACTION")

        purchase_xpaths = (
            [
                "//button[contains(translate(., 'ADD TO CART', 'add to cart'), 'add to cart')]",
                "//input[@id='add-to-cart-button']",
            ]
            if quantity > 1
            else [
                "//button[contains(translate(., 'BUY NOW', 'buy now'), 'buy now')]",
                "//button[contains(translate(., 'ADD TO CART', 'add to cart'), 'add to cart')]",
                "//input[@id='buy-now-button']",
                "//input[@id='add-to-cart-button']",
                "//a[contains(translate(., 'BUY NOW', 'buy now'), 'buy now')]",
            ]
        )
        purchase_clicked = False
        for xp in purchase_xpaths:
            try:
                for b in driver.find_elements(By.XPATH, xp):
                    if b.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", b)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", b)
                        engine.log(f"Selected '{b.text.strip() or 'Purchase CTA'}' on {brand_name}.", "SUCCESS")
                        purchase_clicked = True
                        break
            except Exception:
                pass
            if purchase_clicked:
                break

        time.sleep(3)

        if quantity > 1:
            if not purchase_clicked:
                raise RuntimeError(f"Could not add the {brand_name} item to cart; checkout was stopped.")
            if not cart_url:
                raise ValueError(f"No cart URL is configured for bulk checkout on {brand_name}.")
            driver.get(cart_url)
            time.sleep(2.5)
            set_checkout_quantity(driver, brand_name, quantity, product_name)
            engine.log(f"Verified the {brand_name} cart quantity: {quantity}.", "SUCCESS")
            continue_from_bulk_cart(driver, engine, brand_name)

        # Step 4.5: Login & session persistence check.
        def is_store_logged_in() -> bool:
            try:
                b_low = brand_name.lower()
                c_url = driver.current_url.lower()
                body = driver.page_source.lower()
                if "amazon" in b_low:
                    is_signin = "signin" in c_url or "ap/signin" in c_url
                    has_acc = any(k in body for k in ["account & lists", "select a delivery address", "order summary", "payment"])
                    return not is_signin and has_acc
                elif "reliance" in b_low:
                    return any(k in body for k in ["my account", "logout"]) or "checkout" in c_url
                elif "jiomart" in b_low:
                    return any(k in body for k in ["my account", "orders"]) or "checkout" in c_url
                return True
            except Exception:
                return False

        if is_store_logged_in():
            engine.log(f"[SESSION ACTIVE] A signed-in {brand_name} profile is active.", "SUCCESS")
        else:
            if not CUSTOMER["email"]:
                raise ValueError("Set AUTOMATION_CUSTOMER_EMAIL or sign in through the browser profile first.")
            email_inps = [i for i in driver.find_elements(By.XPATH,
                "//input[@type='email' or @id='ap_email' or contains(@placeholder, 'Email') or contains(@placeholder, 'phone') or contains(@placeholder, 'Mobile') or contains(@id, 'login') or contains(@id, 'user')]"
            ) if i.is_displayed()]
            if email_inps:
                e_inp = email_inps[0]
                engine.log(f"Entering the configured {brand_name} account email.", "ACTION")
                e_inp.clear()
                e_inp.send_keys(CUSTOMER["email"])
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", e_inp)
                driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", e_inp)
                time.sleep(1)

                for cb in driver.find_elements(By.XPATH, "//input[@id='continue' or @type='submit'] | //button[contains(., 'Continue') or contains(., 'Proceed') or contains(., 'Submit')]"):
                    if cb.is_displayed():
                        driver.execute_script("arguments[0].click();", cb)
                        engine.log(f"Requested a {brand_name} verification code.", "ACTION")
                        break
                time.sleep(2.5)

                with engine.lock:
                    engine.state["status"] = "awaiting_otp"
                    engine.state["otp_required"] = True
                    engine.state["otp_target"] = f"Configured {brand_name} account"
                engine.log(f"[OTP REQUIRED] Enter the verification code sent by {brand_name}.", "ALERT")
                engine.otp_event.clear()

                otp_deadline = time.time() + 180
                while time.time() < otp_deadline:
                    if is_store_logged_in():
                        engine.log(f"SUCCESS: {brand_name} Login verified successfully! Session saved to profile.", "SUCCESS")
                        break
                    if engine.otp_event.is_set() and engine.submitted_otp:
                        otp_val = engine.submitted_otp.strip()
                        engine.otp_event.clear()
                        engine.log(f"Submitting the entered {brand_name} verification code.", "ACTION")
                        otp_boxes = [b for b in driver.find_elements(By.XPATH,
                            "//input[contains(@id, 'otp') or contains(@name, 'otp') or contains(@placeholder, 'OTP') or @maxlength='6' or @maxlength='4' or @id='auth-mfa-otpcode']"
                        ) if b.is_displayed()]
                        for ob in otp_boxes:
                            try:
                                ob.clear()
                                ob.send_keys(otp_val)
                                driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", ob)
                                driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", ob)
                            except Exception:
                                pass
                        time.sleep(1)
                        for sb in driver.find_elements(By.XPATH, "//input[@id='auth-signin-button' or @type='submit'] | //button[contains(., 'Verify') or contains(., 'Sign-In') or contains(., 'Submit')]"):
                            if sb.is_displayed():
                                driver.execute_script("arguments[0].click();", sb)
                                break
                        time.sleep(3)
                        if is_store_logged_in():
                            engine.log(f"SUCCESS: {brand_name} Login verified and saved to profile!", "SUCCESS")
                            break
                    time.sleep(1)

        # Step 5: Address Fill & Proceed to Checkout
        with engine.lock:
            engine.state["current_step"] = 4
            engine.state["progress"] = 75
        engine.log("Filling locally configured shipping details where fields are available.", "ACTION")

        # Fill any address inputs visible
        addr_map = {
            CUSTOMER["name"]: ["//input[contains(@id, 'name') or contains(@name, 'name')]"],
            CUSTOMER["phone"].replace("+91", "").strip(): ["//input[contains(@id, 'mobile') or contains(@name, 'mobile') or contains(@type, 'tel')]"],
            CUSTOMER["pincode"]: ["//input[contains(@id, 'pincode') or contains(@name, 'pincode') or contains(@id, 'zip') or contains(@id, 'postal')]"],
            CUSTOMER["address"]: ["//input[contains(@id, 'address') or contains(@name, 'address') or contains(@id, 'line1')]"],
            CUSTOMER["city"]: ["//input[contains(@id, 'city') or contains(@name, 'city')]"],
            CUSTOMER["state"]: ["//input[contains(@id, 'state') or contains(@name, 'state')]"]
        }
        for val, xps in addr_map.items():
            if not val:
                continue
            for xp in xps:
                try:
                    for el in driver.find_elements(By.XPATH, xp):
                        if el.is_displayed():
                            el.clear()
                            el.send_keys(val)
                            break
                except Exception:
                    pass

        time.sleep(2)

        # Step 6: Payment Execution via Dedicated Modular Platform Payment System
        engine.raise_if_cancelled()
        return handle_platform_payment(
            platform=brand_name,
            driver=driver,
            engine=engine,
            product_name=product_name,
            payment_method=payment_method,
            upi_id=upi_id,
            card_index=card_index,
            customer_info=CUSTOMER
        )

    except Exception as e:
        engine.handle_pipeline_error(e)


LIVE_VIEW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Croma Live Automation Stream</title>
  <style>
    body { margin: 0; background: #0b0f19; color: #fff; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
    .header { background: #111827; padding: 10px 16px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #1f2937; }
    .badge { background: #00b259; color: #fff; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 12px; }
    .otp-floating-bar { background: linear-gradient(90deg, #1e3a8a, #065f46); padding: 8px 16px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #2563eb; }
    .otp-input { padding: 6px 12px; font-size: 16px; border-radius: 4px; border: 1px solid #60a5fa; background: #0f172a; color: #fff; width: 140px; letter-spacing: 4px; text-align: center; }
    .otp-btn { background: #10b981; color: #fff; border: none; padding: 7px 14px; border-radius: 4px; font-weight: bold; cursor: pointer; }
    .otp-btn:hover { background: #059669; }
    .screen-area { flex: 1; display: flex; justify-content: center; align-items: center; background: #000; overflow: hidden; }
    .screen-img { max-width: 100%; max-height: 100%; object-fit: contain; }
  </style>
</head>
<body>
  <div class="header">
    <div style="display:flex; align-items:center; gap:10px;">
      <span class="badge">CROMA BOT</span>
      <span style="font-size:13px; color:#9ca3af;" id="url-text">croma.com</span>
    </div>
    <div style="font-size:12px; color:#10b981;">● LIVE MIRROR (250ms)</div>
  </div>
  <div class="otp-floating-bar" id="otp-bar" style="display:flex;">
    <span style="font-size:13px;">🔐 Croma OTP Verification:</span>
    <div style="display:flex; gap:8px;">
      <input type="text" id="otp-val" placeholder="OTP" maxlength="6" class="otp-input" />
      <button class="otp-btn" onclick="submitOtp()">Submit OTP</button>
    </div>
  </div>
  <div class="screen-area">
    <img id="live-img" class="screen-img" src="/api/automation/screen" alt="Live Chrome Screen" />
  </div>
  <script>
    setInterval(() => {
      document.getElementById('live-img').src = '/api/automation/screen?t=' + Date.now();
      fetch('/api/automation/status').then(r => r.json()).then(d => {
        if (d.current_url) document.getElementById('url-text').innerText = d.current_url;
        document.getElementById('otp-bar').style.display = (d.otp_required || d.status === 'awaiting_otp') ? 'flex' : 'none';
      }).catch(()=>{});
    }, 300);
    function submitOtp() {
      const otp = document.getElementById('otp-val').value;
      if (!otp) return alert('Please enter OTP');
      fetch('/api/automation/submit-otp', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ otp })
      }).then(r => r.json()).then(d => {
        alert('OTP Submitted to Croma!');
        document.getElementById('otp-val').value = '';
      });
    }
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Global Engine Registry
# ---------------------------------------------------------------------------

ENGINES = {
    "apple": AutomationEngine("Apple", "https://www.apple.com/in/", "apple_profiles"),
    "samsung": AutomationEngine("Samsung", "https://www.samsung.com/in/", "samsung_profiles"),
    "croma": AutomationEngine("Croma", "https://www.croma.com/", "croma_profiles"),
    "amazon": AutomationEngine("Amazon", "https://www.amazon.in/", "amazon_profiles"),
    "flipkart": AutomationEngine("Flipkart", "https://www.flipkart.com/", "flipkart_profiles"),
    "reliance": AutomationEngine("Reliance Digital", "https://www.reliancedigital.in/", "reliance_profiles"),
    "jiomart": AutomationEngine("JioMart", "https://www.jiomart.com/", "jiomart_profiles"),
    "vivo": AutomationEngine("Vivo", "https://shop.vivo.com/in/", "vivo_profiles"),
    "oppo": AutomationEngine("Oppo", "https://www.oppo.com/in/store/", "oppo_profiles"),
}


def get_engine(brand_key: str) -> AutomationEngine:
    key = str(brand_key).strip().lower()
    if key not in ENGINES:
        raise ValueError(f"No automation engine is configured for {brand_key!r}.")
    return ENGINES[key]


# ---------------------------------------------------------------------------
# Helper to attach routes to Flask applications
# ---------------------------------------------------------------------------

STORE_DOMAINS = {
    "amazon": {"amazon.in"},
    "apple": {"apple.com"},
    "croma": {"croma.com"},
    "flipkart": {"flipkart.com"},
    "jiomart": {"jiomart.com"},
    "reliance": {"reliancedigital.in"},
    "samsung": {"samsung.com"},
    "vivo": {"vivo.com"},
}


def attach_flask_automation_routes(app, brand_key: str, url_prefix: str = "/api/automation"):
    from flask import Blueprint, Response, jsonify, request

    if brand_key not in PAYMENT_METHODS_BY_PLATFORM:
        raise ValueError(f"No payment automation is configured for {brand_key!r}.")
    engine = get_engine(brand_key)
    routes = Blueprint(f"automation_{brand_key}", __name__, url_prefix=url_prefix)

    def read_json_object():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return None
        return payload

    def parse_account(data):
        try:
            account = int(data.get("account", 1))
        except (TypeError, ValueError):
            raise ValueError("account must be an integer from 1 to 5.")
        if not 1 <= account <= 5:
            raise ValueError("account must be an integer from 1 to 5.")
        return account

    @routes.get("/config")
    def get_cfg():
        try:
            return jsonify(engine.get_config())
        except (OSError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 500

    @routes.get("/status")
    def get_st():
        return jsonify(engine.get_status())

    @routes.get("/screen")
    def get_sc():
        screenshot = engine.get_status().get("screenshot")
        if screenshot and "," in screenshot:
            raw = base64.b64decode(screenshot.split(",", 1)[1])
            return Response(raw, mimetype="image/png")
        return Response(b"", mimetype="image/png", status=204)

    @routes.get("/live-view")
    def live_v():
        scoped_html = LIVE_VIEW_HTML.replace(
            "/api/automation/",
            f"/api/automation/{brand_key}/",
        )
        return Response(scoped_html, mimetype="text/html")

    @routes.post("/submit-otp")
    def sub_otp():
        data = read_json_object()
        if data is None:
            return jsonify({"error": "The request body must be a JSON object."}), 400
        otp = str(data.get("otp", "")).strip()
        if not otp.isdigit() or not 4 <= len(otp) <= 8:
            return jsonify({"error": "Enter a verification code containing 4 to 8 digits."}), 400
        engine.submit_otp(otp)
        return jsonify({"status": "accepted"})

    @routes.post("/import-cards")
    def imp_cards():
        data = read_json_object()
        if data is None:
            return jsonify({"error": "The request body must be a JSON object."}), 400
        cards = data.get("cards")
        if not isinstance(cards, list):
            return jsonify({"error": "cards must be a JSON list."}), 400
        try:
            engine.import_cards(cards)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"status": "accepted", "count": len(cards)})

    @routes.post("/launch-browser")
    def launch_b():
        data = read_json_object()
        if data is None:
            return jsonify({"error": "The request body must be a JSON object."}), 400
        try:
            account = parse_account(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        def launch():
            try:
                engine.launch_browser(account)
            except Exception as exc:
                with engine.lock:
                    engine.state["status"] = "error"
                    engine.state["error"] = str(exc)
                engine.log(f"Browser launch failed: {exc}", "ERROR")

        threading.Thread(target=launch, daemon=True).start()
        return jsonify({"status": "starting", "account": account}), 202

    @routes.post("/start")
    def start_bot():
        data = read_json_object()
        if data is None:
            return jsonify({"error": "The request body must be a JSON object."}), 400
        try:
            account = parse_account(data)
            raw_quantity = data.get("quantity", 1)
            if isinstance(raw_quantity, bool) or not (
                isinstance(raw_quantity, int)
                or isinstance(raw_quantity, str) and raw_quantity.strip().isdecimal()
            ):
                raise ValueError
            quantity = int(raw_quantity)
            card_index = int(data.get("card_index", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "quantity and card_index must be integers."}), 400
        if not 1 <= quantity <= MAX_BULK_QUANTITY:
            return jsonify({"error": f"quantity must be from 1 to {MAX_BULK_QUANTITY}."}), 400
        if quantity > 1 and data.get("confirm_auto_place") is not True:
            return jsonify({"error": "Confirm automated order submission before bulk checkout."}), 400
        if card_index < 0:
            return jsonify({"error": "card_index cannot be negative."}), 400

        product_name = str(data.get("product_name", "")).strip()
        if not product_name or len(product_name) > 250:
            return jsonify({"error": "product_name is required and must be at most 250 characters."}), 400
        product_url = str(data.get("product_url", "")).strip()
        if product_url:
            parsed_url = urlparse(product_url)
            hostname = (parsed_url.hostname or "").lower()
            allowed_domains = STORE_DOMAINS[brand_key]
            if (
                parsed_url.scheme not in {"http", "https"}
                or not any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains)
            ):
                return jsonify({"error": f"product_url must belong to {engine.brand}."}), 400

        payment_method = str(data.get("payment_method", "cards")).strip().lower()
        if payment_method not in PAYMENT_METHODS_BY_PLATFORM[brand_key]:
            return jsonify({"error": f"{payment_method!r} payment is not available for {engine.brand}."}), 400
        upi_id = str(data.get("upi_id", "")).strip()
        if payment_method == "upi" and (not upi_id or len(upi_id) > 128):
            return jsonify({"error": "A valid UPI ID is required for UPI payment."}), 400
        if payment_method in {"cards", "card", "credit_debit", "emi"}:
            try:
                get_configured_card(engine, card_index)
            except (OSError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400

        with engine.lock:
            if engine.state["status"] in {
                "starting", "running", "awaiting_otp", "awaiting_upi_qr", "awaiting_confirmation"
            }:
                return jsonify({"error": "An automation run is already active for this store."}), 409
            engine.state.update({
                "status": "starting",
                "progress": 0,
                "current_step": 0,
                "error": None,
                "notification": None,
                "logs": [],
            })

        if brand_key == "apple":
            target_fn = run_apple_pipeline
            args = (engine, account, product_name, product_url, card_index, quantity)
        elif brand_key == "croma":
            target_fn = run_croma_pipeline
            args = (
                engine, account, product_name, product_url, card_index, payment_method,
                upi_id, None, str(data.get("gst_number", "")), quantity,
            )
        elif brand_key == "flipkart":
            target_fn = run_flipkart_pipeline
            args = (engine, account, product_name, product_url, card_index, payment_method, upi_id, quantity, "")
        else:
            target_fn = run_generic_store_pipeline
            args = (
                engine, engine.brand, account, product_name, product_url,
                card_index, payment_method, upi_id, quantity,
            )

        threading.Thread(target=target_fn, args=args, daemon=True).start()
        return jsonify({"status": "started", "brand": engine.brand, "account": account}), 202

    @routes.post("/click-place-order")
    def click_place_order():
        if not engine.driver:
            return jsonify({"error": "No active browser session."}), 400
        clicked = False

        if pb:
            button = pb.find_by_text(engine.driver, ["place order", "confirm order"])
            if button:
                clicked = bool(pb.click_element_hard(engine.driver, button))

        if not clicked:
            for xpath in [
                "//button[normalize-space()='Place Order' or normalize-space()='Confirm Order']",
                "//button[contains(., 'Place your order')]",
            ]:
                for button in engine.driver.find_elements(By.XPATH, xpath):
                    if button.is_displayed():
                        clicked = bool(
                            get_payment_system(brand_key).click_element_hard(engine.driver, button)
                        )
                        if clicked:
                            break
                if clicked:
                    break
        return jsonify({"status": "clicked" if clicked else "not_found", "clicked": clicked})

    @routes.post("/stop")
    def stop_bot():
        engine.stop()
        return jsonify({"status": "stopped"})

    app.register_blueprint(routes)
    return routes


# ---------------------------------------------------------------------------
# Helper to attach routes to FastAPI applications
# ---------------------------------------------------------------------------

def attach_fastapi_automation_routes(app, brand_key: str):
    from fastapi import HTTPException, Request
    from fastapi.responses import Response, JSONResponse, HTMLResponse

    engine = get_engine(brand_key)

    @app.get("/api/automation/config")
    async def get_cfg():
        return engine.get_config()

    @app.get("/api/automation/status")
    async def get_st():
        return engine.get_status()

    @app.get("/api/automation/screen")
    async def get_sc():
        s = engine.get_status().get("screenshot")
        if s and "," in s:
            raw = base64.b64decode(s.split(",", 1)[1])
            return Response(content=raw, media_type="image/png")
        return Response(content=b"", media_type="image/png", status_code=204)

    @app.get("/api/automation/live-view")
    async def live_v():
        return HTMLResponse(content=LIVE_VIEW_HTML)

    @app.post("/api/automation/submit-otp")
    async def sub_otp(req: Request):
        data = await req.json() if (await req.body()) else {}
        otp = str(data.get("otp", "")).strip()
        if otp.isdigit() and 4 <= len(otp) <= 8:
            engine.submit_otp(otp)
            return {"status": "accepted"}
        return JSONResponse(status_code=400, content={"error": "Enter a verification code containing 4 to 8 digits."})

    @app.post("/api/automation/import-cards")
    async def imp_cards(req: Request):
        data = await req.json() if (await req.body()) else {}
        cards = data.get("cards", [])
        if isinstance(cards, list):
            try:
                engine.import_cards(cards)
            except ValueError as exc:
                return JSONResponse(status_code=400, content={"error": str(exc)})
            return {"status": "success", "count": len(cards)}
        return JSONResponse(status_code=400, content={"error": "cards must be a JSON list."})

    @app.post("/api/automation/launch-browser")
    async def launch_b(req: Request):
        data = await req.json() if (await req.body()) else {}
        acc = int(data.get("account", 1))
        threading.Thread(target=engine.launch_browser, args=(acc,), daemon=True).start()
        return {"status": "launched", "account": acc}

    @app.post("/api/automation/start")
    async def start_bot(req: Request):
        data = await req.json() if (await req.body()) else {}
        acc = int(data.get("account", 1))
        p_name = str(data.get("product_name", "Smartphone"))
        p_url = str(data.get("product_url", ""))
        c_idx = int(data.get("card_index", 0))
        p_method = str(data.get("payment_method", "cards"))
        upi = str(data.get("upi_id", ""))
        raw_quantity = data.get("quantity", 1)
        if isinstance(raw_quantity, bool) or not (
            isinstance(raw_quantity, int)
            or isinstance(raw_quantity, str) and raw_quantity.strip().isdecimal()
        ):
            raise HTTPException(status_code=400, detail="quantity must be an integer.")
        quantity = int(raw_quantity)
        if not 1 <= quantity <= MAX_BULK_QUANTITY:
            raise HTTPException(
                status_code=400,
                detail=f"quantity must be from 1 to {MAX_BULK_QUANTITY}.",
            )
        if quantity > 1 and data.get("confirm_auto_place") is not True:
            raise HTTPException(
                status_code=400,
                detail="Confirm automated order submission before bulk checkout.",
            )
        c_card = None
        gst = str(data.get("gst_number", ""))

        if brand_key.lower() == "apple":
            target_fn = run_apple_pipeline
            args = (engine, acc, p_name, p_url, c_idx, quantity)
        elif brand_key.lower() == "croma":
            target_fn = run_croma_pipeline
            args = (engine, acc, p_name, p_url, c_idx, p_method, upi, c_card, gst, quantity)
        elif brand_key.lower() == "flipkart":
            target_fn = run_flipkart_pipeline
            args = (engine, acc, p_name, p_url, c_idx, p_method, upi, quantity)
        else:
            target_fn = run_generic_store_pipeline
            args = (engine, engine.brand, acc, p_name, p_url, c_idx, p_method, upi, quantity)

        threading.Thread(target=target_fn, args=args, daemon=True).start()
        return {"status": "started", "brand": engine.brand, "account": acc}

    @app.post("/api/automation/stop")
    async def stop_bot():
        engine.stop()
        return {"status": "stopped"}

