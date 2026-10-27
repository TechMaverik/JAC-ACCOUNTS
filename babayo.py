#!/usr/bin/env python3
"""
Babayo — the JAC Accounts chatbot (Hermes 3 via Ollama + MongoDB)

Adapted from agent.py for the dashboard chat window. Babayo explores the
database itself (schema discovery -> read-only aggregation pipelines) and
uses a deterministic forecasting tool for predictions so numbers are
computed, not guessed.

Flow: routers -> handlers -> services -> babayo -> mappers. All database reads
go through Mapper.run_readonly_query, which accepts only read-only pipeline
stages, so Babayo can never modify your data.

The dashboard talks to Babayo through Service.process_babayo_question(); the
module also runs on its own for a quick terminal chat:

    python babayo.py
    python babayo.py --model hermes3:8b
"""

import argparse
import functools
import json
import os
import re
import statistics
import threading
from datetime import date, timedelta

import ollama
from pymongo.errors import PyMongoError

from database import mongo
from mappers import AMOUNT, Mapper

BOT_NAME = "Babayo"
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "hermes3")
MAX_ROWS = 200  # cap rows returned to the model
MAX_TOOL_ROUNDS = 12  # safety limit on agent loop
NUM_CTX = 8192  # Ollama defaults to a small context; tool results need room
MAX_HISTORY = 40  # non-system messages kept between questions
MAX_RETRY_NUDGES = 2  # times to push the model to fix a failed query
PERIODS = ["all_time", "this_month", "last_month", "this_year", "last_30_days", "last_90_days"]

MONTH = {"$substrCP": ["$date", 0, 7]}  # 'YYYY-MM' out of a 'YYYY-MM-DD' date


def period_range(period: str):
    """(start, end) ISO dates for a named period; (None, None) means all time."""
    today = date.today()
    period = (period or "all_time").strip().lower()
    if period == "this_month":
        return today.replace(day=1).isoformat(), today.isoformat()
    if period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1).isoformat(), end.isoformat()
    if period == "this_year":
        return today.replace(month=1, day=1).isoformat(), today.isoformat()
    if period == "last_30_days":
        return (today - timedelta(days=30)).isoformat(), today.isoformat()
    if period == "last_90_days":
        return (today - timedelta(days=90)).isoformat(), today.isoformat()
    return None, None


def direct_match(period: str = "all_time") -> dict:
    """Filter for real income/spending (not transfer legs) within a period."""
    match = {"source": "direct"}
    start, end = period_range(period)
    if start:
        match["date"] = {"$gte": start, "$lte": end}
    return match


def parse_pipeline(pipeline):
    """The model may send the pipeline as JSON text instead of a list."""
    if isinstance(pipeline, str):
        pipeline = json.loads(pipeline)
    if pipeline is None:
        return []
    if isinstance(pipeline, dict):
        return [pipeline]
    return pipeline


