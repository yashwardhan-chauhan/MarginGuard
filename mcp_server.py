import logging
from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CostConditionsServer")

# Initialize FastMCP Server
mcp = FastMCP("CostConditionsServer")

# Mock data store for cost conditions covering 5 categories and 4 countries:
# - Categories: electronics, apparel, furniture, toys, home goods
# - Source Countries: CN (China), VN (Vietnam), IN (India), MX (Mexico)
MOCK_CONDITIONS = {
    # Electronics
    ("electronics", "cn"): {"tariff_rate": 0.25, "fx_adjustment_factor": 1.05, "freight_rate_multiplier": 1.25},
    ("electronics", "vn"): {"tariff_rate": 0.05, "fx_adjustment_factor": 0.98, "freight_rate_multiplier": 1.10},
    ("electronics", "in"): {"tariff_rate": 0.08, "fx_adjustment_factor": 1.02, "freight_rate_multiplier": 1.15},
    ("electronics", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 0.80},
    
    # Apparel
    ("apparel", "cn"): {"tariff_rate": 0.20, "fx_adjustment_factor": 1.05, "freight_rate_multiplier": 1.15},
    ("apparel", "vn"): {"tariff_rate": 0.08, "fx_adjustment_factor": 0.98, "freight_rate_multiplier": 1.05},
    ("apparel", "in"): {"tariff_rate": 0.10, "fx_adjustment_factor": 1.02, "freight_rate_multiplier": 1.10},
    ("apparel", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 0.75},

    # Furniture
    ("furniture", "cn"): {"tariff_rate": 0.25, "fx_adjustment_factor": 1.05, "freight_rate_multiplier": 1.35},
    ("furniture", "vn"): {"tariff_rate": 0.04, "fx_adjustment_factor": 0.98, "freight_rate_multiplier": 1.20},
    ("furniture", "in"): {"tariff_rate": 0.06, "fx_adjustment_factor": 1.02, "freight_rate_multiplier": 1.25},
    ("furniture", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 0.85},

    # Toys
    ("toys", "cn"): {"tariff_rate": 0.15, "fx_adjustment_factor": 1.05, "freight_rate_multiplier": 1.10},
    ("toys", "vn"): {"tariff_rate": 0.02, "fx_adjustment_factor": 0.98, "freight_rate_multiplier": 1.02},
    ("toys", "in"): {"tariff_rate": 0.05, "fx_adjustment_factor": 1.02, "freight_rate_multiplier": 1.05},
    ("toys", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 0.70},

    # Home Goods
    ("home goods", "cn"): {"tariff_rate": 0.18, "fx_adjustment_factor": 1.05, "freight_rate_multiplier": 1.20},
    ("home goods", "vn"): {"tariff_rate": 0.03, "fx_adjustment_factor": 0.98, "freight_rate_multiplier": 1.10},
    ("home goods", "in"): {"tariff_rate": 0.05, "fx_adjustment_factor": 1.02, "freight_rate_multiplier": 1.12},
    ("home goods", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 0.78},
}

@mcp.tool()
def get_cost_conditions(product_category: str, source_country: str) -> dict:
    """
    Get current mock cost conditions (tariff rate, FX adjustment factor, freight rate multiplier)
    for a given product category and source country.
    
    Args:
        product_category: The product category, e.g. "Electronics", "Apparel", "Furniture", "Toys", "Home Goods".
        source_country: The source country 2-letter ISO code, e.g. "CN", "VN", "IN", "MX".
    """
    cat_clean = product_category.lower().strip()
    country_clean = source_country.upper().strip()
    
    # Handle minor category naming adjustments
    if "home" in cat_clean:
        cat_clean = "home goods"
    elif "electronic" in cat_clean:
        cat_clean = "electronics"
    elif "toy" in cat_clean:
        cat_clean = "toys"
    
    key = (cat_clean, country_clean.lower())
    conditions = MOCK_CONDITIONS.get(key)
    
    if not conditions:
        logger.info(f"No exact match for ({cat_clean}, {country_clean}). Using general fallback values.")
        # Fallback values
        conditions = {
            "tariff_rate": 0.10,
            "fx_adjustment_factor": 1.00,
            "freight_rate_multiplier": 1.00
        }
    else:
        logger.info(f"Matched conditions for category: {cat_clean}, country: {country_clean}")
        
    return conditions

if __name__ == "__main__":
    mcp.run()
