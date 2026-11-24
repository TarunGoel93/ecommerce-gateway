/**
 * Scalefox Multi-Scraper Search & NLP Service
 * Uses the unified API with Approach 1: Frontend Parallel Fan-Out (Promise.allSettled)
 * and Progressive Streaming (UI updates immediately as each scraper returns).
 */

import {
  ALL_SCRAPERS_CONFIG,
  SCRAPERS_CONFIG,
  UNIFIED_API_BASE,
} from "./scrapersConfig.js";

const HISTORY_STORAGE_KEY = "scalefox_search_history_v1";

// Helper to convert price strings like "₹79,900" or "79900" to float
export function parsePriceNumber(priceStr) {
  if (typeof priceStr === "number") return priceStr;
  if (!priceStr) return 0;
  const cleaned = String(priceStr).replace(/[^0-9.]/g, "");
  return parseFloat(cleaned) || 0;
}

// Helper to convert rating strings like "4.5/5" or "4.3" to float
export function parseRatingNumber(ratingStr) {
  if (typeof ratingStr === "number") return ratingStr;
  if (!ratingStr) return 0;
  const match = String(ratingStr).match(/([0-9]+(?:\.[0-9]+)?)/);
  return match ? parseFloat(match[1]) : 0;
}

/**
 * Smart Natural Language Query Parser
 */
export function parseSmartQuery(queryText = "") {
  const raw = String(queryText).trim();
  if (!raw) {
    return {
      rawQuery: "",
      keyword: "",
      minPrice: null,
      maxPrice: null,
      minRating: null,
      detectedBrand: null,
      detectedBudget: "",
    };
  }

  let minPrice = null;
  let maxPrice = null;
  let minRating = null;
  let detectedBudget = "";
  let workingQuery = raw;

  // 1. Between X and Y
  const betweenMatch = workingQuery.match(
    /(?:between|from)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|l|lakh)?\s*(?:to|and|-)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|l|lakh)?/i
  );
  if (betweenMatch) {
    const toNum = (valStr, unit) => {
      let v = parseFloat(valStr);
      const u = (unit || "").toLowerCase();
      if (u === "k" || u === "thousand" || (v <= 100 && v > 0)) v *= 1000;
      else if (u === "l" || u === "lakh") v *= 100000;
      return v;
    };
    minPrice = toNum(betweenMatch[1], betweenMatch[2]);
    maxPrice = toNum(betweenMatch[3], betweenMatch[4]);
    detectedBudget = `₹${minPrice.toLocaleString()} - ₹${maxPrice.toLocaleString()}`;
    workingQuery = workingQuery.replace(betweenMatch[0], " ");
  }

  // 2. Under / Below / Less than
  if (maxPrice === null) {
    const underMatch = workingQuery.match(
      /(?:under|below|less\s+than|up\s+to|within|max|<=|<)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|l|lakh)?/i
    );
    if (underMatch) {
      let val = parseFloat(underMatch[1]);
      const unit = (underMatch[2] || "").toLowerCase();
      if (unit === "k" || unit === "thousand" || (val <= 100 && val > 0)) {
        val *= 1000;
      } else if (unit === "l" || unit === "lakh") {
        val *= 100000;
      }
      maxPrice = val;
      detectedBudget = `Under ₹${maxPrice.toLocaleString()}`;
      workingQuery = workingQuery.replace(underMatch[0], " ");
    }
  }

  // 3. Above / Over / More than
  if (minPrice === null) {
    const aboveMatch = workingQuery.match(
      /(?:above|over|more\s+than|min|>=|>)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|l|lakh)?/i
    );
    if (aboveMatch) {
      let val = parseFloat(aboveMatch[1]);
      const unit = (aboveMatch[2] || "").toLowerCase();
      if (unit === "k" || unit === "thousand" || (val <= 100 && val > 0)) {
        val *= 1000;
      } else if (unit === "l" || unit === "lakh") {
        val *= 100000;
      }
      minPrice = val;
      detectedBudget = `Above ₹${minPrice.toLocaleString()}`;
      workingQuery = workingQuery.replace(aboveMatch[0], " ");
    }
  }

  // 4. Rating filter
  const ratingMatch = workingQuery.match(
    /(?:above|over|>=|>)?\s*(\d(?:\.\d)?)\s*(?:star|\*|rating)/i
  );
  if (ratingMatch) {
    minRating = parseFloat(ratingMatch[1]);
    workingQuery = workingQuery.replace(ratingMatch[0], " ");
  }

  // 5. Brand detection
  const brands = [
    "Apple",
    "iPhone",
    "Samsung",
    "Galaxy",
    "Croma",
    "OnePlus",
    "Google",
    "Pixel",
    "Xiaomi",
    "Redmi",
    "Realme",
    "Vivo",
    "Oppo",
    "Motorola",
    "Nothing",
    "Asus",
    "Sony",
    "Reliance",
  ];
  let detectedBrand = null;
  for (const b of brands) {
    const regex = new RegExp(`\\b${b}\\b`, "i");
    if (regex.test(raw)) {
      detectedBrand = b === "iPhone" ? "Apple" : b === "Galaxy" ? "Samsung" : b;
      break;
    }
  }

  const keyword = workingQuery.replace(/\s+/g, " ").trim();

  return {
    rawQuery: raw,
    keyword,
    minPrice,
    maxPrice,
    minRating,
    detectedBrand,
    detectedBudget,
  };
}

