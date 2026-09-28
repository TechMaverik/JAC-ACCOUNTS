import sqlite3
from contextlib import contextmanager

from database import query_collection


class Mapper:

    @contextmanager
    def _cursor(self, commit=False):
        conn = sqlite3.connect(query_collection.DB_LOC)
        try:
            yield conn.cursor()
            if commit:
                conn.commit()
        finally:
            conn.close()

    def create_tables(self):
        with self._cursor(commit=True) as cursor:

            def columns_of(table):
                cursor.execute(f"PRAGMA table_info({table})")
                return [row[1] for row in cursor.fetchall()]

            # Renames run first: a CREATE IF NOT EXISTS under the new name would
            # otherwise leave the old table - and its rows - stranded.
            cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            tables = {row[0] for row in cursor.fetchall()}
            for old_name, new_name in query_collection.TABLE_RENAMES:
                if old_name in tables and new_name not in tables:
                    cursor.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
                    tables.add(new_name)

            for table, old_column, new_column in query_collection.COLUMN_RENAMES:
                if table not in tables:
                    continue
                columns = columns_of(table)
                if old_column in columns and new_column not in columns:
                    cursor.execute(
                        f"ALTER TABLE {table} RENAME COLUMN {old_column} TO {new_column}"
                    )

            for statement in query_collection.CREATE_STATEMENTS:
                cursor.execute(statement)

            for table, column, statement in query_collection.COLUMN_MIGRATIONS:
                if column not in columns_of(table):
                    cursor.execute(statement)

    def insert_to_debts(self, data):
        with self._cursor(commit=True) as cursor:
            cursor.execute(query_collection.INSERT_DEBT, data)
        return True

    def insert_to_bankers(self, data):
        with self._cursor(commit=True) as cursor:
            cursor.execute(query_collection.INSERT_BANKER, data)
        return True

    def insert_to_income(self, data):
        with self._cursor(commit=True) as cursor:
            cursor.execute(query_collection.INSERT_INCOME, data)
        return True

    def insert_to_expense(self, data):
        with self._cursor(commit=True) as cursor:
            cursor.execute(query_collection.INSERT_EXPENSE, data)
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

        with self._cursor(commit=True) as cursor:
            cursor.execute(query_collection.INSERT_TRANSFER, data)
            cursor.execute(
                query_collection.INSERT_INCOME,
                (to_amount, to_account, category, date, to_currency, "transfer"),
            )
            cursor.execute(
                query_collection.INSERT_EXPENSE,
                (amount, from_account, category, date, currency, "transfer"),
            )
        return True

    def insert_to_investment(self, data):
        with self._cursor(commit=True) as cursor:
            cursor.execute(query_collection.INSERT_INVESTMENT, data)
        return True

    def delete_all_entries(self):
        with self._cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM banker")
            cursor.execute("DELETE FROM expense")
            cursor.execute("DELETE FROM income")
            cursor.execute("DELETE FROM transfer")
        return True

    def select_accounts(self):
        with self._cursor() as cursor:
            cursor.execute("SELECT id, account_name, currency FROM banker ORDER BY id")
            return cursor.fetchall()

    def select_account_currency(self, account_name):
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT currency FROM banker WHERE account_name = ?", (account_name,)
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def select_income_totals(self):
        with self._cursor() as cursor:
            cursor.execute(
                'SELECT "to", SUM(CAST(amount AS REAL)) FROM income GROUP BY "to"'
            )
            return {row[0]: row[1] or 0.0 for row in cursor.fetchall()}

    def select_expense_totals(self):
        with self._cursor() as cursor:
            cursor.execute(
                'SELECT "from", SUM(CAST(amount AS REAL)) FROM expense GROUP BY "from"'
            )
            return {row[0]: row[1] or 0.0 for row in cursor.fetchall()}

    def select_all_transactions(self):
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM expense")
            expenses = cursor.fetchall()
            cursor.execute("SELECT * FROM income")
            income = cursor.fetchall()
            cursor.execute("SELECT * FROM transfer")
            transfer = cursor.fetchall()
        return expenses, income, transfer

    def select_all__transaction_items(self):
        with self._cursor() as cursor:
            cursor.execute(
                'SELECT id, amount, "from", category, date, currency FROM expense'
            )
            expenses = cursor.fetchall()
            cursor.execute(
                'SELECT id, amount, "to", category, date, currency FROM income'
            )
            income = cursor.fetchall()
            cursor.execute(
                'SELECT id, amount, "from", "to", category, date, currency,'
                " to_amount, to_currency, rate FROM transfer"
            )
            transfer = cursor.fetchall()
        return expenses, income, transfer

    def select_income_by_date(self):
        with self._cursor() as cursor:
            cursor.execute(query_collection.SELECT_INCOME_BY_DATE)
            return cursor.fetchall()

    def select_expense_by_date(self):
        with self._cursor() as cursor:
            cursor.execute(query_collection.SELECT_EXPENSE_BY_DATE)
            return cursor.fetchall()

    def select_debts(self):
        with self._cursor() as cursor:
            cursor.execute(query_collection.SELECT_DEBTS)
            return cursor.fetchall()

    def select_debt(self, debt_id):
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT id, name, amount, description, currency FROM debt WHERE id = ?",
                (debt_id,),
            )
            return cursor.fetchone()

    def insert_debt_payment(self, data):
        with self._cursor(commit=True) as cursor:
            cursor.execute(query_collection.INSERT_DEBT_PAYMENT, data)
        return True

    def select_debt_payments(self):
        with self._cursor() as cursor:
            cursor.execute(query_collection.SELECT_DEBT_PAYMENTS)
            return cursor.fetchall()

    def select_debt_paid_totals(self):
        with self._cursor() as cursor:
            cursor.execute(query_collection.SELECT_DEBT_PAID_TOTALS)
            return {row[0]: row[1] or 0.0 for row in cursor.fetchall()}

    def upsert_exchange_rate(self, data):
        with self._cursor(commit=True) as cursor:
            cursor.execute(query_collection.UPSERT_EXCHANGE_RATE, data)
        return True

    def select_exchange_rates(self):
        with self._cursor() as cursor:
            cursor.execute(query_collection.SELECT_EXCHANGE_RATES)
            return cursor.fetchall()

    def select_latest_exchange_rates(self):
        with self._cursor() as cursor:
            cursor.execute(query_collection.SELECT_LATEST_EXCHANGE_RATES)
            return cursor.fetchall()

    def delete_exchange_rate(self, rate_id):
        with self._cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM exchange_rate WHERE id = ?", (rate_id,))
        return True

    def select_settings(self):
        with self._cursor() as cursor:
            cursor.execute("SELECT key, value FROM app_settings")
            return dict(cursor.fetchall())

    def upsert_setting(self, key, value):
        with self._cursor(commit=True) as cursor:
            cursor.execute(query_collection.UPSERT_SETTING, (key, value))
        return True

    # ------------------------------------------------------------------
    # Read-only access for Babayo, the dashboard chatbot
    # ------------------------------------------------------------------

    @contextmanager
    def _readonly_cursor(self):
        # mode=ro means the chatbot physically cannot modify the data.
        conn = sqlite3.connect(f"file:{query_collection.DB_LOC}?mode=ro", uri=True)
        try:
            yield conn.cursor()
        finally:
            conn.close()

    def select_table_names(self):
        with self._readonly_cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            return [row[0] for row in cursor.fetchall()]

    def describe_table(self, table, sample_rows=5):
        """Columns, row count and a few sample rows of one table."""
        with self._readonly_cursor() as cursor:
            cursor.execute(f'PRAGMA table_info("{table}")')
            columns = [{"name": row[1], "type": row[2]} for row in cursor.fetchall()]
            cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cursor.fetchone()[0]
            cursor.execute(f'SELECT * FROM "{table}" LIMIT ?', (sample_rows,))
            names = [d[0] for d in cursor.description]
            sample = [dict(zip(names, row)) for row in cursor.fetchall()]
        return {"columns": columns, "row_count": count, "sample_rows": sample}

    def run_readonly_query(self, query, max_rows, params=()):
        """Run a SELECT and return (columns, rows, truncated).

        Raises sqlite3.Error for the caller to turn into a message.
        """
        with self._readonly_cursor() as cursor:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchmany(max_rows + 1)
            columns = [d[0] for d in cursor.description]
        truncated = len(rows) > max_rows
        return columns, [list(row) for row in rows[:max_rows]], truncated
