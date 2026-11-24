"""
Base Payment System Architecture for Scalefox Automation
Provides common card utilities, hardware clicks, DOM helpers,
and payment gateway verification across all 5 e-commerce platforms.
"""

import os
import re
import json
import time
import logging
from typing import List, Dict, Any, Optional
from selenium.webdriver.common.by import By

logger = logging.getLogger("BasePaymentSystem")

DEFAULT_CARDS: List[Dict[str, Any]] = []

ORDER_ID_RE = re.compile(r'\b(OD\d{16,20}|\d{3}-\d{7}-\d{7}|RD\d{8,16}|JM\d{8,16}|CR\d{8,16})\b', re.IGNORECASE)


def load_cards() -> List[Dict[str, Any]]:
    """Load payment cards from an explicitly configured local JSON file."""
    cards_path = os.environ.get("AUTOMATION_CARDS_FILE")
    if not cards_path:
        return []

    with open(cards_path, "r", encoding="utf-8") as file:
        cards = json.load(file)
    if not isinstance(cards, list):
        raise ValueError("AUTOMATION_CARDS_FILE must contain a JSON list.")

    normalized = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            raise ValueError(f"Card entry {index + 1} must be a JSON object.")
        number = re.sub(r"\D", "", str(card.get("number", "")))
        expiry = str(card.get("expiry", "")).strip()
        cvv = str(card.get("cvv", "")).strip()
        if len(number) < 12 or not expiry or not cvv:
            raise ValueError(f"Card entry {index + 1} must include number, expiry, and CVV.")
        normalized.append({
            **card,
            "number": number,
            "expiry": expiry,
            "cvv": cvv,
            "last4": number[-4:],
            "brand": card.get("brand") or (
                "Visa" if number.startswith("4")
                else "Mastercard" if number.startswith("5")
                else "Card"
            ),
        })
    return normalized


def get_configured_card(engine, card_index: int, custom_card: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if custom_card is not None:
        return custom_card

    cards = getattr(engine, "imported_cards", None) or load_cards()
    if not cards:
        raise ValueError(
            "No payment card is configured. Import a card through the local UI or set AUTOMATION_CARDS_FILE."
        )
    if not 0 <= card_index < len(cards):
        raise ValueError("Selected payment card index is unavailable.")
    return cards[card_index]


class BasePaymentSystem:
    """Base class providing shared payment routines for any e-commerce storefront."""

    def __init__(self, brand_name: str):
        self.brand_name = brand_name

    def fill_card_inputs(self, driver, engine, card: Dict[str, Any]) -> None:
        """Fill visible payment fields without submitting the payment form."""
        values = (
            (
                str(card.get("number", "")),
                [
                    "input[autocomplete='cc-number']",
                    "input[name*='cardNumber' i]",
                    "input[placeholder*='card number' i]",
                ],
                "card number",
            ),
            (
                str(card.get("name", "")),
                [
                    "input[autocomplete='cc-name']",
                    "input[name*='cardHolder' i]",
                    "input[placeholder*='cardholder' i]",
                ],
                "cardholder name",
            ),
            (
                str(card.get("expiry", "")),
                [
                    "input[autocomplete='cc-exp']",
                    "input[name*='expiry' i]",
                    "input[placeholder*='expiry' i]",
                ],
                "card expiry",
            ),
            (
                str(card.get("cvv", "")),
                [
                    "input[autocomplete='cc-csc']",
                    "input[name*='cvv' i]",
                    "input[name*='cvc' i]",
                    "input[placeholder*='cvv' i]",
                ],
                "card security code",
            ),
        )

        for value, selectors, field_name in values:
            if not value:
                raise ValueError(f"Configured card is missing its {field_name}.")
            for selector in selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                target = next((element for element in elements if element.is_displayed()), None)
                if target is not None:
                    target.clear()
                    target.send_keys(value)
                    break
            else:
                raise RuntimeError(f"Could not find a visible {field_name} field.")

    def click_element_hard(self, driver, el) -> bool:
        """Clicks an element using CDP hardware mouse events if possible, else JS click."""
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            time.sleep(0.2)
        except Exception:
            pass

        try:
            rect = driver.execute_script("return arguments[0].getBoundingClientRect();", el)
            x = int(rect.get("left", 0) + rect.get("width", 0) / 2)
            y = int(rect.get("top", 0) + rect.get("height", 0) / 2)
            if x > 0 and y > 0:
                driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
                driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
                time.sleep(0.05)
                driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
                return True
        except Exception:
            pass

        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            try:
                el.click()
                return True
            except Exception:
                return False

    def click_final_action(self, driver, labels: List[str]) -> str:
        """Click a visible final checkout/payment action or fail explicitly."""
        for element in driver.find_elements(
            By.CSS_SELECTOR,
            "button, input[type='submit'], a[role='button']",
        ):
            if not element.is_displayed() or not element.is_enabled():
                continue
            label = (
                element.text
                or element.get_attribute("value")
                or element.get_attribute("aria-label")
                or ""
            ).strip().lower()
            matched = next(
                (
                    candidate
                    for candidate in labels
                    if label == candidate
                    or (
                        candidate != "continue"
                        and label.startswith(f"{candidate} ")
                    )
                ),
                None,
            )
            if not matched:
                continue
            if not self.click_element_hard(driver, element):
                raise RuntimeError(f"Could not click the {self.brand_name} {matched} control.")
            return matched
        raise RuntimeError(
            f"Could not find a visible {self.brand_name} final action "
            f"({', '.join(labels)})."
        )

    def find_by_text(self, driver, keywords: List[str], tags: Optional[List[str]] = None):
        """Locates first visible DOM element containing one of the provided keywords."""
        tag_str = " or ".join([f"self::{t}" for t in tags]) if tags else "self::*"
        for kw in keywords:
            kw_up = kw.upper()
            xpath = f"//*[({tag_str}) and contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{kw_up}')]"
            try:
                for el in driver.find_elements(By.XPATH, xpath):
                    if el.is_displayed():
                        return el
            except Exception:
                pass
        return None

    def watch_order_confirmation(self, driver, extra_keywords: Optional[List[str]] = None, timeout: int = 15) -> tuple[bool, Optional[str]]:
        """Watches browser DOM and URL for payment success or order confirmation."""
        default_keywords = [
            "order placed", "order confirmed", "your order has been placed",
            "order is confirmed", "thank you for your order", "placed successfully"
        ]
        target_keywords = default_keywords + (extra_keywords or [])

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(1.0)
            try:
                cur_body = driver.page_source.lower()
                cur_url = driver.current_url.lower()

                # Check regex order IDs
                matches = ORDER_ID_RE.findall(driver.page_source)
                if matches:
                    return True, matches[0]

                # Check keyword indicators
                if any(k in cur_body for k in target_keywords):
                    return True, None

                # Check URL indicators
                if any(u in cur_url for u in ["order-confirm", "orderconfirm", "thankyou"]):
                    return True, None
            except Exception:
                pass

        return False, None

