"""
Dedicated Reliance Digital Autonomous Payment System
Handles:
- Cash on Delivery (COD) auto-selection
- Order placement execution
- Real Reliance Order ID extraction
- UPI & Card injection
"""

import time
import logging
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By

from .base_payment import BasePaymentSystem, get_configured_card

logger = logging.getLogger("ReliancePaymentSystem")


class ReliancePaymentSystem(BasePaymentSystem):
    def __init__(self):
        super().__init__("Reliance Digital")

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
        """Executes Reliance Digital checkout and payment."""
        with engine.lock:
            engine.state["current_step"] = 5
            engine.state["progress"] = 90

        p_meth = (payment_method or "cards").lower()
        engine.log(f"Arrived on Reliance Digital Payment Stage. Selected Option: {p_meth.upper()}", "ACTION")

        # ---------------- 1. CASH ON DELIVERY (COD) ----------------
        if "cod" in p_meth:
            engine.log("Selecting Cash on Delivery on Reliance Digital...", "ACTION")
            try:
                for r in driver.find_elements(By.XPATH, "//input[contains(@value, 'COD') or contains(@id, 'cod') or @type='radio'] | //label[contains(., 'Cash on Delivery') or contains(., 'COD')]"):
                    if r.is_displayed():
                        self.click_element_hard(driver, r)
                        engine.log("Selected Cash on Delivery on Reliance Digital.", "SUCCESS")
                        break

                time.sleep(1.5)
                for b in driver.find_elements(By.XPATH, "//button[contains(., 'CONFIRM ORDER') or contains(., 'Place Order') or contains(., 'Proceed To Pay')]"):
                    if b.is_displayed():
                        self.click_element_hard(driver, b)
                        engine.log("Clicked Confirm Order for Reliance COD!", "SUCCESS")
                        break
            except Exception as e:
                engine.log(f"Reliance COD step failed: {e}", "ERROR")
                raise

            confirmed, order_id = self.watch_order_confirmation(driver, timeout=12)
            engine.finish_flow(
                success=confirmed,
                status_title="Order Confirmed (Cash on Delivery)" if confirmed else "Order Placed - Awaiting Confirmation",
                reason=f"Reliance Digital order confirmed! Order ID: {order_id}." if confirmed else "COD selected on Reliance Digital. Verify in Chrome.",
                card_last4="COD",
                product_name=product_name,
                status=None if confirmed else "awaiting_confirmation",
            )
            return confirmed

        # ---------------- 2. UPI ----------------
        elif "upi" in p_meth:
            engine.log("Handling Reliance UPI payment.", "ACTION")
            try:
                for tab in driver.find_elements(By.XPATH, "//input[@type='radio' and contains(@value, 'UPI')] | //span[contains(text(), 'UPI')] | //div[contains(text(), 'UPI')]"):
                    if tab.is_displayed():
                        self.click_element_hard(driver, tab)
                        break
                for u_inp in driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'UPI ID') or contains(@placeholder, 'VPA') or contains(@name, 'upi')]"):
                    if u_inp.is_displayed():
                        u_inp.clear()
                        u_inp.send_keys(upi_id)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", u_inp)
                        engine.log("Entered the configured Reliance UPI ID.", "SUCCESS")
                        break
                self.click_final_action(driver, ["verify", "pay now", "continue"])
            except Exception as e:
                engine.log(f"Reliance UPI step failed: {e}", "ERROR")
                raise

            with engine.lock:
                engine.state["status"] = "awaiting_upi_qr"
                engine.state["upi_qr_active"] = True

            engine.finish_flow(
                success=True,
                status_title="UPI Gateway Active",
                reason="Reliance Digital UPI payment request is active.",
                card_last4="UPI",
                product_name=product_name,
                status="awaiting_upi_qr",
            )
            return True

        # ---------------- 3. CREDIT / DEBIT CARDS ----------------
        else:
            c_obj = get_configured_card(engine, card_index, custom_card)
            card_num = c_obj["number"].replace(" ", "")
            card_last4 = card_num[-4:]

            engine.log(f"Injecting card details on Reliance Digital (ending in {card_last4})...", "ACTION")
            try:
                for xp in ["//input[contains(@placeholder, 'Card Number') or contains(@name, 'cardNumber') or contains(@id, 'card')]"]:
                    for el in driver.find_elements(By.XPATH, xp):
                        if el.is_displayed():
                            el.clear()
                            el.send_keys(card_num)
                            break
                for xp in ["//input[contains(@placeholder, 'CVV') or contains(@name, 'cvv') or contains(@id, 'cvv')]"]:
                    for el in driver.find_elements(By.XPATH, xp):
                        if el.is_displayed():
                            el.clear()
                            el.send_keys(c_obj["cvv"])
                            break
                self.click_final_action(driver, ["place order", "confirm order", "pay now", "make payment"])
            except Exception as e:
                engine.log(f"Reliance card step failed: {e}", "ERROR")
                raise

            confirmed, order_id = self.watch_order_confirmation(driver, timeout=12)
            engine.finish_flow(
                success=confirmed,
                status_title="Reliance Digital Order Confirmed" if confirmed else "Reliance Digital Payment Awaiting Authorization",
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

