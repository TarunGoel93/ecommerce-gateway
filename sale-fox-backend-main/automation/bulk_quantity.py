"""Fail-closed quantity selection helpers shared by checkout pipelines."""

import re
import time
from typing import Any

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

MAX_BULK_QUANTITY = 10

_STORE_SELECTORS = {
    "amazon": (
        "select#quantity",
        "select[name='quantity']",
        "input#quantity",
        "input[name*='quantity' i]",
    ),
    "apple": (
        "select[name*='quantity' i]",
        "select[id*='quantity' i]",
        "input[name*='quantity' i]",
        "input[id*='quantity' i]",
        "select[aria-label*='quantity' i]",
        "input[aria-label*='quantity' i]",
    ),
    "croma": (
        "select[name*='quantity' i]",
        "select[id*='quantity' i]",
        "input[name*='quantity' i]",
        "input[id*='quantity' i]",
        "input[class*='quantity' i]",
    ),
    "flipkart": (
        "select[name*='quantity' i]",
        "input[name*='quantity' i]",
        "input[aria-label*='quantity' i]",
        "input[class*='qty' i]",
    ),
    "jiomart": (
        "input[class*='qty' i]",
        "input[id*='qty' i]",
        "input[name*='qty' i]",
        "input[name*='quantity' i]",
        "[class*='qty' i][class*='value' i]",
        "[class*='quantity' i][class*='value' i]",
        "[class*='qty' i]",
        "[class*='quantity' i]",
    ),
    "reliance": (
        "select[name*='quantity' i]",
        "input[name*='quantity' i]",
        "input[name*='qty' i]",
        "input[class*='qty' i]",
    ),
    "samsung": (
        "input[class*='quantity' i]",
        "input[class*='qty' i]",
        "[class*='quantity']",
        "[class*='qty']",
    ),
    "vivo": (
        "input.quantity",
        "input.qty",
        ".cart-item input[type='number']",
        "input[name*='quantity' i]",
        "input[name*='qty' i]",
    ),
}

_GENERIC_SELECTORS = (
    "select[name*='quantity' i]",
    "select[id*='quantity' i]",
    "select[class*='quantity' i]",
    "select[aria-label*='quantity' i]",
    "input[name*='quantity' i]",
    "input[id*='quantity' i]",
    "input[class*='quantity' i]",
    "input[aria-label*='quantity' i]",
    "input[name*='qty' i]",
    "input[id*='qty' i]",
    "input[class*='qty' i]",
    "input[aria-label*='qty' i]",
    "[class*='quantity' i][class*='value' i]",
    "[class*='qty' i][class*='value' i]",
)

_JIOMART_PRODUCT_QUANTITY_SCRIPT = """
const tokens = arguments[0], threshold = 0.6;
const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
const skip = new Set(['SCRIPT','STYLE','NOSCRIPT','HEAD','TITLE','META','LINK']);
function findQty(root) {
  for (const e of root.querySelectorAll('input,span,div,p,b,strong')) {
    if (!visible(e)) continue;
    if (e.tagName === 'INPUT') {
      if (/^\\d{1,2}$/.test((e.value || '').trim())) return e;
      continue;
    }
    if (e.children.length === 0 && /^\\d{1,2}$/.test((e.innerText || '').trim())) return e;
  }
  return null;
}
for (const element of document.querySelectorAll('body *')) {
  if (skip.has(element.tagName) || !visible(element)) continue;
  const text = (element.innerText || '').trim();
  if (text.length < 8 || text.length > 160) continue;
  const words = new Set(text.toLowerCase().replace(/[^a-z0-9]+/g, ' ').split(' '));
  const matches = tokens.filter(token => words.has(token)).length;
  if (!tokens.length || matches / tokens.length < threshold) continue;
  let ancestor = element;
  for (let depth = 0; depth < 7 && ancestor; depth++) {
    ancestor = ancestor.parentElement;
    if (!ancestor) break;
    const quantity = findQty(ancestor);
    if (quantity) return quantity;
  }
}
return null;
"""


class BulkQuantityError(RuntimeError):
    """Raised when the store cannot confirm the exact requested quantity."""


def _read_quantity(element: Any) -> int | None:
    value = element.get_attribute("value") or element.text
    match = re.fullmatch(r"\s*(?:qty|quantity)?\s*[:x]?\s*(\d+)\s*", value or "", re.I)
    return int(match.group(1)) if match else None


