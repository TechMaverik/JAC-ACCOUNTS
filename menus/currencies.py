"""Currency configuration for JAC Accounts.

Every currency the application understands is declared here. Adding a new one
is a matter of adding an entry to CURRENCIES - the forms, balances and
exchange rate screens all read from this table.
"""

CURRENCIES = {
    "INR": {"code": "INR", "symbol": "₹", "name": "Indian Rupee"},
    "AUD": {"code": "AUD", "symbol": "A$", "name": "Australian Dollar"},
}

DEFAULT_CURRENCY = "INR"

CODES = list(CURRENCIES)


def normalise(code):
    """Return a supported currency code, falling back to the default."""
    if not code:
        return DEFAULT_CURRENCY
    code = str(code).strip().upper()
    return code if code in CURRENCIES else DEFAULT_CURRENCY


def symbol(code):
    return CURRENCIES[normalise(code)]["symbol"]


def name(code):
    return CURRENCIES[normalise(code)]["name"]


def label(code):
    code = normalise(code)
    return f"{CURRENCIES[code]['name']} ({CURRENCIES[code]['symbol']} {code})"


def pairs():
    """Every ordered currency pair, used to seed the exchange rate screen."""
    return [(base, quote) for base in CODES for quote in CODES if base != quote]


def format_amount(amount, code=DEFAULT_CURRENCY, signed=False):
    """Render an amount with its currency symbol, e.g. ₹1,234.56 or A$-20.00."""
    if amount is None:
        return "—"
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return str(amount)

    sign = ""
    if amount < 0:
        sign = "-"
    elif signed:
        sign = "+"
    return f"{sign}{symbol(code)}{abs(amount):,.2f}"