/**
 * Filter product catalog in-memory based on search text and active filters
 */
export function filterProducts(products = [], query = "", filters = {}) {
  const nlp = parseSmartQuery(query);

  const effectiveMinPrice =
    filters.minPrice !== null && filters.minPrice !== ""
      ? parseFloat(filters.minPrice)
      : nlp.minPrice;

  const effectiveMaxPrice =
    filters.maxPrice !== null && filters.maxPrice !== ""
      ? parseFloat(filters.maxPrice)
      : nlp.maxPrice;

  const effectiveMinRating =
    filters.minRating !== null && filters.minRating !== ""
      ? parseFloat(filters.minRating)
      : nlp.minRating;

  const searchKeyword = (nlp.keyword || "").toLowerCase();
  const searchBrand = (filters.brand || nlp.detectedBrand || "").toLowerCase();

  return products.filter((product) => {
    const nameLower = (product.name || "").toLowerCase();
    const sellerLower = (product.seller || "").toLowerCase();
    const brandLower = (product.brand || "").toLowerCase();
    const priceVal = parsePriceNumber(product.price);
    const ratingVal = parseRatingNumber(product.rating);

    // 1. Keyword check
    if (
      searchKeyword &&
      searchKeyword !== "phone" &&
      searchKeyword !== "phones" &&
      searchKeyword !== "mobile" &&
      searchKeyword !== "mobiles" &&
      searchKeyword !== "all"
    ) {
      const isAiQuery = /\b(ai|pulse)\b/i.test(searchKeyword);
      if (isAiQuery) {
        // AI queries match AI flagships and smartphones
        const matchesAi =
          nameLower.includes("ai") ||
          nameLower.includes("galaxy") ||
          nameLower.includes("5g") ||
          nameLower.includes("ultra") ||
          nameLower.includes("pro") ||
          brandLower.includes("samsung") ||
          brandLower.includes("apple") ||
          brandLower.includes("croma");
        if (!matchesAi && !nameLower.includes(searchKeyword)) return false;
      } else {
        // Strict token matching: Ignore pure noise/category words like 'phone', 'phones', 'mobile', 'under'
        const noise = new Set(["phone", "phones", "mobile", "mobiles", "smartphone", "smartphones", "under", "below", "buy", "online", "price", "the", "in", "a", "an", "and", "with"]);
        // Normalize letter-number spacing: "m 17" -> "m17", "17 e" -> "17e", "m17 e" -> "m17e"
        const normKeyword = searchKeyword
          .replace(/\b([a-zA-Z])\s+(\d+)/g, "$1$2")
          .replace(/(\d+)\s+([a-zA-Z])\b/g, "$1$2");
        const words = normKeyword.split(" ").filter((w) => w && !noise.has(w));

        if (words.length > 0) {
          const normalizedTarget = `${nameLower} ${brandLower} ${sellerLower}`
            .toLowerCase()
            .replace(/\b([a-zA-Z])\s+(\d+)/g, "$1$2")
            .replace(/(\d+)\s+([a-zA-Z])\b/g, "$1$2");

          const isSamsungPhone = brandLower.includes("samsung") || nameLower.includes("samsung");

          const matchesAllTokens = words.every((w) => {
            // 'galaxy' exception for Samsung: all Samsung smartphones are Galaxy series, even if store writes 'Samsung M17e 5G'
            if (w === "galaxy" && isSamsungPhone) {
              return true;
            }
            // Strict token & model matching with word boundaries
            try {
              const tokenRegex = new RegExp(`\\b${w}\\b`, "i");
              return tokenRegex.test(normalizedTarget);
            } catch {
              return normalizedTarget.includes(w);
            }
          });
          if (!matchesAllTokens) return false;
        }
      }
    }

    // 2. Brand check
    if (searchBrand) {
      const matchesBrand =
        nameLower.includes(searchBrand) || brandLower.includes(searchBrand);
      if (!matchesBrand) return false;
    }

    // 3. Price checks
    if (effectiveMinPrice !== null && priceVal < effectiveMinPrice) {
      return false;
    }
    if (effectiveMaxPrice !== null && priceVal > effectiveMaxPrice) {
      return false;
    }

    // 4. Rating check
    if (effectiveMinRating !== null && ratingVal < effectiveMinRating) {
      return false;
    }

    // 5. In-stock check
    if (filters.inStockOnly && product.inStock === false) {
      return false;
    }

    // 6. Prime / Assured check
    if (filters.primeOnly) {
      const hasPrimeOrAssured =
        (product.badge && /prime|assured/i.test(product.badge)) ||
        (product.delivery && /prime|tomorrow/i.test(product.delivery));
      if (!hasPrimeOrAssured) return false;
    }

    return true;
  });
}

