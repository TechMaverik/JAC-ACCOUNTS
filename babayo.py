#!/usr/bin/env python3
"""
Babayo — the JAC Accounts chatbot (Hermes 3 via Ollama + SQLite)

Adapted from agent.py for the dashboard chat window. Babayo explores the
database itself (schema discovery -> read-only SQL) and uses a deterministic
forecasting tool for predictions so numbers are computed, not guessed.

Flow: routers -> handlers -> services -> babayo -> mappers. All database reads
go through Mapper's read-only cursor, so Babayo can never modify your data.

The dashboard talks to Babayo through Service.process_babayo_question(); the
module also runs on its own for a quick terminal chat:

    python babayo.py
    python babayo.py --model hermes3:8b
"""

import argparse
import json
import os
import re
import sqlite3
import statistics
import threading
from datetime import date, timedelta

import ollama

from mappers import Mapper

BOT_NAME = "Babayo"
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "hermes3")
MAX_ROWS = 200  # cap rows returned to the model
MAX_TOOL_ROUNDS = 12  # safety limit on agent loop
NUM_CTX = 8192  # Ollama defaults to a small context; tool results need room
MAX_HISTORY = 40  # non-system messages kept between questions
MAX_RETRY_NUDGES = 2  # times to push the model to fix a failed query
RESERVED_COLUMNS = {"from", "to"}  # must be double quoted in SQL
PERIODS = ["all_time", "this_month", "last_month", "this_year", "last_30_days", "last_90_days"]


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


# ---------------------------------------------------------------------------
# Database tools (read-only, via the mapper layer)
# ---------------------------------------------------------------------------


