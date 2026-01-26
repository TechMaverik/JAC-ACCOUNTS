from handlers import Handlers
from menus import categories
from flask import Flask, render_template, request


app = Flask(__name__)


def account_details_total_balance():
    bank_name, bank_balance = Handlers().fetch_all_accounts()
    total_balance = 0

    for balance in bank_balance:
        total_balance = round(total_balance + float(balance), 2)
    return bank_name, bank_balance, total_balance


@app.route("/")
def dashboard():
    bank_name, bank_balance, total_balance = account_details_total_balance()
    expensesitems, incomeitems, transferitems = Handlers().fetch_all_transaction_items()
    account_details = dict(zip(bank_name, bank_balance))
    return render_template(
        "dashboard.html",
        account_details=account_details,
        total_balance=total_balance,
        expensesitems=expensesitems,
        incomeitems=incomeitems,
        transferitems=transferitems,
    )

@app.route("/expenses")
def expenses():
    bank_name, bank_balance, total_balance = account_details_total_balance()
    expensesitems, incomeitems, transferitems = Handlers().fetch_all_transaction_items()
    account_details = dict(zip(bank_name, bank_balance))
    return render_template(
        "all_expense.html",
        account_details=account_details,
        total_balance=total_balance,
        expensesitems=expensesitems,        
    )

@app.route("/incomes")
def incomes():
    bank_name, bank_balance, total_balance = account_details_total_balance()
    expensesitems, incomeitems, transferitems = Handlers().fetch_all_transaction_items()
    account_details = dict(zip(bank_name, bank_balance))
    return render_template(
        "all_income.html",
        account_details=account_details,
        total_balance=total_balance,       
        incomeitems=incomeitems,       
    )

@app.route("/transfers")
def transfers():
    bank_name, bank_balance, total_balance = account_details_total_balance()
    expensesitems, incomeitems, transferitems = Handlers().fetch_all_transaction_items()
    account_details = dict(zip(bank_name, bank_balance))
    return render_template(
        "all_transfers.html",
        account_details=account_details,
        total_balance=total_balance,        
        transferitems=transferitems,
    )


@app.route("/account")
def add_account():
    return render_template("add_account.html")


@app.route("/account/entry", methods=["GET", "POST"])
def account_entry():
    response = Handlers().handle_account_entry()
    return render_template("add_account.html", status=response)


@app.route("/transaction/expense")
def add_transaction():
    bank_name, bank_balance, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_expense.html",
        account_details=bank_name,
        categories=categories,
        total_balance=total_balance,
    )


@app.route("/transaction/expense/entry", methods=["GET", "POST"])
def transaction_expense_entry():
    status = Handlers().handle_expense_transaction()
    bank_name, bank_balance, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_expense.html",
        account_details=bank_name,
        categories=categories,
        total_balance=total_balance,
    )


@app.route("/transaction/income")
def add_transaction_income():
    bank_name, bank_balance, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_income.html",
        categories=categories,
        account_details=bank_name,
        total_balance=total_balance,
    )


@app.route("/transaction/income/entry", methods=["GET", "POST"])
def transaction_income_entry():
    status = Handlers().handle_income_transaction()
    bank_name, bank_balance, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_income.html",
        categories=categories,
        account_details=bank_name,
        total_balance=total_balance,
    )


@app.route("/transaction/transfer")
def add_transaction_transfer():
    bank_name, bank_balance, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_transfer.html",
        categories=categories,
        account_details=bank_name,
        total_balance=total_balance,
    )


@app.route("/transaction/transfer/entry", methods=["GET", "POST"])
def transaction_transfer_entry():
    status = Handlers().handle_transfer_transaction()
    bank_name, bank_balance, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_transfer.html",
        categories=categories,
        account_details=bank_name,
        total_balance=total_balance,
    )


@app.route("/settings")
def settings():
    return render_template("settings.html")


@app.route("/settings/delete", methods=["GET", "POST"])
def settings_delete():
    Handlers().delete_all_entries()
    return render_template("settings.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=2025, debug=True)
