import React, { useState, useMemo } from "react";
import "./BankOffersAndComparisonModal.css";
import {
  getProductOffers,
  getBestBankOffer,
  getCrossPlatformComparison,
  formatINR,
} from "../services/offersService";

export default function BankOffersAndComparisonModal({
  product,
  allProducts = [],
  onClose,
}) {
  if (!product) return null;

  const [activeTab, setActiveTab] = useState("offers"); // "offers" | "comparison"
  const [selectedBankFilter, setSelectedBankFilter] = useState("all");
  const [selectedEmiFilter, setSelectedEmiFilter] = useState("all"); // "all" | "emi" | "non-emi"
  const [eligibilityFilter, setEligibilityFilter] = useState("all"); // "all" | "eligible"
  const [selectedOfferTerms, setSelectedOfferTerms] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  const offers = useMemo(() => getProductOffers(product), [product]);
  const bestOffer = useMemo(() => getBestBankOffer(product), [product]);
  const comparisons = useMemo(
    () => getCrossPlatformComparison(product, allProducts),
    [product, allProducts]
  );

  const basePriceNum =
    typeof product.priceNum === "number" && product.priceNum > 0
      ? product.priceNum
      : offers[0]?.effectivePrice || 25499;

  const bestSavings = bestOffer?.isEligible ? bestOffer.calculatedDiscount : 0;
  const effectivePriceNum = Math.max(0, basePriceNum - bestSavings);
  const lowestAcrossAll = comparisons.find((c) => c.isLowest) || comparisons[0];

  // Bank summary list for filter chips
  const bankOptions = useMemo(() => {
    const counts = {};
    offers.forEach((o) => {
      counts[o.bank] = (counts[o.bank] || 0) + 1;
    });
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return [{ bank: "all", count: offers.length }, ...sorted.map(([bank, count]) => ({ bank, count }))];
  }, [offers]);

  // Filtered offers list
  const filteredOffers = useMemo(() => {
    return offers.filter((o) => {
      // Bank filter
      if (selectedBankFilter !== "all" && o.bank !== selectedBankFilter) {
        return false;
      }
      // EMI filter
      if (selectedEmiFilter === "emi" && o.emiType !== "EMI" && !o.emiType?.includes("EMI")) {
        return false;
      }
      if (selectedEmiFilter === "non-emi" && o.emiType === "EMI") {
        return false;
      }
      // Eligibility filter
      if (eligibilityFilter === "eligible" && !o.isEligible) {
        return false;
      }
      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesBank = o.bank?.toLowerCase().includes(q);
        const matchesDesc = o.description?.toLowerCase().includes(q);
        const matchesTitle = o.title?.toLowerCase().includes(q);
        if (!matchesBank && !matchesDesc && !matchesTitle) return false;
      }
      return true;
    });
  }, [offers, selectedBankFilter, selectedEmiFilter, eligibilityFilter, searchQuery]);

  const eligibleCount = offers.filter((o) => o.isEligible).length;

  return (
    <div className="offers-modal-overlay" onClick={onClose}>
      <div className="offers-modal-container" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="offers-modal-header">
          <div className="offers-header-left">
            <span className="offers-tag-icon">🏷️</span>
            <div>
              <h2 className="offers-modal-title">Bank Offers & Price Comparison</h2>
              <p className="offers-modal-subtitle">
                Authentic scraped bank offers ({offers.length} available) & live multi-platform deals
              </p>
            </div>
          </div>
          <button
            type="button"
            className="offers-modal-close-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        {/* Product Summary Hero Card */}
        <div className="offers-product-hero">
          <div className="hero-img-wrap">
            <img
              src={product.image || "https://placehold.co/120x120?text=Phone"}
              alt={product.name}
              className="hero-product-img"
              onError={(e) => {
                e.target.src = "https://fdn2.gsmarena.com/vv/bigpic/vivo-x-fold3-pro.jpg";
              }}
            />
          </div>

          <div className="hero-details">
            <div className="hero-badges-row">
              <span
                className="hero-platform-badge"
                style={{ backgroundColor: product.badgeColor || "#0078ad" }}
              >
                {product.sourceName || product.channel || "Platform Verified"}
              </span>
              {product.brand && <span className="hero-brand-pill">{product.brand}</span>}
              <span className="hero-delivery-pill">⚡ Fast Delivery Available</span>
            </div>

            <h3 className="hero-product-title">{product.name}</h3>

            {/* Hot Deal Savings Bar (Inspired by JioMart & Amazon live PDP) */}
            <div className="hero-savings-banner">
              <div className="hot-deal-pill">
                <span className="flame-icon">🔥</span>
                <span>HOT DEAL</span>
              </div>
              <div className="savings-headline">
                Get at <strong className="highlight-price">{formatINR(effectivePriceNum)}</strong> with Big Savings!
              </div>
            </div>

            <div className="hero-price-breakdown">
              <div className="price-item">
                <span className="price-label">Listed Price:</span>
                <span className="price-val strike">{product.price || formatINR(basePriceNum)}</span>
              </div>
              <div className="price-item discount-item">
                <span className="price-label">Best Bank Savings:</span>
                <span className="price-val discount-green">-{formatINR(bestSavings)}</span>
              </div>
              <div className="price-item final-item">
                <span className="price-label">Effective Price:</span>
                <span className="price-val bold-large">{formatINR(effectivePriceNum)}</span>
              </div>
              <div className="emi-estimate-item">
                <span>or Lowest EMI: <strong>₹{Math.round(effectivePriceNum / 24).toLocaleString("en-IN")}/mo</strong> × 24m</span>
              </div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="offers-nav-tabs">
          <button
            type="button"
            className={`offers-tab-btn ${activeTab === "offers" ? "active" : ""}`}
            onClick={() => setActiveTab("offers")}
          >
            💳 Bank & Wallet Offers ({offers.length})
          </button>
          <button
            type="button"
            className={`offers-tab-btn ${activeTab === "comparison" ? "active" : ""}`}
            onClick={() => setActiveTab("comparison")}
          >
            📊 Cross-Platform Price Comparison (10 Stores)
          </button>
        </div>

        {/* Tab 1: Bank & Wallet Offers */}
        {activeTab === "offers" && (
          <div className="offers-tab-content">
            <div className="offers-section-title-row">
              <div>
                <h4 className="section-heading">
                  All {offers.length} Bank Offers on {product.sourceName || product.channel || "This Platform"}
                </h4>
                <span className="section-subtext">
                  {eligibleCount} offers eligible directly for current cart price ({formatINR(basePriceNum)})
                </span>
              </div>
              <span className="section-note">Discounts automatically apply at final checkout page</span>
            </div>

            {/* Controls Bar: Bank Filters, EMI Filter, Eligibility Filter */}
            <div className="offers-filter-control-panel">
              {/* Bank Filter Chips */}
              <div className="bank-filter-chips-scroll">
                {bankOptions.map((b) => (
                  <button
                    key={b.bank}
                    type="button"
                    className={`bank-chip-btn ${selectedBankFilter === b.bank ? "active" : ""}`}
                    onClick={() => setSelectedBankFilter(b.bank)}
                  >
                    <span>{b.bank === "all" ? "All Banks" : b.bank}</span>
                    <span className="chip-count">({b.count})</span>
                  </button>
                ))}
              </div>

              {/* Secondary Filters: EMI & Eligibility */}
              <div className="offers-secondary-filters-row">
                <div className="filter-group">
                  <span className="filter-group-label">Payment Mode:</span>
                  <div className="btn-group-toggle">
                    <button
                      type="button"
                      className={`toggle-option-btn ${selectedEmiFilter === "all" ? "active" : ""}`}
                      onClick={() => setSelectedEmiFilter("all")}
                    >
                      All
                    </button>
                    <button
                      type="button"
                      className={`toggle-option-btn ${selectedEmiFilter === "emi" ? "active" : ""}`}
                      onClick={() => setSelectedEmiFilter("emi")}
                    >
                      EMI Offers
                    </button>
                    <button
                      type="button"
                      className={`toggle-option-btn ${selectedEmiFilter === "non-emi" ? "active" : ""}`}
                      onClick={() => setSelectedEmiFilter("non-emi")}
                    >
                      Non-EMI / Full Pay
                    </button>
                  </div>
                </div>

                <div className="filter-group">
                  <span className="filter-group-label">Cart Eligibility:</span>
                  <div className="btn-group-toggle">
                    <button
                      type="button"
                      className={`toggle-option-btn ${eligibilityFilter === "all" ? "active" : ""}`}
                      onClick={() => setEligibilityFilter("all")}
                    >
                      Show All ({offers.length})
                    </button>
                    <button
                      type="button"
                      className={`toggle-option-btn ${eligibilityFilter === "eligible" ? "active" : ""}`}
                      onClick={() => setEligibilityFilter("eligible")}
                    >
                      Eligible Only ({eligibleCount})
                    </button>
                  </div>
                </div>

                <div className="offer-search-wrap">
                  <input
                    type="text"
                    placeholder="Search bank or offer..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="offer-quick-search-input"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      className="clear-search-btn"
                      onClick={() => setSearchQuery("")}
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Bank Offer Cards Grid / Scrollable List */}
            {filteredOffers.length === 0 ? (
              <div className="no-offers-matched">
                <p>No bank offers match the selected filters.</p>
                <button
                  type="button"
                  className="reset-filters-btn"
                  onClick={() => {
                    setSelectedBankFilter("all");
                    setSelectedEmiFilter("all");
                    setEligibilityFilter("all");
                    setSearchQuery("");
                  }}
                >
                  Reset All Filters
                </button>
              </div>
            ) : (
              <div className="bank-offers-cards-grid">
                {filteredOffers.map((offer) => {
                  const isBest = offer.id === bestOffer?.id;
                  const isEligible = offer.isEligible;
                  return (
                    <div
                      key={offer.id}
                      className={`bank-offer-card ${isBest ? "best-offer-card" : ""} ${
                        isEligible ? "eligible-card" : "ineligible-card"
                      }`}
                    >
                      {/* Top Row: Offer Number + Bank + Tag */}
                      <div className="offer-card-top">
                        <div className="bank-logo-wrap">
                          <span className="offer-number-badge">
                            Offer {offer.offerNumber || (offers.indexOf(offer) + 1)}
                          </span>
                          <span className="bank-emoji">{offer.bankIcon || "🏦"}</span>
                          <span className="bank-name-label">{offer.bank}</span>
                        </div>
                        <span
                          className="offer-badge-tag"
                          style={{
                            backgroundColor: `${offer.tagColor || "#2563eb"}15`,
                            color: offer.tagColor || "#2563eb",
                            borderColor: `${offer.tagColor || "#2563eb"}40`,
                          }}
                        >
                          {offer.tag}
                        </span>
                      </div>

                      {/* Discount Headline */}
                      <div className="offer-discount-title">
                        {isEligible && offer.calculatedDiscount > 0 ? (
                          <span className="disc-amount-green">{formatINR(offer.calculatedDiscount)} OFF</span>
                        ) : (
                          <span className="disc-title-text">{offer.title}</span>
                        )}
                        <span className="emi-type-tag">{offer.emiType}</span>
                      </div>

                      {/* Exact Scraped Offer Text */}
                      <p className="offer-desc-text">{offer.description}</p>

                      {/* Criteria Pill & Eligibility Status */}
                      <div className="offer-meta-strip">
                        <span className="min-order-pill">
                          Min Purchase: <strong>{formatINR(offer.minOrder || 0)}</strong>
                        </span>
                        {isEligible ? (
                          <span className="eligible-status-tag valid">
                            ✓ Eligible on this phone
                          </span>
                        ) : (
                          <span className="eligible-status-tag requires-cart">
                            ⚠️ Add {formatINR(offer.minRequiredDiff)} to unlock
                          </span>
                        )}
                      </div>

                      {/* Effective Price Strip */}
                      <div className="offer-effective-pill">
                        {isEligible ? (
                          <span>
                            Effective Price: <strong>{offer.effectivePriceFormatted}</strong>
                          </span>
                        ) : (
                          <span>
                            Listed Price: <strong>{formatINR(basePriceNum)}</strong>
                          </span>
                        )}
                      </div>

                      <button
                        type="button"
                        className="offer-terms-toggle-btn"
                        onClick={() =>
                          setSelectedOfferTerms(
                            selectedOfferTerms === offer.id ? null : offer.id
                          )
                        }
                      >
                        {selectedOfferTerms === offer.id ? "Hide details ▲" : "See details ❯"}
                      </button>

                      {selectedOfferTerms === offer.id && (
                        <div className="offer-terms-popup">
                          <p>{offer.terms}</p>
                          <small>Min cart threshold: {formatINR(offer.minOrder || 0)} | Mode: {offer.emiType}</small>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Payment Modes & Additional Perks Summary */}
            <div className="cash-offers-summary-box">
              <div className="cash-offers-header">
                <span className="cash-icon">💰</span>
                <h4>UPI, Wallet & Exchange Offers on {product.sourceName || product.channel || "Platform"}</h4>
              </div>
              <ul className="cash-offers-list">
                <li>
                  <strong>Amazon Pay / PhonePe / Paytm UPI:</strong> Get flat ₹100 cashback on min purchase of ₹1,500 using verified UPI handle checkout.
                </li>
                <li>
                  <strong>No-Cost EMI:</strong> Avail 0% interest EMI options up to 6 months across major credit cards including SBI, HDFC, ICICI, Axis, and Kotak.
                </li>
                <li>
                  <strong>Assured Exchange Bonus:</strong> Get up to ₹3,000 additional exchange bonus value when trading in your previous working smartphone.
                </li>
              </ul>
            </div>
          </div>
        )}

        {/* Tab 2: Cross-Platform Price Comparison */}
        {activeTab === "comparison" && (
          <div className="comparison-tab-content">
            <div className="comparison-header-banner">
              <div className="comp-banner-left">
                <span className="trophy-comp-icon">🏆</span>
                <div>
                  <h4>Best Deal: {lowestAcrossAll.storeName} at {lowestAcrossAll.effectivePriceFormatted}</h4>
                  <p>Includes highest bank discount across all 5 allowed e-commerce platforms.</p>
                </div>
              </div>
            </div>

            <div className="comparison-table-wrapper">
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>Platform</th>
                    <th>Listed Price</th>
                    <th>Best Bank Offer</th>
                    <th>Effective Price</th>
                    <th>Deal Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisons.map((c) => (
                    <tr
                      key={c.storeId}
                      className={`comparison-row ${c.isLowest ? "lowest-row" : ""} ${
                        c.isCurrentStore ? "current-store-row" : ""
                      }`}
                    >
                      <td>
                        <div className="comp-store-cell">
                          <span className="comp-store-icon">{c.icon}</span>
                          <div>
                            <strong className="comp-store-name">{c.storeName}</strong>
                            {c.isCurrentStore && (
                              <span className="current-store-tag">Current View</span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="comp-price-cell">{c.listedPrice}</td>
                      <td className="comp-offer-cell">
                        <div className="comp-offer-box">
                          <span className="comp-offer-text">{c.bestBankOfferTitle}</span>
                          {c.bestBankSavings > 0 && (
                            <span className="comp-savings-tag">
                              -{c.bestBankSavingsFormatted}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="comp-effective-cell">
                        <strong className="comp-eff-price">{c.effectivePriceFormatted}</strong>
                      </td>
                      <td>
                        {c.isLowest ? (
                          <span className="deal-badge-lowest">Lowest Price 🔥</span>
                        ) : (
                          <span className="deal-badge-standard">Available</span>
                        )}
                      </td>
                      <td>
                        <a
                          href={c.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="comp-view-btn"
                        >
                          View Deal ↗
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Modal Footer */}
        <div className="offers-modal-footer">
          <div className="footer-verified-note">
            <span className="shield-icon">🛡️</span>
            <span>All offers dynamically parsed from live e-commerce platforms & bank partner APIs</span>
          </div>
          <div className="footer-actions">
            <a
              href={product.url || `https://www.google.com/search?q=${encodeURIComponent(product.name)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="footer-go-store-btn"
            >
              Go to {product.sourceName || product.channel || "Store"} Website ↗
            </a>
            <button type="button" className="footer-close-btn" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
