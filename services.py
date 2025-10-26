from mappers import Mapper


class Service:

    def __init__(self):
        self.mapper = Mapper()
        self.mapper.create_tables()

    def create_tables(self):
        self.mapper.create_tables()

    def process_account_entry(self, data):
        print(data)
        return True

    def process_transaction_entry(self, data):
        pass