/**
 * Universal Scraped Item Transformer
 * Normalizes item schemas from the unified scraper API.
 */
export function transformUniversalScrapedItem(item, scraper = {}, index = 0) {
  if (!item) return null;

  const brandName =
    (typeof item.brand === "string" ? item.brand : item.brand?.name) ||
    scraper.brand ||
    scraper.name ||
    "Brand";
  const channelName = scraper.channel || (scraper.id || "store").toLowerCase();
  const identifier =
    item._source_id ||
    item.asin ||
    item.sku ||
    item.product_id ||
    item.code ||
    `${channelName}_${index}_${Date.now()}`;

  const priceNum = item.price_num || parsePriceNumber(item.price);
  let formattedPrice = "Out of Stock";
  if (priceNum > 0) {
    formattedPrice = `₹${priceNum.toLocaleString("en-IN")}`;
  } else if (item.price && item.price !== "₹0" && item.price !== "0" && item.price !== "₹0.00" && item.price !== "Out of Stock") {
    formattedPrice = item.price;
  } else {
    formattedPrice = "Out of Stock";
  }

  let mrpText = item.mrp || "";
  if (priceNum > 0 && !mrpText && item.mrp_num) {
    mrpText = `₹${item.mrp_num.toLocaleString("en-IN")}`;
  } else if (priceNum <= 0) {
    mrpText = "";
  }

  let discountText = item.discount || "";
  if (priceNum <= 0 || discountText === "0%" || discountText === "0% OFF" || discountText === "0% off") {
    discountText = "";
  } else if (discountText && !discountText.includes("off") && !discountText.includes("OFF")) {
    discountText = `${discountText.replace("-", "")} off`;
  }

  const ratingStr = item.rating
    ? String(item.rating).includes("/")
      ? item.rating
      : `${item.rating}/5`
    : "4.3/5";

  const defaultImg =
    channelName === "apple"
      ? "https://fdn2.gsmarena.com/vv/bigpic/apple-iphone-15.jpg"
      : channelName === "samsung"
      ? "https://fdn2.gsmarena.com/vv/bigpic/samsung-galaxy-s24-5g.jpg"
      : channelName === "oppo"
      ? "https://www.oppo.com/content/dam/oppo_com/common/mkt/v2-2/oppo-reno16-series-en/navigation/reno16/440-440-white.png"
      : "https://placehold.co/300x300?text=Product+Image";

  return {
    id: `${channelName}_${identifier}`,
    asin: item.asin || null,
    sku: item.sku || null,
    name: item.title || item.name || item.model || `${brandName} Device`,
    image: (() => {
      let rawImg = item.image_url || item.image || item.plpImage || defaultImg;
      if (typeof rawImg === "string") {
        if (rawImg.includes("reno16c/440-440-white.png")) {
          return "https://www.oppo.com/content/dam/oppo_com/common/mkt/v2-2/oppo-reno16-series-en/navigation/reno16-f/440-440-white.png";
        }
        if (rawImg.includes("oppo-find-x10-series/navigation/x10-pro-max")) {
          return "https://www.oppo.com/content/dam/oppo_com/common/mkt/v2-2/find-x10-series-en/navigation/find-x10-pro-max/440-440-white.png";
        }
        if (rawImg.includes("oppo-find-x10-series/navigation/x10/")) {
          return "https://www.oppo.com/content/dam/oppo_com/common/mkt/v2-2/find-x10-series-en/navigation/find-x10/440-440-blue.png";
        }
        if (rawImg.includes("oppo-f35-series-en/navigation/f35-pro")) {
          return "https://www.oppo.com/content/dam/oppo_com/common/mkt/v2-2/f35-pro-in/navigation/440-440-orange.png";
        }
        if (rawImg.includes("oppo-f35-series-en/navigation/f35/")) {
          return "https://www.oppo.com/content/dam/oppo_com/common/mkt/v2-2/oppo-a7-pro-serice-en/navigation/a7-pro/440-440-blue.png";
        }
        if (rawImg.includes("oppo-reno13-pro.jpg") || rawImg.includes("oppo-reno13.jpg")) {
          return "https://rukminim2.flixcart.com/image/416/416/xif0q/mobile/p/n/e/-resized-original-imahzx4mab5zr9y3.jpeg?q=70";
        }
        if (
          rawImg.includes("040909a72fc45b94") ||
          rawImg.includes("t3.png") ||
          rawImg.includes("t3pro") ||
          rawImg.includes("t3ultra")
        ) {
          return "https://fdn2.gsmarena.com/vv/bigpic/vivo-x-fold3-pro.jpg";
        }
      }
      return rawImg;
    })(),
    price: formattedPrice,
    priceNum: priceNum,
    originalPrice: mrpText,
    discount: discountText,
    rating: ratingStr,
    delivery:
      item.delivery ||
      (priceNum <= 0 || item.in_stock === false ? "Currently unavailable" : "Express Delivery Available"),
    seller: item.seller || `${scraper.name || brandName} Official Store`,
    badge: scraper.badge || (item.is_prime ? "Prime" : `${scraper.name} Verified`),
    badgeType: channelName,
    badgeColor: scraper.color || "#444444",
    brand: brandName,
    inStock: priceNum > 0 && item.in_stock !== false,
    channel: channelName,
    sourceName: scraper.name || brandName,
    url: (() => {
      let cleanUrl = item.url || "";
      const rawTitle = item.title || item.name || item.model || brandName || "smartphone";
      const cleanTitle = rawTitle.replace(/\(.*?\)/g, "").replace(/\[.*?\]/g, "").replace(/[,]/g, " ").trim();
      const encodedTitle = encodeURIComponent(cleanTitle);

      if (channelName.includes("jiomart") || cleanUrl.includes("jiomart.com")) {
        if (cleanUrl.includes("/p/") && !cleanUrl.includes("/p/digital/")) {
          const articleId = item.article_id || item.item_code || item.sku || item.uid;
          const slug = item.slug || cleanUrl.split("/p/")[1]?.split("/")[0] || "";
          if (slug && articleId && !slug.endsWith(articleId)) {
            return `https://www.jiomart.com/p/digital/${slug}/${articleId}`;
          } else if (slug) {
            return `https://www.jiomart.com/p/digital/${slug}`;
          }
        }
        if (!cleanUrl || cleanUrl === "#" || cleanUrl.includes("text=null")) {
          return `https://www.jiomart.com/search?q=${encodedTitle}`;
        }
        return cleanUrl;
      }

      if (channelName.includes("croma") || cleanUrl.includes("croma.com")) {
        if (!cleanUrl || cleanUrl === "#" || cleanUrl.includes("null") || cleanUrl.includes("text=null")) {
          return `https://www.croma.com/searchB?q=${encodedTitle}`;
        }
        return cleanUrl;
      }

      if (channelName.includes("reliance") || cleanUrl.includes("reliancedigital")) {
        if (!cleanUrl || cleanUrl === "#" || cleanUrl.includes("null")) {
          return `https://www.reliancedigital.in/search?q=${encodedTitle}:relevance`;
        }
        return cleanUrl;
      }

      if (channelName.includes("amazon") || cleanUrl.includes("amazon.in")) {
        if (item.asin) return `https://www.amazon.in/dp/${item.asin}`;
        if (!cleanUrl || cleanUrl === "#" || cleanUrl.includes("null")) {
          return `https://www.amazon.in/s?k=${encodedTitle}`;
        }
        return cleanUrl;
      }

      if (channelName.includes("flipkart") || cleanUrl.includes("flipkart.com")) {
        if (!cleanUrl || cleanUrl === "#" || cleanUrl.includes("null")) {
          return `https://www.flipkart.com/search?q=${encodedTitle}`;
        }
        return cleanUrl;
      }

      return cleanUrl && cleanUrl !== "#" ? cleanUrl : `https://www.flipkart.com/search?q=${encodedTitle}`;
    })(),
    specs: item.specs || [],
    bank_offers: item.bank_offers || null,
    best_bank_offer: item.best_bank_offer || null,
    isLiveScraped: true,
  };
}