class BabayoDB:
    def __init__(self, mapper=None):
        self.mapper = mapper or Mapper()

    def list_tables(self) -> dict:
        return {"tables": self.mapper.select_table_names()}

    def describe_table(self, table: str) -> dict:
        tables = self.list_tables()["tables"]
        if table not in tables:
            return {"error": f"Unknown table '{table}'. Available tables: {tables}"}
        info = self.mapper.describe_table(table)
        return {
            "table": table,
            "row_count": info["row_count"],
            "columns": info["columns"],
            "sample_rows": info["sample_rows"],
        }

    def run_sql(self, query: str) -> dict:
        q = query.strip().rstrip(";")
        if not re.match(r"^\s*(SELECT|WITH)\b", q, re.I):
            return {"error": "Only SELECT/WITH queries are allowed."}
        try:
            columns, rows, truncated = self.mapper.run_readonly_query(q, MAX_ROWS, ())
            return {"columns": columns, "rows": rows, "truncated": truncated}
        except sqlite3.Error as e:
            return {
                "error": str(e),
                "available_tables": self.list_tables()["tables"],
                "hint": "Use only the tables/columns listed in the DATABASE SCHEMA.",
            }

    def schema_line(self) -> str:
        """One-line table(column, ...) list for tool descriptions."""
        parts = []
        for t in self.list_tables()["tables"]:
            cols = ", ".join(
                f'"{c["name"]}"' if c["name"] in RESERVED_COLUMNS else c["name"]
                for c in self.mapper.describe_table(t, sample_rows=0)["columns"]
            )
            parts.append(f"{t}({cols})")
        return "; ".join(parts)

    def schema_summary(self) -> str:
        """Compact schema + a couple of sample rows, injected into the system prompt."""
        parts = []
        for t in self.list_tables()["tables"]:
            info = self.describe_table(t)
            cols = ", ".join(
                f'"{c["name"]}"' if c["name"] in RESERVED_COLUMNS else c["name"]
                for c in info["columns"]
            )
            parts.append(f'{t}({cols})  -- {info["row_count"]} rows')
            for r in info["sample_rows"][:2]:
                parts.append(f"    e.g. {json.dumps(r, default=str)}")
        return "\n".join(parts)

    # Ready-made questions. Fixed SQL means a small model cannot get these wrong.

    def _query(self, sql: str, params=()) -> dict:
        try:
            columns, rows, truncated = self.mapper.run_readonly_query(sql, MAX_ROWS, params)
        except sqlite3.Error as e:
            return {"error": str(e)}
        result = {"rows": [dict(zip(columns, r)) for r in rows], "truncated": truncated}
        if not rows:
            result["note"] = (
                "No data matched. Tell the user there is nothing recorded for this; "
                "do not invent figures."
            )
        return result

    def account_balances(self) -> dict:
        return self._query(
            """SELECT b.account_name, b.currency,
                 ROUND((SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM income WHERE "to" = b.account_name)
                     - (SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM expense WHERE "from" = b.account_name), 2)
                 AS balance
               FROM banker b ORDER BY b.account_name"""
        )

    def income_expense_totals(self, period: str = "all_time") -> dict:
        start, end = period_range(period)
        where = "source = 'direct'"
        params = []
        if start:
            where += " AND date >= ?"
            params.append(start)
        if end:
            where += " AND date <= ?"
            params.append(end)
        result = self._query(
            f"""SELECT currency,
                 ROUND(COALESCE(SUM(CASE WHEN kind = 'income' THEN amount END), 0), 2) AS income,
                 ROUND(COALESCE(SUM(CASE WHEN kind = 'expense' THEN amount END), 0), 2) AS expense,
                 ROUND(COALESCE(SUM(CASE WHEN kind = 'income' THEN amount ELSE -amount END), 0), 2) AS net
               FROM (
                 SELECT 'income' AS kind, currency, CAST(amount AS REAL) AS amount FROM income WHERE {where}
                 UNION ALL
                 SELECT 'expense', currency, CAST(amount AS REAL) FROM expense WHERE {where}
               ) GROUP BY currency ORDER BY currency""",
            params * 2,
        )
        for row in result.get("rows", []):
            income = row.get("income") or 0
            row["savings_rate_pct"] = round(row["net"] / income * 100, 1) if income else None
        result["period"] = period or "all_time"
        return result

    def monthly_totals(self, months: int = 12) -> dict:
        return self._query(
            """SELECT month, currency,
                 ROUND(COALESCE(SUM(CASE WHEN kind = 'income' THEN amount END), 0), 2) AS income,
                 ROUND(COALESCE(SUM(CASE WHEN kind = 'expense' THEN amount END), 0), 2) AS expense
               FROM (
                 SELECT 'income' AS kind, strftime('%Y-%m', date) AS month, currency, CAST(amount AS REAL) AS amount
                 FROM income WHERE source = 'direct'
                 UNION ALL
                 SELECT 'expense', strftime('%Y-%m', date), currency, CAST(amount AS REAL)
                 FROM expense WHERE source = 'direct'
               ) GROUP BY month, currency
               ORDER BY month DESC, currency LIMIT ?""",
            (max(1, int(months or 12)) * 4,),
        )

    def top_categories(self, kind: str = "expense", limit: int = 5, period: str = "all_time") -> dict:
        table = "income" if str(kind).lower().startswith("inc") else "expense"
        start, end = period_range(period)
        where = "source = 'direct'"
        params = []
        if start:
            where += " AND date >= ? AND date <= ?"
            params += [start, end]
        params.append(max(1, int(limit or 5)))
        return self._query(
            f"""SELECT category, currency, ROUND(SUM(CAST(amount AS REAL)), 2) AS total, COUNT(*) AS transactions
               FROM {table} WHERE {where}
               GROUP BY category, currency ORDER BY total DESC LIMIT ?""",
            params,
        )

    def largest_transactions(self, kind: str = "expense", limit: int = 5) -> dict:
        table = "income" if str(kind).lower().startswith("inc") else "expense"
        account = '"to"' if table == "income" else '"from"'
        return self._query(
            f"""SELECT date, category, {account} AS account, currency,
                 ROUND(CAST(amount AS REAL), 2) AS amount
               FROM {table} WHERE source = 'direct'
               ORDER BY CAST(amount AS REAL) DESC LIMIT ?""",
            (max(1, int(limit or 5)),),
        )

    def debt_overview(self) -> dict:
        return self._query(
            """SELECT d.name, d.description, d.currency,
                 ROUND(CAST(d.amount AS REAL), 2) AS borrowed,
                 ROUND(COALESCE((SELECT SUM(CAST(amount AS REAL)) FROM debt_payment WHERE debt_id = d.id), 0), 2) AS paid,
                 ROUND(CAST(d.amount AS REAL)
                   - COALESCE((SELECT SUM(CAST(amount AS REAL)) FROM debt_payment WHERE debt_id = d.id), 0), 2) AS outstanding
               FROM debt d ORDER BY outstanding DESC"""
        )

    def forecast(self, query: str, periods_ahead: int = 3) -> dict:
        """
        query must return 2 columns ordered by time: (period_label, amount).
        Fits a linear trend + reports moving average and volatility.
        """
        res = self.run_sql(query)
        if "error" in res:
            return res
        rows = [(str(r[0]), float(r[1] or 0)) for r in res["rows"]]
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


def build_tools(schema_line: str) -> list:
    """Tool schemas for Ollama. The live table list rides along in run_sql's description,
    which a small model reads more reliably than the system prompt."""
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
        tool("list_tables", "List all tables/views in the SQLite database."),
        tool("describe_table",
             "Get columns, types, row count and 5 sample rows of a table.",
             {"table": {"type": "string", "description": "Table name"}}, ["table"]),
        tool("run_sql",
             "Run a read-only SQLite SELECT for anything the other tools do not cover. Use ONLY "
             "these tables and columns: " + schema_line + ". amount is TEXT: use "
             "CAST(amount AS REAL). Quote \"from\" and \"to\". Real income/spending has "
             "source = 'direct'. Use strftime('%Y-%m', date) for months. Returns up to 200 rows.",
             {"query": {"type": "string", "description": "SQLite SELECT query"}}, ["query"]),
        tool("forecast",
             "Forecast future values from a time series. The query MUST return exactly two "
             "columns (period, amount) ordered oldest->newest, e.g. "
             "SELECT strftime('%Y-%m', date) AS m, SUM(CAST(amount AS REAL)) FROM expense "
             "WHERE source='direct' AND currency='AUD' GROUP BY m ORDER BY m. Returns trend, "
             "moving average and prediction ranges.",
             {"query": {"type": "string", "description": "SELECT returning (period, amount)"},
              "periods_ahead": {"type": "integer",
                                "description": "How many periods to predict (default 3)"}},
             ["query"]),
    ]


