# MarginGuard

MarginGuard is a local multi-agent system designed to detect silent margin erosion for import and e-commerce sellers. Landed costs keep changing due to tariff shifts, exchange rate fluctuations, and freight market costs. MarginGuard helps sellers flag low-margin items and calculates precise target-restoring prices or alternative country sourcing switches using real, deterministic arithmetic.

## Architecture

The system follows a multi-agent orchestration architecture coupled with a local Model Context Protocol (MCP) server:

```
+-------------------------------------------------------+
|                    HTML Dashboard                     |
+-------------------------------------------------------+
                           |  (1) Upload CSV / Run Analysis
                           v
+-------------------------------------------------------+
|             Orchestrator Agent (Root)                 |
+-------------------------------------------------------+
                           |  (2) Coordinates Pipeline
                           v
+-------------------------------------------------------+
|                  Cost Monitor Agent                   |
+-------------------------------------------------------+
                           |  (3) Queries Trade Lanes
                           v
+-----------------------+     +-------------------------+
|    MCP Cost Server    | <-> | get_cost_conditions()   |
+-----------------------+     +-------------------------+
                           |  (4) Returns mock tariff/FX/freight conditions
                           v
+-------------------------------------------------------+
|                     Margin Agent                      |
+-------------------------------------------------------+
                           |  (5) Recalculates Landed Cost & Margins
                           v
+-------------------------------------------------------+
|                   Repricing Agent                     |
+-------------------------------------------------------+
                           |  (6) Estimates target prices & alternate countries
                           v
+-------------------------------------------------------+
|                    HTML Dashboard                     | (Render OK/Flagged and Fix Recommendations)
+-------------------------------------------------------+
```

### Components

1. **HTML Dashboard**: Serves the user interface on `localhost`. Shows current data, analysis statuses, and alternative sourcing options.
2. **Orchestrator Agent**: Manages the data pipeline flow and coordinates invocation of downstream agents using the Google Antigravity SDK.
3. **Cost Monitor Agent**: Interacts with the local MCP server to fetch tariff, exchange rate, and freight factors for category/country lanes.
4. **MCP Cost Conditions Server**: Exposes a local tool `get_cost_conditions(category, country)` containing realistic, mock economic factors.
5. **Margin Agent**: Uses deterministic Python calculations to compute actual landed costs and flags products below target margin.
6. **Repricing Agent**: Computes the minimum sale price to restore margins and checks alternate country supplier margins.

---

## CSV File Format

You can upload your own products list in CSV format. The CSV file must contain the following headers:

`sku,supplier_cost,shipping_cost,sale_price,target_margin,product_category,hs_code,source_country`

- **sku**: Unique alphanumeric code representing the product (e.g. `ELEC-SMART-001`).
- **supplier_cost**: Cost per unit paid to the supplier (e.g. `50.00`).
- **shipping_cost**: Baseline shipping cost per unit (e.g. `8.00`).
- **sale_price**: Current sale price on the store (e.g. `99.00`).
- **target_margin**: The target margin percentage (e.g. `40` for 40%).
- **product_category**: Product category, matching: `Electronics`, `Apparel`, `Furniture`, `Toys`, or `Home Goods`.
- **hs_code**: HS classification code (e.g. `8517.62`).
- **source_country**: 2-letter ISO country code (e.g. `CN`, `VN`, `IN`, `MX`).

### Sample CSV Row
```csv
sku,supplier_cost,shipping_cost,sale_price,target_margin,product_category,hs_code,source_country
ELEC-SMART-001,50.00,8.00,99.00,40,Electronics,8517.62,CN
```

---

## Setup & Running Instructions

### 1. Set up the API Key

The Google Antigravity SDK requires a Gemini API key. Set it up using the following command in your terminal (typing will be hidden):

```bash
printf "Enter GEMINI_API_KEY (typing hidden): " && read -s val && echo && echo "GEMINI_API_KEY=$val" >> "/Users/mac/Documents/Kaggle Capstone/.env" && echo "Saved."
```

### 2. Start the Server

Start the local FastAPI server using the virtual environment's Python interpreter:

```bash
/Users/mac/Documents/Capstone/.venv/bin/python app.py
```

The application will start, serving the dashboard at:
`http://127.0.0.1:8000`

Open your web browser and navigate to this address. Click **Run Analysis** to execute the pipeline on the sample dataset immediately.