def _safe(method):
    """Turn database and validation errors into a result the model can read."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except (ValueError, PyMongoError) as e:
            return {"error": str(e)}

    return wrapper


# ---------------------------------------------------------------------------
# Database tools (read-only, via the mapper layer)
# ---------------------------------------------------------------------------


class BabayoDB:
    def __init__(self, mapper=None):
        self.mapper = mapper or Mapper()

    def list_collections(self) -> dict:
        return {"collections": self.mapper.select_collection_names()}

    def describe_collection(self, collection: str) -> dict:
        collections = self.list_collections()["collections"]
        if collection not in collections:
            return {
                "error": f"Unknown collection '{collection}'. Available collections: {collections}"
            }
        info = self.mapper.describe_collection(collection)
        return {
            "collection": collection,
            "row_count": info["row_count"],
            "fields": info["columns"],
            "sample_rows": info["sample_rows"],
        }

    def run_query(self, collection: str, pipeline) -> dict:
        try:
            columns, rows, truncated = self.mapper.run_readonly_query(
                collection, parse_pipeline(pipeline), MAX_ROWS
            )
            return {"columns": columns, "rows": rows, "truncated": truncated}
        except (ValueError, PyMongoError) as e:
            return {
                "error": str(e),
                "available_collections": self.list_collections()["collections"],
                "hint": "Send a JSON aggregation pipeline using only the collections "
                "and fields listed in the DATABASE SCHEMA.",
            }

    def schema_line(self) -> str:
        """One-line collection(field, ...) list for tool descriptions."""
        parts = []
        for name in self.list_collections()["collections"]:
            cols = ", ".join(
                c["name"] for c in self.mapper.describe_collection(name, sample_rows=0)["columns"]
            )
            parts.append(f"{name}({cols})")
        return "; ".join(parts)

    def schema_summary(self) -> str:
        """Compact schema + a couple of sample rows, injected into the system prompt."""
        parts = []
        for name in self.list_collections()["collections"]:
            info = self.describe_collection(name)
            cols = ", ".join(f'{c["name"]}: {c["type"]}' for c in info["fields"])
            parts.append(f'{name}({cols})  -- {info["row_count"]} documents')
            for r in info["sample_rows"][:2]:
                parts.append(f"    e.g. {json.dumps(r, default=str)}")
        return "\n".join(parts)

    # Ready-made questions. Fixed pipelines mean a small model cannot get these wrong.

    def _rows(self, collection: str, pipeline: list):
        columns, rows, truncated = self.mapper.run_readonly_query(collection, pipeline, MAX_ROWS)
        return [dict(zip(columns, r)) for r in rows], truncated

    @staticmethod
    def _result(rows: list, truncated: bool = False) -> dict:
        result = {"rows": rows, "truncated": truncated}
        if not rows:
            result["note"] = (
                "No data matched. Tell the user there is nothing recorded for this; "
                "do not invent figures."
            )
        return result

    @_safe
    def account_balances(self) -> dict:
        income = self.mapper.select_income_totals()
        expense = self.mapper.select_expense_totals()
        rows = [
            {
                "account_name": name,
                "currency": currency,
                "balance": round(income.get(name, 0.0) - expense.get(name, 0.0), 2),
            }
            for _id, name, currency in sorted(
                self.mapper.select_accounts(), key=lambda row: row[1] or ""
            )
        ]
        return self._result(rows)

    @_safe
    def income_expense_totals(self, period: str = "all_time") -> dict:
        pipeline = [
            {"$match": direct_match(period)},
            {"$group": {"_id": "$currency", "total": {"$sum": AMOUNT}}},
        ]
        income = {r["_id"]: r["total"] for r in self._rows(mongo.INCOME, pipeline)[0]}
        expense = {r["_id"]: r["total"] for r in self._rows(mongo.EXPENSE, pipeline)[0]}

        rows = []
        for currency in sorted(set(income) | set(expense), key=str):
            earned = round(income.get(currency, 0.0), 2)
            spent = round(expense.get(currency, 0.0), 2)
            net = round(earned - spent, 2)
            rows.append(
                {
                    "currency": currency,
                    "income": earned,
                    "expense": spent,
                    "net": net,
                    "savings_rate_pct": round(net / earned * 100, 1) if earned else None,
                }
            )
        result = self._result(rows)
        result["period"] = period or "all_time"
        return result

    @_safe
    def monthly_totals(self, months: int = 12) -> dict:
        pipeline = [
            {"$match": {"source": "direct"}},
            {
                "$group": {
                    "_id": {"month": MONTH, "currency": "$currency"},
                    "total": {"$sum": AMOUNT},
                }
            },
        ]
        buckets = {}
        for kind, collection in (("income", mongo.INCOME), ("expense", mongo.EXPENSE)):
            for r in self._rows(collection, pipeline)[0]:
                key = (r["_id"]["month"], r["_id"]["currency"])
                bucket = buckets.setdefault(
                    key, {"month": key[0], "currency": key[1], "income": 0.0, "expense": 0.0}
                )
                bucket[kind] = round(r["total"], 2)

        rows = list(buckets.values())
        rows.sort(key=lambda b: str(b["currency"]))
        rows.sort(key=lambda b: str(b["month"]), reverse=True)  # newest month first
        limit = max(1, int(months or 12)) * 4
        return self._result(rows[:limit], truncated=len(rows) > limit)

    @_safe
    def top_categories(self, kind: str = "expense", limit: int = 5, period: str = "all_time") -> dict:
        collection = mongo.INCOME if str(kind).lower().startswith("inc") else mongo.EXPENSE
        rows, truncated = self._rows(
            collection,
            [
                {"$match": direct_match(period)},
                {
                    "$group": {
                        "_id": {"category": "$category", "currency": "$currency"},
                        "total": {"$sum": AMOUNT},
                        "transactions": {"$sum": 1},
                    }
                },
                {"$sort": {"total": -1}},
                {"$limit": max(1, int(limit or 5))},
                {
                    "$project": {
                        "_id": 0,
                        "category": "$_id.category",
                        "currency": "$_id.currency",
                        "total": {"$round": ["$total", 2]},
                        "transactions": 1,
                    }
                },
            ],
        )
        return self._result(rows, truncated)

    @_safe
    def largest_transactions(self, kind: str = "expense", limit: int = 5) -> dict:
        collection = mongo.INCOME if str(kind).lower().startswith("inc") else mongo.EXPENSE
        account = "$to" if collection == mongo.INCOME else "$from"
        rows, truncated = self._rows(
            collection,
            [
                {"$match": {"source": "direct"}},
                {"$addFields": {"_amount": AMOUNT}},
                {"$sort": {"_amount": -1}},
                {"$limit": max(1, int(limit or 5))},
                {
                    "$project": {
                        "_id": 0,
                        "date": 1,
                        "category": 1,
                        "account": account,
                        "currency": 1,
                        "amount": {"$round": ["$_amount", 2]},
                    }
                },
            ],
        )
        return self._result(rows, truncated)

    @_safe
    def debt_overview(self) -> dict:
        paid_totals = self.mapper.select_debt_paid_totals()
        rows = []
        for debt_id, name, amount, description, currency in self.mapper.select_debts():
            try:
                borrowed = round(float(amount), 2)
            except (TypeError, ValueError):
                borrowed = 0.0
            paid = round(paid_totals.get(debt_id, 0.0), 2)
            rows.append(
                {
                    "name": name,
                    "description": description,
                    "currency": currency,
                    "borrowed": borrowed,
                    "paid": paid,
                    "outstanding": round(borrowed - paid, 2),
                }
            )
        rows.sort(key=lambda r: r["outstanding"], reverse=True)
        return self._result(rows)

    def forecast(self, collection: str, pipeline, periods_ahead: int = 3) -> dict:
        """
        pipeline must produce documents with the period as _id (or a 'period'
        field) and an 'amount' field. Fits a linear trend + reports moving
        average and volatility.
        """
        res = self.run_query(collection, pipeline)
        if "error" in res:
            return res
        columns = res["columns"]
        period_col = "period" if "period" in columns else (columns[0] if columns else None)
        amount_col = (
            "amount"
            if "amount" in columns
            else next((c for c in columns if c != period_col), None)
        )
        if period_col is None or amount_col is None:
            return {
                "error": "The pipeline must return documents with a period and an "
                'amount, e.g. {"_id": "2026-08", "amount": 123.4}.'
            }

        rows = []
        for values in res["rows"]:
            doc = dict(zip(columns, values))
            try:
                rows.append((str(doc.get(period_col)), float(doc.get(amount_col) or 0)))
            except (TypeError, ValueError):
                return {"error": f"'{amount_col}' must be numeric in every document."}
        rows.sort(key=lambda r: r[0])  # oldest -> newest, whatever order came back

        if len(rows) < 3:
            return {
                "error": f"Only {len(rows)} period(s) of history; a forecast needs at least 3.",
                "history": rows,
                "instruction": "Tell the user there is not enough history to forecast yet and "
                "show the periods you do have as past figures, not as predictions.",
            }

        ys = [y for _, y in rows]
        n = len(ys)
        xs = list(range(n))
        x_mean, y_mean = statistics.mean(xs), statistics.mean(ys)
        denom = sum((x - x_mean) ** 2 for x in xs)
        slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
        intercept = y_mean - slope * x_mean

        resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
        resid_sd = statistics.stdev(resid) if n > 2 else 0.0
        window = min(3, n)
        moving_avg = statistics.mean(ys[-window:])

        preds = []
        for k in range(1, periods_ahead + 1):
            trend = intercept + slope * (n - 1 + k)
            blended = 0.6 * trend + 0.4 * moving_avg  # dampen pure-trend extrapolation
            preds.append(
                {
                    "step": k,
                    "predicted": round(max(blended, 0), 2),
                    "low": round(max(blended - 1.96 * resid_sd, 0), 2),
                    "high": round(blended + 1.96 * resid_sd, 2),
                }
            )

        return {
            "history_periods": n,
            "last_period": rows[-1][0],
            "trend_per_period": round(slope, 2),
            f"moving_avg_last_{window}": round(moving_avg, 2),
            "mean": round(y_mean, 2),
            "volatility_sd": round(statistics.stdev(ys), 2),
            "forecast": preds,
        }


# ---------------------------------------------------------------------------
# Tool schemas for Ollama
# ---------------------------------------------------------------------------

def tool(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


KIND = {"type": "string", "enum": ["expense", "income"],
        "description": "'expense' for spending or 'income' for money received"}
LIMIT = {"type": "integer", "description": "How many rows to return (default 5)"}
PERIOD = {"type": "string", "enum": PERIODS,
          "description": "Time window. Use all_time unless the user names a period."}
COLLECTION = {"type": "string", "description": "Collection to query, e.g. expense"}
PIPELINE = {"type": "array", "items": {"type": "object"},
            "description": "MongoDB aggregation stages as JSON objects, e.g. "
                           '[{"$match": {"source": "direct"}}, {"$group": {...}}]'}


def build_tools(schema_line: str) -> list:
    """Tool schemas for Ollama. The live collection list rides along in run_query's
    description, which a small model reads more reliably than the system prompt."""
    return [
        tool("account_balances",
             "Current balance of every bank account in its own currency. Use for questions about "
             "balances, how much money the user has, or a specific account."),
        tool("income_expense_totals",
             "Total income, total expense and net (income - expense) per currency, optionally "
             "limited to a period, with the savings rate already computed as savings_rate_pct. "
             "Use for totals, savings rate and cash flow questions.",
             {"period": PERIOD}),
        tool("monthly_totals",
             "Income and expense per month and currency, newest month first. Use for trends, "
             "month-over-month comparisons and 'this month' / 'last month' questions.",
             {"months": {"type": "integer", "description": "How many recent months (default 12)"}}),
        tool("top_categories",
             "Biggest expense or income categories by total amount, all time or for a period.",
             {"kind": KIND, "limit": LIMIT, "period": PERIOD}),
        tool("largest_transactions",
             "The single largest expense or income transactions with their date, category and account.",
             {"kind": KIND, "limit": LIMIT}),
        tool("debt_overview",
             "Every debt with the amount borrowed, amount repaid and what is still outstanding."),
        tool("list_collections", "List all collections in the MongoDB database."),
        tool("describe_collection",
             "Get fields, types, document count and 5 sample documents of a collection.",
             {"collection": {"type": "string", "description": "Collection name"}}, ["collection"]),
        tool("run_query",
             "Run a read-only MongoDB aggregation pipeline for anything the other tools do not "
             "cover. Use ONLY these collections and fields: " + schema_line + ". amount is a "
             'string: sum it with {"$sum": {"$toDouble": "$amount"}}. Real income/spending has '
             'source = "direct". Month of a date = {"$substrCP": ["$date", 0, 7]}. '
             "Returns up to 200 documents.",
             {"collection": COLLECTION, "pipeline": PIPELINE}, ["collection", "pipeline"]),
        tool("forecast",
             "Forecast future values from a time series. The pipeline MUST produce documents "
             "with the period as _id and an amount field, sorted oldest->newest, e.g. collection "
             'expense with [{"$match": {"source": "direct", "currency": "AUD"}}, {"$group": '
             '{"_id": {"$substrCP": ["$date", 0, 7]}, "amount": {"$sum": {"$toDouble": '
             '"$amount"}}}}, {"$sort": {"_id": 1}}]. Returns trend, moving average and '
             "prediction ranges.",
             {"collection": COLLECTION, "pipeline": PIPELINE,
              "periods_ahead": {"type": "integer",
                                "description": "How many periods to predict (default 3)"}},
             ["collection", "pipeline"]),
    ]


# Plain string, not an f-string: the example pipelines are full of braces.
SYSTEM_PROMPT = """You are {bot}. Always introduce yourself as {bot}, the friendly \
personal finance assistant built into the JAC Accounts app. You chat with the user inside a small \
chat window on their dashboard and you have READ-ONLY access to the app's MongoDB database.

