"""Data access for JAC Accounts on MongoDB.

Documents mirror the rows of the SQLite tables the data was exported from:
each keeps its integer ``id``, ``amount`` stays text, and the ``from`` /
``to`` field names are unchanged. Every method returns tuples and dicts
shaped like the old SQLite rows, so the services layer and the templates were
unaffected by the move.
"""

import json

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from database import mongo

# amount is stored as text, as it was in SQLite. Text that is not a number
# counts as zero instead of failing the whole aggregation.
AMOUNT = {
    "$convert": {"input": "$amount", "to": "double", "onError": 0.0, "onNull": 0.0}
}

# Aggregation stages that only read. Everything else, above all $out and
# $merge, is refused: that is what keeps Babayo's queries read-only.
READ_ONLY_STAGES = {
    "$addFields",
    "$bucket",
    "$bucketAuto",
    "$count",
    "$densify",
    "$facet",
    "$fill",
    "$group",
    "$limit",
    "$lookup",
    "$match",
    "$project",
    "$redact",
    "$replaceRoot",
    "$replaceWith",
    "$sample",
    "$set",
    "$setWindowFields",
    "$skip",
    "$sort",
    "$sortByCount",
    "$unionWith",
    "$unset",
    "$unwind",
}
FORBIDDEN_OPERATORS = {"$out", "$merge", "$function", "$accumulator", "$where"}


def _int_id(value):
    """Form fields arrive as text; ids are stored as integers."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _plain(value):
    """JSON friendly copy of a document value."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_plain(inner) for inner in value]
    return value


def _type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _check_collection(name):
    if name not in mongo.DATA_COLLECTIONS:
        raise ValueError(
            f"Unknown collection '{name}'. Available collections: {mongo.DATA_COLLECTIONS}"
        )