def _find_visible_quantity_elements(driver: Any, store_key: str, product_name: str) -> list[Any]:
    elements: list[Any] = []
    seen: set[str] = set()
    selectors = (*_STORE_SELECTORS.get(store_key, ()), *_GENERIC_SELECTORS)
    if store_key == "jiomart":
        tokens = re.findall(r"[a-z0-9]+", product_name.lower())
        quantity_element = driver.execute_script(_JIOMART_PRODUCT_QUANTITY_SCRIPT, tokens)
        return [quantity_element] if quantity_element is not None else []

    for selector in selectors:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            if element.is_displayed() and element.tag_name.lower() in {"input", "select"}:
                identity = getattr(element, "id", None) or repr(element)
                if identity not in seen:
                    seen.add(identity)
                    elements.append(element)
    if elements:
        return elements

    for selector in selectors:
        if selector.startswith(("input", "select")):
            continue
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            if element.is_displayed() and _read_quantity(element) is not None:
                identity = getattr(element, "id", None) or repr(element)
                if identity not in seen:
                    seen.add(identity)
                    elements.append(element)
    return elements


def _stepper_buttons(driver: Any, quantity_element: Any) -> tuple[Any | None, Any | None]:
    controls = driver.execute_script(
        """
        let node = arguments[0];
        for (let depth = 0; node && depth < 6; depth++) {
          const parent = node.parentElement;
          if (!parent) break;
          const buttons = [...parent.querySelectorAll('button,[role="button"]')];
          const plus = buttons.find(button => {
            const label = `${button.getAttribute('aria-label') || ''} ${button.textContent || ''} ${button.className || ''}`.toLowerCase();
            return /increase|increment|plus/.test(label) || button.textContent.trim() === '+';
          });
          const minus = buttons.find(button => {
            const label = `${button.getAttribute('aria-label') || ''} ${button.textContent || ''} ${button.className || ''}`.toLowerCase();
            return /decrease|decrement|minus/.test(label) || button.textContent.trim() === '-';
          });
          if (plus || minus) return { plus, minus };
          const siblings = [...parent.children];
          const index = siblings.indexOf(node);
          if (index >= 0 && siblings.length >= 3) {
            return { plus: siblings[index + 1], minus: siblings[index - 1] };
          }
          node = parent;
        }
        return null;
        """,
        quantity_element,
    )
    return (controls or {}).get("plus"), (controls or {}).get("minus")


def set_checkout_quantity(driver: Any, store: str, quantity: int, product_name: str = "") -> int:
    """Set and verify quantity on the current product/cart page, or fail closed."""
    if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= MAX_BULK_QUANTITY:
        raise ValueError(f"quantity must be an integer from 1 to {MAX_BULK_QUANTITY}.")

    store_key = store.strip().lower().replace(" digital", "").replace(" ", "")
    elements = _find_visible_quantity_elements(driver, store_key, product_name)
    if len(elements) > 1:
        raise BulkQuantityError(
            f"{store} has multiple visible quantity controls. Clean the cart and retry; "
            "checkout was stopped before payment."
        )

    for element in elements:
        if element.tag_name.lower() == "select":
            options = Select(element).options
            option_values = {option.get_attribute("value") for option in options}
            target = str(quantity)
            if target not in option_values:
                continue
            Select(element).select_by_value(target)
        elif (
            element.tag_name.lower() == "input"
            and not element.get_attribute("disabled")
            and not element.get_attribute("readonly")
        ):
            element.clear()
            element.send_keys(str(quantity), Keys.TAB)
            driver.execute_script(
                "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                element,
            )

        time.sleep(0.25)
        if _read_quantity(element) == quantity:
            return quantity

    for element in elements:
        current = _read_quantity(element)
        if current is None or current == quantity:
            continue
        plus_button, minus_button = _stepper_buttons(driver, element)
        if current < quantity and plus_button is None:
            continue
        if current > quantity and minus_button is None:
            continue

        for _ in range(abs(quantity - current)):
            button = plus_button if current < quantity else minus_button
            if button is None or not button.is_enabled():
                break
            button.click()
            time.sleep(0.25)
            current = _read_quantity(element)
            if current is None:
                break
            if current == quantity:
                return quantity
            plus_button, minus_button = _stepper_buttons(driver, element)

    raise BulkQuantityError(
        f"{store} did not expose a quantity control that could be set and verified at {quantity}. "
        "Checkout was stopped before payment."
    )
