from flask import request
from services import Service


class Handlers:

    def __init__(self):
        self.service = Service()

    def create_tables(self):
        self.service.create_tables()

    def handle_account_entry(self):
        balance = request.form.get("balance")
        name = request.form.get("name")
        data = (name, balance)
        response = self.service.process_account_entry(data)
        return response

    def delete_all_entries(self):
        response = self.service.delete_all_entries()
        return response

    def fetch_all_accounts(self):
        accounts = self.service.get_all_accounts()
        return accounts

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
