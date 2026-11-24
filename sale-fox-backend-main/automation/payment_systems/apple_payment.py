"""
Dedicated Apple Official Store Autonomous Payment System
Handles:
- Credit / Debit Card & Netbanking progression on Apple India (apple.com/in/)
- Apple bag to guest checkout progression
- Order progression and Order Number extraction
"""

import time
import logging
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By

from .base_payment import BasePaymentSystem, get_configured_card

logger = logging.getLogger("ApplePaymentSystem")


class ApplePaymentSystem(BasePaymentSystem):
    def __init__(self):
        super().__init__("Apple")

    def process_payment(
        self,
        driver,
        engine,
        product_name: str,
        payment_method: str = "cards",
        upi_id: str = "",
        card_index: int = 0,
        custom_card: Optional[Dict[str, Any]] = None,
        customer_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Executes Apple India checkout payment stage."""
        with engine.lock:
            engine.state["current_step"] = 5
            engine.state["progress"] = 90

        p_meth = (payment_method or "cards").lower()
        engine.log(f"Arrived on Apple Store Payment Stage. Method: {p_meth.upper()}", "ACTION")

        card = get_configured_card(engine, card_index, custom_card)

        try:
            # Look for Credit / Debit Card radio on Apple payment screen
            card_radio = driver.find_elements(By.XPATH, "//input[@type='radio' and (contains(@value, 'credit') or contains(@id, 'creditCard') or contains(@name, 'paymentMethod'))]")
            for r in card_radio:
                if r.is_displayed():
                    self.click_element_hard(driver, r)
                    engine.log("Selected Apple Card Payment option.", "SUCCESS")
                    break

            time.sleep(1.5)
            self.fill_card_inputs(driver, engine, card)
            self.click_final_action(
                driver,
                ["place your order", "place order", "pay now", "submit order"],
            )
            confirmed, order_id = self.watch_order_confirmation(driver, timeout=12)
            engine.finish_flow(
                success=confirmed,
                status_title="Apple Order Confirmed" if confirmed else "Apple Payment Awaiting Authorization",
                reason=(
                    f"Apple order confirmation detected{f' ({order_id})' if order_id else ''}."
                    if confirmed
                    else "Payment was submitted. Complete any bank verification in the visible browser."
                ),
                card_last4=str(card.get("last4") or card.get("number", "")[-4:]),
                product_name=product_name,
                status=None if confirmed else "awaiting_confirmation",
            )
            return True
        except Exception as e:
            engine.log(f"Apple payment step failed: {e}", "ERROR")
            raise
