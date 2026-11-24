"""
Dedicated Flipkart Autonomous Payment System
Handles:
- Cash on Delivery (COD) auto-selection
- Hardware click 'Place Order' / 'Confirm Order' via CDP
- 3-character Captcha loop with real-time UI modal alert
- Real Order ID extraction (OD...) & orders.csv record
- UPI & Card injection
"""

import os
import csv
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By

from .base_payment import BasePaymentSystem, get_configured_card

logger = logging.getLogger("FlipkartPaymentSystem")


class FlipkartPaymentSystem(BasePaymentSystem):
    def __init__(self):
        super().__init__("Flipkart")

    def process_payment(
        self,
        driver,
        engine,
        product_name: str,
        payment_method: str = "cod",
        upi_id: str = "",
        card_index: int = 0,
        custom_card: Optional[Dict[str, Any]] = None,
        quantity: int = 1,
        customer_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Executes Flipkart final payment step according to selected payment method."""
        p_meth = (payment_method or "cod").lower()
        engine.log(f"Arrived on Flipkart Payment Stage. Selected Option: {p_meth.upper()}", "ACTION")

        with engine.lock:
            engine.state["current_step"] = 5
            engine.state["progress"] = 90

        # ---------------- 1. CASH ON DELIVERY (COD) ----------------
        if "cod" in p_meth:
            engine.log("Selecting 'Cash on Delivery (COD)' on Flipkart...", "ACTION")
            cod_el = self.find_by_text(driver, ["cash on delivery", "cod"])
            if not cod_el:
                for r in driver.find_elements(By.XPATH, "//*[(self::label or self::div or self::span or self::p or self::input) and (contains(., 'Cash on Delivery') or contains(., 'COD'))]"):
                    try:
                        if r.is_displayed():
                            cod_el = r
                            break
                    except Exception:
                        pass

            if cod_el:
                self.click_element_hard(driver, cod_el)
                engine.log("Cash on Delivery (COD) selected on Flipkart. Waiting for fee calculation...", "SUCCESS")

            time.sleep(2.0)

            # Step B: Click yellow 'Place Order' / 'Confirm Order' button via hardware mouse click
            place_order_clicked = False
            for attempt in range(6):
                place_order_el = self.find_by_text(driver, ["place order", "confirm order", "pay ₹", "continue"])
                if not place_order_el:
                    for xp in [
                        "//*[(self::button or self::div or self::a or self::span) and (translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')='PLACE ORDER' or translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')='CONFIRM ORDER')]",
                        "//*[contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'PLACE ORDER') and (self::button or self::div or self::a or self::span)]",
                        "//button[contains(., 'Place Order') or contains(., 'PLACE ORDER') or contains(., 'Confirm Order') or contains(., 'CONFIRM ORDER')]",
                        "//div[contains(@class, 'button') or contains(@class, 'btn') or contains(@class, 'QqFHMw')][contains(., 'Place Order') or contains(., 'Confirm Order')]",
                        "//span[contains(., 'Place Order') or contains(., 'CONFIRM ORDER')]"
                    ]:
                        try:
                            for cob in driver.find_elements(By.XPATH, xp):
                                if cob.is_displayed():
                                    place_order_el = cob
                                    break
                            if place_order_el:
                                break
                        except Exception:
                            pass

                if place_order_el:
                    self.click_element_hard(driver, place_order_el)
                    engine.log("SUCCESS: Clicked yellow 'Place Order' button via CDP hardware mouse event!", "SUCCESS")
                    place_order_clicked = True
                    break
                time.sleep(1.5)

            # Step C: Watch for Confirmation & Captcha Loop (up to 45 seconds)
            engine.log("Monitoring order confirmation and captcha verification...", "ACTION")
            order_confirmed = False
            confirmed_id = None
            deadline = time.time() + 45

            while time.time() < deadline:
                time.sleep(1.2)
                # Check if Flipkart requires 3-digit Captcha
                captcha_inputs = driver.find_elements(By.XPATH, "//input[@id='captcha' or contains(@placeholder, 'characters') or contains(@class, '_16q7du') or contains(@class, 'captcha')]")
                if any(ci.is_displayed() for ci in captcha_inputs):
                    engine.log("[ACTION REQUIRED] Flipkart displayed a 3-character Captcha. Please enter it in Chrome to confirm your order!", "ALERT")
                    with engine.lock:
                        engine.state["status"] = "awaiting_otp"
                        engine.state["otp_required"] = True
                        engine.state["otp_target"] = "3-Digit Captcha"
                    while any(ci.is_displayed() for ci in driver.find_elements(By.XPATH, "//input[@id='captcha' or contains(@placeholder, 'characters') or contains(@class, '_16q7du') or contains(@class, 'captcha')]")) and time.time() < deadline:
                        time.sleep(1.0)
                    # Click Confirm Order after captcha
                    for cb in driver.find_elements(By.XPATH, "//button[contains(., 'CONFIRM ORDER') or contains(., 'Confirm Order') or contains(., 'SUBMIT')]"):
                        if cb.is_displayed():
                            self.click_element_hard(driver, cb)
                            time.sleep(2)
                            break

                cur_body = driver.page_source
                cur_url = driver.current_url.lower()
                matches = self.watch_order_confirmation(driver, timeout=1)
                if matches[0]:
                    confirmed_id = matches[1]
                    order_confirmed = True
                    break

            if order_confirmed:
                engine.log(
                    f"FLIPKART ORDER CONFIRMED!{f' Order ID: {confirmed_id}' if confirmed_id else ''}",
                    "SUCCESS",
                )
                # Record to orders.csv
                if confirmed_id:
                    try:
                        orders_file = Path(
                            os.environ.get(
                                "AUTOMATION_ORDERS_FILE",
                                str(Path.home() / ".sale-fox" / "orders.csv"),
                            )
                        ).expanduser()
                        if not orders_file.parent.exists():
                            orders_file = Path(__file__).resolve().parent.parent / "orders.csv"
                        with open(orders_file, "a", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f)
                            writer.writerow([confirmed_id, engine.state.get("account", 1), product_name, quantity, "COD", time.strftime("%Y-%m-%d %H:%M:%S")])
                    except Exception as exc:
                        engine.log(f"Could not record the Flipkart order locally: {exc}", "WARNING")

                engine.finish_flow(
                    success=True,
                    status_title="Order Confirmed (Cash on Delivery)",
                    reason=(
                        f"Order successfully placed on Flipkart! Order ID: {confirmed_id}."
                        if confirmed_id
                        else "Flipkart order confirmation detected. Verify the order details in the browser."
                    ),
                    card_last4="COD",
                    product_name=product_name
                )
                return True
            else:
                engine.log("Notice: Order pending final confirmation or captcha in Chrome.", "ALERT")
                engine.finish_flow(
                    success=True,
                    status_title="Order Pending Final Confirmation",
                    reason=f"Checkout reached payment step. Please verify and confirm directly in the visible Chrome window on your desktop.",
                    card_last4="COD",
                    product_name=product_name,
                    status="awaiting_confirmation",
                )
                return True

        # ---------------- 2. UPI ----------------
        elif "upi" in p_meth:
            engine.log("Handling Flipkart UPI payment.", "ACTION")
            upi_el = self.find_by_text(driver, ["upi"])
            if upi_el:
                self.click_element_hard(driver, upi_el)
            else:
                for r in driver.find_elements(By.XPATH, "//label[contains(., 'UPI')] | //input[@type='radio' and contains(@value, 'UPI')]"):
                    if r.is_displayed():
                        driver.execute_script("arguments[0].click();", r)
                        break
            time.sleep(1)

            for u_inp in driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'UPI ID') or contains(@placeholder, 'VPA') or contains(@name, 'upi')]"):
                if u_inp.is_displayed():
                    u_inp.clear()
                    u_inp.send_keys(upi_id)
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", u_inp)
                    engine.log("Entered the configured Flipkart UPI ID.", "SUCCESS")
                    break

            for p_btn in driver.find_elements(By.XPATH, "//button[contains(., 'Pay') or contains(., 'CONTINUE') or contains(., 'Verify')]"):
                if p_btn.is_displayed():
                    self.click_element_hard(driver, p_btn)
                    break

            with engine.lock:
                engine.state["status"] = "awaiting_upi_qr"
                engine.state["upi_qr_active"] = True

            engine.finish_flow(
                success=True,
                status_title="UPI Payment Gateway Active",
                reason="Flipkart UPI payment request is active.",
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

            engine.log(f"Selecting Credit/Debit Cards on Flipkart (Card ending in {card_last4})...", "ACTION")
            card_tab = self.find_by_text(driver, ["credit / debit", "credit card", "debit card", "cards"])
            if card_tab:
                self.click_element_hard(driver, card_tab)
            time.sleep(1)

            # Inject card fields
            for el in driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'Card Number') or contains(@name, 'cardNumber') or contains(@id, 'cardNumber')]"):
                if el.is_displayed():
                    el.clear()
                    el.send_keys(card_num)
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", el)
                    break

            for el in driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'MM/YY') or contains(@placeholder, 'MM / YY') or contains(@name, 'expiry')]"):
                if el.is_displayed():
                    el.clear()
                    el.send_keys(c_obj["expiry"])
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", el)
                    break

            for el in driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'CVV') or contains(@name, 'cvv') or contains(@id, 'cvv')]"):
                if el.is_displayed():
                    el.clear()
                    el.send_keys(c_obj.get("cvv", "123"))
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", el)
                    break

            # Click Pay
            for pb_el in driver.find_elements(By.XPATH, "//button[contains(., 'PAY') or contains(., 'Pay') or contains(., 'Continue')]"):
                if pb_el.is_displayed():
                    self.click_element_hard(driver, pb_el)
                    engine.log("Submitted card payment to Flipkart. Awaiting 3D Secure / OTP handoff...", "SUCCESS")
                    break

            engine.finish_flow(
                success=True,
                status_title="Payment Gateway Awaiting Bank OTP",
                reason=f"Card ending in {card_last4} submitted. Please authorize transaction in the desktop Chrome window.",
                card_last4=card_last4,
                product_name=product_name,
                status="awaiting_confirmation",
            )
            return True

