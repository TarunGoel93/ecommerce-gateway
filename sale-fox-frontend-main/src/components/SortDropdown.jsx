import React, { useState, useRef, useEffect } from "react";
import "./SortDropdown.css";

const SORT_OPTIONS = [
  { id: "relevance", label: "Featured / Relevance", shortLabel: "Featured", icon: "✨" },
  { id: "price_asc", label: "Price: Low to High", shortLabel: "Price: Low to High", icon: "📈" },
  { id: "price_desc", label: "Price: High to Low", shortLabel: "Price: High to Low", icon: "📉" },
  { id: "rating_desc", label: "Customer Rating", shortLabel: "Rating: High to Low", icon: "⭐" },
];

export default function SortDropdown({
  sortBy = "relevance",
  onSortChange,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Handle escape key
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const currentOption = SORT_OPTIONS.find((opt) => opt.id === sortBy) || SORT_OPTIONS[0];

  const handleSelect = (optionId) => {
    if (onSortChange) {
      onSortChange(optionId);
    }
    setIsOpen(false);
  };

  return (
    <div className="sort-dropdown-wrapper" ref={containerRef}>
      <button
        type="button"
        className={`sort-dropdown-btn ${isOpen ? "active" : ""}`}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        title="Sort smartphones by price or rating"
      >
        <span className="sort-icon-svg">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="4" y1="6" x2="20" y2="6" />
            <line x1="4" y1="12" x2="14" y2="12" />
            <line x1="4" y1="18" x2="8" y2="18" />
          </svg>
        </span>
        <span className="sort-dropdown-label">SORT:</span>
        <span className="sort-dropdown-value">{currentOption.shortLabel}</span>
        <span className="sort-dropdown-chevron">{isOpen ? "▲" : "▼"}</span>
      </button>

      {isOpen && (
        <div className="sort-dropdown-menu" role="listbox">
          <div className="sort-menu-header">
            <span>Sort Products</span>
          </div>
          {SORT_OPTIONS.map((opt) => {
            const isSelected = opt.id === sortBy;
            return (
              <button
                key={opt.id}
                type="button"
                role="option"
                aria-selected={isSelected}
                className={`sort-menu-item ${isSelected ? "selected" : ""}`}
                onClick={() => handleSelect(opt.id)}
              >
                <span className="sort-item-icon">{opt.icon}</span>
                <span className="sort-item-label">{opt.label}</span>
                {isSelected && <span className="sort-item-check">✓</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

