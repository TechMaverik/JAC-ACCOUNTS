from flask import request
from services import Service


class Handlers:

    def __init__(self):
        self.service = Service()

    def handle_account_entry(self):
        pass

    def handle_transaction_entry(self):
        pass
