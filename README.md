# MarginGuard - Automatic Margin-Erosion Detector & Repricer for Import Sellers

**A local multi-agent system that detects silent margin erosion for import and e-commerce sellers — and tells you exactly what price to set to fix it.**

MarginGuard Dashboard <img width="1259" height="824" alt="Screenshot 2026-07-07 at 1 51 17 AM" src="https://github.com/user-attachments/assets/5a22efb5-2720-4d78-b3aa-9b918fe90274" />
*The local dashboard — sample dataset loaded, flagged rows highlighted in red with a recommended fix.*

---

## The Problem

Small businesses that import products — Amazon FBA sellers, Shopify importers, small retailers — buy from overseas suppliers and set a sale price once. But their true cost to have that product in-hand, the **landed cost**, keeps changing quietly:

- Tariff rates shift
- Exchange rates move
- Freight/shipping rates swing

Nobody manually re-checks this every week. Sellers keep selling at the old price while their margin silently shrinks — and they usually don't notice until the P&L looks bad at quarter-end.

MarginGuard automates that check: give it your product list, and it tells you which products are bleeding margin right now, and the exact price (or sourcing change) needed to restore it.

```
You give it your product list + costs
        →  it watches the things that change your true cost
                →  it tells you exactly which products are bleeding margin
                        and what price to set to fix it
```

---

## New in This Update: Workspace Upgrades & Real-Time Engine

The system has been updated from a static report viewer to a **High-Fidelity Premium Workspace Suite**. Key improvements include:

*   **Interactive Core KPI Cards:** The master statistics grid (**Revenue at Risk, Products Loaded, Avg Margin Profile, Potential Recovery**) is now directly wired to the simulation calculation core. Metrics update *instantly* as variables change.
*   **Global Freight & Trade Disruption Simulator:** Added interactive modifier sliders to test portfolio resistance against macro shocks. You can adjust global tariff baselines and inbound freight surcharges in real time.
*   **Multi-Screen Navigation Canvas:** The single-page view has been partitioned into a high-performance sidebar layout separating distinct analytical operations:
    *   **Ledger Workspace:** Core tabular system data, CSV uploads, and localized row-flagging.
    *   **Variance Graphs:** Horizontal dynamic charts displaying localized portfolio target deviations.
    *   **Forward Forecast:** Pro-forma simulated landed-cost forecasting matrices.
    *   **Audit Directives:** System-isolated log sheets outlining localized supply lane mitigation instructions.
*   **Premium Visual Identity:** Integrated a frosted-glass glassmorphism UI using radial accent gradients, fixed background alignment mesh filters, and unified micro-dot grid guides.

---

## How It Works

MarginGuard runs a **4-agent pipeline** behind a local dashboard. Each agent hands off structured data to the next — nothing here is an LLM guessing at numbers; the cost and margin math is deterministic Python and JavaScript arithmetic.

Architecture Diagram <img width="1149" height="1369" alt="ChatGPT Image Jul 7, 2026, 01_51_39 AM" src="https://github.com/user-attachments/assets/b95c9a09-4d61-4b19-9827-f16d2eeed7a1" />        

### Pipeline steps

1. **HTML Dashboard** — served on `localhost`. Use the built-in sample inventory registry or stream your own CSV, then click **Run Analysis**.
2. **Orchestrator Agent (Root)** — reads the active product list and coordinates the rest of the pipeline.
3. **Cost Monitor Agent** — for each product's category and source country, calls a local MCP tool to fetch current tariff %, FX rate, and freight rate.
4. **MCP Cost Conditions Server** — exposes `get_cost_conditions(product_category, source_country)`, backed by a small, clearly-labeled **mock dataset** (no real trade API needed).
5. **Margin Agent** — recalculates the true landed cost and actual current margin per product using explicit, commented arithmetic:
   - `landed_cost = supplier_cost × (1 + tariff_rate) × fx_adjustment_factor + shipping_cost`
   - `margin = (sale_price − landed_cost) / sale_price`
   - Flags any product that has fallen below its target margin.
6. **Repricing Agent** — for every flagged product, computes the minimum sale price that restores the target margin, and checks whether sourcing from an alternate country would help more.
7. **Dashboard renders the report** — updates the dynamic charts, populates the multi-view tabs, and syncs the live KPI metric blocks instantly.

---

## Why a Multi-Agent Design

| Concept | How MarginGuard covers it |
|---|---|
| **Multi-agent orchestration** | Cost Monitor Agent → Margin Agent → Repricing Agent, coordinated by a root Orchestrator Agent |
| **MCP Server** | `get_cost_conditions(product_category, source_country)` returns mock current tariff %, FX rate, and freight rate |
| **Security** | Supplier costs and margins are business-sensitive — processed only in-session, never logged in plaintext (logs read like `"margin recalculated for [REDACTED SKU]"`) |
| **Deterministic math** | All landed-cost and margin arithmetic is explicit, commented Python — never an LLM-estimated number, so results are trustworthy and explainable |
| **Deployability** | In production, the Cost Monitor Agent would pull live tariff/FX/freight data and run on a weekly cron instead of reading from a mock dataset |

