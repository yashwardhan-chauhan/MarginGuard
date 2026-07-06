"""
MarginGuard — Local FastAPI backend.

Pipeline modes
--------------
• DIRECT MODE (no GEMINI_API_KEY required):
    Python functions directly call the MCP mock data, run the deterministic
    landed-cost / margin arithmetic, and compute repricing — all in the same
    process.  This makes the demo work immediately without any API setup.

• AGENT MODE (GEMINI_API_KEY required):
    Three Antigravity SDK agents (Cost Monitor → Margin → Repricing) each
    receive structured prompts, call the tools, and hand structured output
    to the next stage, exactly as specified in the requirements.

Security notes
--------------
• Raw financial numbers are NEVER written to disk or printed in logs.
• SKUs are REDACTED in log messages.
• Uploaded CSV is validated / sanitised before processing; malformed rows are
  rejected with a descriptive error rather than crashing the server.
"""

import os
import json
import logging
import csv
import io
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MarginGuard")

def _log_action(action: str) -> None:
    """Log a pipeline action without revealing any sensitive SKU or cost data."""
    logger.info(f"[Pipeline] {action} — SKU [REDACTED]")

# ---------------------------------------------------------------------------
# Environment / API key
# ---------------------------------------------------------------------------
def _load_env_file() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as fh:
            for raw in fh:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env_file()

def _api_key() -> Optional[str]:
    return os.environ.get("GEMINI_API_KEY") or None

# ---------------------------------------------------------------------------
# SDK import (optional)
# ---------------------------------------------------------------------------
try:
    from google.antigravity import Agent, LocalAgentConfig, types as ag_types
    SDK_AVAILABLE = True
    logger.info("Google Antigravity SDK loaded — agent mode available.")
except ImportError:
    SDK_AVAILABLE = False
    logger.warning("Google Antigravity SDK not found — will use direct mode.")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="MarginGuard", description="Local margin erosion detector")

