"""
MarginGuard — Synchronized Local FastAPI backend.
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
# SDK import
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
# Mock cost-conditions data 
# ---------------------------------------------------------------------------
_MOCK_CONDITIONS: Dict[tuple, dict] = {
    ("electronics", "cn"): {"tariff_rate: 0.15", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("electronics", "vn"): {"tariff_rate: 0.05", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("electronics", "in"): {"tariff_rate: 0.08", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("electronics", "mx"): {"tariff_rate: 0.00", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    
    ("apparel",    "cn"): {"tariff_rate: 0.15", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("apparel",    "vn"): {"tariff_rate: 0.08", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    
    ("furniture",  "cn"): {"tariff_rate: 0.15", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("furniture",  "vn"): {"tariff_rate: 0.04", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    
    ("toys",       "cn"): {"tariff_rate: 0.15", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("toys",       "vn"): {"tariff_rate: 0.02", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    
    ("home goods", "cn"): {"tariff_rate: 0.15", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("home goods", "in"): {"tariff_rate: 0.05", "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
}

_FALLBACK_CONDITIONS = {"tariff_rate": 0.15, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00}

def _normalise_category(cat: str) -> str:
    c = cat.lower().strip()
    if "home" in c:      return "home goods"
    if "electronic" in c: return "electronics"
    if "toy" in c:        return "toys"
    if "appa" in c:       return "apparel"
    if "furn" in c:       return "furniture"
    return c

def _get_conditions(category: str, country: str) -> dict:
    key = (_normalise_category(category), country.lower().strip())
    return dict(_MOCK_CONDITIONS.get(key, _FALLBACK_CONDITIONS))

# ---------------------------------------------------------------------------
# Sourcing Rules mapping standard UI calculations 
# ---------------------------------------------------------------------------
def _compute_landed_cost(supplier_cost: float, tariff_rate: float, shipping_cost: float) -> float:
    return supplier_cost + (supplier_cost * tariff_rate) + shipping_cost

def _compute_margin(sale_price: float, landed_cost: float) -> float:
    return ((sale_price - landed_cost) / sale_price) * 100 if sale_price > 0 else 0.0

def _compute_target_price(landed_cost: float, target_margin_pct: float) -> float:
    if target_margin_pct >= 100:
        return landed_cost
    return landed_cost / (1 - (target_margin_pct / 100.0))

# ---------------------------------------------------------------------------
# Direct processing loop mirroring JS Logic
# ---------------------------------------------------------------------------
def _run_direct_pipeline(products: List[dict]) -> List[dict]:
    results = []
    for p in products:
        cat = p["product_category"]
        country = p["source_country"].lower()
        sup_cost = float(p["supplier_cost"])
        ship_cost = float(p["shipping_cost"])
        sale_pr = float(p["current_sale_price"])
        tgt_pct = float(p["target_margin_pct"])

        # Default flat calculation configuration mapping UI script
        tariff = 0.15 if country == "cn" else (0.05 if country == "vn" else 0.00)
        
        landed = _compute_landed_cost(sup_cost, tariff, ship_cost)
        margin = _compute_margin(sale_pr, landed)
        flagged = margin < tgt_pct

        _log_action("Calculated margin validation sequence completed")

        rec_price = None
        recommendation = "OK"
        alt_option = "-"

        if flagged:
            rec_price = round(_compute_target_price(landed, tgt_pct), 2)
            recommendation = f"Increase price to ${rec_price:.2f}"
            
            if country == "cn":
                proj_landed = (sup_cost * 0.9) + (ship_cost * 0.85)
                proj_margin = ((sale_pr - proj_landed) / sale_pr) * 100
                if proj_margin < tgt_pct:
                    alt_option = f"Alt supplier MX: Landed ${proj_landed:.2f}, Margin {proj_margin:.1f}% (still below target — min price ${(proj_landed / (1 - (tgt_pct / 100.0))):.2f})"
                else:
                    alt_option = f"Alt supplier MX: Landed ${proj_landed:.2f}, Margin {proj_margin:.1f}% (Healthy)"
            else:
                alt_option = "Consolidate global pathway loads to decrease cross-docking overheads by 10%."

        results.append({
            **p,
            "landed_cost": round(landed, 2),
            "est_margin_pct": round(margin, 1),
            "is_violated": flagged,
            "action_directive": recommendation,
            "sourcing_directive": alt_option
        })
    return results

# ---------------------------------------------------------------------------
# Pydantic request model matching UI schema configuration
# ---------------------------------------------------------------------------
class ProductInput(BaseModel):
    sku: str
    product_category: str
    source_country: str
    supplier_cost: float
    shipping_cost: float
    current_sale_price: float
    target_margin_pct: float

class AnalyzeRequest(BaseModel):
    products: List[ProductInput]

# ---------------------------------------------------------------------------
# Sync validation mapping updated header configuration matrix
# ---------------------------------------------------------------------------
_HEADER_MAP = {
    "sku": "sku",
    "category": "product_category", "product_category": "product_category",
    "country": "source_country", "source_country": "source_country",
    "cost": "supplier_cost", "supplier_cost": "supplier_cost",
    "shipping": "shipping_cost", "shipping_cost": "shipping_cost",
    "sale price": "current_sale_price", "current_sale_price": "current_sale_price",
    "target %": "target_margin_pct", "target_margin_pct": "target_margin_pct"
}

_REQUIRED = ["sku", "product_category", "source_country", "supplier_cost", "shipping_cost", "current_sale_price", "target_margin_pct"]

def _validate_csv(content: str) -> dict:
    reader = csv.reader(io.StringIO(content))
    try:
        raw_headers = next(reader)
    except StopIteration:
        return {"success": False, "error": "CSV file is completely empty", "products": [], "errors": []}

    headers = [_HEADER_MAP.get(h.strip().lower(), h.strip().lower()) for h in raw_headers]
    missing = [r for r in _REQUIRED if r not in headers]
    if missing:
        return {"success": False, "error": f"Missing required structural columns: {', '.join(missing)}", "products": [], "errors": []}

    valid, errors = [], []
    for row_num, row in enumerate(reader, start=2):
        if not row or all(c.strip() == "" for c in row): continue
        if len(row) < len(raw_headers): row += [""] * (len(raw_headers) - len(row))

        rd = dict(zip(headers, row))
        sku = rd.get("sku", "").strip()
        cat = rd.get("product_category", "").strip()
        country = rd.get("source_country", "").strip().upper()

        errs = []
        if not sku: errs.append("SKU target reference is missing")
        if not cat: errs.append("Category specification is missing")
        if not country: errs.append("Country origin tag is missing")

        def _parse_num(field):
            try:
                return float(rd.get(field, "0") or "0")
            except ValueError:
                errs.append(f"{field} must be parsed as valid numeric text")
                return 0.0

        sup = _parse_num("supplier_cost")
        ship = _parse_num("shipping_cost")
        sale = _parse_num("current_sale_price")
        tgt = _parse_num("target_margin_pct")

        if errs:
            errors.append({"row_number": row_num, "sku": sku or f"Row {row_num}", "reasons": errs})
        else:
            valid.append({
                "sku": sku, "product_category": cat, "source_country": country,
                "supplier_cost": sup, "shipping_cost": ship, "current_sale_price": sale, "target_margin_pct": tgt
            })

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
        return "<h3>index.html file was not detected within workspace footprint.</h3>"

@app.post("/validate-csv")
async def validate_csv_endpoint(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        text = raw.decode("utf-8")
    except Exception as exc:
        logger.error(f"Inbound reading crash sequence triggered: {exc}")
        return JSONResponse(status_code=400, content={"success": False, "error": "Unable to read dataset payload", "products": [], "errors": []})
    return JSONResponse(content=_validate_csv(text))

@app.post("/analyze")
async def analyze_endpoint(req: AnalyzeRequest):
    products = [p.model_dump() for p in req.products]
    try:
        results = _run_direct_pipeline(products)
        return JSONResponse(content={"success": True, "mode": "direct", "results": results})
    except Exception as exc:
        logger.error(f"Pipeline tracking error logged: {exc}")
        raise HTTPException(status_code=500, detail=f"Pipeline loop termination: {exc}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)