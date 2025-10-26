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
