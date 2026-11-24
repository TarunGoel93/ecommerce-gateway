"""Store-specific payment processors used by the unified automation API."""

from typing import Any, Dict, Optional

from .base_payment import BasePaymentSystem, DEFAULT_CARDS, get_configured_card, load_cards
from .flipkart_payment import FlipkartPaymentSystem
from .croma_payment import CromaPaymentSystem
from .amazon_payment import AmazonPaymentSystem
from .reliance_payment import ReliancePaymentSystem
from .jiomart_payment import JioMartPaymentSystem
from .vivo_payment import VivoPaymentSystem
from .apple_payment import ApplePaymentSystem
from .samsung_payment import SamsungPaymentSystem


PAYMENT_SYSTEMS: Dict[str, BasePaymentSystem] = {
    "flipkart": FlipkartPaymentSystem(),
    "croma": CromaPaymentSystem(),
    "amazon": AmazonPaymentSystem(),
    "reliance": ReliancePaymentSystem(),
    "jiomart": JioMartPaymentSystem(),
    "vivo": VivoPaymentSystem(),
    "apple": ApplePaymentSystem(),
    "samsung": SamsungPaymentSystem(),
}

PAYMENT_METHODS_BY_PLATFORM: Dict[str, list[str]] = {
    "amazon": ["cod", "upi", "cards"],
    "apple": ["cards"],
    "croma": ["cards", "emi", "upi", "netbanking", "cod"],
    "flipkart": ["cod", "upi", "cards"],
    "jiomart": ["cod", "upi", "cards"],
    "reliance": ["cod", "upi", "cards"],
    "samsung": ["cod", "upi", "cards"],
    "vivo": ["cod", "upi", "cards"],
}


def get_payment_system(brand_name: str) -> BasePaymentSystem:
    """Return the dedicated processor or fail for an unsupported platform."""
    brand_key = str(brand_name).strip().lower()
    aliases = {"reliance digital": "reliance", "jio mart": "jiomart"}
    key = aliases.get(brand_key, brand_key)
    if key not in PAYMENT_SYSTEMS:
        raise ValueError(f"No payment automation is configured for {brand_name!r}.")
    return PAYMENT_SYSTEMS[key]


def handle_platform_payment(
    platform: str,
    driver,
    engine,
    product_name: str,
    payment_method: str = "cards",
    upi_id: str = "",
    card_index: int = 0,
    custom_card: Optional[Dict[str, Any]] = None,
    quantity: int = 1,
    gst_number: str = "",
    customer_info: Optional[Dict[str, Any]] = None,
) -> bool:
    """Validate the selected store/method and delegate to its processor."""
    platform_key = str(platform).strip().lower()
    aliases = {"reliance digital": "reliance", "jio mart": "jiomart"}
    platform_key = aliases.get(platform_key, platform_key)
    payment_method = str(payment_method).strip().lower()
    supported_methods = PAYMENT_METHODS_BY_PLATFORM.get(platform_key)
    if supported_methods is None:
        raise ValueError(f"No payment automation is configured for {platform!r}.")
    if payment_method not in supported_methods:
        raise ValueError(
            f"{payment_method!r} payment is not supported for {platform_key}."
        )
    if payment_method == "upi" and not upi_id.strip():
        raise ValueError("A UPI ID is required for UPI payment.")
    if payment_method in {"cards", "card", "credit_debit", "emi"}:
        get_configured_card(engine, card_index, custom_card)

    processor = get_payment_system(platform_key)
    common: Dict[str, Any] = {
        "driver": driver,
        "engine": engine,
        "product_name": product_name,
        "payment_method": payment_method,
        "upi_id": upi_id,
        "card_index": card_index,
        "custom_card": custom_card,
        "customer_info": customer_info,
    }
    if platform_key == "flipkart":
        common["quantity"] = quantity
    elif platform_key == "croma":
        common["gst_number"] = gst_number
    if not processor.process_payment(**common):
        raise RuntimeError(f"The {platform_key} payment flow did not complete successfully.")
    return True


__all__ = [
    "BasePaymentSystem",
    "load_cards",
    "get_configured_card",
    "DEFAULT_CARDS",
    "FlipkartPaymentSystem",
    "CromaPaymentSystem",
    "AmazonPaymentSystem",
    "ReliancePaymentSystem",
    "JioMartPaymentSystem",
    "VivoPaymentSystem",
    "ApplePaymentSystem",
    "SamsungPaymentSystem",
    "PAYMENT_SYSTEMS",
    "PAYMENT_METHODS_BY_PLATFORM",
    "get_payment_system",
    "handle_platform_payment",
]
