"""
Dedicated Samsung Official Store Autonomous Payment System
Handles:
- Samsung India (samsung.com/in/) payment checkout
- Cash on Delivery (COD), UPI, and Credit / Debit card selection
- Order progression and Samsung Order ID extraction
"""

import time
import logging
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By

from .base_payment import BasePaymentSystem, get_configured_card

logger = logging.getLogger("SamsungPaymentSystem")


class SamsungPaymentSystem(BasePaymentSystem):
    def __init__(self):
        super().__init__("Samsung")

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
        """Executes Samsung India checkout payment stage."""
        with engine.lock:
            engine.state["current_step"] = 5
            engine.state["progress"] = 90

        p_meth = (payment_method or "cod").lower()
        engine.log(f"Arrived on Samsung Payment Stage. Method: {p_meth.upper()}", "ACTION")

        try:
            card = None
            if "cod" in p_meth:
                for el in driver.find_elements(By.XPATH, "//div[contains(., 'Cash on Delivery') or contains(., 'COD')] | //input[@value='COD']"):
                    if el.is_displayed():
                        self.click_element_hard(driver, el)
                        engine.log("Selected Samsung Cash on Delivery option.", "SUCCESS")
                        break
            elif "upi" in p_meth:
                for el in driver.find_elements(By.XPATH, "//div[contains(., 'UPI')] | //input[contains(@value, 'UPI')]"):
                    if el.is_displayed():
                        self.click_element_hard(driver, el)
                        engine.log("Selected Samsung UPI option.", "SUCCESS")
                        break
                upi_input = next(
                    (
                        element
                        for element in driver.find_elements(
                            By.XPATH,
                            "//input[contains(@placeholder, 'UPI') or contains(@placeholder, 'VPA') or contains(@name, 'upi')]",
                        )
                        if element.is_displayed()
                    ),
                    None,
                )
                if upi_input is None:
                    raise RuntimeError("Could not find a visible Samsung UPI ID field.")
                upi_input.clear()
                upi_input.send_keys(upi_id)
            else:
                card = get_configured_card(engine, card_index, custom_card)
                self.fill_card_inputs(driver, engine, card)

            action = self.click_final_action(
                driver,
                ["place your order", "place order", "confirm order", "pay now", "make payment", "verify"],
            )
            engine.log(f"Submitted Samsung checkout using the {action} control.", "SUCCESS")
            if "upi" in p_meth:
                engine.finish_flow(
                    success=True,
                    status_title="Samsung UPI Awaiting Authorization",
                    reason="UPI request submitted. Complete the payment in your UPI app or the visible browser.",
                    card_last4="UPI",
                    product_name=product_name,
                    status="awaiting_upi_qr",
                )
                return True

            confirmed, order_id = self.watch_order_confirmation(driver, timeout=12)
            card_last4 = str((card or {}).get("last4") or (card or {}).get("number", "")[-4:])
            engine.finish_flow(
                success=confirmed,
                status_title="Samsung Order Confirmed" if confirmed else "Samsung Checkout Awaiting Confirmation",
                reason=(
                    f"Order confirmation detected{f' ({order_id})' if order_id else ''}."
                    if confirmed
                    else "Final order action submitted. Complete any store or bank verification in the visible browser."
                ),
                card_last4=card_last4 or "COD",
                product_name=product_name,
                status=None if confirmed else "awaiting_confirmation",
            )
            return True
        except Exception as e:
            engine.log(f"Samsung payment step failed: {e}", "ERROR")
            raise
