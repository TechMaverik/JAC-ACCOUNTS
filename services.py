from menus import currencies
from mappers import Mapper

DISPLAY_CURRENCY_KEY = "display_currency"


class Service:

    def __init__(self):
        self.mapper = Mapper()
        self.mapper.create_tables()
        self._rate_cache = None

    def create_tables(self):
        self.mapper.create_tables()

    # ------------------------------------------------------------------
    # Currency configuration
    # ------------------------------------------------------------------

    def get_display_currency(self):
        """Currency used for the headline balance and the recommendations."""
        settings = self.mapper.select_settings()
        return currencies.normalise(settings.get(DISPLAY_CURRENCY_KEY))

    def set_display_currency(self, code):
        self.mapper.upsert_setting(DISPLAY_CURRENCY_KEY, currencies.normalise(code))
        return True

    def get_exchange_rates(self):
        rows = self.mapper.select_exchange_rates()
        return [
            {
                "id": row[0],
                "base_currency": row[1],
                "quote_currency": row[2],
                "rate": row[3],
                "date": row[4],
            }
            for row in rows
        ]

    def latest_rates(self):
        """{(base, quote): rate} using the most recent date entered per pair."""
        if self._rate_cache is None:
            self._rate_cache = {
                (row[0], row[1]): row[2]
                for row in self.mapper.select_latest_exchange_rates()
            }
        return self._rate_cache

    def rate(self, from_currency, to_currency):
        """Rate to turn 1 unit of from_currency into to_currency, or None."""
        from_currency = currencies.normalise(from_currency)
        to_currency = currencies.normalise(to_currency)
        if from_currency == to_currency:
            return 1.0

        rates = self.latest_rates()
        direct = rates.get((from_currency, to_currency))
        if direct:
            return float(direct)

        inverse = rates.get((to_currency, from_currency))
        if inverse:
            return round(1 / float(inverse), 8)

        # One hop through any other currency we do have rates for.
        for pivot in currencies.CODES:
            if pivot in (from_currency, to_currency):
                continue
            first = rates.get((from_currency, pivot))
            second = rates.get((pivot, to_currency))
            if first and second:
                return float(first) * float(second)
        return None

    def convert(self, amount, from_currency, to_currency):
        """Amount expressed in to_currency, or None when no rate is known."""
        rate = self.rate(from_currency, to_currency)
        if rate is None:
            return None
        return round(float(amount) * rate, 2)

    def process_exchange_rate_entry(self, data):
        base, quote, rate, date = data
        base = currencies.normalise(base)
        quote = currencies.normalise(quote)

        if base == quote:
            return "Pick two different currencies."
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            return "Rate must be a number."
        if rate <= 0:
            return "Rate must be greater than zero."

        self.mapper.upsert_exchange_rate((base, quote, rate, date))
        self._rate_cache = None
        return f"Saved 1 {base} = {rate:g} {quote} as of {date}."

    def delete_exchange_rate(self, rate_id):
        self.mapper.delete_exchange_rate(rate_id)
        self._rate_cache = None
        return "Exchange rate removed."

    def rate_lookup_table(self):
        """Rates for every supported pair, for the transfer form to read."""
        table = {}
        for base, quote in currencies.pairs():
            rate = self.rate(base, quote)
            if rate is not None:
                table[f"{base}>{quote}"] = rate
        return table

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def process_account_entry(self, data):
        name, currency = data
        name = (name or "").strip()
        if not name:
            return "Account name is required."

        # Transactions are tied to an account by name, so two accounts sharing
        # one name would pool their balances - and their currencies with them.
        existing = {row[1].lower() for row in self.mapper.select_accounts()}
        if name.lower() in existing:
            return f"An account named {name} already exists. Pick another name."

        currency = currencies.normalise(currency)
        self.mapper.insert_to_bankers((name, currency))
        return f"Added {name} in {currencies.label(currency)}."

    def get_account_currency(self, account_name):
        return currencies.normalise(self.mapper.select_account_currency(account_name))

    def get_accounts(self):
        """Every account with its own currency and balance in that currency."""
        income_totals = self.mapper.select_income_totals()
        expense_totals = self.mapper.select_expense_totals()

        accounts = []
        for _id, account_name, currency in self.mapper.select_accounts():
            currency = currencies.normalise(currency)
            balance = round(
                income_totals.get(account_name, 0.0)
                - expense_totals.get(account_name, 0.0),
                2,
            )
            accounts.append(
                {
                    "name": account_name,
                    "currency": currency,
                    "symbol": currencies.symbol(currency),
                    "balance": balance,
                }
            )
        return accounts

    def get_account_summary(self, display_currency=None):
        """Accounts, per currency subtotals and a converted grand total."""
        display_currency = currencies.normalise(
            display_currency or self.get_display_currency()
        )

        accounts = self.get_accounts()
        totals_by_currency = {}
        total_balance = 0.0
        missing_rates = []

        for account in accounts:
            currency = account["currency"]
            totals_by_currency[currency] = round(
                totals_by_currency.get(currency, 0.0) + account["balance"], 2
            )
            converted = self.convert(account["balance"], currency, display_currency)
            if converted is None:
                if currency not in missing_rates:
                    missing_rates.append(currency)
            else:
                total_balance = round(total_balance + converted, 2)

        return {
            "accounts": accounts,
            "totals_by_currency": totals_by_currency,
            "total_balance": total_balance,
            "display_currency": display_currency,
            "missing_rates": missing_rates,
        }

    def get_all_accounts(self):
        """Backwards compatible view: parallel lists of names and balances."""
        accounts = self.get_accounts()
        return (
            [account["name"] for account in accounts],
            [account["balance"] for account in accounts],
        )

    def delete_all_entries(self):
        self.mapper.delete_all_entries()
        return "All accounts and transactions deleted."

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    def process_debt_entry(self, data):
        name, amount, description, currency = data
        name = (name or "").strip()
        if not name:
            return "Debt name is required."
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return "Amount must be a number."
        if amount <= 0:
            return "Amount must be greater than zero."

        currency = currencies.normalise(currency)
        self.mapper.insert_to_debts((name, amount, description, currency))
        return f"Added debt {name} of {currencies.format_amount(amount, currency)}."

    def get_debts(self):
        """Each debt with what has been paid, what is left, and its status."""
        paid_totals = self.mapper.select_debt_paid_totals()

        debts = []
        for row in self.mapper.select_debts():
            debt_id = row[0]
            currency = currencies.normalise(row[4])
            try:
                original = float(row[2])
            except (TypeError, ValueError):
                original = 0.0
            paid = round(paid_totals.get(debt_id, 0.0), 2)
            outstanding = round(original - paid, 2)
            debts.append(
                {
                    "id": debt_id,
                    "name": row[1],
                    "amount": original,
                    "description": row[3],
                    "currency": currency,
                    "paid": paid,
                    "outstanding": outstanding,
                    # A rounded zero is settled: a debt paid to the cent should
                    # not stay open on a floating point remainder.
                    "status": "closed" if outstanding <= 0 else "open",
                }
            )
        return debts

    def get_debt_payments(self):
        payments = {}
        for row in self.mapper.select_debt_payments():
            payments.setdefault(row[1], []).append(
                {
                    "id": row[0],
                    "amount": row[2],
                    "currency": currencies.normalise(row[3]),
                    "date": row[4],
                    "from_account": row[5] or "",
                }
            )
        return payments

    def get_debt_summary(self):
        """Outstanding totals per currency, plus open/closed counts."""
        debts = self.get_debts()
        outstanding_by_currency = {}
        open_count = 0
        for debt in debts:
            if debt["status"] == "open":
                open_count += 1
                outstanding_by_currency[debt["currency"]] = round(
                    outstanding_by_currency.get(debt["currency"], 0.0)
                    + debt["outstanding"],
                    2,
                )
        return {
            "debts": debts,
            "payments": self.get_debt_payments(),
            "outstanding_by_currency": outstanding_by_currency,
            "open_count": open_count,
            "closed_count": len(debts) - open_count,
        }

    def process_debt_payment(self, data):
        """Record a payment against a debt, optionally spending from an account."""
        debt_id, amount, date, from_account = data

        row = self.mapper.select_debt(debt_id)
        if not row:
            return "That debt no longer exists."

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return "Payment amount must be a number."
        if amount <= 0:
            return "Payment amount must be greater than zero."

        debt = next((d for d in self.get_debts() if d["id"] == row[0]), None)
        currency = debt["currency"]
        if debt["status"] == "closed":
            return f"{debt['name']} is already closed."
        if amount > debt["outstanding"]:
            return (
                f"That is more than the {currencies.format_amount(debt['outstanding'], currency)}"
                f" still owed on {debt['name']}."
            )

        from_account = (from_account or "").strip()
        if from_account:
            account_currency = self.get_account_currency(from_account)
            spent = self.convert(amount, currency, account_currency)
            if spent is None:
                return (
                    f"No exchange rate for {currency} to {account_currency}."
                    " Add one under Exchange Rates, or record the payment without"
                    " an account."
                )
            self.mapper.insert_to_expense(
                (spent, from_account, "💳Debt Payment", date, account_currency, "direct")
            )

        self.mapper.insert_debt_payment(
            (debt["id"], amount, currency, date, from_account)
        )

        left = round(debt["outstanding"] - amount, 2)
        paid_from = f" from {from_account}" if from_account else ""
        if left <= 0:
            return (
                f"Paid {currencies.format_amount(amount, currency)}{paid_from}."
                f" {debt['name']} is now closed."
            )
        return (
            f"Paid {currencies.format_amount(amount, currency)}{paid_from}."
            f" {currencies.format_amount(left, currency)} still owed on {debt['name']}."
        )

    def process_expense_transaction(self, data):
        amount, from_account, category, date = data
        currency = self.get_account_currency(from_account)
        self.mapper.insert_to_expense(
            (amount, from_account, category, date, currency, "direct")
        )
        return (
            f"Recorded expense of {currencies.format_amount(amount, currency)}"
            f" from {from_account}."
        )

    def process_income_transaction(self, data):
        amount, to_account, category, date = data
        currency = self.get_account_currency(to_account)
        self.mapper.insert_to_income(
            (amount, to_account, category, date, currency, "direct")
        )
        return (
            f"Recorded income of {currencies.format_amount(amount, currency)}"
            f" to {to_account}."
        )

    def process_transfer_transaction(self, data):
        amount, from_account, to_account, category, date, rate = data

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return "Amount must be a number."

        from_currency = self.get_account_currency(from_account)
        to_currency = self.get_account_currency(to_account)

        if from_currency == to_currency:
            rate = 1.0
        else:
            rate = self._transfer_rate(rate, from_currency, to_currency)
            if rate is None:
                return (
                    f"No exchange rate for {from_currency} to {to_currency}."
                    " Add one under Exchange Rates, or type a rate on this form."
                )

        to_amount = round(amount * rate, 2)
        self.mapper.insert_to_transfer(
            (
                amount,
                from_account,
                to_account,
                category,
                date,
                from_currency,
                to_amount,
                to_currency,
                rate,
            )
        )
        return (
            f"Transferred {currencies.format_amount(amount, from_currency)}"
            f" to {currencies.format_amount(to_amount, to_currency)}"
            f" at 1 {from_currency} = {rate:g} {to_currency}."
        )

    def _transfer_rate(self, rate, from_currency, to_currency):
        """A rate typed on the transfer form wins over the stored rate."""
        if rate not in (None, ""):
            try:
                rate = float(rate)
            except (TypeError, ValueError):
                rate = None
            if rate and rate > 0:
                return rate
        return self.rate(from_currency, to_currency)

    def select_all__transaction_items(self):
        expenses, income, transfer = self.mapper.select_all__transaction_items()

        expense_items = [
            {
                "id": row[0],
                "amount": row[1],
                "account": row[2],
                "category": row[3],
                "date": row[4],
                "currency": currencies.normalise(row[5]),
            }
            for row in expenses
        ]
        income_items = [
            {
                "id": row[0],
                "amount": row[1],
                "account": row[2],
                "category": row[3],
                "date": row[4],
                "currency": currencies.normalise(row[5]),
            }
            for row in income
        ]
        transfer_items = [
            {
                "id": row[0],
                "amount": row[1],
                "from_account": row[2],
                "to_account": row[3],
                "category": row[4],
                "date": row[5],
                "currency": currencies.normalise(row[6]),
                "to_amount": row[7] if row[7] is not None else row[1],
                "to_currency": currencies.normalise(row[8]),
                "rate": row[9],
            }
            for row in transfer
        ]
        return expense_items, income_items, transfer_items

    def income_expense_trend(self, display_currency=None):
        """Daily income and expense totals, converted into one currency.

        Internal transfers are left out - moving money between your own
        accounts is neither earning nor spending.
        """
        display_currency = currencies.normalise(
            display_currency or self.get_display_currency()
        )

        buckets = {}
        unconverted = []
        sources = (
            ("income", self.mapper.select_income_by_date()),
            ("expense", self.mapper.select_expense_by_date()),
        )
        for series, rows in sources:
            for date, currency, total in rows:
                if not date:
                    continue
                currency = currencies.normalise(currency)
                converted = self.convert(total or 0.0, currency, display_currency)
                if converted is None:
                    if currency not in unconverted:
                        unconverted.append(currency)
                    continue
                bucket = buckets.setdefault(date, {"income": 0.0, "expense": 0.0})
                bucket[series] = round(bucket[series] + converted, 2)

        points = [
            {"date": date, "income": totals["income"], "expense": totals["expense"]}
            for date, totals in sorted(buckets.items())
        ]
        return {
            "points": points,
            "currency": display_currency,
            "symbol": currencies.symbol(display_currency),
            "unconverted": unconverted,
        }

    def total_income_expenses(self, display_currency=None):
        """Income, expense and net totals converted into one currency."""
        trend = self.income_expense_trend(display_currency)
        income_total = round(sum(point["income"] for point in trend["points"]), 2)
        expense_total = round(sum(point["expense"] for point in trend["points"]), 2)
        return {
            "Expenses": expense_total,
            "Income": income_total,
            "Balance": round(income_total - expense_total, 2),
            "Currency": trend["currency"],
        }
