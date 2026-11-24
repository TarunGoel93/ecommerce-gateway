import re
import json

raw_amazon_text = """
Offer 1
Additional flat INR 750 Instant Discount on SBI Credit Card EMI Trxn. Minimum purchase value INR 34990.00 See details

See details
Offer 2
Additional flat INR 1000 Instant Discount on SBI Credit Card EMI Trxn. Minimum purchase value INR 49990.00 See details

See details
Offer 3
Additional flat INR 500 Instant Discount on SBI Credit Card EMI Trxn. Minimum purchase value INR 24990.00 See details

See details
Offer 4
10% Instant Discount up to INR 1000 on SBI Credit Card EMI Trxn. Minimum purchase value INR 5000.00 See details

See details
Offer 5
Additional flat INR 250 Instant Discount up to on HDFC Bank Credit Card 9 months and above EMI Trxn. Min purchase value INR 15000.00 See details

See details
Offer 6
Additional flat INR 1750 Instant Discount on HDFC Bank Credit Card 6 month and above EMI Trxn. Min purchase value INR 50000.00 See details

See details
Offer 7
Additional flat INR 250 Instant Discount on HDFC Bank Credit Card 9 month and above EMI Trxn. Min purchase value INR 50000.00 See details

See details
Offer 8
Flat Instant Discount up to INR 1250 on HDFC Bank Credit Card 6 month and above EMI Trxn. Min purchase value INR 15000.00 See details

See details
Offer 9
Additional flat INR 250 Instant Discount on HDFC Bank Credit Card 12 month and above EMI Trxn. Min purchase value INR 50000.00 See details

See details
Offer 10
Additional flat INR 250 Instant Discount on HDFC Bank Credit Card 12 month and above EMI Trxn. Min purchase value INR 15000.00 See details

See details
Offer 11
10% Instant Discount up to INR 1000 on IDFC FIRST Bank Credit Card EMI Trxn. Minimum purchase value INR 10000.00 See details

See details
Offer 12
Additional flat INR 1250 Instant Discount on Axis Bank Credit Card EMI Trxn. Min purchase value INR 44990.00 See details

See details
Offer 13
Additional flat INR 500 Instant Discount on Axis Bank Credit Card EMI Trxn. Min purchase value INR 24990.00 See details

See details
Offer 14
Additional flat INR 250 Instant Discount on Axis Bank Credit Card EMI Trxn. Min purchase value INR 19990.00 See details

See details
Offer 15
10% Instant Discount up to INR 1000 on J and K Mastercard Credit Card Non-EMI Trnxs. Minimum purchase value INR 5000.00 See details

See details
Offer 16
10% Instant Discount up to INR 1000 on IndusInd Bank Credit Card EMI Trxn. Minimum purchase value INR 5000.00 See details

See details
Offer 17
10% Instant Discount up to INR 1250 on Axis Bank Credit Card EMI Trxn. Minimum purchase value INR 4990.00 See details

See details
Offer 18
10% Instant Discount up to INR 750 on RBL Bank Credit Card EMI Trxn. Minimum purchase value INR 7490.00 See details

See details
Offer 19
10% Instant Discount up to INR 1000 on PNB Mastercard Debit Card Non-EMI Trxn. Minimum purchase value INR 5000.00 See details

See details
Offer 20
7% Instant Discount up to INR 750 on PNB LUXURA Credit Card Non-EMI Trxn. Minimum purchase value INR 4990.00 See details

See details
Offer 21
7.5% Instant Discount up to INR 1000 on Kotak Bank Credit Card EMI Trxn. Minimum purchase value INR 10000.00 See details

See details
Offer 22
Additional INR 750 Instant Discount on IndusInd Bank Credit Card EMI Trxn. Minimum purchase value INR 34990.00 See details

See details
Offer 23
7% Instant Discount up to INR 600 on Punjab National Bank Credit Card Non-EMI Trxn. Minimum purchase value INR 4990.00 See details

See details
Offer 24
Additional flat INR 750 Instant Discount on PNB LUXURA Credit Card on Non-EMI Trxn. Min purchase value INR 14990.00 See details

See details
Offer 25
Additional flat INR 2000 Instant Discount on PNB Bank Credit Card on Non-EMI Trxn. Min purchase value INR 49990.00 See details

See details
Offer 26
10% Instant Discount up to INR 2000 on Indian Bank Credit Card Trxn. Minimum purchase value INR 4999.00 See details

See details
Offer 27
Additional INR 1000 Instant Discount on IndusInd Bank Credit Card EMI Trxn. Minimum purchase value INR 49990.00 See details

See details
Offer 28
Additional flat INR 1000 Instant Discount on PNB Bank Credit Card on Non-EMI Trxn. Min purchase value INR 24990.00 See details

See details
Offer 29
Additional up to INR 1000 Instant Discount on Indian Bank Credit Card Trxn. Minimum purchase value INR 54990.00 See details

See details
Offer 30
Additional up to INR 1000 Instant Discount on Indian Bank Credit Card Trxn. Minimum purchase value INR 39990.00 See details

See details
Offer 31
Additional Flat INR 1000 Instant Discount on Indian Bank Credit Card Trxn. Minimum purchase value INR 49990.00 See details

See details
Offer 32
Additional flat INR 600 Instant Discount on PNB Bank Credit Card on Non-EMI Trxn. Min purchase value INR 14990.00 See details

See details
Offer 33
Additional Flat INR 1500 Instant Discount on Indian Bank Credit Card Trxn. Minimum purchase value INR 69990.00 See details

See details
Offer 34
Additional Flat INR 1500 Instant Discount on Indian Bank Credit Card Trxn. Minimum purchase value INR 84990.00 See details

See details
Offer 35
Additional flat INR 2500 Instant Discount on PNB LUXURA Credit Card on Non-EMI Trxn. Min purchase value INR 49990.00 See details

See details
Offer 36
Additional flat INR 1250 Instant Discount on PNB LUXURA Credit Card on Non-EMI Trxn. Min purchase value INR 24990.00 See details

See details
Offer 37
Additional INR 500 Instant Discount on IndusInd Bank Credit Card EMI Trxn. Minimum purchase value INR 24990.00 See details

See details
Offer 38
Additional INR 500 Instant Discount on Kotak Bank Credit Card on 6 months and above EMI Trxn. Minimum purchase value INR 24990.00 See details

See details
Offer 39
Additional up to INR 500 Instant Discount on Indian Bank Credit Card Trxn. Minimum purchase value INR 24990.00 See details

See details
Offer 40
Additional Flat INR 500 Instant Discount on Indian Bank Credit Card Trxn. Minimum purchase value INR 34990.00 See details

See details
Offer 41
Additional Flat INR 500 Instant Discount on RBL Bank Credit Card EMI Trxn. Minimum purchase value INR 24990.00 See details

See details
Offer 42
5% Instant Discount up to INR 1500 on Scapia Federal Bank Credit Card EMI Trnxs. Min purchase value INR 10000.00 See details

See details
Offer 43
Additional Flat INR 250 Instant Discount on Indian Bank Credit Card Trxn. Minimum purchase value INR 17490.00 See details

See details
Offer 44
Additional Flat INR 250 Instant Discount on Indian Bank Credit Card Trxn. Minimum purchase value INR 14990.00 See details

See details
Offer 45
Additional INR 1000 Instant Discount on IDFC FIRST Bank 6 month and above EMI Trxn. Minimum purchase value INR 49990.00 See details

See details
Offer 46
Additional INR 750 Instant Discount on IDFC FIRST Bank 6 month and above EMI Trxn. Minimum purchase value INR 34990.00 See details

See details
Offer 47
7.5% Instant Discount up to INR 3000 on Yes Bank Credit Card EMI Trxn. Minimum purchase value INR 4990.00 See details

See details
Offer 48
Additional flat INR 1000 Instant Discount on HSBC Taj Credit Card on Non-EMI Trxn. Min purchase value INR 49990.00 See details

See details
Offer 49
Additional flat INR 1000 Instant Discount on HSBC Taj Credit Card on Non-EMI Trxn. Min purchase value INR 74990.00 See details

See details
Offer 50
20% Instant Discount up to INR 3000 on HSBC Taj Credit Card Non-EMI Trxn. Minimum purchase value INR 10000.00 See details
"""