export async function fetchUnifiedCatalog() {
  const response = await fetch(`${UNIFIED_API_BASE}/products`, {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) {
    throw new Error(`Catalog request returned HTTP ${response.status}`);
  }

  const data = await response.json();
  if (!Array.isArray(data.products)) {
    throw new Error("Unified API returned an invalid product catalog.");
  }

  const scrapersById = new Map(ALL_SCRAPERS_CONFIG.map((scraper) => [scraper.id, scraper]));
  return data.products
    .map((item, index) => {
      const scraper = scrapersById.get(item._source_brand);
      return scraper ? transformUniversalScrapedItem(item, scraper, index) : null;
    })
    .filter(Boolean);
}

/**
 * Check health of a specific scraper
 */
export async function checkScraperHealth(scraper) {
  try {
    const res = await fetch(`${scraper.baseUrl}${scraper.statusEndpoint || "/api/status"}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return false;
    const data = await res.json();
    return Boolean(data && (data.status !== undefined || data.products !== undefined));
  } catch {
    return false;
  }
}

/**
 * Check all scrapers health in parallel
 */
export async function checkAllScrapersHealth() {
  const results = await Promise.allSettled(
    SCRAPERS_CONFIG.map(async (scraper) => {
      const isOnline = await checkScraperHealth(scraper);
      return { id: scraper.id, name: scraper.name, isOnline };
    })
  );

  const statusMap = {};
  results.forEach((res, idx) => {
    const scraper = SCRAPERS_CONFIG[idx];
    if (res.status === "fulfilled") {
      statusMap[scraper.id] = res.value.isOnline;
    } else {
      statusMap[scraper.id] = false;
    }
  });
  return statusMap;
}

/**
 * Search a single scraper with retry, polling, and data extraction
 */
export async function searchSingleScraper(scraper, query, filters = {}, onProgress = null) {
  const trimmed = String(query || "").trim();
  if (!trimmed) return [];

  const payload = {
    query: trimmed,
    pages: 3,
    pincode: import.meta.env.VITE_SCRAPER_PINCODE || "110058",
    in_stock_only: Boolean(filters.inStockOnly),
    min_price: filters.minPrice ? Number(filters.minPrice) : null,
    max_price: filters.maxPrice ? Number(filters.maxPrice) : null,
    min_rating: filters.minRating ? Number(filters.minRating) : null,
    prime_only: Boolean(filters.primeOnly),
  };

  onProgress?.({
    status: "connecting",
    progress: 10,
    message: `Connecting to ${scraper.name} scraper...`,
  });

  try {
    // 1. Trigger the scraper
    const triggerRes = await fetch(`${scraper.baseUrl}${scraper.scrapeEndpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(6000),
    });

    const triggerData = await triggerRes.json();
    if (!triggerRes.ok) {
      throw new Error(triggerData.error || `Scraper start returned HTTP ${triggerRes.status}`);
    }

    // If endpoint returns synchronous results (e.g. serverless or instant cache)
    const directResults = triggerData.results || triggerData.products;
    if (Array.isArray(directResults) && directResults.length > 0) {
      onProgress?.({
        status: "completed",
        progress: 100,
        message: `${scraper.name}: ${directResults.length} items found`,
      });
      return directResults
        .map((item, idx) => transformUniversalScrapedItem(item, scraper, idx))
        .filter(Boolean);
    }

    // 2. Poll the unified job status until completed or timed out.
    const maxPollAttempts = 180;
    for (let attempt = 0; attempt < maxPollAttempts; attempt++) {
      await new Promise((r) => setTimeout(r, 1000));

      const statusRes = await fetch(`${scraper.baseUrl}${scraper.statusEndpoint}`, {
        method: "GET",
        headers: { Accept: "application/json" },
        signal: AbortSignal.timeout(3000),
      });
      if (!statusRes.ok) {
        throw new Error(`${scraper.name} status returned HTTP ${statusRes.status}`);
      }
      const job = await statusRes.json();
      const progress = Number(job.progress) || Math.min(15 + attempt * 4, 95);
      const message =
        job.message ||
        (Array.isArray(job.logs) ? job.logs.at(-1)?.msg || job.logs.at(-1) : null) ||
        `Scraping ${scraper.name}...`;

      onProgress?.({
        status: job.status || "scraping",
        progress,
        message,
      });

      if (job.status === "error") {
        throw new Error(job.error || job.message || `${scraper.name} scraper reported an error`);
      }

      const queryMatches =
        !job.query ||
        job.query.toLowerCase().trim() === trimmed.toLowerCase().trim();
      if (job.status === "completed" && queryMatches) {
        const productsRes = await fetch(`${scraper.baseUrl}${scraper.productsEndpoint}`, {
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(10000),
        });
        if (!productsRes.ok) {
          throw new Error(`${scraper.name} products returned HTTP ${productsRes.status}`);
        }
        const productsData = await productsRes.json();
        if (!Array.isArray(productsData.products)) {
          throw new Error(`${scraper.name} returned an invalid product list.`);
        }
        return productsData.products
          .map((item, index) => transformUniversalScrapedItem(item, scraper, index))
          .filter(Boolean);
      }
    }

    throw new Error(`${scraper.name} search timed out before it completed.`);
  } catch (err) {
    onProgress?.({
      status: "error",
      progress: 0,
      message: `${scraper.name}: ${err.message}`,
      error: err.message,
    });
    throw err;
  }
}

/**
 * APPROACH 1: Frontend Parallel Fan-Out (Promise.allSettled) with Progressive Streaming
 *
 * Simultaneously sends HTTP requests to all configured scrapers.
 * As soon as any scraper returns results, `onProductsBatch` is invoked immediately
 * so the frontend UI renders partial results instantly without waiting for every store.
 */
export async function searchAcrossConfiguredScrapers(
  query,
  filters = {},
  onScraperStatus = null,
  onProductsBatch = null
) {
  const trimmed = String(query || "").trim();
  if (!trimmed) return [];

  // Initialize all active scrapers to "searching" status
  SCRAPERS_CONFIG.forEach((scraper) => {
    onScraperStatus?.(scraper.id, {
      status: "searching",
      progress: 5,
      message: `Searching ${scraper.name}...`,
      count: 0,
      color: scraper.color,
      name: scraper.name,
    });
  });

  // Launch all scrapers concurrently
  const scraperPromises = SCRAPERS_CONFIG.map(async (scraper) => {
    try {
      const items = await searchSingleScraper(scraper, trimmed, filters, (prog) => {
        onScraperStatus?.(scraper.id, {
          ...prog,
          color: scraper.color,
          name: scraper.name,
        });
      });

      // Sanitize items: strictly ensure returned products match query so non-matching models never leak or inflate counts!
      const validItems = filterProducts(items, trimmed, filters);

      // Stream only verified matching products directly to the UI immediately!
      if (validItems && validItems.length > 0) {
        onProductsBatch?.(validItems, scraper.id);
        onScraperStatus?.(scraper.id, {
          status: "completed",
          progress: 100,
          message: `${scraper.name}: ${validItems.length} products found`,
          count: validItems.length,
          color: scraper.color,
          name: scraper.name,
        });
      } else {
        onProductsBatch?.([], scraper.id);
        onScraperStatus?.(scraper.id, {
          status: "completed",
          progress: 100,
          message: `${scraper.name}: No matching items`,
          count: 0,
          color: scraper.color,
          name: scraper.name,
        });
      }

      return validItems;
    } catch (err) {
      onProductsBatch?.([], scraper.id);
      onScraperStatus?.(scraper.id, {
        status: "error",
        progress: 0,
        message: `${scraper.name} error: ${err.message}`,
        count: 0,
        color: scraper.color,
        name: scraper.name,
      });
      return [];
    }
  });

  // Wait for all scrapers to settle
  const settled = await Promise.allSettled(scraperPromises);
  const allAggregated = settled.flatMap((r) => (r.status === "fulfilled" ? r.value : []));

  return allAggregated;
}

// Search History Management
export function getSearchHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    return [];
  }
}

