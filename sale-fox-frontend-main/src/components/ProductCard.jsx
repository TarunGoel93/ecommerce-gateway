import React, { useState, useMemo } from "react";
import { getBestBankOffer, getProductOffers } from "../services/offersService";

function ProductCard({
  name,
  image,
  price,
  originalPrice,
  discount,
  rating,
  delivery,
  seller,
  badge,
  badgeType,
  url,
  channel,
  brand,
  sourceName,
  specs,
  onOpenOffersModal,
  onOpenBulkAutomation,
  onSelectProduct,
}) {
  const [isWishListed, setIsWishListed] = useState(false);

  const currentProductObj = useMemo(() => ({
    name,
    image,
    price,
    originalPrice,
    discount,
    rating,
    delivery,
    seller,
    badge,
    badgeType,
    url,
    channel: channel || badgeType || seller || "",
    brand: brand || "",
    sourceName: sourceName || seller || "",
    specs: specs || [],
  }), [name, image, price, originalPrice, discount, rating, delivery, seller, badge, badgeType, url, channel, brand, sourceName, specs]);

  const cardOffers = useMemo(() => {
    return getProductOffers(currentProductObj);
  }, [currentProductObj]);

  const bestBankOffer = useMemo(() => {
    return getBestBankOffer(currentProductObj);
  }, [currentProductObj]);

  const isSamsungProduct =
    (badgeType && badgeType.toLowerCase().includes("samsung")) ||
    (seller && seller.toLowerCase().includes("samsung")) ||
    (name && name.toLowerCase().includes("samsung"));

  const isAppleProduct =
    (badgeType && badgeType.toLowerCase().includes("apple")) ||
    (seller && seller.toLowerCase().includes("apple")) ||
    (name && (name.toLowerCase().includes("apple") || name.toLowerCase().includes("iphone")));

  return (
    <div className={`product-card ${badgeType ? `card-${badgeType}` : ""}`}>
      <div
        className="product-image clickable-pdp-trigger"
        onClick={() => onSelectProduct?.(currentProductObj)}
        title={`Click to open product page for ${name}`}
      >
        {badge && (
          <span className={`product-badge-tag badge-${badgeType || "default"}`}>
            {badge}
          </span>
        )}
        <img
          src={image}
          alt={name}
          loading="lazy"
          decoding="async"
          onError={(e) => {
            // Prevent infinite loop if placeholder also fails
            if (!e.target.dataset.errored) {
              e.target.dataset.errored = "1";
              const lBrand = (brand || seller || channel || badgeType || name || "").toLowerCase();
              if (lBrand.includes("oppo")) {
                e.target.src = "https://www.oppo.com/content/dam/oppo_com/common/mkt/v2-2/oppo-reno16-series-en/navigation/reno16/440-440-white.png";
              } else if (lBrand.includes("apple") || lBrand.includes("iphone")) {
                e.target.src = "https://fdn2.gsmarena.com/vv/bigpic/apple-iphone-15.jpg";
              } else if (lBrand.includes("samsung") || lBrand.includes("galaxy")) {
                e.target.src = "https://fdn2.gsmarena.com/vv/bigpic/samsung-galaxy-s24-5g.jpg";
              } else {
                e.target.src =
                  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200' viewBox='0 0 200 200'%3E%3Crect width='200' height='200' fill='%23f0f0f0'/%3E%3Crect x='60' y='50' width='80' height='70' rx='4' fill='%23d0d0d0'/%3E%3Ccircle cx='85' cy='75' r='10' fill='%23b0b0b0'/%3E%3Cpolygon points='60,120 90,85 115,105 140,75 140,120' fill='%23c0c0c0'/%3E%3Ctext x='100' y='155' text-anchor='middle' font-family='sans-serif' font-size='11' fill='%23999'%3ENo image%3C/text%3E%3C/svg%3E";
              }
            }
          }}
        />
      </div>
      <button
        type="button"
        className={`wishlist-button ${isWishListed ? "Clicked" : "notClicked"}`}
        onClick={() => setIsWishListed((prev) => !prev)}
        aria-label={isWishListed ? "Remove from wishlist" : "Add to wishlist"}
      >
        {isWishListed ? "♥" : "♡"}
      </button>
      <div className="product-info">
        <h3 title={`View product page: ${name}`}>
          <a
            href={url || "#"}
            className="product-title-link"
            title={`Open product page for ${name}`}
            onClick={(e) => {
              if (onSelectProduct) {
                e.preventDefault();
                onSelectProduct(currentProductObj);
              }
            }}
          >
            {name}
          </a>
        </h3>

        <div className="product-price-row">
          <p className={`product-price ${price === "Out of Stock" ? "out-of-stock-price" : ""}`}>
            {price}
          </p>
          {originalPrice && originalPrice !== "₹0" && (
            <span className="product-original-price">{originalPrice}</span>
          )}
          {discount && discount !== "0% OFF" && discount !== "0%" && (
            <span className="product-discount-pill">{discount}</span>
          )}
        </div>

        <div className="product-seller-row" title={`Sold by: ${seller}`}>
          <span className="seller-label">Seller:</span>
          <span className="product-seller-name">{seller}</span>
          {seller && (seller.includes("(FBA)") || seller.toLowerCase().includes("fba")) && (
            <span className="seller-fba-pill" title="Fulfilled by Amazon">FBA</span>
          )}
          {seller && (seller.includes("(F-Assured)") || seller.toLowerCase().includes("f-assured")) && (
            <span className="seller-fassured-pill" title="Flipkart Assured">F-Assured</span>
          )}
          {url && url !== "#" && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="seller-store-link-pill"
              title={`Open live store listing on ${sourceName || channel || "Store"}`}
              onClick={(e) => e.stopPropagation()}
            >
              Store ↗
            </a>
          )}
        </div>
      </div>

      <div className="product-details">
        <div className="product-details-left">
          <p className="product-rating">
            <span className="star-icon">★</span> {rating}
          </p>
          <p className="product-delivery">Delivery: {delivery}</p>
        </div>
      </div>

      {/* Bank Offers Strip & View Offers Modal Trigger (JioMart Style) */}
      <div className="card-bank-offers-row">
        <div className="card-offer-preview">
          <span className="card-offer-badge-tag">{bestBankOffer?.tag || "BEST OFFER"}</span>
          <span className="card-offer-text" title={bestBankOffer ? `${bestBankOffer.bank}: ${bestBankOffer.title}` : "Bank Offers Available"}>
            {bestBankOffer ? `${bestBankOffer.bank}: ${bestBankOffer.discountFormatted}` : "Bank Offers Available"}
          </span>
          {bestBankOffer && (
            <span className="card-effective-price">
              • Eff: <strong>{bestBankOffer.effectivePriceFormatted}</strong>
            </span>
          )}
        </div>
        <button
          type="button"
          className="card-view-offers-btn"
          title="View bank offers and compare prices across 10 stores"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onOpenOffersModal?.(currentProductObj);
          }}
        >
          <span>View Offers ({cardOffers.length})</span>
          <span className="offers-btn-arrow">❯</span>
        </button>
      </div>
      {onOpenBulkAutomation && (
        <button
          type="button"
          className="card-view-offers-btn"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onOpenBulkAutomation(currentProductObj);
          }}
        >
          Start store checkout
        </button>
      )}
    </div>
  );
}

export default ProductCard;
