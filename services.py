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
