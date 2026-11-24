import React, { useState, useEffect, useRef } from "react";
import "./SamsungBulkBotModal.css";

const DEFAULT_ACCOUNTS = [
  { id: 1, name: "Profile 1", profile: "account_1", desc: "Local browser profile" },
  { id: 2, name: "Profile 2", profile: "account_2", desc: "Local browser profile" },
  { id: 3, name: "Profile 3", profile: "account_3", desc: "Local browser profile" },
  { id: 4, name: "Profile 4", profile: "account_4", desc: "Local browser profile" },
  { id: 5, name: "Profile 5", profile: "account_5", desc: "Local browser profile" },
];

const MAX_BULK_QUANTITY = 10;

const CARD_GRADIENTS = [
  "linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)",
  "linear-gradient(135deg, #eb3349 0%, #f45c43 100%)",
  "linear-gradient(135deg, #134e5e 0%, #71b280 100%)",
];

const STORES = {
  amazon: { name: "Amazon", logo: "AMAZON", defaultUrl: "https://www.amazon.in/" },
  apple: { name: "Apple", logo: "Apple", defaultUrl: "https://www.apple.com/in/" },
  croma: { name: "Croma", logo: "CROMA", defaultUrl: "https://www.croma.com/" },
  flipkart: { name: "Flipkart", logo: "FLIPKART", defaultUrl: "https://www.flipkart.com/" },
  jiomart: { name: "JioMart", logo: "JIOMART", defaultUrl: "https://www.jiomart.com/" },
  reliance: { name: "Reliance Digital", logo: "RELIANCE", defaultUrl: "https://www.reliancedigital.in/" },
  samsung: { name: "Samsung", logo: "SAMSUNG", defaultUrl: "https://www.samsung.com/in/" },
  vivo: { name: "Vivo", logo: "VIVO", defaultUrl: "https://shop.vivo.com/in/" },
};

const STORE_ALIASES = {
  "amazon": "amazon",
  "apple": "apple",
  "croma": "croma",
  "flipkart": "flipkart",
  "jio mart": "jiomart",
  "jiomart": "jiomart",
  "reliance": "reliance",
  "reliance digital": "reliance",
  "samsung": "samsung",
  "vivo": "vivo",
};

const PIPELINE_STEPS = [
  { id: 1, name: "Profile Init", desc: "Launch Chrome Profile with detached mode" },
  { id: 2, name: "SKU Select", desc: "Configure specs, color, storage & buy now" },
  { id: 3, name: "Cart & Checkout", desc: "Continue through the store checkout flow" },
  { id: 4, name: "Address Fill", desc: "Use the saved browser profile or local settings" },
  { id: 5, name: "Card Injection", desc: "Auto-fill card & await OTP handoff" },
];