export function saveSearchQuery(queryText, appliedFilters = {}) {
  const trimmed = String(queryText || "").trim();
  if (!trimmed) return getSearchHistory();

  try {
    const existing = getSearchHistory();
    const filtered = existing.filter(
      (item) => item.query.toLowerCase() !== trimmed.toLowerCase()
    );

    const now = new Date();
    const formattedDate = now.toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
    const formattedTime = now.toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
    });

    const newItem = {
      id: "sh_" + Date.now(),
      query: trimmed,
      date: `${formattedDate}, ${formattedTime}`,
      timestamp: Date.now(),
      filters: appliedFilters,
    };

    const updated = [newItem, ...filtered].slice(0, 15);
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(updated));
    return updated;
  } catch (err) {
    return getSearchHistory();
  }
}

export function deleteHistoryItem(id) {
  try {
    const existing = getSearchHistory();
    const updated = existing.filter((item) => item.id !== id);
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(updated));
    return updated;
  } catch {
    return getSearchHistory();
  }
}

export function clearAllHistory() {
  try {
    localStorage.removeItem(HISTORY_STORAGE_KEY);
    return [];
  } catch {
    return [];
  }
}

// Backward compatibility exports
export const checkBackendHealth = () => {
  const amazonScraper = SCRAPERS_CONFIG.find((s) => s.id === "amazon") || SCRAPERS_CONFIG[0];
  return checkScraperHealth(amazonScraper);
};
export const searchWithBackendScraper = (q, f, p) => {
  const amazonScraper = SCRAPERS_CONFIG.find((s) => s.id === "amazon") || SCRAPERS_CONFIG[0];
  return searchSingleScraper(amazonScraper, q, f, p);
};
export const searchWithBrandScraper = (brand, q, f, p) => {
  const scraper = SCRAPERS_CONFIG.find((s) => s.brand.toLowerCase() === brand.toLowerCase()) || SCRAPERS_CONFIG[0];
  return searchSingleScraper(scraper, q, f, p);
};
export const fetchScraperHistory = async () => [];
export const fetchBrandProducts = async (brand) => {
  const scraper = SCRAPERS_CONFIG.find((s) => s.brand.toLowerCase() === brand.toLowerCase());
  if (!scraper) return [];
  try {
    const res = await fetch(`${scraper.baseUrl}${scraper.statusEndpoint}`, { signal: AbortSignal.timeout(2000) });
    if (!res.ok) return [];
    const data = await res.json();
    const items = data.products || data.results || [];
    return items.map((it, idx) => transformUniversalScrapedItem(it, scraper, idx));
  } catch {
    return [];
  }
};