def parse_amazon_offers(text):
    offers = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^Offer\s+(\d+)$", line, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            i += 1
            desc_parts = []
            while i < len(lines) and not re.match(r"^Offer\s+\d+$", lines[i], re.IGNORECASE):
                if lines[i] != "See details":
                    desc_parts.append(lines[i])
                i += 1
            full_desc = " ".join(desc_parts).strip()
            offers.append((num, full_desc))
        else:
            i += 1
    return offers

parsed = parse_amazon_offers(raw_amazon_text)
print(f"Total parsed Amazon offers: {len(parsed)}")

def classify_offer(num, desc):
    # Detect Bank
    bank = "Bank Offer"
    bank_icon = "🏦"
    tag_color = "#2563eb"
    if "SBI" in desc:
        bank = "SBI"
        bank_icon = "🏦"
        tag_color = "#0284c7"
    elif "HDFC" in desc:
        bank = "HDFC"
        bank_icon = "🏛️"
        tag_color = "#1d4ed8"
    elif "Axis" in desc:
        bank = "Axis Bank"
        bank_icon = "💳"
        tag_color = "#991b1b"
    elif "IDFC" in desc:
        bank = "IDFC FIRST"
        bank_icon = "🏢"
        tag_color = "#b91c1c"
    elif "IndusInd" in desc:
        bank = "IndusInd"
        bank_icon = "💳"
        tag_color = "#831843"
    elif "PNB" in desc or "Punjab National Bank" in desc:
        bank = "PNB"
        bank_icon = "🏛️"
        tag_color = "#c2410c"
    elif "Kotak" in desc:
        bank = "Kotak"
        bank_icon = "🏦"
        tag_color = "#dc2626"
    elif "Indian Bank" in desc:
        bank = "Indian Bank"
        bank_icon = "🏦"
        tag_color = "#15803d"
    elif "RBL" in desc:
        bank = "RBL Bank"
        bank_icon = "💳"
        tag_color = "#4338ca"
    elif "Scapia" in desc or "Federal" in desc:
        bank = "Scapia Federal"
        bank_icon = "💳"
        tag_color = "#047857"
    elif "Yes Bank" in desc:
        bank = "Yes Bank"
        bank_icon = "🏦"
        tag_color = "#0369a1"
    elif "HSBC" in desc:
        bank = "HSBC Taj"
        bank_icon = "💎"
        tag_color = "#b45309"
    elif "J and K" in desc:
        bank = "J&K Bank"
        bank_icon = "💳"
        tag_color = "#0f766e"

    # Detect Discount type & amount
    disc_type = "flat"
    disc_amount = 0
    disc_percent = 0
    max_disc = 0

    pct_m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*Instant\s*Discount\s*up\s*to\s*(?:INR|Rs\.?)\s*(\d+(?:\.\d+)?)", desc, re.I)
    if pct_m:
        disc_type = "percentage"
        disc_percent = float(pct_m.group(1))
        max_disc = float(pct_m.group(2))
    else:
        flat_m = re.search(r"(?:flat|up to|Additional|Instant Discount)?\s*(?:INR|Rs\.?)\s*(\d+(?:\.\d+)?)\s*Instant Discount", desc, re.I)
        if flat_m:
            disc_amount = float(flat_m.group(1))
        else:
            flat_m2 = re.search(r"(?:INR|Rs\.?)\s*(\d+(?:\.\d+)?)", desc, re.I)
            if flat_m2:
                disc_amount = float(flat_m2.group(1))

    # Min purchase
    min_order = 5000
    min_m = re.search(r"Min(?:imum)?\s*purchase\s*value\s*(?:INR|Rs\.?)\s*(\d+(?:\.\d+)?)", desc, re.I)
    if min_m:
        min_order = float(min_m.group(1))

    # EMI type
    is_emi = "Non-EMI" not in desc and "EMI" in desc
    emi_label = "EMI Offer" if is_emi else ("Non-EMI" if "Non-EMI" in desc else "Card Offer")

    # Tag
    tag = "INSTANT OFF"
    if is_emi:
        tag = "EMI SPECIAL"
    elif "LUXURA" in desc or "Taj" in desc:
        tag = "PREMIUM CARD"
    elif disc_percent >= 10 or disc_amount >= 1500:
        tag = "SUPER DEAL"

    title = f"{bank} ₹{int(disc_amount or max_disc)} Off"
    if disc_percent > 0:
        title = f"{bank} {disc_percent}% Off"

    return {
        "id": f"amz_live_{num}",
        "offerNumber": num,
        "bank": bank,
        "bankIcon": bank_icon,
        "title": title,
        "tag": tag,
        "tagColor": tag_color,
        "discountType": disc_type,
        "discountPercent": disc_percent,
        "discountAmount": disc_amount,
        "maxDiscount": max_disc,
        "minOrder": int(min_order),
        "emiType": emi_label,
        "description": desc,
        "terms": f"Valid on {bank} cards. Minimum transaction value ₹{int(min_order):,}. Automatically applied at final checkout.",
    }

structured_offers = [classify_offer(num, desc) for num, desc in parsed]
print(f"Structured {len(structured_offers)} Amazon offers successfully.")
print("Sample first offer:", json.dumps(structured_offers[0], indent=2))
print("Sample offer 4 (percentage):", json.dumps(structured_offers[3], indent=2))

# Save to a json file so both JS and Python can import/use it
with open("amazon_50_bank_offers.json", "w", encoding="utf-8") as f:
    json.dump(structured_offers, f, indent=2)
print("Saved to amazon_50_bank_offers.json")

