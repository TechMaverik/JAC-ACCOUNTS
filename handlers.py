from flask import request

from services import Service


class Handlers:

    def __init__(self):
        self.service = Service()

    def create_tables(self):
        self.service.create_tables()

    def handle_debt_entry(self):
        name = request.form.get("name")
        amount = request.form.get("amount")
        description = request.form.get("description")
        currency = request.form.get("currency")
        data = (name, amount, description, currency)
        response = self.service.process_debt_entry(data=data)
        return response

    def handle_debt_payment(self):
        debt_id = request.form.get("debt_id")
        amount = request.form.get("amount")
        date = request.form.get("date")
        from_account = request.form.get("from_account")
        data = (debt_id, amount, date, from_account)
        response = self.service.process_debt_payment(data)
        return response

    def handle_account_entry(self):
        name = request.form.get("name")
        currency = request.form.get("currency")
        data = (name, currency)
        response = self.service.process_account_entry(data)
        return response

    def delete_all_entries(self):
        response = self.service.delete_all_entries()
        return response

    def fetch_all_accounts(self):
        bank_name, bank_balance = self.service.get_all_accounts()
        return bank_name, bank_balance

    def fetch_accounts(self):
        return self.service.get_accounts()

    def fetch_account_summary(self, display_currency=None):
        return self.service.get_account_summary(display_currency)

    def handle_expense_transaction(self):
        amount = request.form.get("amount")
        from_account = request.form.get("from_account")
        category = request.form.get("category")
        date = request.form.get("date")
        data = (amount, from_account, category, date)
        response = self.service.process_expense_transaction(data)
        return response

    def handle_income_transaction(self):
        amount = request.form.get("amount")
        to_account = request.form.get("to_account")
        category = request.form.get("category")
        date = request.form.get("date")
        data = (amount, to_account, category, date)
        response = self.service.process_income_transaction(data)
        return response

    def handle_transfer_transaction(self):
        amount = request.form.get("amount")
        from_account = request.form.get("from_account")
        to_account = request.form.get("to_account")
        category = request.form.get("category")
        date = request.form.get("date")
        rate = request.form.get("rate")
        data = (amount, from_account, to_account, category, date, rate)
        response = self.service.process_transfer_transaction(data)
        return response

    def handle_exchange_rate_entry(self):
        base_currency = request.form.get("base_currency")
        quote_currency = request.form.get("quote_currency")
        rate = request.form.get("rate")
        date = request.form.get("date")
        data = (base_currency, quote_currency, rate, date)
        response = self.service.process_exchange_rate_entry(data)
        return response

    def handle_exchange_rate_delete(self):
        rate_id = request.form.get("rate_id")
        return self.service.delete_exchange_rate(rate_id)

    def handle_display_currency(self):
        currency = request.form.get("display_currency")
        self.service.set_display_currency(currency)
        return f"Display currency set to {currency}."

    def fetch_exchange_rates(self):
        return self.service.get_exchange_rates()

    def fetch_rate_lookup_table(self):
        return self.service.rate_lookup_table()

    def fetch_display_currency(self):
        return self.service.get_display_currency()

    def fetch_debt_summary(self):
        return self.service.get_debt_summary()

    def fetch_income_expense_trend(self, display_currency=None):
        return self.service.income_expense_trend(display_currency)

    def total_income_expenses(self, display_currency=None):
        return self.service.total_income_expenses(display_currency)

    def fetch_all_transaction_items(self):
        expenses, income, transfer = self.service.select_all__transaction_items()
        return expenses, income, transfer

    def handle_babayo_question(self):
        payload = request.get_json(silent=True) or {}
        question = payload.get("question") or request.form.get("question")
        return self.service.process_babayo_question(question)

    def handle_babayo_reset(self):
        return self.service.reset_babayo()
