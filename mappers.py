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
