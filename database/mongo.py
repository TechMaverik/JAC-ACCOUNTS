"""MongoDB connection and schema for JAC Accounts.

Connection settings are read from the .env file in the project root:
MONGOHOST, MONGOPORT, MONGOUSER, MONGOPASSWORD, MONGOAUTH and, optionally,
MONGODATABASE (defaults to jac_accounts).

The collections mirror the SQLite tables the data was exported from. Each
document keeps the integer ``id`` it had as a row, allocated from the
``counters`` collection, because the templates and debt payments refer to
rows by that id rather than by Mongo's own ``_id``.
"""

import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient, ReturnDocument

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE = os.getenv("MONGODATABASE", "jac_accounts")

BANKER = "banker"
EXPENSE = "expense"
INCOME = "income"
TRANSFER = "transfer"
INVESTMENT = "investment"
DEBT = "debt"
DEBT_PAYMENT = "debt_payment"
EXCHANGE_RATE = "exchange_rate"
APP_SETTINGS = "app_settings"
COUNTERS = "counters"

# Collections that hold application data, in the order Babayo is shown them.
DATA_COLLECTIONS = [
    BANKER,
    INCOME,
    EXPENSE,
    TRANSFER,
    INVESTMENT,
    DEBT,
    DEBT_PAYMENT,
    EXCHANGE_RATE,
    APP_SETTINGS,
]

# Collections whose documents carry an auto-incrementing integer id.
NUMBERED_COLLECTIONS = [
    BANKER,
    EXPENSE,
    INCOME,
    TRANSFER,
    INVESTMENT,
    DEBT,
    DEBT_PAYMENT,
    EXCHANGE_RATE,
]

# Expected fields and types per collection. amount stays text, exactly as the
# SQLite TEXT column held it, so every reader converts it with $toDouble.
FIELDS = {
    BANKER: {"id": "int", "account_name": "string", "currency": "string"},
    INCOME: {
        "id": "int",
        "amount": "string",
        "to": "string",
        "category": "string",
        "date": "string",
        "currency": "string",
        "source": "string",
    },
    EXPENSE: {
        "id": "int",
        "amount": "string",
        "from": "string",
        "category": "string",
        "date": "string",
        "currency": "string",
        "source": "string",
    },
    TRANSFER: {
        "id": "int",
        "amount": "string",
        "from": "string",
        "to": "string",
        "category": "string",
        "date": "string",
        "currency": "string",
        "to_amount": "string",
        "to_currency": "string",
        "rate": "double",
    },
    INVESTMENT: {
        "id": "int",
        "amount": "string",
        "from": "string",
        "category": "string",
        "date": "string",
        "currency": "string",
    },
    DEBT: {
        "id": "int",
        "name": "string",
        "amount": "string",
        "description": "string",
        "currency": "string",
    },
    DEBT_PAYMENT: {
        "id": "int",
        "debt_id": "int",
        "amount": "string",
        "currency": "string",
        "date": "string",
        "from_account": "string",
    },
    EXCHANGE_RATE: {
        "id": "int",
        "base_currency": "string",
        "quote_currency": "string",
        "rate": "double",
        "date": "string",
    },
    APP_SETTINGS: {"key": "string", "value": "string"},
}

# (keys, options) per collection. Creating an index also creates the
# collection, which is the Mongo equivalent of CREATE TABLE IF NOT EXISTS.
INDEXES = {
    BANKER: [
        ([("id", ASCENDING)], {"unique": True}),
        ([("account_name", ASCENDING)], {}),
    ],
    INCOME: [
        ([("id", ASCENDING)], {"unique": True}),
        ([("to", ASCENDING)], {}),
        ([("date", ASCENDING)], {}),
    ],
    EXPENSE: [
        ([("id", ASCENDING)], {"unique": True}),
        ([("from", ASCENDING)], {}),
        ([("date", ASCENDING)], {}),
    ],
    TRANSFER: [([("id", ASCENDING)], {"unique": True})],
    INVESTMENT: [([("id", ASCENDING)], {"unique": True})],
    DEBT: [([("id", ASCENDING)], {"unique": True})],
    DEBT_PAYMENT: [
        ([("id", ASCENDING)], {"unique": True}),
        ([("debt_id", ASCENDING)], {}),
    ],
    EXCHANGE_RATE: [
        ([("id", ASCENDING)], {"unique": True}),
        (
            [
                ("base_currency", ASCENDING),
                ("quote_currency", ASCENDING),
                ("date", ASCENDING),
            ],
            {"unique": True, "name": "exchange_rate_pair_date"},
        ),
    ],
    APP_SETTINGS: [([("key", ASCENDING)], {"unique": True})],
}

_client = None
_client_lock = threading.Lock()
_schema_ready = False
_schema_lock = threading.Lock()


def get_client():
    """One MongoClient per process; pymongo pools connections behind it."""
    global _client
    with _client_lock:
        if _client is None:
            options = {
                "host": os.getenv("MONGOHOST", "localhost"),
                "port": int(os.getenv("MONGOPORT", "27017")),
                "serverSelectionTimeoutMS": int(os.getenv("MONGOTIMEOUT_MS", "5000")),
            }
            username = os.getenv("MONGOUSER")
            if username:
                # Passed as options, not in the URI, so passwords with
                # characters like @ or / need no escaping.
                options.update(
                    username=username,
                    password=os.getenv("MONGOPASSWORD", ""),
                    authSource=os.getenv("MONGOAUTH", "admin"),
                )
            _client = MongoClient(**options)
        return _client


def get_db():
    return get_client()[DATABASE]


def next_id(db, collection):
    """Next integer id for a collection, like SQLite's AUTOINCREMENT."""
    counter = db[COUNTERS].find_one_and_update(
        {"_id": collection},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(counter["seq"])


def ensure_schema():
    """Create indexes and seed the id counters. Runs once per process."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        db = get_db()
        for collection, indexes in INDEXES.items():
            for keys, options in indexes:
                db[collection].create_index(keys, **options)

        # The exported rows brought their ids with them; new documents must
        # continue the sequence instead of colliding with them.
        for collection in NUMBERED_COLLECTIONS:
            newest = db[collection].find_one(sort=[("id", -1)], projection={"id": 1})
            highest = int(newest["id"]) if newest and newest.get("id") is not None else 0
            db[COUNTERS].update_one(
                {"_id": collection}, {"$max": {"seq": highest}}, upsert=True
            )
        _schema_ready = True
