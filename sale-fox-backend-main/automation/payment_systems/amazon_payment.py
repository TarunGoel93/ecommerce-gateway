"""
Dedicated Amazon Autonomous Payment System
Handles:
- Pay on Delivery (Cash on Delivery / COD) auto-selection
- 'Use this payment method' / 'Continue' CTA progression
- 'Place your order' final button execution
- Real Amazon Order ID extraction (e.g. 402-1234567-1234567)
- UPI & Card injection
"""

import time
import logging
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By

from .base_payment import BasePaymentSystem, get_configured_card

logger = logging.getLogger("AmazonPaymentSystem")


class AmazonPaymentSystem(BasePaymentSystem):
    def __init__(self):
        super().__init__("Amazon")

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
        """Executes Amazon final checkout and payment stage."""
        with engine.lock:
            engine.state["current_step"] = 5
            engine.state["progress"] = 90

        p_meth = (payment_method or "cards").lower()
        engine.log(f"Arrived on Amazon Payment Stage. Selected Method: {p_meth.upper()}", "ACTION")

        # ---------------- 1. CASH ON DELIVERY (COD) ----------------
        if "cod" in p_meth:
            engine.log("Handling Amazon Cash on Delivery (Pay on Delivery)...", "ACTION")
            try:
                # Select COD radio
                for r in driver.find_elements(By.XPATH, "//input[@type='radio' and (@value='COD' or contains(@name, 'ppw-instrumentRowSelection') or contains(@id, 'cod'))] | //span[contains(text(), 'Cash on Delivery') or contains(text(), 'Pay on Delivery')]"):
                    if r.is_displayed():
                        self.click_element_hard(driver, r)
                        engine.log("Selected Amazon 'Cash on Delivery (Pay on Delivery)' option.", "SUCCESS")
                        break

                time.sleep(1.5)

                # Click Continue / Use this payment method
                for b in driver.find_elements(By.XPATH, "//input[@name='ppw-widgetEvent:SetPaymentPlanSelectContinueEvent'] | //input[contains(@value, 'Use this payment method')] | //button[contains(., 'Use this payment method') or contains(., 'Continue')]"):
                    if b.is_displayed():
                        self.click_element_hard(driver, b)
                        engine.log("Confirmed COD payment mode on Amazon.", "SUCCESS")
                        break

                time.sleep(2.5)

                # Click Place your order
                for po_btn in driver.find_elements(By.XPATH, "//input[contains(@value, 'Place your order') or contains(@name, 'placeYourOrder1')] | //button[contains(., 'Place your order')]"):
                    if po_btn.is_displayed():
                        self.click_element_hard(driver, po_btn)
                        engine.log("Clicked 'Place your order in COD' on Amazon!", "SUCCESS")
                        break
            except Exception as e:
                engine.log(f"Amazon COD step failed: {e}", "ERROR")
                raise

            # Watch for order confirmation
            confirmed, order_id = self.watch_order_confirmation(
                driver,
                extra_keywords=["order placed, thank you", "thank you for your order"],
                timeout=15,
            )
            engine.finish_flow(
                success=confirmed,
                status_title="Order Confirmed (Cash on Delivery)" if confirmed else "Order Placed - Awaiting Confirmation",
                reason=f"Amazon order confirmed! Order ID: {order_id}." if confirmed else "COD selected on Amazon. Please check the visible Chrome window.",
                card_last4="COD",
                product_name=product_name,
                status=None if confirmed else "awaiting_confirmation",
            )
            return True

        # ---------------- 2. UPI ----------------
        elif "upi" in p_meth:
            engine.log("Handling Amazon UPI payment.", "ACTION")
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
                        engine.log("Entered the configured Amazon UPI ID.", "SUCCESS")
                        break
                self.click_final_action(driver, ["verify", "continue", "pay now"])
            except Exception as e:
                engine.log(f"Amazon UPI step failed: {e}", "ERROR")
                raise

            with engine.lock:
                engine.state["status"] = "awaiting_upi_qr"
                engine.state["upi_qr_active"] = True

            engine.finish_flow(
                success=True,
                status_title="UPI Payment Gateway Active",
                reason="Amazon UPI collect request is active.",
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

            engine.log(f"Injecting card details on Amazon (ending in {card_last4})...", "ACTION")
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
                self.click_final_action(
                    driver,
                    ["place your order", "place order", "pay now"],
                )
            except Exception as e:
                engine.log(f"Amazon card step failed: {e}", "ERROR")
                raise

            confirmed, order_id = self.watch_order_confirmation(driver, timeout=12)
            engine.finish_flow(
                success=confirmed,
                status_title="Amazon Order Confirmed" if confirmed else "Amazon Payment Awaiting Authorization",
                reason=(
                    f"Amazon order confirmation detected{f' ({order_id})' if order_id else ''}."
                    if confirmed
                    else f"Card ending in {card_last4} was submitted. Complete any bank verification in the visible browser."
                ),
                card_last4=card_last4,
                product_name=product_name,
                status=None if confirmed else "awaiting_confirmation",
            )
            return True

