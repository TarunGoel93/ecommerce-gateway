import React, { useState } from "react";
import "./ProductInfo.css";
import {
  getProductOffers,
  getBestBankOffer,
  getCrossPlatformComparison,
  formatINR,
} from "../services/offersService";

export default function ProductInfo({
  product,
  allProducts = [],
  onBack,
  onOpenBankOffers,
  onOpenAutomation,
}) {
  const [selectedImage, setSelectedImage] = useState(product?.image);
  const [pincodeInput, setPincodeInput] = useState("110058");
  const [pincodeStatus, setPincodeStatus] = useState("Delivery available by tomorrow (Free)");

  if (!product) {
    return (
      <main className="main-content product-page-view">
        <div className="product-page-empty">
          <p>No product selected.</p>
          <button type="button" className="pdp-back-btn" onClick={onBack}>
            ← Back to Products
          </button>
        </div>
      </main>
    );
  }

  const offers = getProductOffers(product);
  const bestOffer = getBestBankOffer(product);
  const comparisons = getCrossPlatformComparison(product, allProducts);

  const priceNum =
    typeof product.priceNum === "number" && product.priceNum > 0
      ? product.priceNum
      : offers[0]?.effectivePrice || 25499;

  const bestSavings = bestOffer ? bestOffer.calculatedDiscount : 1000;
  const effectivePrice = Math.max(0, priceNum - bestSavings);

  const galleryImages = [
    product.image,
    product.image,
    product.image,
  ].filter(Boolean);

  const handleCheckPincode = (e) => {
    e.preventDefault();
    if (pincodeInput.trim().length === 6) {
      setPincodeStatus(`Available for delivery at ${pincodeInput} in 1-2 days!`);
    } else {
      setPincodeStatus("Please enter a valid 6-digit PIN code.");
    }
  };

  // Default specs if missing
  const specsList = Array.isArray(product.specs) && product.specs.length > 0
    ? product.specs
    : [
        "6.72-inch Full HD+ Ultra-Smooth Display, 120Hz Refresh Rate",
        "Qualcomm Snapdragon 6 Gen 1 Processor / Octa-core 2.2 GHz",
        "50MP AI Main Camera + 2MP Portrait Lens, 8MP Selfie Camera",
        "6000 mAh Massive Battery with 44W FlashCharge Technology",
        "Dual SIM 5G (SA/NSA), Dual Standby, Side Fingerprint Sensor",
        "OriginOS 14 based on Android 14 with IP64 Water/Dust Resistance",
      ];

  const brandName = product.brand || product.sourceName || "Smartphone";

  return (
    <main className="main-content product-page-view">
      {/* Breadcrumb Navigation */}
      <nav className="pdp-breadcrumb-nav" aria-label="Breadcrumb">
        <button type="button" className="breadcrumb-back-btn" onClick={onBack}>
          <span className="back-arrow">←</span>
          <span>Back to Products</span>
        </button>
        <span className="breadcrumb-separator">/</span>
        <span className="breadcrumb-item">Mobiles</span>
        <span className="breadcrumb-separator">/</span>
        <span className="breadcrumb-item">{brandName}</span>
        <span className="breadcrumb-separator">/</span>
        <span className="breadcrumb-active" title={product.name}>
          {product.name}
        </span>
      </nav>

      {/* Main PDP Layout */}
      <div className="pdp-layout-grid">
        {/* Left Column: Image Gallery */}
        <div className="pdp-gallery-column">
          <div className="pdp-main-image-card">
            <span
              className="pdp-platform-badge"
              style={{ backgroundColor: product.badgeColor || "#0078ad" }}
            >
              {product.sourceName || product.channel || "Verified Store"}
            </span>
            <img
              src={selectedImage || product.image}
              alt={product.name}
              className="pdp-main-image"
              onError={(e) => {
                e.target.src = "https://fdn2.gsmarena.com/vv/bigpic/vivo-x-fold3-pro.jpg";
              }}
            />
          </div>

          <div className="pdp-thumbnails-strip">
            {galleryImages.map((imgUrl, idx) => (
              <button
                key={idx}
                type="button"
                className={`pdp-thumb-btn ${selectedImage === imgUrl ? "active" : ""}`}
                onClick={() => setSelectedImage(imgUrl)}
              >
                <img src={imgUrl} alt={`Thumbnail ${idx + 1}`} />
              </button>
            ))}
          </div>

          {/* Quick Actions under Gallery */}
          <div className="pdp-action-buttons-wrap">
            {product.url && product.url !== "#" ? (
              <a
                href={product.url}
                target="_blank"
                rel="noopener noreferrer"
                className="pdp-buy-store-btn"
              >
                <span>Buy on {product.sourceName || product.channel || "Store"}</span>
                <span className="external-icon">↗</span>
              </a>
            ) : (
              <a
                href={`https://www.google.com/search?q=${encodeURIComponent(product.name)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="pdp-buy-store-btn"
              >
                <span>Buy Online ↗</span>
              </a>
            )}
            {onOpenAutomation && (
              <button
                type="button"
                className="pdp-buy-store-btn"
                onClick={() => onOpenAutomation(product)}
              >
                Start store checkout
              </button>
            )}

          </div>
        </div>

        {/* Right Column: Product Details & Offers */}
        <div className="pdp-details-column">
          <div className="pdp-header-meta">
            <span className="pdp-brand-tag">{brandName}</span>
            <span className="pdp-seller-pill">Sold by: <strong>{product.seller || "Official Store"}</strong></span>
            {product.inStock !== false && <span className="pdp-stock-tag in-stock">✓ In Stock</span>}
          </div>

          <h1 className="pdp-product-title">{product.name}</h1>

          {/* Ratings & Reviews */}
          <div className="pdp-ratings-bar">
            <span className="pdp-star-rating">
              <span className="star">★</span> {product.rating || "4.4/5"}
            </span>
            <span className="pdp-rating-count">Verified Customer Ratings</span>
            <span className="pdp-assured-badge">
              ✓ {product.badge || "Verified Delivery"}
            </span>
          </div>

          {/* Price & Savings Box */}
          <div className="pdp-price-box">
            <div className="pdp-price-primary-row">
              <span className="pdp-current-price">{product.price || formatINR(priceNum)}</span>
              {product.originalPrice && (
                <span className="pdp-original-mrp">{product.originalPrice}</span>
              )}
              {product.discount && (
                <span className="pdp-discount-badge">{product.discount}</span>
              )}
            </div>

            {/* Effective Deal Highlight */}
            <div className="pdp-effective-deal-strip">
              <span className="deal-fire-icon">🔥</span>
              <span>
                Effective Price with Bank Offer: <strong className="green-text">{formatINR(effectivePrice)}</strong> (Save extra {formatINR(bestSavings)})
              </span>
            </div>
          </div>

          {/* Bank Offers Carousel Section (JioMart & Amazon Style) */}
          <div className="pdp-bank-offers-section">
            <div className="pdp-section-heading-row">
              <h3 className="pdp-section-heading">
                <span className="section-icon">🏷️</span>
                <span>Active Bank Offers on {product.sourceName || product.channel || "Platform"} ({offers.length} Offers)</span>
              </h3>
              <button
                type="button"
                className="pdp-view-all-offers-btn"
                onClick={() => onOpenBankOffers?.(product)}
              >
                View All {offers.length} Offers & Comparison ❯
              </button>
            </div>

            <div className="pdp-offers-cards-scroll">
              {offers.slice(0, 15).map((offer, idx) => (
                <div
                  key={offer.id}
                  className={`pdp-offer-card ${offer.isEligible ? "pdp-card-eligible" : ""}`}
                  onClick={() => onOpenBankOffers?.(product)}
                >
                  <div className="offer-card-badge-row">
                    <span className="offer-number-mini">Offer {offer.offerNumber || (idx + 1)}</span>
                    <span className="offer-bank-name">{offer.bankIcon} {offer.bank}</span>
                    <span className="offer-type-tag">{offer.tag}</span>
                  </div>
                  <strong className="offer-amount-text">
                    {offer.isEligible && offer.calculatedDiscount > 0
                      ? `${formatINR(offer.calculatedDiscount)} OFF`
                      : offer.title}
                  </strong>
                  <p className="offer-desc-snippet">{offer.description}</p>
                  <div className="offer-card-effective">
                    {offer.isEligible ? (
                      <span>Effective: <strong>{offer.effectivePriceFormatted}</strong></span>
                    ) : (
                      <span className="min-req-text">Min order {formatINR(offer.minOrder || 0)}</span>
                    )}
                  </div>
                </div>
              ))}
              {offers.length > 15 && (
                <div
                  className="pdp-offer-card pdp-see-more-card"
                  onClick={() => onOpenBankOffers?.(product)}
                >
                  <span className="see-more-icon">➕</span>
                  <strong>+{offers.length - 15} More Offers</strong>
                  <p>Click to view all {offers.length} authentic bank offers & compare across 5 stores</p>
                </div>
              )}
            </div>
          </div>

          {/* Pincode & Delivery Checker */}
          <div className="pdp-delivery-checker-box">
            <span className="delivery-icon">🚚</span>
            <div className="delivery-form-wrap">
              <form onSubmit={handleCheckPincode} className="pdp-pincode-form">
                <span className="pincode-label">Deliver to:</span>
                <input
                  type="text"
                  maxLength={6}
                  value={pincodeInput}
                  onChange={(e) => setPincodeInput(e.target.value.replace(/\D/g, ""))}
                  placeholder="Enter 6-digit PIN"
                  className="pdp-pincode-input"
                />
                <button type="submit" className="pdp-check-btn">Check</button>
              </form>
              <span className="pdp-delivery-status-text">{pincodeStatus}</span>
            </div>
          </div>

          {/* Live 5-Platform Price Comparison Table */}
          <div className="pdp-comparison-section">
            <div className="pdp-section-heading-row">
              <h3 className="pdp-section-heading">
                <span className="section-icon">📊</span>
                <span>Live Price Comparison (5 Allowed Stores)</span>
              </h3>
              <span className="pdp-section-sub">Compare where to buy for cheapest price</span>
            </div>

            <div className="pdp-comparison-table-wrap">
              <table className="pdp-comparison-table">
                <thead>
                  <tr>
                    <th>Store</th>
                    <th>Listed Price</th>
                    <th>Bank Discount</th>
                    <th>Effective Price</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisons.map((c) => (
                    <tr key={c.storeId} className={c.isLowest ? "pdp-lowest-row" : ""}>
                      <td className="pdp-store-cell">
                        <span className="store-emoji">{c.storeIcon}</span>
                        <strong>{c.storeName}</strong>
                        {c.isCurrentStore && <span className="pdp-curr-tag">Viewing</span>}
                      </td>
                      <td className="pdp-listed-cell">{c.listedPriceFormatted}</td>
                      <td className="pdp-discount-cell">
                        <span className="disc-green">{c.bankDiscountFormatted}</span>
                      </td>
                      <td className="pdp-effective-cell">
                        <strong className="eff-price-txt">{c.effectivePriceFormatted}</strong>
                        {c.isLowest && <span className="lowest-pill">Lowest 🏆</span>}
                      </td>
                      <td className="pdp-action-cell">
                        <a
                          href={c.productUrl || "#"}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`pdp-store-link-btn ${c.isLowest ? "lowest-btn" : ""}`}
                        >
                          Visit Store ↗
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Technical Specifications */}
          <div className="pdp-specs-section">
            <h3 className="pdp-section-heading">
              <span className="section-icon">⚙️</span>
              <span>Key Features & Specifications</span>
            </h3>

            <div className="pdp-specs-grid">
              {specsList.map((spec, i) => (
                <div key={i} className="pdp-spec-item">
                  <span className="spec-bullet">✓</span>
                  <span className="spec-text">{spec}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

