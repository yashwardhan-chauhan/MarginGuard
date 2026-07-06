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
    ("electronics", "cn"): {"tariff_rate": 0.15, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("electronics", "vn"): {"tariff_rate": 0.05, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("electronics", "in"): {"tariff_rate": 0.08, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("electronics", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    
    # Apparel
    ("apparel", "cn"): {"tariff_rate": 0.15, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("apparel", "vn"): {"tariff_rate": 0.08, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("apparel", "in"): {"tariff_rate": 0.10, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("apparel", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},

    # Furniture
    ("furniture", "cn"): {"tariff_rate": 0.15, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("furniture", "vn"): {"tariff_rate": 0.04, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("furniture", "in"): {"tariff_rate": 0.06, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("furniture", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},

    # Toys
    ("toys", "cn"): {"tariff_rate": 0.15, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("toys", "vn"): {"tariff_rate": 0.02, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("toys", "in"): {"tariff_rate": 0.05, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("toys", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},

    # Home Goods
    ("home goods", "cn"): {"tariff_rate": 0.15, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("home goods", "vn"): {"tariff_rate": 0.03, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("home goods", "in"): {"tariff_rate": 0.05, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
    ("home goods", "mx"): {"tariff_rate": 0.00, "fx_adjustment_factor": 1.00, "freight_rate_multiplier": 1.00},
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
    elif "appa" in cat_clean:
        cat_clean = "apparel"
    elif "furn" in cat_clean:
        cat_clean = "furniture"
    
    key = (cat_clean, country_clean.lower())
    conditions = MOCK_CONDITIONS.get(key)
    
    if not conditions:
        logger.info(f"No exact match for ({cat_clean}, {country_clean}). Using general fallback values.")
        # Fallback values tracking your UI profile baseline rules
        conditions = {
            "tariff_rate": 0.15 if country_clean == "CN" else (0.05 if country_clean == "VN" else 0.00),
            "fx_adjustment_factor": 1.00,
            "freight_rate_multiplier": 1.00
        }
    else:
        logger.info(f"Matched conditions for category: {cat_clean}, country: {country_clean}")
        
    return conditions

if __name__ == "__main__":
    mcp.run()