DATA GUIDE (this is how the data is organised — rely on it):
- banker: the user's bank accounts (account_name, currency).
- income: money coming IN, one document per transaction (to = receiving account).
- expense: money going OUT, one document per transaction (from = paying account).
- transfer: moves between the user's own accounts. Each transfer also writes one income document \
and one expense document with source = "transfer"; real income/spending is source = "direct".
- debt: money the user owes; debt_payment: repayments against a debt (debt_id = the debt's id).
- exchange_rate: 1 base_currency = rate quote_currency on a date. app_settings: display currency.
- There is NO "transactions" collection. Use income and expense.
- amount is stored as a string: always convert it with {"$toDouble": "$amount"}. date is a \
"YYYY-MM-DD" string, so the month is {"$substrCP": ["$date", 0, 7]}.
- Every document has its own currency. Group by currency; never add different currencies together.

EXAMPLE QUERIES for run_query (copy the pattern; collection first, then the pipeline):
- Income per currency: income, [{"$match": {"source": "direct"}}, {"$group": {"_id": "$currency", \
"total": {"$sum": {"$toDouble": "$amount"}}}}]
- Expense per currency: expense, [{"$match": {"source": "direct"}}, {"$group": {"_id": "$currency", \
"total": {"$sum": {"$toDouble": "$amount"}}}}]
- Monthly spending: expense, [{"$match": {"source": "direct"}}, {"$group": {"_id": {"month": \
{"$substrCP": ["$date", 0, 7]}, "currency": "$currency"}, "total": {"$sum": {"$toDouble": \
"$amount"}}}}, {"$sort": {"_id.month": 1}}]
- Top categories: expense, [{"$match": {"source": "direct"}}, {"$group": {"_id": {"category": \
"$category", "currency": "$currency"}, "total": {"$sum": {"$toDouble": "$amount"}}}}, \
{"$sort": {"total": -1}}, {"$limit": 5}]
- Spending from one account: expense, [{"$match": {"source": "direct", "from": "Common Wealth"}}, \
{"$group": {"_id": "$currency", "total": {"$sum": {"$toDouble": "$amount"}}}}]

How to work:
1. Prefer the ready-made tools: account_balances, income_expense_totals, monthly_totals, \
top_categories, largest_transactions, debt_overview. They cannot fail.
2. Use run_query only for questions those tools cannot answer, with ONLY the collections and \
fields listed in the DATABASE SCHEMA below. Copy names exactly.
3. If a query fails, read the error, fix the pipeline using the schema and call run_query again. \
Never tell the user about a failed query and never make up numbers instead.
4. For ANY prediction, call the forecast tool — never invent forecast numbers yourself.
5. Only report numbers that came from tool results. If there is no data for a question, say so.
6. If the user just greets you or chats, reply briefly and warmly as {bot} without \
running queries.

Answer format: plain text that reads well in a small chat bubble. Keep answers short. Use \
short bullet lines with figures for insights, written with the currency code (for example \
1,522.92 AUD or 7,408 INR, never a $ sign for INR), give predictions with their \
low–high range, and add 1–3 practical recommendations when they are useful. Do not use markdown \
tables.""".replace("{bot}", BOT_NAME)

REPORT_PROMPT = """Give me a full financial health report: income vs expenses over time, \
monthly net cash flow, savings rate, top expense categories, any anomalies or unusual \
transactions, and a 3-month forecast for both income and expenses."""


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


class Babayo:
    """One conversation with Babayo. Safe to reuse across web requests."""

    name = BOT_NAME

    def __init__(self, db: BabayoDB = None, model: str = DEFAULT_MODEL, verbose: bool = False):
        self.db = db or BabayoDB()
        self.model, self.verbose = model, verbose
        self.history = []  # user / assistant / tool messages, without the system prompt
        self._lock = threading.Lock()
        self.dispatch = {
            "account_balances": lambda a: self.db.account_balances(),
            "income_expense_totals": lambda a: self.db.income_expense_totals(
                a.get("period") or "all_time"
            ),
            "monthly_totals": lambda a: self.db.monthly_totals(a.get("months") or 12),
            "top_categories": lambda a: self.db.top_categories(
                a.get("kind") or "expense", a.get("limit") or 5, a.get("period") or "all_time"
            ),
            "largest_transactions": lambda a: self.db.largest_transactions(
                a.get("kind") or "expense", a.get("limit") or 5
            ),
            "debt_overview": lambda a: self.db.debt_overview(),
            "list_collections": lambda a: self.db.list_collections(),
            "describe_collection": lambda a: self.db.describe_collection(
                a.get("collection") or a.get("table", "")
            ),
            "run_query": lambda a: self.db.run_query(
                a.get("collection", ""), a.get("pipeline", [])
            ),
            "forecast": lambda a: self.db.forecast(
                a.get("collection", ""), a.get("pipeline", []), int(a.get("periods_ahead", 3))
            ),
        }

    def system_message(self) -> dict:
        # Rebuilt on every question so the document counts and samples Babayo
        # sees keep up with transactions added through the app.
        schema = self.db.schema_summary()
        if not schema:
            schema = "(the database has no collections yet)"
        today = date.today()
        this_month = today.strftime("%Y-%m")
        last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        return {
            "role": "system",
            "content": SYSTEM_PROMPT
            + f"\n\nTODAY is {today.isoformat()}. 'This month' means {this_month} and "
            f"'last month' means {last_month}. Use period = all_time unless the user names a period."
            + "\n\nDATABASE SCHEMA (these are the ONLY collections and fields that exist — "
            "never guess other names; copy these exactly):\n" + schema,
        }

    def reset(self):
        with self._lock:
            self.history = []

    def ask(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "Ask me anything about your accounts, spending, income or debts."
        if question.lower() == "report":
            question = REPORT_PROMPT

        # One question at a time; the conversation history is shared state.
        with self._lock:
            try:
                return self._ask(question)
            except ollama.ResponseError as e:
                return (
                    f"{BOT_NAME} could not get an answer from the model '{self.model}': "
                    f"{e.error or e}. Pull it with `ollama pull {self.model}` and try again."
                )
            except PyMongoError as e:
                return (
                    f"{BOT_NAME} cannot read the database right now "
                    f"({e.__class__.__name__}: {e}). Check the MongoDB settings in .env."
                )
            except Exception as e:  # noqa: BLE001 - connection refused, timeouts, ...
                return (
                    f"{BOT_NAME} cannot reach Ollama right now ({e.__class__.__name__}: {e}). "
                    "Start it with `ollama serve` and try again."
                )

    def _ask(self, question: str) -> str:
        self.history.append({"role": "user", "content": question})
        self.history = self.history[-MAX_HISTORY:]
        messages = [self.system_message()] + self.history
        tools = build_tools(self.db.schema_line())
        last_error = None  # error from the most recent tool round, if any
        nudges = 0

        for _ in range(MAX_TOOL_ROUNDS):
            resp = ollama.chat(
                model=self.model,
                messages=messages,
                tools=tools,
                options={"temperature": 0.1, "num_ctx": NUM_CTX},
            )
            msg = resp.message
            messages.append(msg)
            self.history.append(msg)

            calls = [
                (c.function.name, c.function.arguments) for c in (msg.tool_calls or [])
            ]
            if not calls:
                # Hermes 3 sometimes emits <tool_call>{...}</tool_call> as plain text
                calls = parse_hermes_tool_calls(msg.content or "")
            if not calls:
                # A small model tends to apologise and stop after one bad query.
                # Push it to fix the query instead of answering with the error.
                if last_error and nudges < MAX_RETRY_NUDGES:
                    nudges += 1
                    nudge = {
                        "role": "user",
                        "content": (
                            f"Your last query failed: {last_error}. Do not apologise or "
                            "explain the error. Write a corrected aggregation pipeline that "
                            "uses only the collections and fields in the DATABASE SCHEMA "
                            '(remember {"$toDouble": "$amount"} for amounts), call '
                            "run_query, then answer the question."
                        ),
                    }
                    messages.append(nudge)
                    self.history.append(nudge)
                    continue
                answer = clean_output(msg.content or "")
                return answer or f"{BOT_NAME} had nothing to say. Try rephrasing the question."

            last_error = None
            for name, args in calls:
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                args = args or {}
                if self.verbose:
                    print(f"  🔧 {name}({json.dumps(args)[:200]})")
                fn = self.dispatch.get(name)
                try:
                    result = fn(args) if fn else {"error": f"Unknown tool {name}"}
                except (TypeError, ValueError) as e:
                    result = {"error": f"Bad arguments for {name}: {e}"}
                if isinstance(result, dict) and result.get("error"):
                    last_error = result["error"]
                if self.verbose:
                    print(f"     -> {json.dumps(result, default=str)[:200]}")
                tool_message = {
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps(result, default=str),
                }
                messages.append(tool_message)
                self.history.append(tool_message)

        return "I ran too many queries without reaching an answer. Try a more specific question."


def parse_hermes_tool_calls(text: str) -> list:
    """Fallback: extract Hermes-format <tool_call>{"name":..,"arguments":..}</tool_call> blocks."""
    calls = []
    for block in re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", text, flags=re.S):
        try:
            obj = json.loads(block)
            calls.append((obj.get("name", ""), obj.get("arguments", {})))
        except json.JSONDecodeError:
            continue
    return calls


def clean_output(text: str) -> str:
    return re.sub(r"</?tool_call>|<\|im_(start|end)\|>", "", text).strip()


# ---------------------------------------------------------------------------
# Shared instance for the web app
# ---------------------------------------------------------------------------

_babayo = None
_babayo_lock = threading.Lock()


def get_babayo() -> Babayo:
    """The one Babayo the dashboard talks to, so the chat remembers context."""
    global _babayo
    with _babayo_lock:
        if _babayo is None:
            _babayo = Babayo()
        return _babayo


def main():
    p = argparse.ArgumentParser(description=f"{BOT_NAME} — JAC Accounts chatbot (Hermes 3 via Ollama)")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument(
        "--report", action="store_true", help="Generate one full report and exit"
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Show tool calls")
    args = p.parse_args()

    bot = Babayo(BabayoDB(), args.model, args.verbose)

    if args.report:
        print(bot.ask(REPORT_PROMPT))
        return

    print(f"{BOT_NAME} ready ({args.model}). Type 'report', a question, or 'exit'.\n")
    while True:
        try:
            q = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"exit", "quit"}:
            break
        if not q:
            continue
        print(f"\n{BOT_NAME}:\n{bot.ask(q)}\n")


if __name__ == "__main__":
    main()
