from mappers import Mapper


class Service:

    def __init__(self):
        self.mapper = Mapper()
        self.mapper.create_tables()

    def create_tables(self):
        self.mapper.create_tables()

    def process_account_entry(self, data):
        print(data)
        status = self.mapper.insert_to_bankers(data)
        return status

    def get_all_accounts(self):
        accounts = self.mapper.select_accounts()
        return accounts

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

    def check_balance_after_transaction(self):
        transaction_history_list = []
        balance_list = []

        accounts = self.get_all_accounts()
        expenserows, incomerows, transferrows = Mapper().select_all_transactions()

        for account in accounts:
            transaction = 0.0

            for row in expenserows:
                if row[2] == account[1]:
                    transaction += float(row[1]) * -1

            for row in incomerows:
                if row[2] == account[1]:
                    transaction += float(row[1]) * 1

            balance = float(account[2]) - transaction
            transaction_history_list.append(transaction)
            balance_list.append(balance)

        return balance_list, transaction_history_list


data = Service().check_balance_after_transaction()
print(data)
