import sqlite3
from database import query_collection


class Mapper:

    def __init__(self):

        self.conn = sqlite3.connect(query_collection.DB_LOC)
        self.cursor = self.conn.cursor()

    def create_tables(self):
        try:

            self.cursor.execute(query_collection.CREATE_BANKERS)
            self.cursor.execute(query_collection.CREATE_EXPENSE)
            self.cursor.execute(query_collection.CREATE_INCOME)
            self.cursor.execute(query_collection.CREATE_TRANSFER)
            self.cursor.execute(query_collection.CREATE_INVESTMENT)
            self.conn.commit()

        except:
            pass

    def insert_to_bankers(self, data):

        self.cursor.execute(
            "INSERT INTO banker (account_name, balance) VALUES (?, ?)",
            data,
        )
        self.conn.commit()
        self.conn.close()
        return True

    def insert_to_income(self, data):

        self.cursor.execute(
            'INSERT INTO income (amount, "to", category, date) VALUES (?, ?, ?, ?)',
            data,
        )
        self.conn.commit()
        self.conn.close()
        return True

    def insert_to_expense(self, data):

        self.cursor.execute(
            'INSERT INTO expense (amount, "from", category, date) VALUES (?, ?, ?, ?)',
            data,
        )
        self.conn.commit()
        self.conn.close()
        return True

    def insert_to_transfer(self, data):

        amount = data[0]
        from_account = data[1]
        to_account = data[2]
        category = data[3]
        date = data[4]
        transfer_data_income = (amount, to_account, category, date)
        transfer_data_expense = (amount, from_account, category, date)

        self.cursor.execute(
            'INSERT INTO transfer (amount, "from", "to", category, date) VALUES (?, ?, ?, ?, ?)',
            data,
        )
        self.cursor.execute(
            'INSERT INTO income (amount, "to", category, date) VALUES (?, ?, ?, ?)',
            transfer_data_income,
        )
        self.cursor.execute(
            'INSERT INTO expense (amount, "from", category, date) VALUES (?, ?, ?, ?)',
            transfer_data_expense,
        )
        self.conn.commit()
        self.conn.close()
        return True

    def insert_to_investment(self, data):

        self.cursor.execute(
            'INSERT INTO investment (amount, "from", category, date) VALUES (?, ?, ?, ?)',
            data,
        )
        self.conn.commit()
        self.conn.close()
        return True

    def select_accounts(self):

        self.cursor.execute("SELECT * FROM banker")
        accounts = self.cursor.fetchall()
        self.conn.close()
        return accounts

    def delete_all_entries(self):

        self.cursor.execute("DELETE FROM banker")
        self.cursor.execute("DELETE FROM expense")
        self.cursor.execute("DELETE FROM income")
        self.cursor.execute("DELETE FROM transfer")
        self.conn.commit()
        self.conn.close()
        return True

    def select_all_transactions(self):
        self.cursor.execute("SELECT * FROM expense")
        expenses = self.cursor.fetchall()
        self.cursor.execute("SELECT * FROM income")
        income = self.cursor.fetchall()
        self.cursor.execute("SELECT * FROM transfer")
        transfer = self.cursor.fetchall()
        self.conn.close()
        return expenses, income, transfer

    def select_expense_specific_account(self, account_name):
        self.cursor.execute(
            'SELECT amount FROM expense WHERE "from" = ?', (account_name,)
        )
        expenses = self.cursor.fetchall()
        expenses_list = [int(amount[0]) for amount in expenses]
        self.conn.close()
        return expenses_list

    def select_expense_specific_account(self, account_name):
        self.cursor.execute(
            'SELECT amount FROM expense WHERE "from" = ?', (account_name,)
        )
        expenses = self.cursor.fetchall()
        expenses_list = [int(amount[0]) for amount in expenses]
        self.conn.close()
        return expenses_list

    def select_income_specific_account(self, account_name):
        self.cursor.execute('SELECT amount FROM income WHERE "to" = ?', (account_name,))
        incomes = self.cursor.fetchall()
        income_list = [int(amount[0]) for amount in incomes]
        self.conn.close()
        return income_list


ans = Mapper().select_income_specific_account("TEST Bank 1")
print(ans)
