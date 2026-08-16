DB_LOC = "database/jac_accounts.db"

CREATE_CREDENTIALS = """
CREATE TABLE IF NOT EXISTS credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    password TEXT NOT NULL
) """

CREATE_BANKERS = """
CREATE TABLE IF NOT EXISTS banker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR'
)
"""

CREATE_EXPENSE = """
CREATE TABLE IF NOT EXISTS expense (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount TEXT NOT NULL,
    "from" TEXT DEFAULT 0,
    category TEXT NOT NULL,
    date TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    source TEXT NOT NULL DEFAULT 'direct'
)
"""

CREATE_INCOME = """
CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount TEXT NOT NULL,
    "to" TEXT DEFAULT 0,
    category TEXT NOT NULL,
    date TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    source TEXT NOT NULL DEFAULT 'direct'
)
"""

CREATE_TRANSFER = """
CREATE TABLE IF NOT EXISTS transfer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount TEXT NOT NULL,
    "from" TEXT DEFAULT 0,
    "to" TEXT DEFAULT 0,
    category TEXT NOT NULL,
    date TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    to_amount TEXT,
    to_currency TEXT NOT NULL DEFAULT 'INR',
    rate REAL NOT NULL DEFAULT 1
)
"""

CREATE_INVESTMENT = """
CREATE TABLE IF NOT EXISTS investment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount TEXT NOT NULL,
    "from" TEXT DEFAULT 0,
    category TEXT NOT NULL,
    date TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR'
)
"""

CREATE_DEBT = """
CREATE TABLE IF NOT EXISTS debt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    amount TEXT NOT NULL,
    description TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR'
) """

CREATE_DEBT_PAYMENT = """
CREATE TABLE IF NOT EXISTS debt_payment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debt_id INTEGER NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    date TEXT NOT NULL,
    from_account TEXT DEFAULT ''
)
"""

CREATE_EXCHANGE_RATE = """
CREATE TABLE IF NOT EXISTS exchange_rate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    base_currency TEXT NOT NULL,
    quote_currency TEXT NOT NULL,
    rate REAL NOT NULL,
    date TEXT NOT NULL
)
"""

CREATE_EXCHANGE_RATE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS exchange_rate_pair_date
ON exchange_rate (base_currency, quote_currency, date)
"""

CREATE_APP_SETTINGS = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

CREATE_STATEMENTS = [
    CREATE_CREDENTIALS,
    CREATE_BANKERS,
    CREATE_EXPENSE,
    CREATE_INCOME,
    CREATE_TRANSFER,
    CREATE_INVESTMENT,
    CREATE_DEBT,
    CREATE_DEBT_PAYMENT,
    CREATE_EXCHANGE_RATE,
    CREATE_EXCHANGE_RATE_INDEX,
    CREATE_APP_SETTINGS,
]

# "Liabilities" were renamed to "debts". Applied before the CREATE statements so
# the existing rows carry over instead of a fresh empty table appearing.
TABLE_RENAMES = [("liability", "debt")]

COLUMN_RENAMES = [("debt", "liability", "name")]

# Columns added after the first release. Applied only when missing, so an
# existing database picks up currency support without losing its rows.
COLUMN_MIGRATIONS = [
    ("banker", "currency", "ALTER TABLE banker ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR'"),
    ("expense", "currency", "ALTER TABLE expense ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR'"),
    ("income", "currency", "ALTER TABLE income ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR'"),
    ("expense", "source", "ALTER TABLE expense ADD COLUMN source TEXT NOT NULL DEFAULT 'direct'"),
    ("income", "source", "ALTER TABLE income ADD COLUMN source TEXT NOT NULL DEFAULT 'direct'"),
    ("transfer", "currency", "ALTER TABLE transfer ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR'"),
    ("transfer", "to_amount", "ALTER TABLE transfer ADD COLUMN to_amount TEXT"),
    ("transfer", "to_currency", "ALTER TABLE transfer ADD COLUMN to_currency TEXT NOT NULL DEFAULT 'INR'"),
    ("transfer", "rate", "ALTER TABLE transfer ADD COLUMN rate REAL NOT NULL DEFAULT 1"),
    ("investment", "currency", "ALTER TABLE investment ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR'"),
    ("debt", "currency", "ALTER TABLE debt ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR'"),
]

INSERT_BANKER = "INSERT INTO banker (account_name, currency) VALUES (?, ?)"

INSERT_EXPENSE = (
    'INSERT INTO expense (amount, "from", category, date, currency, source)'
    " VALUES (?, ?, ?, ?, ?, ?)"
)

INSERT_INCOME = (
    'INSERT INTO income (amount, "to", category, date, currency, source)'
    " VALUES (?, ?, ?, ?, ?, ?)"
)

# Trend series exclude the legs written by a transfer: moving your own money
# between accounts is neither income nor expense.
SELECT_INCOME_BY_DATE = """
SELECT date, currency, SUM(CAST(amount AS REAL))
FROM income WHERE source = 'direct'
GROUP BY date, currency ORDER BY date
"""

SELECT_EXPENSE_BY_DATE = """
SELECT date, currency, SUM(CAST(amount AS REAL))
FROM expense WHERE source = 'direct'
GROUP BY date, currency ORDER BY date
"""

INSERT_TRANSFER = """
INSERT INTO transfer (amount, "from", "to", category, date, currency, to_amount, to_currency, rate)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_INVESTMENT = (
    'INSERT INTO investment (amount, "from", category, date, currency) VALUES (?, ?, ?, ?, ?)'
)

INSERT_DEBT = (
    "INSERT INTO debt (name, amount, description, currency) VALUES (?, ?, ?, ?)"
)

SELECT_DEBTS = (
    "SELECT id, name, amount, description, currency FROM debt ORDER BY id DESC"
)

INSERT_DEBT_PAYMENT = """
INSERT INTO debt_payment (debt_id, amount, currency, date, from_account)
VALUES (?, ?, ?, ?, ?)
"""

SELECT_DEBT_PAYMENTS = """
SELECT id, debt_id, amount, currency, date, from_account
FROM debt_payment ORDER BY date, id
"""

SELECT_DEBT_PAID_TOTALS = (
    "SELECT debt_id, SUM(CAST(amount AS REAL)) FROM debt_payment GROUP BY debt_id"
)

UPSERT_EXCHANGE_RATE = """
INSERT INTO exchange_rate (base_currency, quote_currency, rate, date)
VALUES (?, ?, ?, ?)
ON CONFLICT (base_currency, quote_currency, date)
DO UPDATE SET rate = excluded.rate
"""

SELECT_EXCHANGE_RATES = """
SELECT id, base_currency, quote_currency, rate, date
FROM exchange_rate
ORDER BY date DESC, id DESC
"""

SELECT_LATEST_EXCHANGE_RATES = """
SELECT rate_row.base_currency, rate_row.quote_currency, rate_row.rate, rate_row.date
FROM exchange_rate AS rate_row
JOIN (
    SELECT base_currency, quote_currency, MAX(date) AS latest_date
    FROM exchange_rate
    GROUP BY base_currency, quote_currency
) AS latest
ON rate_row.base_currency = latest.base_currency
AND rate_row.quote_currency = latest.quote_currency
AND rate_row.date = latest.latest_date
"""

UPSERT_SETTING = """
INSERT INTO app_settings (key, value) VALUES (?, ?)
ON CONFLICT (key) DO UPDATE SET value = excluded.value
"""
