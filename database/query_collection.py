DB_LOC = "database/jac_accounts.db"
CREATE_BANKERS = """
CREATE TABLE banker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name TEXT NOT NULL,
    balance TEXT NOT NULL
)
"""

CREATE_EXPENSE = """
CREATE TABLE expense (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount TEXT NOT NULL,
    "from" TEXT DEFAULT 0,
    category TEXT NOT NULL,
    date TEXT NOT NULL
)
"""

INSERT_EXPENSE = (
    """INSERT INTO income (amount, "to", category, date) VALUES (?, ?, ?, ?)"""
)

CREATE_INCOME = """
CREATE TABLE income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount TEXT NOT NULL,
    "to" TEXT DEFAULT 0,
    category TEXT NOT NULL,
    date TEXT NOT NULL
)
"""

CREATE_TRANSFER = """
CREATE TABLE transfer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount TEXT NOT NULL,
    "from" TEXT DEFAULT 0,
    "to" TEXT DEFAULT 0,
    category TEXT NOT NULL,
    date TEXT NOT NULL
)
"""

CREATE_INVESTMENT = """
CREATE TABLE investment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount TEXT NOT NULL,
    "from" TEXT DEFAULT 0,
    category TEXT NOT NULL,
    date TEXT NOT NULL
)
"""