export default function SamsungBulkBotModal({ product, onClose }) {
  const productUrl = product?.url || product?.link || "";
  const explicitStore = [product?.channel, product?.scraper, product?.store]
    .map((value) => String(value || "").trim().toLowerCase())
    .map((value) => STORE_ALIASES[value])
    .find(Boolean);
  const urlHost = (() => {
    try {
      return new URL(productUrl).hostname.toLowerCase();
    } catch {
      return "";
    }
  })();
  const urlStore = Object.keys(STORES).find((key) => {
    const host = new URL(STORES[key].defaultUrl).hostname;
    return urlHost === host || urlHost.endsWith(`.${host}`);
  });
  const brandKey = explicitStore || urlStore || "";
  const store = STORES[brandKey];
  const brandName = store?.name || "Unsupported Store";
  const brandLogo = store?.logo || "STORE";
  const defaultUrl = store?.defaultUrl || "";
  const apiBase = brandKey ? `/api/automation/${brandKey}` : "";

  const isApple = brandKey === "apple";
  const isCroma = brandKey === "croma";
  const isAmazon = brandKey === "amazon";

  const [selectedAccount, setSelectedAccount] = useState(1);
  const [selectedCardIndex, setSelectedCardIndex] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [confirmAutoPlace, setConfirmAutoPlace] = useState(false);
  const [botStatus, setBotStatus] = useState("idle");
  const [currentStep, setCurrentStep] = useState(0);
  const [logs, setLogs] = useState([]);
  const [browserLaunching, setBrowserLaunching] = useState(false);
  const [cards, setCards] = useState([]);
  const [availablePaymentMethods, setAvailablePaymentMethods] = useState([]);
  const [configurationError, setConfigurationError] = useState("");
  const [screenTab, setScreenTab] = useState("screen"); // "screen" | "terminal"
  const [liveScreenshot, setLiveScreenshot] = useState(null);
  const [liveUrl, setLiveUrl] = useState(defaultUrl);
  const [notification, setNotification] = useState(null);

  // Croma Payment & OTP state
  const [paymentMethod, setPaymentMethod] = useState("cards");
  const [upiId, setUpiId] = useState("");
  const [gstNumber, setGstNumber] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpSubmitting, setOtpSubmitting] = useState(false);
  const [otpRequired, setOtpRequired] = useState(false);

  const csvInputRef = useRef(null);

  const pipelineSteps = [
    { id: 1, name: "Browser Profile", desc: `Open the local ${brandName} profile` },
    { id: 2, name: "Product & Cart", desc: "Navigate to the selected product and store checkout" },
    { id: 3, name: "Account Verification", desc: "Use the signed-in profile or enter a verification code" },
    { id: 4, name: "Delivery & Payment", desc: "Use saved details and the selected payment method" },
    { id: 5, name: "Review", desc: "Review the checkout result in the visible browser" },
  ];

  const logsEndRef = useRef(null);
  const pollTimerRef = useRef(null);

  // Auto-scroll logs terminal
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const startPolling = () => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = setInterval(async () => {
      try {
        const statusRes = await fetch(`${apiBase}/status`);
        if (!statusRes.ok) return;
        const data = await statusRes.json();
        if (data.logs && data.logs.length > 0) {
          setLogs(data.logs);
        }
        if (data.screenshot) {
          setLiveScreenshot(data.screenshot);
        }
        if (data.current_url) {
          setLiveUrl(data.current_url);
        }
        if (data.current_step !== undefined && data.current_step > 0) {
          setCurrentStep(data.current_step);
        }
        if (data.otp_required !== undefined) {
          setOtpRequired(Boolean(data.otp_required));
        }
        if (data.status) {
          setBotStatus(data.status);
          if (data.status === "awaiting_otp") {
            setOtpRequired(true);
          } else if (data.status === "awaiting_upi_qr") {
            setOtpRequired(false);
            // Keep polling active to stream live UPI QR code
          } else if (data.status === "completed" || data.status === "error" || data.status === "cancelled") {
            setOtpRequired(false);
            // Keep streaming for 20 more seconds so live mirror doesn't freeze abruptly
            setTimeout(() => {
              if (pollTimerRef.current) {
                clearInterval(pollTimerRef.current);
                pollTimerRef.current = null;
              }
            }, 25000);
          }
        }
        if (data.notification) {
          setNotification(data.notification);
        }
      } catch {
        // ignore transient poll errors
      }
    }, 350);
  };

  // Load automation cards config from backend & check initial status
  useEffect(() => {
    if (!apiBase) {
      setConfigurationError("Automated checkout is not available for this store.");
      return;
    }

    let active = true;
    const loadConfiguration = async () => {
      try {
        const response = await fetch(`${apiBase}/config`);
        const config = await response.json();
        if (!response.ok) throw new Error(config.error || `Server returned ${response.status}`);
        if (!active) return;
        const methods = config.payment_methods || [];
        setAvailablePaymentMethods(methods);
        setPaymentMethod((current) => methods.includes(current) ? current : (methods[0] || ""));
        setCards((config.cards || []).map((card, index) => ({
          ...card,
          id: `configured-${index}`,
          color: CARD_GRADIENTS[index % CARD_GRADIENTS.length],
        })));
        setConfigurationError("");

        const statusResponse = await fetch(`${apiBase}/status`);
        const status = await statusResponse.json();
        if (!statusResponse.ok) throw new Error(status.error || `Server returned ${statusResponse.status}`);
        if (!active) return;
        if (status.screenshot) setLiveScreenshot(status.screenshot);
        if (status.current_url) setLiveUrl(status.current_url);
        if (status.logs?.length) setLogs(status.logs);
        if (["starting", "running", "awaiting_otp", "awaiting_upi_qr", "awaiting_confirmation"].includes(status.status)) {
          setBotStatus(status.status);
          startPolling();
        }
      } catch (error) {
        if (active) setConfigurationError(`Could not load automation settings: ${error.message}`);
      }
    };
    loadConfiguration();
    return () => {
      active = false;
    };
  }, [apiBase]);

  // Cleanup polling interval on unmount
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, []);

  // Initial greeting log
  useEffect(() => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs([
      `[${timestamp}] [SYSTEM] ${brandName} Automation Bot initialized.`,
      `[${timestamp}] [SYSTEM] Connected to /api/automation/${brandKey}.`,
      `[${timestamp}] [INFO] Target Device: ${product?.name || brandName + " Smartphone"}.`,
      `[${timestamp}] [INFO] Active Account: Account ${selectedAccount} (profile: account_${selectedAccount}).`,
      `[${timestamp}] [INFO] Ready to open the store flow in a visible Chrome browser.`,
    ]);
  }, [product, selectedAccount, brandName, brandKey]);

  // Calculate pricing
  const unitPriceNum = (() => {
    if (typeof product?.price === "number") return product.price;
    const cleaned = String(product?.price || "").replace(/[^0-9.]/g, "");
    return parseFloat(cleaned) || 0;
  })();
  const estimatedTotalPrice = unitPriceNum * quantity;

  // Add a log entry helper
  const addLog = (msg, level = "INFO") => {
    const ts = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, `[${ts}] [${level}] ${msg}`]);
  };

  // Launch Live Chrome Window via Backend
  const handleLaunchBrowser = async () => {
    if (!apiBase) return;
    setBrowserLaunching(true);
    addLog(`Opening the local ${brandName} browser profile ${selectedAccount}...`, "ACTION");
    try {
      const res = await fetch(`${apiBase}/launch-browser`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account: selectedAccount }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `Server returned ${res.status}`);
      addLog(`Browser profile ${selectedAccount} is starting.`, "SUCCESS");
      startPolling();
    } catch (error) {
      addLog(`Could not launch browser: ${error.message}`, "ERROR");
    } finally {
      setBrowserLaunching(false);
    }
  };

  // Handle CSV Virtual Cards Import
  const handleCsvImport = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (event) => {
      try {
        const text = event.target.result;
        const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
        if (lines.length < 2) {
          alert("CSV must contain a header row and at least 1 card row.");
          return;
        }

        const rawHeaders = lines[0].split(",").map((h) => h.trim().toLowerCase().replace(/['"]/g, ""));
        const findCol = (aliases) => rawHeaders.findIndex((h) => aliases.some((a) => h.includes(a)));

        const numIdx = findCol(["number", "card_number", "pan", "cardnum", "card"]);
        const nameIdx = findCol(["name", "holder", "cardholder"]);
        const expIdx = findCol(["exp", "expiry", "expire", "valid"]);
        const cvvIdx = findCol(["cvv", "cvc", "security", "code"]);
        const passIdx = findCol(["password", "pass", "pin", "virtual_password", "pwd"]);
        const brandIdx = findCol(["brand", "type", "network"]);
        const labelIdx = findCol(["label", "bank", "title", "alias"]);
        if (numIdx < 0 || expIdx < 0 || cvvIdx < 0) {
          alert("CSV must include card number, expiry, and CVV columns.");
          return;
        }

        const gradients = [
          "linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%)",
          "linear-gradient(135deg, #11998e 0%, #38ef7d 100%)",
          "linear-gradient(135deg, #8a2387 0%, #e94057 50%, #f27121 100%)",
          "linear-gradient(135deg, #4b6cb7 0%, #182848 100%)",
          "linear-gradient(135deg, #fc4a1a 0%, #f7b733 100%)"
        ];

        const parsedCards = [];
        for (let i = 1; i < lines.length; i++) {
          const row = lines[i].split(",").map((c) => c.trim().replace(/^["']|["']$/g, ""));
          if (row.length === 0 || !row[0]) continue;

          let rawNum = numIdx >= 0 ? row[numIdx] : row[0];
          rawNum = rawNum.replace(/\D/g, "");
          if (rawNum.length < 12) continue;

          const cardLast4 = rawNum.slice(-4);
          const cardName = (nameIdx >= 0 && row[nameIdx]) ? row[nameIdx] : "";
          const cardExp = row[expIdx] || "";
          const cardCvv = row[cvvIdx] || "";
          if (!cardExp || !cardCvv) continue;
          const cardPass = (passIdx >= 0 && row[passIdx]) ? row[passIdx] : "";
          let cardBrand = (brandIdx >= 0 && row[brandIdx]) ? row[brandIdx] : "";
          if (!cardBrand) {
            if (rawNum.startsWith("4")) cardBrand = "Visa";
            else if (rawNum.startsWith("5")) cardBrand = "Mastercard";
            else if (rawNum.startsWith("3")) cardBrand = "Amex";
            else if (rawNum.startsWith("6")) cardBrand = "RuPay";
            else cardBrand = "Virtual Card";
          }
          const cardLabel = (labelIdx >= 0 && row[labelIdx]) ? row[labelIdx] : `Virtual Card ${i}`;

          parsedCards.push({
            id: `virtual_${Date.now()}_${i}`,
            label: cardLabel,
            number: rawNum.replace(/(\d{4})(?=\d)/g, "$1 "),
            last4: cardLast4,
            name: cardName,
            expiry: cardExp,
            cvv: cardCvv,
            password: cardPass,
            brand: cardBrand,
            isVirtual: true,
            color: gradients[(i - 1) % gradients.length]
          });
        }

        if (parsedCards.length === 0) {
          alert("Could not find valid card numbers in the uploaded CSV.");
          return;
        }

        const response = await fetch(`${apiBase}/import-cards`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cards: parsedCards }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `Server returned ${response.status}`);
        setCards((prev) => [...parsedCards, ...prev]);
        setSelectedCardIndex(0);
        addLog(`Imported ${parsedCards.length} payment card(s) into the local session.`, "SUCCESS");
      } catch (err) {
        alert("Failed to parse CSV: " + err.message);
      }
    };
    reader.readAsText(file);
    if (csvInputRef.current) csvInputRef.current.value = "";
  };

  // Submit OTP handler
  const handleSubmitOtp = async () => {
    if (!otpCode || otpCode.trim().length === 0) {
      alert("Please enter the verification OTP");
      return;
    }
    setOtpSubmitting(true);
    addLog(`Submitting the verification code to ${brandName}...`, "ACTION");
    try {
      const res = await fetch(`${apiBase}/submit-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ otp: otpCode.trim() }),
      });
      const data = await res.json();
      if (res.ok) {
        addLog("Verification code accepted by the local backend.", "SUCCESS");
        setOtpCode("");
        setOtpRequired(false);
      } else {
        throw new Error(data.error || `Server returned ${res.status}`);
      }
    } catch (err) {
      addLog(`Failed to send OTP: ${err.message}`, "ERROR");
    } finally {
      setOtpSubmitting(false);
    }
  };

  // Start the selected store's checkout flow.
  const handleStartBot = async () => {
    if (!apiBase || !availablePaymentMethods.includes(paymentMethod)) return;
    if (["starting", "running", "awaiting_otp", "awaiting_upi_qr", "awaiting_confirmation"].includes(botStatus)) return;
    if (quantity > 1 && !confirmAutoPlace) {
      setConfigurationError("Confirm automated final order submission before starting bulk checkout.");
      return;
    }
    if (["cards", "card", "credit_debit", "emi"].includes(paymentMethod) && !cards.length) {
      setConfigurationError("Import a card or configure AUTOMATION_CARDS_FILE before selecting card payment.");
      return;
    }
    if (paymentMethod === "upi" && !upiId.trim()) {
      setConfigurationError("Enter a UPI ID before starting this payment flow.");
      return;
    }
    setConfigurationError("");
    setCurrentStep(1);
    setNotification(null);

    addLog(`[START] Starting the ${brandName} checkout flow...`, "START");

    try {
      const res = await fetch(`${apiBase}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account: selectedAccount,
          product_name: product?.name || `${brandName} Smartphone`,
          product_url: productUrl,
          quantity,
          confirm_auto_place: confirmAutoPlace,
          card_index: selectedCardIndex,
          payment_method: paymentMethod,
          upi_id: paymentMethod === "upi" ? upiId.trim() : "",
          gst_number: gstNumber,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || `Server returned ${res.status}`);
      }
      setBotStatus("starting");
      startPolling();

    } catch (err) {
      setBotStatus("error");
      addLog(`Failed to start automation bot: ${err.message}`, "ERROR");
    }
  };

  const handleResetBot = async () => {
    try {
      const response = await fetch(`${apiBase}/stop`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Server returned ${response.status}`);
      setBotStatus("cancelled");
      addLog("Stop requested. Check the browser to confirm its current state.", "SYSTEM");
    } catch (error) {
      addLog(`Could not stop automation: ${error.message}`, "ERROR");
    }
  };

  return (
    <div className="samsung-bulk-modal-overlay" onClick={onClose}>
      <div className="samsung-bulk-modal-container" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="samsung-bulk-header">
          <div className="samsung-bulk-header-left">
            <span
              className="samsung-logo-badge"
              style={
                isApple
                  ? { background: "#0071e3", boxShadow: "0 0 15px rgba(0, 113, 227, 0.5)" }
                  : brandKey === "croma"
                  ? { background: "#00b259", boxShadow: "0 0 15px rgba(0, 178, 89, 0.5)" }
                  : brandKey === "flipkart"
                  ? { background: "#2874f0", color: "#fff", boxShadow: "0 0 15px rgba(40, 116, 240, 0.5)" }
                  : brandKey === "amazon"
                  ? { background: "#ff9900", color: "#111", boxShadow: "0 0 15px rgba(255, 153, 0, 0.5)" }
                  : brandKey === "vivo"
                  ? { background: "#415fff", color: "#fff", boxShadow: "0 0 15px rgba(65, 95, 255, 0.5)" }
                  : brandKey === "reliance"
                  ? { background: "#e11b22", boxShadow: "0 0 15px rgba(225, 27, 34, 0.5)" }
                  : brandKey === "jiomart"
                  ? { background: "#008ecc", boxShadow: "0 0 15px rgba(0, 142, 204, 0.5)" }
                  : brandKey === "oppo"
                  ? { background: "#008b47", boxShadow: "0 0 15px rgba(0, 139, 71, 0.5)" }
                  : {}
              }
            >
              {brandLogo}
            </span>
            <div className="header-titles">
              <h2>{brandName} Checkout Automation</h2>
              <p>Store checkout automation • Connected to <code>{apiBase || "unavailable"}</code></p>
            </div>
          </div>
          <div className="samsung-bulk-header-right">
            <span className={`bot-status-pill status-${botStatus}`}>
              {botStatus === "idle" && "⚪ Bot Idle"}
              {botStatus === "starting" && "🟡 Starting"}
              {botStatus === "running" && "🟡 Bot Running"}
              {botStatus === "awaiting_otp" && "🔐 Verification Required"}
              {botStatus === "awaiting_confirmation" && "🟠 Store / bank action required"}
              {botStatus === "completed" && "🟢 Ready for OTP"}
              {botStatus === "cancelled" && "🟠 Purchase Cancelled (Alert Sent)"}
              {botStatus === "error" && "🔴 Error"}
            </span>
            <button type="button" className="bulk-modal-close-btn" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="samsung-bulk-body">
          {/* Left Column: Device & Order Specs */}
          <div className="bulk-col bulk-col-product">
            <div className="bulk-section-card">
              <h3 className="section-title">📱 Target Device</h3>
              <div className="bulk-product-preview">
                <img src={product?.image} alt={product?.name} className="bulk-product-img" />
                <div className="bulk-product-meta">
                  <h4>{product?.name}</h4>
                  <p className="bulk-product-price">Unit Price: <strong>{product?.price}</strong></p>
                  <p className="bulk-product-seller">Store: {product?.seller || `${brandName} Official Store`}</p>
                </div>
              </div>

              <p className="section-hint">
                Bulk checkout is supported for up to {MAX_BULK_QUANTITY} units. The final estimated total may differ from the store's total.
              </p>

              {/* Order Calculation */}
              <div className="bulk-pricing-summary">
                <div className="pricing-row">
                  <span>Unit Price:</span>
                  <span>₹{Math.round(unitPriceNum).toLocaleString("en-IN")}</span>
                </div>
                <div className="pricing-row">
                  <span>Quantity:</span>
                  <input
                    aria-label="Order quantity"
                    type="number"
                    min="1"
                    max={MAX_BULK_QUANTITY}
                    step="1"
                    value={quantity}
                    onChange={(event) => {
                      const nextQuantity = Math.min(
                        MAX_BULK_QUANTITY,
                        Math.max(1, Math.floor(Number(event.target.value) || 1)),
                      );
                      setQuantity(nextQuantity);
                      setConfirmAutoPlace(false);
                    }}
                  />
                </div>
                <div className="pricing-row total-row">
                  <span>Total Estimated:</span>
                  <span className="total-val">₹{Math.round(estimatedTotalPrice).toLocaleString("en-IN")}</span>
                </div>
              </div>

              {/* Delivery Address Card */}
              <div className="bulk-address-card">
                <div className="address-header">
                  <span>📍 Shipping Details</span>
                </div>
                <p className="address-lines">
                  Shipping information is read from the local browser profile or environment settings. Personal details are not returned by the API.
                </p>
                {isCroma ? (
                  <div style={{ marginTop: "8px", display: "flex", alignItems: "center", gap: "8px" }}>
                    <label htmlFor="croma-gst-number">GST number (optional):</label>
                    <input
                      id="croma-gst-number"
                      type="text"
                      value={gstNumber}
                      onChange={(e) => setGstNumber(e.target.value)}
                      placeholder="Enter GST number"
                    />
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          {/* Middle Column: Multi-Account & Payment Rotation */}
          <div className="bulk-col bulk-col-config">
            {/* Account Selector */}
            <div className="bulk-section-card">
              <h3 className="section-title">
                👥 Browser Profile
                <span className="section-badge">Local</span>
              </h3>
              <p className="section-hint">Choose one of the local browser profiles configured for this store:</p>
              <div className="accounts-grid">
                {DEFAULT_ACCOUNTS.map((acc) => (
                  <button
                    key={acc.id}
                    type="button"
                    className={`account-card ${selectedAccount === acc.id ? "active" : ""}`}
                    onClick={() => {
                      setSelectedAccount(acc.id);
                      addLog(`Switched active profile to Account ${acc.id} (${acc.profile}).`);
                    }}
                  >
                    <span className="account-avatar">👤</span>
                    <div className="account-details">
                      <span className="account-name">{acc.name}</span>
                      <span className="account-desc">{acc.profile} • {acc.desc}</span>
                    </div>
                    {selectedAccount === acc.id && <span className="account-check">✓</span>}
                  </button>
                ))}
              </div>
            </div>

            {/* Payment Method Selector */}
            <div className="bulk-section-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3 className="section-title" style={{ margin: 0 }}>
                  💰 Payment Method
                  <span className="section-badge" style={{ background: "#00b259" }}>{availablePaymentMethods.length} Available</span>
                </h3>
              </div>
              <p className="section-hint" style={{ marginTop: "4px" }}>Select payment option for {brandName} checkout:</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "8px", marginTop: "10px" }}>
                {[
                  { id: "cards", label: "Credit / Debit Cards", icon: "💳", desc: "Use a locally configured card" },
                  { id: "emi", label: "EMI on Cards", icon: "🏦", desc: "Use the configured card with EMI" },
                  { id: "upi", label: "UPI", icon: "📱", desc: "Enter the UPI ID for this session" },
                  { id: "cod", label: "Cash on Delivery", icon: "💵", desc: "Choose COD if the store offers it" },
                  { id: "netbanking", label: "Netbanking", icon: "🌐", desc: "Continue with the store's bank flow" },
                ].filter((option) => availablePaymentMethods.includes(option.id)).map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    style={{
                      background: paymentMethod === opt.id ? "rgba(0, 178, 89, 0.22)" : "rgba(255, 255, 255, 0.04)",
                      border: paymentMethod === opt.id ? "1.5px solid #00b259" : "1px solid rgba(255, 255, 255, 0.1)",
                      borderRadius: "8px",
                      padding: "8px 10px",
                      textAlign: "left",
                      cursor: "pointer",
                      display: "flex",
                      flexDirection: "column",
                      gap: "2px",
                      transition: "all 0.15s ease"
                    }}
                    onClick={() => {
                      setPaymentMethod(opt.id);
                      addLog(`Selected payment method: ${opt.label}`);
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <span>{opt.icon}</span>
                      <strong style={{ color: "#fff", fontSize: "11px" }}>{opt.label}</strong>
                    </div>
                    <span style={{ fontSize: "9.5px", color: "#94a3b8" }}>{opt.desc}</span>
                  </button>
                ))}
              </div>

              {paymentMethod === "upi" && (
                <div style={{ marginTop: "8px", padding: "8px 10px", background: "rgba(0,0,0,0.25)", borderRadius: "6px", display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "11px", color: "#cbd5e1" }}>UPI ID:</span>
                  <input
                    type="text"
                    value={upiId}
                    onChange={(e) => setUpiId(e.target.value)}
                    placeholder="UPI ID"
                    style={{ flex: 1, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: "4px", padding: "4px 8px", color: "#fff", fontSize: "11px" }}
                  />
                </div>
              )}

              {paymentMethod === "cod" && (
                <div style={{ marginTop: "8px", padding: "8px 12px", background: "rgba(16, 185, 129, 0.12)", border: "1px solid rgba(16, 185, 129, 0.3)", borderRadius: "6px", display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "16px" }}>💵</span>
                  <span style={{ fontSize: "11px", color: "#a7f3d0" }}>
                    <strong>COD selected:</strong> The store may place an order automatically. Review the item, address, and payment details in the visible browser.
                  </span>
                </div>
              )}
            </div>

            {/* Rotating Cards Selector with Import CSV */}
            <div className="bulk-section-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3 className="section-title" style={{ margin: 0 }}>
                  💳 Payment Card Rotation
                  <span className="section-badge">{cards.length} Cards</span>
                </h3>
                {/* Hidden File Input for CSV */}
                <input
                  type="file"
                  ref={csvInputRef}
                  accept=".csv"
                  style={{ display: "none" }}
                  onChange={handleCsvImport}
                />
                <button
                  type="button"
                  style={{
                    background: "linear-gradient(135deg, #00b259 0%, #008b47 100%)",
                    color: "#fff",
                    border: "none",
                    borderRadius: "6px",
                    padding: "5px 10px",
                    fontSize: "11px",
                    fontWeight: "600",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                    boxShadow: "0 2px 8px rgba(0, 178, 89, 0.3)"
                  }}
                  onClick={() => csvInputRef.current?.click()}
                  title="Upload CSV to auto-read virtual cards & passwords"
                >
                  📥 Import CSV
                </button>
              </div>

              <div className="cards-slider">
                {cards.length ? cards.map((card, idx) => (
                    <div
                      key={card.id || idx}
                      className={`virtual-card ${selectedCardIndex === idx ? "active-card" : ""}`}
                      style={{ background: card.color || CARD_GRADIENTS[0] }}
                      onClick={() => {
                        setSelectedCardIndex(idx);
                        addLog(`Selected ${card.label} (${card.brand} ending ${card.last4}).`);
                      }}
                    >
                      <div className="card-top">
                        <span className="card-chip">💳</span>
                        <span className="card-brand">{card.brand}</span>
                      </div>
                      <div className="card-number">•••• •••• •••• {card.last4}</div>
                      <div className="card-bottom">
                        <span className="card-lbl">Stored locally for this session</span>
                      </div>
                    </div>
                  )) : (
                    <p className="section-hint">
                      No card is configured. Import a local CSV or set AUTOMATION_CARDS_FILE on the backend.
                    </p>
                  )}
              </div>
            </div>

            <div className="bulk-section-card">
              <h3 className="section-title">Checkout review</h3>
              <p className="section-hint">
                Use your own signed-in browser profile. Review the store, product, quantity, delivery details, and final store total. OTP, 3-D Secure, and UPI authentication remain interactive.
              </p>
              {quantity > 1 && (
                <label style={{ display: "flex", gap: "8px", alignItems: "flex-start", marginTop: "10px", color: "#fbbf24", fontSize: "12px" }}>
                  <input
                    type="checkbox"
                    checked={confirmAutoPlace}
                    onChange={(event) => {
                      setConfirmAutoPlace(event.target.checked);
                      setConfigurationError("");
                    }}
                  />
                  <span>I authorize automated final order submission for this bulk quantity.</span>
                </label>
              )}
            </div>
          </div>

          {/* Right Column: Execution Stepper & Terminal Console */}
          <div className="bulk-col bulk-col-terminal">
            {/* Pipeline Stepper */}
            <div className="bulk-section-card">
              <h3 className="section-title">⚡ Automation Pipeline</h3>
              <div className="pipeline-steps">
                {pipelineSteps.map((st) => {
                  let stepState = "pending";
                  if (currentStep > st.id || botStatus === "completed") stepState = "done";
                  else if (currentStep === st.id) stepState = "active";

                  return (
                    <div key={st.id} className={`pipeline-step step-${stepState}`}>
                      <div className="step-circle">
                        {stepState === "done" ? "✓" : st.id}
                      </div>
                      <div className="step-info">
                        <span className="step-title">{st.name}</span>
                        <span className="step-desc">{st.desc}</span>
                      </div>
                      {stepState === "active" && <span className="step-pulse" />}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Payment Gateway Alert / UPI QR Code / COD Confirmation Banner */}
            {notification && (botStatus === "completed" || botStatus === "cancelled" || botStatus === "awaiting_upi_qr" || botStatus === "awaiting_confirmation") && (() => {
              const statusUpper = (notification.status || "").toUpperCase();
              const reasonUpper = (notification.reason || "").toUpperCase();
              const isCodConfirmed = Boolean(
                statusUpper.includes("COD") ||
                statusUpper.includes("CASH ON DELIVERY")
              );
              const isUpiActive = Boolean(
                !isCodConfirmed &&
                (statusUpper.includes("UPI") || reasonUpper.includes("UPI")) &&
                !statusUpper.includes("CART") &&
                !statusUpper.includes("EMPTY") &&
                !statusUpper.includes("DECLINED")
              );
              const isSuccessBanner = isCodConfirmed || isUpiActive;

              return (
                <div style={{
                  background: isSuccessBanner
                    ? "linear-gradient(90deg, rgba(16, 185, 129, 0.25), rgba(6, 182, 212, 0.2))"
                    : "linear-gradient(90deg, rgba(239, 68, 68, 0.25), rgba(245, 158, 11, 0.2))",
                  border: isSuccessBanner
                    ? "1px solid rgba(16, 185, 129, 0.6)"
                    : "1px solid rgba(239, 68, 68, 0.6)",
                  borderRadius: "10px",
                  padding: "14px 18px",
                  marginBottom: "14px",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "14px",
                  boxShadow: isSuccessBanner
                    ? "0 4px 20px rgba(16, 185, 129, 0.25)"
                    : "0 4px 20px rgba(239, 68, 68, 0.25)"
                }}>
                  <span style={{ fontSize: "30px", marginTop: "2px" }}>
                    {isCodConfirmed ? "💵" : isUpiActive ? "⚡" : "⚠️"}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                      <strong style={{
                        color: isSuccessBanner ? "#34d399" : "#f87171",
                        fontSize: "14px",
                        letterSpacing: "0.5px"
                      }}>
                        {notification.status ? notification.status.toUpperCase() : "ALERT"}
                      </strong>
                      <span style={{
                        background: isSuccessBanner ? "#10b981" : "#ef4444",
                        color: "#fff",
                        fontSize: "10px",
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontWeight: "700"
                      }}>
                        {isCodConfirmed ? "COD CONFIRMED" : isUpiActive ? "UPI FLOW ACTIVE" : "ACTION REQUIRED"}
                      </span>
                    </div>

                    {isCodConfirmed ? (
                      <>
                        <p style={{ margin: "6px 0 0", color: "#f1f5f9", fontSize: "13px", lineHeight: "1.5" }}>
                          ✅ <strong>Cash on Delivery:</strong> {notification.reason || "Review the order status in the store browser."}
                        </p>
                      </>
                    ) : isUpiActive ? (
                      <>
                        <p style={{ margin: "6px 0 0", color: "#f1f5f9", fontSize: "13px", lineHeight: "1.5" }}>
                          📱 <strong>UPI flow active:</strong> Continue and verify the payment in the visible store browser.
                        </p>
                        <div style={{ marginTop: "8px", display: "flex", gap: "10px", alignItems: "center" }}>
                          <a
                            href={`${apiBase}/live-view`}
                            target="_blank"
                            rel="noreferrer"
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "6px",
                              background: "#10b981",
                              color: "#fff",
                              padding: "6px 14px",
                              borderRadius: "6px",
                              fontSize: "12px",
                              fontWeight: "700",
                              textDecoration: "none"
                            }}
                          >
                            ↗️ Open Live View
                          </a>
                          <span style={{ fontSize: "11px", color: "#94a3b8" }}>
                            Or scan from the Desktop Live Screen below
                          </span>
                        </div>
                      </>
                    ) : (
                      <>
                        <p style={{ margin: "6px 0 0", color: "#f1f5f9", fontSize: "13px", lineHeight: "1.5" }}>
                          <strong>Reason:</strong> {notification.reason || "Action required on payment portal."}
                        </p>
                        <div style={{ marginTop: "6px", padding: "6px 10px", background: "rgba(0,0,0,0.35)", borderRadius: "6px", fontSize: "11px", color: "#94a3b8" }}>
                          💡 <strong>Notice:</strong> Please inspect the visible Chrome window on your desktop to complete or verify your checkout.
                        </div>
                      </>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* Live Streaming Terminal & Desktop Screen Mirror */}
            <div className="bulk-section-card terminal-card">
              <div className="terminal-header">
                <div className="terminal-dots">
                  <span className="dot red" />
                  <span className="dot yellow" />
                  <span className="dot green" />
                </div>
                <div className="screen-view-tabs">
                  <button
                    type="button"
                    className={`screen-tab-btn ${screenTab === "screen" ? "active" : ""}`}
                    onClick={() => setScreenTab("screen")}
                  >
                    🖥️ Desktop Live Screen
                  </button>
                  <button
                    type="button"
                    className={`screen-tab-btn ${screenTab === "terminal" ? "active" : ""}`}
                    onClick={() => setScreenTab("terminal")}
                  >
                    ⌨️ Terminal Logs
                  </button>
                </div>
                <span className={`terminal-badge ${screenTab === "screen" ? "badge-screen" : ""}`}>
                  {screenTab === "screen" ? "● SCREEN LIVE" : "LIVE STREAM"}
                </span>
              </div>

              {screenTab === "screen" ? (
                <div className="desktop-screen-viewport">
                  <div className="screen-browser-bar">
                    <div className="browser-nav-icons">
                      <span>‹</span>
                      <span>›</span>
                      <span>↻</span>
                    </div>
                    <div className="screen-url-bar">
                      <span className="lock-icon">🔒</span>
                      <span className="url-text">{liveUrl || "https://www.samsung.com/in/"}</span>
                    </div>
                    <span className="browser-profile-tag">account_{selectedAccount}</span>
                    <a
                      href={`${apiBase}/live-view`}
                      target="_blank"
                      rel="noreferrer"
                      className="btn-popout-screen"
                      title="Open full live Chrome screen stream in a separate tab or window"
                    >
                      ↗️ Pop Out
                    </a>
                  </div>
                  <div className="screen-display-area">
                    {liveScreenshot ? (
                      <div className="screen-img-wrapper">
                        <img src={liveScreenshot} alt="Live Chrome Desktop Screen" className="screen-live-img" />
                        <span className="screen-live-tag">● LIVE STREAMING</span>
                      </div>
                    ) : (
                      <div className="screen-idle-placeholder">
                        <div className="placeholder-icon">🖥️</div>
                        <h4>Desktop Screen Mirror Ready</h4>
                        <p>Active Profile: <code>account_{selectedAccount}</code></p>
                        <p className="placeholder-sub">
                          Click <strong>"Start Checkout Flow"</strong> or <strong>"Launch Browser Profile"</strong> to stream Chrome live here.
                        </p>
                        <div className="os-hint-box">
                          💡 The real Chrome window also opens on your desktop and remains available for review.
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="terminal-output">
                  {logs.map((log, index) => (
                    <div key={index} className={`terminal-line ${log.includes("SUCCESS") ? "line-success" : log.includes("START") ? "line-start" : log.includes("ACTION") ? "line-action" : log.includes("HANDOFF") ? "line-handoff" : ""}`}>
                      {log}
                    </div>
                  ))}
                  <div ref={logsEndRef} />
                </div>
              )}
            </div>

            {/* Controls */}
            <div className="bulk-actions-footer">
              <button
                type="button"
                className="btn-launch-browser"
                onClick={handleLaunchBrowser}
                disabled={!apiBase || browserLaunching || ["starting", "running", "awaiting_otp", "awaiting_upi_qr", "awaiting_confirmation"].includes(botStatus)}
              >
                {browserLaunching ? "Launching..." : "🌐 Launch Browser Profile"}
              </button>
              {["running", "awaiting_otp", "awaiting_upi_qr", "awaiting_confirmation"].includes(botStatus) ? (
                <button
                  type="button"
                  className="btn-stop-bot"
                  onClick={handleResetBot}
                >
                  ⏹ Stop Automation
                </button>
              ) : (
                <button
                  type="button"
                  className="btn-start-bot"
                  onClick={handleStartBot}
                  disabled={!apiBase || !availablePaymentMethods.includes(paymentMethod) || (quantity > 1 && !confirmAutoPlace)}
                >
                  ▶ Start Checkout Flow
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Floating Interactive OTP Pop-Out Window */}
        {(botStatus === "awaiting_otp" || otpRequired) && (
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(5, 10, 20, 0.88)",
              backdropFilter: "blur(8px)",
              zIndex: 9999,
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              animation: "fadeIn 0.25s ease-out",
            }}
          >
            <div
              style={{
                width: "480px",
                maxWidth: "92%",
                background: "linear-gradient(145deg, #111827 0%, #1f2937 100%)",
                border: "2px solid #00b259",
                borderRadius: "16px",
                padding: "26px",
                boxShadow: "0 20px 50px rgba(0, 178, 89, 0.35)",
                textAlign: "center",
                color: "#fff",
              }}
            >
              <div style={{ fontSize: "42px", marginBottom: "8px" }}>🔐</div>
              <h3 style={{ margin: "0 0 6px", fontSize: "20px", fontWeight: "700", color: "#f9fafb" }}>
                {brandName} Login OTP Verification
              </h3>
              <p style={{ margin: "0 0 16px", fontSize: "13px", color: "#9ca3af", lineHeight: "1.5" }}>
                Enter the verification code sent to the account signed in to the visible browser.
              </p>

              {/* Digital OTP Input Box */}
              <div style={{ margin: "18px 0" }}>
                <input
                  type="text"
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSubmitOtp();
                  }}
                  autoFocus
                  placeholder="• • • • • •"
                  style={{
                    width: "220px",
                    padding: "12px",
                    fontSize: "24px",
                    fontWeight: "700",
                    letterSpacing: "8px",
                    textAlign: "center",
                    background: "#030712",
                    border: "2px solid #10b981",
                    borderRadius: "10px",
                    color: "#34d399",
                    outline: "none",
                    boxShadow: "0 0 15px rgba(16, 185, 129, 0.3)",
                  }}
                />
              </div>

              {/* Action Buttons */}
              <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "20px" }}>
                <button
                  type="button"
                  disabled={otpSubmitting || !otpCode}
                  onClick={handleSubmitOtp}
                  style={{
                    background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
                    color: "#fff",
                    border: "none",
                    padding: "12px",
                    borderRadius: "8px",
                    fontSize: "14px",
                    fontWeight: "700",
                    cursor: otpSubmitting || !otpCode ? "not-allowed" : "pointer",
                    boxShadow: "0 4px 15px rgba(16, 185, 129, 0.4)",
                    transition: "transform 0.1s ease",
                  }}
                >
                  {otpSubmitting ? `⏳ Submitting OTP to ${brandName}...` : "✓ Submit OTP & Continue Checkout"}
                </button>

                <div style={{ display: "flex", gap: "10px" }}>
                  <button
                    type="button"
                    onClick={() => {
                      window.open(`${apiBase}/live-view`, `${brandName}OTPStream`, "width=540,height=700,resizable=yes,scrollbars=yes");
                    }}
                    style={{
                      flex: 1,
                      background: "rgba(255, 255, 255, 0.08)",
                      border: "1px solid rgba(255, 255, 255, 0.18)",
                      color: "#e2e8f0",
                      padding: "8px",
                      borderRadius: "6px",
                      fontSize: "12px",
                      cursor: "pointer",
                    }}
                  >
                    ↗️ Pop Out Floating Window
                  </button>
                  <button
                    type="button"
                    onClick={() => setOtpRequired(false)}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "#9ca3af",
                      padding: "8px",
                      fontSize: "12px",
                      cursor: "pointer",
                      textDecoration: "underline",
                    }}
                  >
                    Dismiss
                  </button>
                </div>
              </div>

              <div style={{ marginTop: "14px", fontSize: "11px", color: "#6b7280" }}>
                💡 <strong>Tip:</strong> The real Chrome window is also visible on your Windows desktop. You can enter the OTP directly there or right here in this floating window.
              </div>
            </div>
          </div>
        )}
        {configurationError && (
          <div className="bulk-config-error" role="alert">
            {configurationError}
          </div>
        )}
      </div>
    </div>
  );
}