# ---------------------------------------------------------------------------
# Mock cost-conditions data  (mirrors mcp_server.py exactly)
# ---------------------------------------------------------------------------
_MOCK_CONDITIONS: Dict[tuple, dict] = {
    # Electronics
    ("electronics", "cn"): {"tariff_rate": 0.25, "fx_adjustment_factor": 1.05, "freight_rate_multiplier": 1.25},
    ("electronics", "vn"): {"tariff_rate": 0.05, "fx_adjustment_factor": 0.98, "freight_rate_multiplier": 1.10},
    ("electronics", "in"): {"tariff_rate": 0.08, "fx_adjustment_factor": 1.02, "freight_rate_multiplier": 1.15},
    ("electronics", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 0.80},
    # Apparel
    ("apparel",    "cn"): {"tariff_rate": 0.20, "fx_adjustment_factor": 1.05, "freight_rate_multiplier": 1.15},
    ("apparel",    "vn"): {"tariff_rate": 0.08, "fx_adjustment_factor": 0.98, "freight_rate_multiplier": 1.05},
    ("apparel",    "in"): {"tariff_rate": 0.10, "fx_adjustment_factor": 1.02, "freight_rate_multiplier": 1.10},
    ("apparel",    "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 0.75},
    # Furniture
    ("furniture",  "cn"): {"tariff_rate": 0.25, "fx_adjustment_factor": 1.05, "freight_rate_multiplier": 1.35},
    ("furniture",  "vn"): {"tariff_rate": 0.04, "fx_adjustment_factor": 0.98, "freight_rate_multiplier": 1.20},
    ("furniture",  "in"): {"tariff_rate": 0.06, "fx_adjustment_factor": 1.02, "freight_rate_multiplier": 1.25},
    ("furniture",  "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 0.85},
    # Toys
    ("toys",       "cn"): {"tariff_rate": 0.15, "fx_adjustment_factor": 1.05, "freight_rate_multiplier": 1.10},
    ("toys",       "vn"): {"tariff_rate": 0.02, "fx_adjustment_factor": 0.98, "freight_rate_multiplier": 1.02},
    ("toys",       "in"): {"tariff_rate": 0.05, "fx_adjustment_factor": 1.02, "freight_rate_multiplier": 1.05},
    ("toys",       "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 0.70},
    # Home Goods
    ("home goods", "cn"): {"tariff_rate": 0.18, "fx_adjustment_factor": 1.05, "freight_rate_multiplier": 1.20},
    ("home goods", "vn"): {"tariff_rate": 0.03, "fx_adjustment_factor": 0.98, "freight_rate_multiplier": 1.10},
    ("home goods", "in"): {"tariff_rate": 0.05, "fx_adjustment_factor": 1.02, "freight_rate_multiplier": 1.12},
    ("home goods", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 0.78},
}

_FALLBACK_CONDITIONS = {"tariff_rate": 0.10, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00}

def _normalise_category(cat: str) -> str:
    c = cat.lower().strip()
    if "home" in c:      return "home goods"
    if "electronic" in c: return "electronics"
    if "toy" in c:        return "toys"
    if "appa" in c:       return "apparel"
    if "furn" in c:       return "furniture"
    return c

def _get_conditions(category: str, country: str) -> dict:
    """Pure-Python analogue of the MCP get_cost_conditions tool."""
    key = (_normalise_category(category), country.lower().strip())
    cond = _MOCK_CONDITIONS.get(key, _FALLBACK_CONDITIONS)
    return dict(cond)

# ---------------------------------------------------------------------------
# Alternate-sourcing helper  (deterministic, no LLM)
# ---------------------------------------------------------------------------
_ALT_COUNTRY_SUPPLIER_RATIO: Dict[str, Dict[str, float]] = {
    "cn": {
        "vn": 0.95, "mx": 1.10, "in": 0.90,
    },
    "vn": {"in": 0.95, "mx": 1.15},
    "in": {"mx": 1.15, "vn": 1.05},
    "mx": {"vn": 0.90, "in": 0.88},
}
_ALT_COUNTRY_SHIPPING_RATIO: Dict[str, Dict[str, float]] = {
    "cn": {"vn": 1.25, "mx": 0.75, "in": 1.20},
    "vn": {"in": 1.05, "mx": 0.80},
    "in": {"mx": 0.70, "vn": 1.10},
    "mx": {"vn": 1.30, "in": 1.25},
}

def _get_alternative_countries(current_country: str) -> List[str]:
    return list(_ALT_COUNTRY_SUPPLIER_RATIO.get(current_country.lower(), {}).keys())

# ---------------------------------------------------------------------------
# Core deterministic maths (Step 2 of the spec — "real calculation, not LLM")
# ---------------------------------------------------------------------------

def _compute_landed_cost(supplier_cost: float, tariff_rate: float,
                          fx_factor: float, shipping_cost: float,
                          freight_multiplier: float) -> float:
    """
    landed_cost = supplier_cost × (1 + tariff_rate) × fx_factor
                + shipping_cost × freight_multiplier
    """
    return supplier_cost * (1.0 + tariff_rate) * fx_factor + shipping_cost * freight_multiplier

def _compute_margin(sale_price: float, landed_cost: float) -> float:
    """margin = (sale_price - landed_cost) / sale_price"""
    if sale_price <= 0:
        return 0.0
    return (sale_price - landed_cost) / sale_price

def _compute_target_price(landed_cost: float, target_margin: float) -> float:
    """recommended_price = landed_cost / (1 - target_margin)"""
    if target_margin >= 1.0:
        return landed_cost  # can't achieve margin ≥ 100 %
    return landed_cost / (1.0 - target_margin)

# ---------------------------------------------------------------------------
# Direct pipeline  (no API key needed)
# ---------------------------------------------------------------------------

def _run_direct_pipeline(products: List[dict]) -> List[dict]:
    """
    Cost Monitor → Margin Agent → Repricing Agent  entirely in Python.
    All maths is explicit and deterministic.
    """
    results = []

    for p in products:
        cat       = p["product_category"]
        country   = p["source_country"].upper()
        sup_cost  = float(p["supplier_cost"])
        ship_cost = float(p["shipping_cost"])
        sale_pr   = float(p["current_sale_price"])
        tgt_pct   = float(p["target_margin_pct"])
        tgt_frac  = tgt_pct / 100.0

        # ── Cost Monitor Agent (via direct MCP data) ──────────────────────
        cond = _get_conditions(cat, country)
        tariff  = cond["tariff_rate"]
        fx      = cond["fx_adjustment_factor"]
        freight = cond["freight_rate_multiplier"]

        # ── Margin Agent (deterministic arithmetic) ────────────────────────
        landed   = _compute_landed_cost(sup_cost, tariff, fx, ship_cost, freight)
        margin   = _compute_margin(sale_pr, landed)
        flagged  = margin < tgt_frac

        _log_action("Margin recalculated")

        # ── Repricing Agent ────────────────────────────────────────────────
        rec_price:      Optional[float] = None
        recommendation: str             = "OK"
        alt_option:     Optional[str]   = None

        if flagged:
            rec_price     = round(_compute_target_price(landed, tgt_frac), 2)
            recommendation = f"Increase price to ${rec_price:.2f}"

            # Evaluate alternative source countries
            alt_countries = _get_alternative_countries(country)
            best_alt_margin  = -999.0
            best_alt: Optional[dict] = None

            for alt_c in alt_countries:
                alt_sup  = sup_cost  * _ALT_COUNTRY_SUPPLIER_RATIO[country.lower()][alt_c]
                alt_ship = ship_cost * _ALT_COUNTRY_SHIPPING_RATIO[country.lower()].get(alt_c, 1.0)
                alt_cond = _get_conditions(cat, alt_c)
                alt_land = _compute_landed_cost(
                    alt_sup, alt_cond["tariff_rate"],
                    alt_cond["fx_adjustment_factor"],
                    alt_ship, alt_cond["freight_rate_multiplier"]
                )
                alt_margin = _compute_margin(sale_pr, alt_land)
                alt_rec_p  = round(_compute_target_price(alt_land, tgt_frac), 2)

                if alt_margin > best_alt_margin:
                    best_alt_margin = alt_margin
                    best_alt = {
                        "country":       alt_c.upper(),
                        "landed_cost":   round(alt_land, 2),
                        "margin_pct":    round(alt_margin * 100, 2),
                        "rec_price":     alt_rec_p,
                    }

            if best_alt:
                if best_alt["margin_pct"] >= tgt_pct:
                    alt_option = (
                        f"Switch to {best_alt['country']} supplier "
                        f"(Est. Landed: ${best_alt['landed_cost']:.2f}, "
                        f"Margin: {best_alt['margin_pct']:.1f}% ✓ — "
                        f"no price change needed)"
                    )
                else:
                    alt_option = (
                        f"Alt supplier {best_alt['country']}: "
                        f"Landed ${best_alt['landed_cost']:.2f}, "
                        f"Margin {best_alt['margin_pct']:.1f}% "
                        f"(still below target — min price ${best_alt['rec_price']:.2f})"
                    )

            _log_action("Repricing calculated")

        results.append({
            **p,
            "tariff_rate":            round(tariff * 100, 1),
            "fx_adjustment_factor":   round(fx, 4),
            "freight_rate_multiplier": round(freight, 4),
            "landed_cost":            round(landed, 2),
            "actual_margin_pct":      round(margin * 100, 2),
            "below_target":           flagged,
            "recommended_price":      rec_price,
            "recommendation":         recommendation,
            "alt_sourcing_option":    alt_option,
        })

    return results

# ---------------------------------------------------------------------------
# Agent pipeline  (requires GEMINI_API_KEY)
# ---------------------------------------------------------------------------

class _CostConditionVal(BaseModel):
    tariff_rate: float
    fx_adjustment_factor: float
    freight_rate_multiplier: float

class _CostMonitorOut(BaseModel):
    conditions: Dict[str, _CostConditionVal]

class _MarginOut(BaseModel):
    results_json: str

class _RepricingOut(BaseModel):
    results_json: str

# Tools exposed to agents  (same deterministic maths as direct mode)
def calculate_margin_for_batch(products_json: str, conditions_json: str) -> str:
    """
    Recalculate landed cost and margin for every product using mock cost conditions.

    Args:
        products_json: JSON list of product dicts.
        conditions_json: JSON dict mapping "category,country" → condition fields.
    """
    products   = json.loads(products_json)
    conditions = json.loads(conditions_json)
    out = []
    for p in products:
        cat    = p["product_category"]
        cc     = p["source_country"].upper()
        key    = f"{_normalise_category(cat)},{cc.lower()}"
        cond   = conditions.get(key, _FALLBACK_CONDITIONS)
        tariff  = float(cond["tariff_rate"])
        fx      = float(cond["fx_adjustment_factor"])
        freight = float(cond["freight_rate_multiplier"])
        sup     = float(p["supplier_cost"])
        ship    = float(p["shipping_cost"])
        sale    = float(p["current_sale_price"])
        tgt     = float(p["target_margin_pct"]) / 100.0

        landed = _compute_landed_cost(sup, tariff, fx, ship, freight)
        margin = _compute_margin(sale, landed)
        _log_action("Margin recalculated")

        out.append({
            **p,
            "tariff_rate": tariff,
            "fx_adjustment_factor": fx,
            "freight_rate_multiplier": freight,
            "landed_cost": round(landed, 2),
            "actual_margin_pct": round(margin * 100, 2),
            "below_target": margin < tgt,
        })
    return json.dumps(out)

def calculate_repricing_and_alternatives_for_batch(products_json: str, conditions_json: str) -> str:
    """
    For flagged products compute the minimum restoring price and compare
    alternative source countries.

    Args:
        products_json: JSON list of margin-recalculated product dicts.
        conditions_json: JSON dict of cost conditions.
    """
    products   = json.loads(products_json)
    conditions = json.loads(conditions_json)
    out = []

    for p in products:
        cat     = p["product_category"]
        country = p["source_country"].upper()
        landed  = float(p["landed_cost"])
        tgt_pct = float(p["target_margin_pct"])
        tgt_frac = tgt_pct / 100.0
        sale_pr  = float(p["current_sale_price"])
        flagged  = p["below_target"]

        rec_price: Optional[float] = None
        recommendation = "OK"
        alt_option: Optional[str] = None

        if flagged:
            rec_price     = round(_compute_target_price(landed, tgt_frac), 2)
            recommendation = f"Increase price to ${rec_price:.2f}"

            alt_countries = _get_alternative_countries(country)
            best_alt_margin = -999.0
            best_alt: Optional[dict] = None

            for alt_c in alt_countries:
                alt_sup  = float(p["supplier_cost"]) * _ALT_COUNTRY_SUPPLIER_RATIO[country.lower()].get(alt_c, 1.0)
                alt_ship = float(p["shipping_cost"]) * _ALT_COUNTRY_SHIPPING_RATIO[country.lower()].get(alt_c, 1.0)
                key      = f"{_normalise_category(cat)},{alt_c}"
                alt_cond = conditions.get(key, _FALLBACK_CONDITIONS)
                alt_land = _compute_landed_cost(
                    alt_sup, float(alt_cond["tariff_rate"]),
                    float(alt_cond["fx_adjustment_factor"]),
                    alt_ship, float(alt_cond["freight_rate_multiplier"])
                )
                alt_margin = _compute_margin(sale_pr, alt_land)
                alt_rec_p  = round(_compute_target_price(alt_land, tgt_frac), 2)

                if alt_margin > best_alt_margin:
                    best_alt_margin = alt_margin
                    best_alt = {
                        "country":     alt_c.upper(),
                        "landed_cost": round(alt_land, 2),
                        "margin_pct":  round(alt_margin * 100, 2),
                        "rec_price":   alt_rec_p,
                    }

            if best_alt:
                if best_alt["margin_pct"] >= tgt_pct:
                    alt_option = (
                        f"Switch to {best_alt['country']} supplier "
                        f"(Est. Landed: ${best_alt['landed_cost']:.2f}, "
                        f"Margin: {best_alt['margin_pct']:.1f}% ✓ — no price change needed)"
                    )
                else:
                    alt_option = (
                        f"Alt supplier {best_alt['country']}: "
                        f"Landed ${best_alt['landed_cost']:.2f}, "
                        f"Margin {best_alt['margin_pct']:.1f}% "
                        f"(still below target — min price ${best_alt['rec_price']:.2f})"
                    )
            _log_action("Repricing calculated")

        out.append({
            **p,
            "recommended_price":  rec_price,
            "recommendation":     recommendation,
            "alt_sourcing_option": alt_option,
        })

    return json.dumps(out)

async def _run_agent_pipeline(products: List[dict]) -> List[dict]:
    mcp_servers = [
        ag_types.McpStdioServer(
            command="/Users/mac/Documents/Capstone/.venv/bin/python",
            args=["/Users/mac/Documents/Kaggle Capstone/mcp_server.py"],
        )
    ]

    # ── Cost Monitor Agent ─────────────────────────────────────────────────
    trade_lanes = list({
        (p["product_category"].lower().strip(), p["source_country"].upper())
        for p in products
    })
    lanes_list = [{"category": c, "country": co} for c, co in trade_lanes]

    cost_cfg = LocalAgentConfig(
        response_schema=_CostMonitorOut,
        mcp_servers=mcp_servers,
        system_instructions=(
            "You are the Cost Monitor Agent. Use get_cost_conditions for EVERY trade lane "
            "listed. Build a dict where each key is 'normalised_category,country_lowercase' "
            "and the value contains tariff_rate, fx_adjustment_factor, freight_rate_multiplier."
        ),
    )
    async with Agent(cost_cfg) as agent:
        res = await agent.chat(f"Fetch conditions for: {json.dumps(lanes_list)}")
        cost_out = await res.structured_output()

    conditions_dict = {k: v.model_dump() for k, v in cost_out.conditions.items()}

    # ── Margin Agent ───────────────────────────────────────────────────────
    margin_cfg = LocalAgentConfig(
        response_schema=_MarginOut,
        tools=[calculate_margin_for_batch],
        system_instructions=(
            "You are the Margin Agent. Call calculate_margin_for_batch with the products "
            "and conditions provided. Return the result JSON in results_json."
        ),
    )
    async with Agent(margin_cfg) as agent:
        res = await agent.chat(
            f"Products: {json.dumps(products)}\nConditions: {json.dumps(conditions_dict)}"
        )
        margin_out = await res.structured_output()

    margin_results = json.loads(margin_out.results_json)

    # ── Repricing Agent ────────────────────────────────────────────────────
    reprice_cfg = LocalAgentConfig(
        response_schema=_RepricingOut,
        tools=[calculate_repricing_and_alternatives_for_batch],
        system_instructions=(
            "You are the Repricing Agent. Call calculate_repricing_and_alternatives_for_batch "
            "with the recalculated products and conditions. Return result JSON in results_json."
        ),
    )
    async with Agent(reprice_cfg) as agent:
        res = await agent.chat(
            f"Products: {json.dumps(margin_results)}\nConditions: {json.dumps(conditions_dict)}"
        )
        reprice_out = await res.structured_output()

    return json.loads(reprice_out.results_json)

# ---------------------------------------------------------------------------
# Pydantic request model
# ---------------------------------------------------------------------------
class ProductInput(BaseModel):
    sku: str
    supplier_cost: float
    shipping_cost: float
    current_sale_price: float
    target_margin_pct: float
    product_category: str
    hs_code: str
    source_country: str

class AnalyzeRequest(BaseModel):
    products: List[ProductInput]

# ---------------------------------------------------------------------------
# CSV validation helper
# ---------------------------------------------------------------------------
_HEADER_MAP = {
    "sku": "sku",
    "supplier cost": "supplier_cost",    "supplier_cost": "supplier_cost",
    "shipping cost": "shipping_cost",    "shipping_cost": "shipping_cost",
    "shipping cost per unit": "shipping_cost",
    "current sale price": "current_sale_price", "sale price": "current_sale_price",
    "current_sale_price": "current_sale_price", "sale_price": "current_sale_price",
    "target margin %": "target_margin_pct", "target margin": "target_margin_pct",
    "target_margin_%": "target_margin_pct", "target_margin": "target_margin_pct",
    "target_margin_pct": "target_margin_pct",
    "product category": "product_category", "category": "product_category",
    "product_category": "product_category",
    "hs code": "hs_code", "hs_code": "hs_code",
    "source country": "source_country", "country": "source_country",
    "source_country": "source_country",
}
_REQUIRED = ["sku", "supplier_cost", "shipping_cost", "current_sale_price",
             "target_margin_pct", "product_category", "source_country"]

def _validate_csv(content: str) -> dict:
    reader = csv.reader(io.StringIO(content))
    try:
        raw_headers = next(reader)
    except StopIteration:
        return {"success": False, "error": "CSV file is empty", "products": [], "errors": []}

    headers = [_HEADER_MAP.get(h.strip().lower(), h.strip().lower()) for h in raw_headers]
    missing = [r for r in _REQUIRED if r not in headers]
    if missing:
        return {"success": False,
                "error": f"Missing required columns: {', '.join(missing)}",
                "products": [], "errors": []}

    valid, errors = [], []
    for row_num, row in enumerate(reader, start=2):
        if not row or all(c.strip() == "" for c in row):
            continue
        if len(row) < len(raw_headers):
            row += [""] * (len(raw_headers) - len(row))

        rd = dict(zip(headers, row))
        sku      = rd.get("sku", "").strip()
        cat      = rd.get("product_category", "").strip()
        country  = rd.get("source_country", "").strip().upper()
        hs_code  = rd.get("hs_code", "").strip() or "N/A"

        errs = []
        if not sku:     errs.append("SKU is empty")
        if not cat:     errs.append("Category is empty")
        if not country: errs.append("Source country is empty")
        elif len(country) != 2: errs.append("Source country must be a 2-letter ISO code")

        def _num(field, must_positive=False, must_nonneg=True):
            try:
                v = float(rd.get(field, "0") or "0")
                if must_nonneg and v < 0:
                    errs.append(f"{field} cannot be negative")
                if must_positive and v <= 0:
                    errs.append(f"{field} must be > 0")
                return v
            except ValueError:
                errs.append(f"{field} must be a number")
                return 0.0

        sup  = _num("supplier_cost")
        ship = _num("shipping_cost")
        sale = _num("current_sale_price", must_positive=True)
        tgt  = _num("target_margin_pct")
        if not errs and (tgt < 0 or tgt >= 100):
            errs.append("Target margin % must be 0–99")

        if errs:
            errors.append({"row_number": row_num, "sku": sku or f"Row {row_num}", "reasons": errs})
        else:
            valid.append({"sku": sku, "supplier_cost": sup, "shipping_cost": ship,
                          "current_sale_price": sale, "target_margin_pct": tgt,
                          "product_category": cat, "hs_code": hs_code,
                          "source_country": country})

    return {"success": True, "products": valid, "errors": errors}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    try:
        with open(html_path) as fh:
            return fh.read()
    except FileNotFoundError:
        return "<h3>index.html not found in the workspace directory.</h3>"

@app.post("/validate-csv")
async def validate_csv_endpoint(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        text = raw.decode("utf-8")
    except Exception as exc:
        logger.error(f"CSV read error: {exc}")
        return JSONResponse(status_code=400,
                            content={"success": False, "error": "Cannot read file", "products": [], "errors": []})
    result = _validate_csv(text)
    return JSONResponse(content=result)

@app.post("/analyze")
async def analyze_endpoint(req: AnalyzeRequest):
    products = [p.model_dump() for p in req.products]
    api_key  = _api_key()

    if api_key and SDK_AVAILABLE:
        # ── AGENT MODE ─────────────────────────────────────────────────────
        logger.info("Running AGENT mode pipeline (Gemini API key detected)")
        try:
            results = await _run_agent_pipeline(products)
            return JSONResponse(content={"success": True, "mode": "agent", "results": results})
        except Exception as exc:
            logger.error(f"Agent pipeline error: {exc}")
            # Fall through to direct mode on failure
            logger.warning("Agent pipeline failed — falling back to direct mode")

    # ── DIRECT MODE ────────────────────────────────────────────────────────
    logger.info("Running DIRECT mode pipeline (no Gemini API key / fallback)")
    try:
        results = _run_direct_pipeline(products)
        return JSONResponse(content={"success": True, "mode": "direct", "results": results})
    except Exception as exc:
        logger.error(f"Direct pipeline error: {exc}")
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}")

@app.get("/status")
def status():
    return {
        "server": "MarginGuard",
        "sdk_available": SDK_AVAILABLE,
        "api_key_set": bool(_api_key()),
        "mode": "agent" if (_api_key() and SDK_AVAILABLE) else "direct",
    }

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
