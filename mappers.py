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
            self.conn.close()
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

        self.cursor.execute(
            'INSERT INTO transfer (amount, "from", "to", category, date) VALUES (?, ?, ?, ?, ?)',
            data,
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
        self.cursor.execute("DELETE FROM investment")
        self.conn.commit()
        self.conn.close()
        return True
