# UPI SpendSense – Micro-Transaction Leakage & Spending Behaviour Intelligence

An enterprise-grade financial intelligence engine engineered to detect, quantify, and explain subliminal budget leakage caused by repetitive, low-value UPI micro-transactions. 

**Positioning:** This is *not* merely an expense tracker. It is a behavioral intelligence system designed to **DETECT → EXPLAIN → QUANTIFY → SIMULATE** unconscious spending patterns.

---

## 1. Problem Statement
With the widespread adoption of real-time payment interfaces (UPI), low-friction micro-transactions (≤ ₹100) have become psychologically invisible. While individually negligible, their cumulative frequency creates severe budget leakage and unobserved repetitive spending habits that traditional banking apps fail to highlight.

## 2. Existing Limitations
Traditional expense trackers act as simple ledgers. They require heavy manual data entry, broadly categorize spending without behavioral context, and fail to identify the exact recurring habits (e.g., daily ₹40 canteen purchases) that silently drain liquidity. 

## 3. Proposed Solution
UPI SpendSense solves this by introducing a batch-ingestion pipeline that analyzes historical bank statements to expose "Vampire Habits." It translates raw financial outflow into an explainable **Leakage Score**, flags statistical anomalies, and provides a What-If simulation to project annual savings through micro-spend reduction.

## 4. Core Features
- **Batch CSV Ingestion Pipeline:** Ingests statement CSVs with strict header validation, encoding checks, and data type coercion.
- **Python-Level Deduplication:** Prevents duplicate transaction imports using parameterized multi-column database lookups.
- **Merchant Normalization Engine:** Cleans noisy UPI note strings (e.g., `UPI/SWIGGY/1234`) into standardized merchant entities using regex and dictionary mapping.
- **Recurring Habit Detector (Vampire Spend):** Uses SQL `GROUP BY / HAVING` to isolate repetitive micro-purchases (same merchant and amount ≥ 3 times).
- **Explainable Spending Leakage Score (0–100):** Transparent rule-based metric evaluating value ratio, frequency ratio, recurring habit density, and MoM velocity.
- **Statistical Anomaly Detector:** Flags transactions exceeding historical category thresholds using SQL-calculated Standard Deviation (`STDDEV`) and Means.
- **Life-Energy Time Exchange View:** Translates spending into required working hours based on user-defined monthly compensation.
- **What-If Savings Scenario Simulator:** Mathematically projects annual capital preservation by curbing micro-spending.

## 5. Architecture & Technology Stack
- **Architecture:** Monolithic REST API Backend with a Decoupled Single-Page Application (SPA) Frontend.
- **Backend:** Python 3.x, Flask (REST APIs, WSGI)
- **Database:** MySQL Server 8.0, PyMySQL Connector (Parameterized Queries, Composite Indexing)
- **Frontend:** Vanilla HTML5, CSS3 Grid, JavaScript (ES6+ Fetch API, async/await)
- **Data Visualization:** Chart.js (CDN)

## 6. Database Design
Designed for read-heavy analytical workloads with composite B-Tree indexing.
```sql
CREATE TABLE transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    txn_date DATE NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    note VARCHAR(255),
    merchant VARCHAR(100) DEFAULT 'Unknown',
    category VARCHAR(50) DEFAULT 'Uncategorized',
    source VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date_amount (txn_date, amount),
    INDEX idx_merchant_amount (merchant, amount),
    INDEX idx_category (category)
);