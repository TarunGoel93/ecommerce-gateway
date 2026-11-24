"""
Dedicated Vivo Official Store Autonomous Payment System
Handles:
- Cash on Delivery (COD) auto-selection on Vivo India Official Store (shop.vivo.com/in/)
- UPI (VPA injection & Dynamic QR mirror)
- Credit / Debit Cards auto-fill
- Order progression and Vivo Order ID extraction
"""

import time
import logging
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By

from .base_payment import BasePaymentSystem, get_configured_card

logger = logging.getLogger("VivoPaymentSystem")


class VivoPaymentSystem(BasePaymentSystem):
    def __init__(self):
        super().__init__("Vivo")

    def process_payment(
        self,
        driver,
        engine,
        product_name: str,
        payment_method: str = "cod",
        upi_id: str = "",
        card_index: int = 0,
        custom_card: Optional[Dict[str, Any]] = None,
        customer_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Executes Vivo India checkout payment stage."""
        with engine.lock:
            engine.state["current_step"] = 5
            engine.state["progress"] = 90

        p_meth = (payment_method or "cod").lower()
        engine.log(f"Arrived on Vivo Payment Stage. Selected Method: {p_meth.upper()}", "ACTION")

        # ---------------- 1. CASH ON DELIVERY (COD) ----------------
        if "cod" in p_meth:
            engine.log("Handling Vivo Cash on Delivery...", "ACTION")
            try:
                cod_selectors = [
                    "//div[contains(text(), 'Cash on Delivery') or contains(text(), 'COD')]",
                    "//input[@type='radio' and (contains(@value, 'COD') or contains(@id, 'cod') or contains(@name, 'payment'))]",
                    "//label[contains(., 'Cash on Delivery')]",
                    "//span[contains(text(), 'Cash On Delivery')]"
                ]
                selected = False
                for sel in cod_selectors:
                    for el in driver.find_elements(By.XPATH, sel):
                        if el.is_displayed():
                            self.click_element_hard(driver, el)
                            engine.log("Selected Vivo 'Cash on Delivery' option.", "SUCCESS")
                            selected = True
                            break
                    if selected:
                        break

                time.sleep(1.5)

                self.click_final_action(
                    driver,
                    ["place order", "confirm order", "pay now", "submit order"],
                )
                confirmed, order_id = self.watch_order_confirmation(driver, timeout=12)
                engine.finish_flow(
                    success=confirmed,
                    status_title="Vivo Order Confirmed" if confirmed else "Vivo Checkout Awaiting Confirmation",
                    reason=(
                        f"Order confirmation detected{f' ({order_id})' if order_id else ''}."
                        if confirmed
                        else "Final order action submitted. Complete any store verification in the visible browser."
                    ),
                    card_last4="COD",
                    product_name=product_name,
                    status=None if confirmed else "awaiting_confirmation",
                )
                return True
            except Exception as e:
                engine.log(f"Vivo COD step failed: {e}", "ERROR")
                raise

        # ---------------- 2. UPI PAYMENT ----------------
        elif "upi" in p_meth:
            engine.log("Handling Vivo UPI payment.", "ACTION")
            try:
                upi_selectors = [
                    "//div[contains(text(), 'UPI') or contains(., 'Google Pay') or contains(., 'PhonePe')]",
                    "//input[@type='radio' and (contains(@value, 'upi') or contains(@id, 'upi'))]",
                    "//label[contains(., 'UPI')]"
                ]
                for sel in upi_selectors:
                    for el in driver.find_elements(By.XPATH, sel):
                        if el.is_displayed():
                            self.click_element_hard(driver, el)
                            engine.log("Selected Vivo UPI option.", "SUCCESS")
                            break

                time.sleep(1)
                # Input VPA
                vpa_inputs = driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'VPA') or contains(@placeholder, 'UPI ID') or contains(@name, 'vpa')]")
                for inp in vpa_inputs:
                    if inp.is_displayed():
                        inp.clear()
                        inp.send_keys(upi_id)
                        engine.log("Entered the configured Vivo UPI ID.", "SUCCESS")
                        break
                if not any(inp.is_displayed() for inp in vpa_inputs):
                    raise RuntimeError("Could not find a visible Vivo UPI ID field.")
                self.click_final_action(
                    driver,
                    ["verify", "pay now", "continue", "continue to payment", "generate qr"],
                )
                engine.finish_flow(
                    success=True,
                    status_title="Vivo UPI Awaiting Authorization",
                    reason="UPI request submitted. Complete the payment in your UPI app or the visible browser.",
                    card_last4="UPI",
                    product_name=product_name,
                    status="awaiting_upi_qr",
                )

                return True
            except Exception as e:
                engine.log(f"Vivo UPI step failed: {e}", "ERROR")
                raise

        # ---------------- 3. CREDIT / DEBIT CARDS ----------------
        else:
            engine.log("Handling Vivo Card Payment...", "ACTION")
            card = get_configured_card(engine, card_index, custom_card)
            try:
                card_selectors = [
                    "//div[contains(text(), 'Credit / Debit Card') or contains(., 'Card')]",
                    "//input[@type='radio' and (contains(@value, 'card') or contains(@id, 'card'))]"
                ]
                for sel in card_selectors:
                    for el in driver.find_elements(By.XPATH, sel):
                        if el.is_displayed():
                            self.click_element_hard(driver, el)
                            engine.log("Selected Vivo Card payment option.", "SUCCESS")
                            break

                time.sleep(1)
                self.fill_card_inputs(driver, engine, card)
                self.click_final_action(
                    driver,
                    ["place your order", "place order", "confirm order", "pay now", "make payment"],
                )
                confirmed, order_id = self.watch_order_confirmation(driver, timeout=12)
                card_last4 = str(card.get("last4") or card.get("number", "")[-4:])
                engine.finish_flow(
                    success=confirmed,
                    status_title="Vivo Order Confirmed" if confirmed else "Vivo Payment Awaiting Authorization",
                    reason=(
                        f"Order confirmation detected{f' ({order_id})' if order_id else ''}."
                        if confirmed
                        else f"Card ending in {card_last4} was submitted. Complete any bank verification in the visible browser."
                    ),
                    card_last4=card_last4,
                    product_name=product_name,
                    status=None if confirmed else "awaiting_confirmation",
                )
                return True
            except Exception as e:
                engine.log(f"Vivo card step failed: {e}", "ERROR")
                raise

        return False

    def extract_order_id(self, driver) -> str:
        """Extracts genuine Vivo Order ID from URL or page text."""
        import re
        try:
            curr_url = driver.current_url
            match = re.search(r"(?:orderId|order_id|orderNo|order)=(\w+)", curr_url, re.I)
            if match:
                return match.group(1)

            body_text = driver.find_element(By.TAG_NAME, "body").text
            match_txt = re.search(r"(?:Order\s*(?:ID|Number|No|#))\s*[:#-]?\s*([A-Za-z0-9_-]{8,24})", body_text, re.I)
            if match_txt:
                return match_txt.group(1)
        except Exception:
            pass

        return ""
