/**
 * Multi-Scraper Global Registry & Configuration
 * Configured for the scraper engines exposed by the unified API:
 * The unified API currently supports ten stores. Placeholder stores without backend adapters remain inactive.
 */

export const UNIFIED_API_BASE = import.meta.env.VITE_UNIFIED_API_BASE_URL || "/api";
const SUPPORTED_SCRAPERS = new Set([
  "jiomart",
  "reliance",
  "flipkart",
  "amazon",
  "croma",
  "samsung",
  "apple",
  "vivo",
  "oppo",
  "xiaomi",
]);

export const ALL_SCRAPERS_CONFIG = [
  {
    id: "jiomart",
    name: "JioMart",
    brand: "JioMart",
    type: "brand_store",
    color: "#0078ad",
    badge: "JioMart Verified",
    channel: "jiomart",
  },
  {
    id: "reliance",
    name: "Reliance Digital",
    brand: "Reliance",
    type: "brand_store",
    color: "#e42529",
    badge: "Reliance Assured",
    channel: "reliance",
  },
  {
    id: "flipkart",
    name: "Flipkart",
    brand: "Flipkart",
    type: "marketplace",
    color: "#2874F0",
    badge: "Flipkart Assured",
    channel: "flipkart",
  },
  {
    id: "amazon",
    name: "Amazon",
    brand: "Amazon",
    type: "marketplace",
    color: "#FF9900",
    badge: "Amazon Prime",
    channel: "amazon",
  },
  {
    id: "croma",
    name: "Croma",
    brand: "Croma",
    type: "brand_store",
    color: "#00b5b5",
    badge: "Croma Verified",
    channel: "croma",
  },
  {
    id: "samsung",
    name: "Samsung",
    brand: "Samsung",
    type: "brand_store",
    color: "#1428a0",
    badge: "Samsung Official",
    channel: "samsung",
  },
  {
    id: "apple",
    name: "Apple",
    brand: "Apple",
    type: "brand_store",
    color: "#555555",
    badge: "Apple Official",
    channel: "apple",
  },
  {
    id: "vivo",
    name: "Vivo",
    brand: "Vivo",
    type: "brand_store",
    color: "#415fff",
    badge: "Vivo Official",
    channel: "vivo",
  },
  {
    id: "oppo",
    name: "Oppo",
    brand: "Oppo",
    type: "brand_store",
    color: "#008b47",
    badge: "Oppo Official",
    channel: "oppo",
  },
  // Placeholders without unified API adapters.
  {
    id: "vijaysales",
    name: "Vijay Sales",
    brand: "Vijay Sales",
    type: "brand_store",
    color: "#d71920",
    badge: "Vijay Sales",
    channel: "vijaysales",
  },
  {
    id: "poorvika",
    name: "Poorvika",
    brand: "Poorvika",
    type: "brand_store",
    color: "#f26522",
    badge: "Poorvika Express",
    channel: "poorvika",
  },
  {
    id: "sangeetha",
    name: "Sangeetha",
    brand: "Sangeetha",
    type: "brand_store",
    color: "#009688",
    badge: "Sangeetha Verified",
    channel: "sangeetha",
  },
  {
    id: "oneplus",
    name: "OnePlus",
    brand: "OnePlus",
    type: "brand_store",
    color: "#f5010c",
    badge: "OnePlus Official",
    channel: "oneplus",
  },
  {
    id: "xiaomi",
    name: "Xiaomi Mi",
    brand: "Xiaomi",
    type: "brand_store",
    color: "#ff6700",
    badge: "Mi Store",
    channel: "xiaomi",
  },
];

for (const scraper of ALL_SCRAPERS_CONFIG) {
  scraper.baseUrl = UNIFIED_API_BASE;
  scraper.statusEndpoint = `/brands/${scraper.id}/status`;
  scraper.scrapeEndpoint = `/brands/${scraper.id}/scrape`;
  scraper.productsEndpoint = `/brands/${scraper.id}/products`;
  scraper.isActive = SUPPORTED_SCRAPERS.has(scraper.id);
}

export const SCRAPERS_CONFIG = ALL_SCRAPERS_CONFIG.filter((s) => s.isActive);