SYSTEM_PROMPT = f"""You are {BOT_NAME}. Always introduce yourself as {BOT_NAME}, the friendly \
personal finance assistant built into the JAC Accounts app. You chat with the user inside a small \
chat window on their dashboard and you have READ-ONLY access to the app's SQLite database.

DATA GUIDE (this is how the data is organised — rely on it):
- banker: the user's bank accounts (account_name, currency).
- income: money coming IN, one row per transaction ("to" = receiving account).
- expense: money going OUT, one row per transaction ("from" = paying account).
- transfer: moves between the user's own accounts. Each transfer also writes one income row and \
one expense row with source = 'transfer'; real income/spending is source = 'direct'.
- debt: money the user owes; debt_payment: repayments against a debt.
- exchange_rate: 1 base_currency = rate quote_currency on a date. app_settings: display currency.
- There is NO 'transactions' table. Use income and expense.
- amount is stored as TEXT: always use CAST(amount AS REAL). date is 'YYYY-MM-DD' text.
- "from" and "to" are reserved words: write them in double quotes.
- Every row has its own currency. Group by currency; never add different currencies together.

EXAMPLE QUERIES (copy the pattern):
- Income per currency: SELECT currency, SUM(CAST(amount AS REAL)) FROM income WHERE source='direct' GROUP BY currency
- Expense per currency: SELECT currency, SUM(CAST(amount AS REAL)) FROM expense WHERE source='direct' GROUP BY currency
- Monthly spending: SELECT strftime('%Y-%m', date) AS month, currency, SUM(CAST(amount AS REAL)) FROM expense WHERE source='direct' GROUP BY month, currency ORDER BY month
- Top categories: SELECT category, currency, SUM(CAST(amount AS REAL)) AS total FROM expense WHERE source='direct' GROUP BY category, currency ORDER BY total DESC LIMIT 5
- Account balance: SELECT b.account_name, b.currency, (SELECT COALESCE(SUM(CAST(amount AS REAL)),0) FROM income WHERE "to"=b.account_name) - (SELECT COALESCE(SUM(CAST(amount AS REAL)),0) FROM expense WHERE "from"=b.account_name) AS balance FROM banker b

How to work:
1. Prefer the ready-made tools: account_balances, income_expense_totals, monthly_totals, \
top_categories, largest_transactions, debt_overview. They cannot fail.
2. Use run_sql only for questions those tools cannot answer, with ONLY the tables and columns \
listed in the DATABASE SCHEMA below. Copy names exactly.
3. If a query fails, read the error, fix the query using the schema and call run_sql again. \
Never tell the user about a failed query and never make up numbers instead.
4. For ANY prediction, call the forecast tool — never invent forecast numbers yourself.
5. Only report numbers that came from tool results. If there is no data for a question, say so.
6. If the user just greets you or chats, reply briefly and warmly as {BOT_NAME} without \
running queries.

Answer format: plain text that reads well in a small chat bubble. Keep answers short. Use \
short bullet lines with figures for insights, written with the currency code (for example \
1,522.92 AUD or 7,408 INR, never a $ sign for INR), give predictions with their \
low–high range, and add 1–3 practical recommendations when they are useful. Do not use markdown \
tables."""

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
            "list_tables": lambda a: self.db.list_tables(),
            "describe_table": lambda a: self.db.describe_table(a.get("table", "")),
            "run_sql": lambda a: self.db.run_sql(a.get("query", "")),
            "forecast": lambda a: self.db.forecast(
                a.get("query", ""), int(a.get("periods_ahead", 3))
            ),
        }

    def system_message(self) -> dict:
        # Rebuilt on every question so the row counts and samples Babayo sees
        # keep up with transactions added through the app.
        schema = self.db.schema_summary()
        if not schema:
            schema = "(the database has no tables yet)"
        today = date.today()
        this_month = today.strftime("%Y-%m")
        last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        return {
            "role": "system",
            "content": SYSTEM_PROMPT
            + f"\n\nTODAY is {today.isoformat()}. 'This month' means {this_month} and "
            f"'last month' means {last_month}. Use period = all_time unless the user names a period."
            + "\n\nDATABASE SCHEMA (these are the ONLY tables and columns that exist — "
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
                            "explain the error. Write a corrected SELECT that uses only "
                            "the tables and columns in the DATABASE SCHEMA (remember "
                            "CAST(amount AS REAL) and double quotes around \"from\" and "
                            "\"to\"), call run_sql, then answer the question."
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
