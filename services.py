from mappers import Mapper


class Service:

    def __init__(self):
        self.mapper = Mapper()
        self.mapper.create_tables()

    def process_account_entry(self, data):
        pass

    def process_transaction_entry(self, data):
        pass