def _check_operators(value):
    """Refuse operators that write or run code, anywhere in the pipeline."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if key in FORBIDDEN_OPERATORS:
                raise ValueError(f"{key} is not allowed in a read-only query.")
            if key == "$lookup" and isinstance(inner, dict):
                _check_collection(inner.get("from"))
            if key == "$unionWith":
                _check_collection(inner if isinstance(inner, str) else (inner or {}).get("coll"))
            _check_operators(inner)
    elif isinstance(value, list):
        for item in value:
            _check_operators(item)


def validate_pipeline(pipeline):
    """A pipeline the chatbot may run: a list of read-only stages."""
    if isinstance(pipeline, str):
        pipeline = json.loads(pipeline)
    if isinstance(pipeline, dict):
        pipeline = [pipeline]
    if pipeline is None:
        pipeline = []
    if not isinstance(pipeline, list) or not all(isinstance(s, dict) for s in pipeline):
        raise ValueError("pipeline must be a JSON list of stage objects.")
    for stage in pipeline:
        if len(stage) != 1:
            raise ValueError(
                f"Each stage must have exactly one key, got {list(stage)}."
            )
        (name,) = stage
        if name not in READ_ONLY_STAGES:
            raise ValueError(
                f"Stage {name} is not allowed. Use only: {', '.join(sorted(READ_ONLY_STAGES))}."
            )
        _check_operators(stage)
    return pipeline


class Mapper:

    def __init__(self):
        self.db = mongo.get_db()

    def ensure_schema(self):
        mongo.ensure_schema()

    def _insert(self, collection, document):
        document["id"] = mongo.next_id(self.db, collection)
        self.db[collection].insert_one(document)
        return document["id"]

    def insert_to_debts(self, data):
        name, amount, description, currency = data
        self._insert(
            mongo.DEBT,
            {
                "name": name,
                "amount": str(amount),
                "description": description,
                "currency": currency,
            },
        )
        return True

    def insert_to_bankers(self, data):
        name, currency = data
        self._insert(mongo.BANKER, {"account_name": name, "currency": currency})
        return True

    def insert_to_income(self, data):
        amount, to_account, category, date, currency, source = data
        self._insert(
            mongo.INCOME,
            {
                "amount": str(amount),
                "to": to_account,
                "category": category,
                "date": date,
                "currency": currency,
                "source": source,
            },
        )
        return True

    def insert_to_expense(self, data):
        amount, from_account, category, date, currency, source = data
        self._insert(
            mongo.EXPENSE,
            {
                "amount": str(amount),
                "from": from_account,
                "category": category,
                "date": date,
                "currency": currency,
                "source": source,
            },
        )
        return True

    def insert_to_transfer(self, data):
        """Record a transfer plus the income/expense legs it produces.

        The expense leg is booked in the sending account's currency and the
        income leg in the receiving account's currency, so a cross currency
        transfer leaves both balances correct.
        """
        (
            amount,
            from_account,
            to_account,
            category,
            date,
            currency,
            to_amount,
            to_currency,
            rate,
        ) = data

        self._insert(
            mongo.TRANSFER,
            {
                "amount": str(amount),
                "from": from_account,
                "to": to_account,
                "category": category,
                "date": date,
                "currency": currency,
                "to_amount": str(to_amount),
                "to_currency": to_currency,
                "rate": float(rate),
            },
        )
        self.insert_to_income(
            (to_amount, to_account, category, date, to_currency, "transfer")
        )
        self.insert_to_expense(
            (amount, from_account, category, date, currency, "transfer")
        )
        return True

    def insert_to_investment(self, data):
        amount, from_account, category, date, currency = data
        self._insert(
            mongo.INVESTMENT,
            {
                "amount": str(amount),
                "from": from_account,
                "category": category,
                "date": date,
                "currency": currency,
            },
        )
        return True

    def delete_all_entries(self):
        for collection in (mongo.BANKER, mongo.EXPENSE, mongo.INCOME, mongo.TRANSFER):
            self.db[collection].delete_many({})
        return True

    def select_accounts(self):
        return [
            (doc.get("id"), doc.get("account_name"), doc.get("currency"))
            for doc in self.db[mongo.BANKER].find({}, sort=[("id", ASCENDING)])
        ]

    def select_account_currency(self, account_name):
        doc = self.db[mongo.BANKER].find_one({"account_name": account_name})
        return doc.get("currency") if doc else None

    def _totals_by(self, collection, field):
        rows = self.db[collection].aggregate(
            [{"$group": {"_id": f"${field}", "total": {"$sum": AMOUNT}}}]
        )
        return {row["_id"]: row["total"] or 0.0 for row in rows}

    def select_income_totals(self):
        return self._totals_by(mongo.INCOME, "to")

    def select_expense_totals(self):
        return self._totals_by(mongo.EXPENSE, "from")

    def select_all__transaction_items(self):
        expenses = [
            (
                doc.get("id"),
                doc.get("amount"),
                doc.get("from"),
                doc.get("category"),
                doc.get("date"),
                doc.get("currency"),
            )
            for doc in self.db[mongo.EXPENSE].find({}, sort=[("id", ASCENDING)])
        ]
        income = [
            (
                doc.get("id"),
                doc.get("amount"),
                doc.get("to"),
                doc.get("category"),
                doc.get("date"),
                doc.get("currency"),
            )
            for doc in self.db[mongo.INCOME].find({}, sort=[("id", ASCENDING)])
        ]
        transfer = [
            (
                doc.get("id"),
                doc.get("amount"),
                doc.get("from"),
                doc.get("to"),
                doc.get("category"),
                doc.get("date"),
                doc.get("currency"),
                doc.get("to_amount"),
                doc.get("to_currency"),
                doc.get("rate"),
            )
            for doc in self.db[mongo.TRANSFER].find({}, sort=[("id", ASCENDING)])
        ]
        return expenses, income, transfer

    def _totals_by_date(self, collection):
        # Trend series exclude the legs written by a transfer: moving your own
        # money between accounts is neither income nor expense.
        rows = self.db[collection].aggregate(
            [
                {"$match": {"source": "direct"}},
                {
                    "$group": {
                        "_id": {"date": "$date", "currency": "$currency"},
                        "total": {"$sum": AMOUNT},
                    }
                },
                {"$sort": {"_id.date": ASCENDING, "_id.currency": ASCENDING}},
            ]
        )
        return [(row["_id"]["date"], row["_id"]["currency"], row["total"]) for row in rows]

    def select_income_by_date(self):
        return self._totals_by_date(mongo.INCOME)

    def select_expense_by_date(self):
        return self._totals_by_date(mongo.EXPENSE)

    @staticmethod
    def _debt_row(doc):
        return (
            doc.get("id"),
            doc.get("name"),
            doc.get("amount"),
            doc.get("description"),
            doc.get("currency"),
        )

    def select_debts(self):
        return [
            self._debt_row(doc)
            for doc in self.db[mongo.DEBT].find({}, sort=[("id", DESCENDING)])
        ]

    def select_debt(self, debt_id):
        debt_id = _int_id(debt_id)
        if debt_id is None:
            return None
        doc = self.db[mongo.DEBT].find_one({"id": debt_id})
        return self._debt_row(doc) if doc else None

    def insert_debt_payment(self, data):
        debt_id, amount, currency, date, from_account = data
        self._insert(
            mongo.DEBT_PAYMENT,
            {
                "debt_id": int(debt_id),
                "amount": str(amount),
                "currency": currency,
                "date": date,
                "from_account": from_account or "",
            },
        )
        return True

    def select_debt_payments(self):
        return [
            (
                doc.get("id"),
                doc.get("debt_id"),
                doc.get("amount"),
                doc.get("currency"),
                doc.get("date"),
                doc.get("from_account"),
            )
            for doc in self.db[mongo.DEBT_PAYMENT].find(
                {}, sort=[("date", ASCENDING), ("id", ASCENDING)]
            )
        ]

    def select_debt_paid_totals(self):
        return self._totals_by(mongo.DEBT_PAYMENT, "debt_id")

    def upsert_exchange_rate(self, data):
        base, quote, rate, date = data
        pair = {"base_currency": base, "quote_currency": quote, "date": date}
        updated = self.db[mongo.EXCHANGE_RATE].update_one(
            pair, {"$set": {"rate": float(rate)}}
        )
        if updated.matched_count == 0:
            try:
                self._insert(mongo.EXCHANGE_RATE, {**pair, "rate": float(rate)})
            except DuplicateKeyError:
                # Someone saved the same pair and date in between: keep theirs
                # updated rather than failing.
                self.db[mongo.EXCHANGE_RATE].update_one(
                    pair, {"$set": {"rate": float(rate)}}
                )
        return True

    def select_exchange_rates(self):
        return [
            (
                doc.get("id"),
                doc.get("base_currency"),
                doc.get("quote_currency"),
                doc.get("rate"),
                doc.get("date"),
            )
            for doc in self.db[mongo.EXCHANGE_RATE].find(
                {}, sort=[("date", DESCENDING), ("id", DESCENDING)]
            )
        ]

    def select_latest_exchange_rates(self):
        rows = self.db[mongo.EXCHANGE_RATE].aggregate(
            [
                {"$sort": {"date": DESCENDING, "id": DESCENDING}},
                {
                    "$group": {
                        "_id": {"base": "$base_currency", "quote": "$quote_currency"},
                        "rate": {"$first": "$rate"},
                        "date": {"$first": "$date"},
                    }
                },
            ]
        )
        return [
            (row["_id"]["base"], row["_id"]["quote"], row["rate"], row["date"])
            for row in rows
        ]

    def delete_exchange_rate(self, rate_id):
        rate_id = _int_id(rate_id)
        if rate_id is not None:
            self.db[mongo.EXCHANGE_RATE].delete_one({"id": rate_id})
        return True

    def select_settings(self):
        return {
            doc["key"]: doc.get("value")
            for doc in self.db[mongo.APP_SETTINGS].find({}, {"key": 1, "value": 1})
        }

    def upsert_setting(self, key, value):
        self.db[mongo.APP_SETTINGS].update_one(
            {"key": key}, {"$set": {"value": value}}, upsert=True
        )
        return True

    # ------------------------------------------------------------------
    # Read-only access for Babayo, the dashboard chatbot
    # ------------------------------------------------------------------

    def select_collection_names(self):
        existing = set(self.db.list_collection_names())
        return [name for name in mongo.DATA_COLLECTIONS if name in existing]

    def describe_collection(self, collection, sample_rows=5):
        """Fields, document count and a few sample documents of one collection."""
        _check_collection(collection)
        store = self.db[collection]
        # Start from the known layout so an empty collection still has a
        # schema, then let the live documents refine the types.
        fields = dict(mongo.FIELDS.get(collection, {}))
        for doc in store.find({}, {"_id": 0}).sort("id", ASCENDING).limit(50):
            for key, value in doc.items():
                if key not in fields or (fields[key] == "null" and value is not None):
                    fields[key] = _type_name(value)
        sample = []
        if sample_rows:
            sample = [
                _plain(doc)
                for doc in store.find({}, {"_id": 0}).sort("id", ASCENDING).limit(sample_rows)
            ]
        return {
            "columns": [{"name": name, "type": kind} for name, kind in fields.items()],
            "row_count": store.count_documents({}),
            "sample_rows": sample,
        }

    def run_readonly_query(self, collection, pipeline, max_rows):
        """Run a read-only aggregation and return (columns, rows, truncated).

        Raises ValueError for a pipeline that is malformed or would write, and
        pymongo errors for the caller to turn into a message.
        """
        _check_collection(collection)
        stages = validate_pipeline(pipeline) + [{"$limit": max_rows + 1}]
        docs = list(
            self.db[collection].aggregate(stages, allowDiskUse=False, maxTimeMS=15000)
        )
        truncated = len(docs) > max_rows
        docs = docs[:max_rows]

        columns = []
        for doc in docs:
            # A document's own ObjectId says nothing useful; a group key does.
            if isinstance(doc.get("_id"), ObjectId):
                doc.pop("_id")
            for key in doc:
                if key not in columns:
                    columns.append(key)
        rows = [[_plain(doc.get(column)) for column in columns] for doc in docs]
        return columns, rows, truncated
