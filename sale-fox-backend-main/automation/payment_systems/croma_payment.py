"""
Dedicated Croma Autonomous Payment System
Handles all 4 official Croma payment gateways:
1. Credit / Debit Cards (with virtual card PIN / password auto-fill)
2. EMI on Cards (Bank selection & tenure selection)
3. UPI (Instant VPA injection & Verify)
4. Netbanking (Primary bank selection & Pay Now)
5. Cash on Delivery (if enabled for pincode)
"""

import time
import logging
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By

from .base_payment import BasePaymentSystem, get_configured_card

logger = logging.getLogger("CromaPaymentSystem")


class CromaPaymentSystem(BasePaymentSystem):
    def __init__(self):
        super().__init__("Croma")

    def process_payment(
        self,
        driver,
        engine,
        product_name: str,
        payment_method: str = "cards",
        upi_id: str = "",
        card_index: int = 0,
        custom_card: Optional[Dict[str, Any]] = None,
        gst_number: str = "",
        customer_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Executes Croma final payment stage according to selected method."""
        with engine.lock:
            engine.state["current_step"] = 5
            engine.state["progress"] = 90

        p_meth = (payment_method or "cards").lower()
        engine.log(f"Arrived on Croma Payment Screen (croma.com/payment). Selected Payment Option: '{p_meth.upper()}'.", "ACTION")

        card_obj = None
        card_num = ""
        card_last4 = ""
        card_expiry = ""
        card_cvv = ""
        virtual_pass = ""
        if p_meth in {"cards", "card", "credit_debit", "emi"}:
            card_obj = get_configured_card(engine, card_index, custom_card)
            card_num = card_obj["number"].replace(" ", "")
            card_last4 = card_num[-4:]
            card_expiry = card_obj["expiry"]
            card_cvv = card_obj["cvv"]
            virtual_pass = card_obj.get("password") or card_obj.get("pin") or ""

        # ---------------- 1. CREDIT / DEBIT CARDS ----------------
        if "card" in p_meth or p_meth == "credit_debit":
            engine.log(f"Handling Croma Option 1: Credit / Debit Cards. Injecting Card ending in {card_last4}...", "ACTION")
            try:
                for tab in driver.find_elements(By.XPATH, "//div[contains(text(), 'Credit / Debit Cards')] | //span[contains(text(), 'Credit / Debit Cards')] | //li[contains(., 'Credit / Debit Cards')]"):
                    if tab.is_displayed():
                        self.click_element_hard(driver, tab)
                        time.sleep(1)
                        break

                # Inject Card Number
                for el in driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'card number') or contains(@id, 'card') or contains(@name, 'cardNumber') or contains(@name, 'card')]"):
                    if el.is_displayed():
                        el.clear()
                        el.send_keys(card_num)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", el)
                        engine.log(f"Card number populated (•••• •••• •••• {card_last4}).", "SUCCESS")
                        break

                # Inject Expiry
                for el in driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'MM/YY') or contains(@placeholder, 'MM / YY') or contains(@name, 'expiry') or contains(@id, 'expiry')]"):
                    if el.is_displayed():
                        el.clear()
                        el.send_keys(card_expiry)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", el)
                        break

                # Inject CVV
                for el in driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'CVV') or contains(@name, 'cvv') or contains(@id, 'cvv')]"):
                    if el.is_displayed():
                        el.clear()
                        el.send_keys(card_cvv)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", el)
                        break

                # Inject virtual password / PIN if available
                if virtual_pass:
                    engine.log(f"Virtual card PIN/Password loaded from CSV: {'•' * len(virtual_pass)}", "SUCCESS")
                    for p_el in driver.find_elements(By.XPATH, "//input[@type='password' or contains(@placeholder, 'password') or contains(@placeholder, 'PIN')]"):
                        if p_el.is_displayed():
                            p_el.clear()
                            p_el.send_keys(virtual_pass)
                            break

                time.sleep(1.5)

                # Click 'Place Order & Pay'
                submit_clicked = False
                for pay_b in driver.find_elements(By.XPATH, "//button[contains(., 'Place Order & Pay') or contains(., 'Pay Now')]"):
                    if pay_b.is_displayed():
                        submit_clicked = self.click_element_hard(driver, pay_b)
                        engine.log("Clicked 'Place Order & Pay' button on Croma!", "SUCCESS")
                        break
                if not submit_clicked:
                    raise RuntimeError("Croma did not expose a final card payment button.")
            except Exception as e:
                engine.log(f"Croma card payment step failed: {e}", "ERROR")
                raise

            # Check 3D secure handoff / confirmation
            confirmed, order_id = self.watch_order_confirmation(driver, timeout=10)
            engine.finish_flow(
                success=confirmed,
                status_title="Payment Gateway Handshake Complete" if not confirmed else "Croma Order Confirmed",
                reason=f"Card ending in {card_last4} submitted. Complete any bank verification in the visible browser." if not confirmed else f"Order placed successfully! ID: {order_id}",
                card_last4=card_last4,
                product_name=product_name,
                status=None if confirmed else "awaiting_confirmation",
            )
            return True

        # ---------------- 2. EMI ON CARDS ----------------
        elif "emi" in p_meth:
            engine.log("Handling Croma Option 2: EMI on Cards...", "ACTION")
            try:
                for tab in driver.find_elements(By.XPATH, "//div[contains(text(), 'EMI on Cards')] | //span[contains(text(), 'EMI on Cards')] | //li[contains(., 'EMI')]"):
                    if tab.is_displayed():
                        self.click_element_hard(driver, tab)
                        time.sleep(1.5)
                        break
                plan_selected = False
                for plan in driver.find_elements(By.XPATH, "//input[@name='emiPlan' or contains(@class, 'emi')] | //button[contains(., 'Select Plan')]"):
                    if plan.is_displayed():
                        plan_selected = self.click_element_hard(driver, plan)
                        break
                if not plan_selected:
                    raise RuntimeError("Croma did not expose an EMI plan selector.")
                self.fill_card_inputs(driver, engine, card_obj)
                self.click_final_action(driver, ["place order", "pay now", "place order & pay"])
                engine.log("Selected an EMI plan, filled the configured card, and submitted payment.", "SUCCESS")
            except Exception as e:
                engine.log(f"Croma EMI step failed: {e}", "ERROR")
                raise

            confirmed, order_id = self.watch_order_confirmation(driver, timeout=10)
            engine.finish_flow(
                success=confirmed,
                status_title="Croma EMI Order Confirmed" if confirmed else "Croma EMI Awaiting Authorization",
                reason=(
                    f"Order confirmation detected{f' ({order_id})' if order_id else ''}."
                    if confirmed
                    else f"EMI payment was submitted for {product_name}. Complete any bank verification in the visible browser."
                ),
                card_last4=card_last4,
                product_name=product_name,
                status=None if confirmed else "awaiting_confirmation",
            )
            return True

        # ---------------- 3. UPI ----------------
        elif "upi" in p_meth:
            engine.log("Handling Croma UPI payment.", "ACTION")
            try:
                for tab in driver.find_elements(By.XPATH, "//div[contains(text(), 'UPI')] | //span[contains(text(), 'UPI')] | //li[contains(., 'UPI')]"):
                    if tab.is_displayed():
                        self.click_element_hard(driver, tab)
                        time.sleep(1)
                        break
                upi_entered = False
                for u_inp in driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'UPI ID') or contains(@placeholder, 'VPA') or contains(@id, 'upi')]"):
                    if u_inp.is_displayed():
                        u_inp.clear()
                        u_inp.send_keys(upi_id)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", u_inp)
                        engine.log("Entered the configured Croma UPI ID.", "SUCCESS")
                        upi_entered = True
                        break
                if not upi_entered:
                    raise RuntimeError("Could not find a visible Croma UPI ID field.")
                self.click_final_action(driver, ["verify", "pay now", "continue"])
            except Exception as e:
                engine.log(f"Croma UPI step failed: {e}", "ERROR")
                raise

            with engine.lock:
                engine.state["status"] = "awaiting_upi_qr"
                engine.state["upi_qr_active"] = True

            engine.finish_flow(
                success=True,
                status_title="UPI Gateway Active",
                reason="Croma UPI payment request is active.",
                card_last4="UPI",
                product_name=product_name,
                status="awaiting_upi_qr",
            )
            return True

        # ---------------- 4. NETBANKING ----------------
        elif "netbanking" in p_meth or "bank" in p_meth:
            engine.log("Handling Croma Option 4: Netbanking. Selecting primary bank...", "ACTION")
            try:
                for tab in driver.find_elements(By.XPATH, "//div[contains(text(), 'Netbanking')] | //span[contains(text(), 'Netbanking')] | //li[contains(., 'Netbanking')]"):
                    if tab.is_displayed():
                        self.click_element_hard(driver, tab)
                        time.sleep(1)
                        break
                for b_radio in driver.find_elements(By.XPATH, "//input[@type='radio' and contains(@name, 'bank')] | //div[contains(@class, 'bank')]"):
                    if b_radio.is_displayed():
                        self.click_element_hard(driver, b_radio)
                        engine.log("Selected primary netbanking partner bank.", "SUCCESS")
                        break
                self.click_final_action(driver, ["pay now", "place order"])
            except Exception as e:
                engine.log(f"Croma netbanking step failed: {e}", "ERROR")
                raise

            engine.finish_flow(
                success=True,
                status_title="Netbanking Redirection Initialized",
                reason="Redirecting to selected partner bank portal.",
                card_last4="NETB",
                product_name=product_name,
                status="awaiting_confirmation",
            )
            return True

        # ---------------- 5. CASH ON DELIVERY (COD) ----------------
        else:
            engine.log("Checking Cash on Delivery option on Croma...", "ACTION")
            for cod_r in driver.find_elements(By.XPATH, "//input[contains(@value, 'COD') or contains(@id, 'cod')] | //label[contains(., 'Cash on Delivery') or contains(., 'COD')]"):
                if cod_r.is_displayed():
                    self.click_element_hard(driver, cod_r)
                    break
            time.sleep(1)
            for po_btn in driver.find_elements(By.XPATH, "//button[contains(., 'Place Order') or contains(., 'Confirm')]"):
                if po_btn.is_displayed():
                    self.click_element_hard(driver, po_btn)
                    break
            confirmed, order_id = self.watch_order_confirmation(driver, timeout=10)
            engine.finish_flow(
                success=confirmed,
                status_title="Order Confirmed (Cash on Delivery)" if confirmed else "Order Placed - Awaiting Confirmation",
                reason="Order confirmation detected." if confirmed else "COD selected. Check the open browser for confirmation.",
                card_last4="COD",
                product_name=product_name,
                status=None if confirmed else "awaiting_confirmation",
            )
            return True