---

## CSV File Format

Upload your own product list in CSV format with these headers:

`sku,supplier_cost,shipping_cost,current_sale_price,target_margin_pct,product_category,source_country`

| Column | Description | Example |
|---|---|---|
| `sku` | Unique alphanumeric product code | `ELEC-SMART-001` |
| `supplier_cost` | Cost per unit paid to the supplier | `50.00` |
| `shipping_cost` | Baseline shipping cost per unit | `8.00` |
| `current_sale_price` | Current sale price on the store | `99.00` |
| `target_margin_pct` | Target margin percentage | `40` (for 40%) |
| `product_category` | One of: `Electronics`, `Apparel`, `Furniture`, `Toys`, `Home Goods` | `Electronics` |
| `source_country` | 2-letter ISO country code | `CN`, `VN`, `IN`, `MX` |

### Sample row

```csv
sku,supplier_cost,shipping_cost,current_sale_price,target_margin_pct,product_category,source_country
ELEC-SMART-001,48.00,8.50,99.99,40.0,Electronics,CN
ELEC-HEADPHONE-002,24.50,4.20,59.99,35.0,Electronics,VN
HOME-LAMP-003,18.00,6.00,44.99,40.0,Home Goods,IN
TOYS-BLOCK-004,10.00,2.50,29.99,45.0,Toys,VN
APPA-JACKET-005,28.00,5.00,69.99,50.0,Apparel,CN

Rows that fail validation (e.g. negative costs, unrecognized category) are skipped, and the dashboard shows exactly which rows were rejected and why — the rest of the file still loads and runs.

---

## Sample Walkthrough

Given a product like this:

| SKU | Supplier Cost | Shipping | Sale Price | Target Margin | Category | Country |
|---|---|---|---|---|---|---|
| `ELEC-SMART-001` | $50.00 | $8.00 | $99.00 | 40% | Electronics | CN |

The pipeline works out to something like:

- **Cost Monitor Agent** pulls current tariff/FX/freight conditions for Electronics sourced from CN.
- **Margin Agent** recalculates the landed cost against those updated conditions and finds the actual margin has drifted down to ~28% — below the 40% target.
- **Repricing Agent** flags the product and reports the exact new sale price needed to restore 40% margin, and separately checks whether an alternate source country would land at a better cost.

The dashboard then shows that row in red, badged **FLAGGED**, with the recommended fix right next to it — no manual spreadsheet work required.

---

## Setup & Running Instructions

### 1. Set up the API key

The agent pipeline runs on the Google Antigravity SDK, which requires a Gemini API key:

```bash
printf "Enter GEMINI_API_KEY (typing hidden): " && read -s val && echo && echo "GEMINI_API_KEY=$val" >> ".env" && echo "Saved."
```

> Save this in the project's `.env` file (adjust the path above to wherever you've cloned this repo).

### 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Start the server

```bash
python app.py
```

The app serves the dashboard at:

```
http://127.0.0.1:8000
```

Open that address in your browser. The dashboard loads with a built-in sample dataset of 9 products — click **Run Analysis** to run the full pipeline immediately, or use **Upload CSV** to test your own data, and **Reset to Sample Data** to switch back.

---

## Project Structure

```
MarginGuard/
├── app.py                 # FastAPI server — serves dashboard + /analyze and /validate-csv endpoints
├── index.html              # Dashboard frontend (table, upload, run/reset controls)
├── requirements.txt         # Python dependencies
├── test.csv                 # Example CSV for testing upload/validation
└── README.md
```

## Requirements

```
fastapi>=0.111.0
uvicorn>=0.30.1
pydantic>=2.10.1
mcp>=1.2.0
python-multipart>=0.0.9
pandas>=2.2.0
```

---

## Security Notes

- Supplier costs, margins, and pricing data are business-sensitive and are processed **only in-session** — nothing is written to disk in plaintext.
- Application logs redact identifying cost data (e.g. `"margin recalculated for [REDACTED SKU]"` instead of raw numbers).
- Uploaded CSVs are validated before processing; malformed rows are rejected individually rather than crashing the whole upload.

---

## Notes on the Mock Dataset

This build uses a clearly-labeled **mock** dataset for tariff %, FX rate, and freight rate — covering the categories `Electronics`, `Apparel`, `Furniture`, `Toys`, and `Home Goods` across source countries `CN`, `VN`, `IN`, and `MX`. No real trade API keys are required to run or demo the project. In a production deployment, the Cost Monitor Agent would instead call live freight, FX, and tariff data providers on a scheduled (e.g. weekly) basis.
