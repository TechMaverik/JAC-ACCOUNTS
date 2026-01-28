from mappers import Mapper


class Service:

    def __init__(self):
        self.mapper = Mapper()
        self.mapper.create_tables()

    def create_tables(self):
        self.mapper.create_tables()

    def process_liability_entry(self, data):
        status = self.mapper.insert_to_liabilities(data)
        return status

    def process_account_entry(self, data):
        status = self.mapper.insert_to_bankers(data)
        return status

    def get_all_accounts(self):
        bank_name, bank_balance = self.mapper.select_accounts()
        return bank_name, bank_balance

    def delete_all_entries(self):
        status = self.mapper.delete_all_entries()
        return status

    def process_expense_transaction(self, data):
        status = self.mapper.insert_to_expense(data)
        return status

    def process_income_transaction(self, data):
        status = self.mapper.insert_to_income(data)
        return status

    def process_transfer_transaction(self, data):
        status = self.mapper.insert_to_transfer(data)
        return status

    def total_income_expenses(self):

        try:

            accounts = self.get_all_accounts()
            expenserows, incomerows, transferrows = Mapper().select_all_transactions()
            expenses = []
            income = []
            for account in accounts:
                for row in expenserows:
                    if row[2] == account[1]:
                        expenses.append(row[1])
                for row in incomerows:
                    if row[2] == account[1]:
                        income.append(row[1])
            return {
                "Expenses": sum([int(x) for x in expenses]),
                "Income": sum([int(x) for x in income]),
                "Balance": sum([int(x) for x in income])
                - sum([int(x) for x in expenses]),
            }
        except:
            return {
                "Expenses": 0,
                "Income": 0,
                "Balance": 0,
            }

    def select_all__transaction_items(self):
        expenses, income, transfer = self.mapper.select_all__transaction_items()
        return expenses, income, transfer
