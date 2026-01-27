from flask import request
from services import Service


class Handlers:

    def __init__(self):
        self.service = Service()

    def create_tables(self):
        self.service.create_tables()

    def handle_account_entry(self):       
        name = request.form.get("name")
        data = (name,)
        response = self.service.process_account_entry(data)
        return response

    def delete_all_entries(self):
        response = self.service.delete_all_entries()
        return response

    def fetch_all_accounts(self):
        bank_name, bank_balance = self.service.get_all_accounts()
        return bank_name, bank_balance

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
        data = (amount, from_account, to_account, category, date)
        response = self.service.process_transfer_transaction(data)
        return response

    def total_income_expenses(self):
        data = Service().total_income_expenses()
        return data

    def fetch_all_transaction_items(self):
        expenses, income, transfer = self.service.select_all__transaction_items()
        return expenses, income, transfer
