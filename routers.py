from handlers import Handlers
from menus import categories
from flask import Flask, render_template, request


app = Flask(__name__)


def account_details_total_balance():
    account_details = Handlers().fetch_all_accounts()
    total_balance = 0
    for balance in account_details:
        total_balance = total_balance + float(balance[2])
    return account_details, total_balance


@app.route("/")
def dashboard():
    account_details, total_balance = account_details_total_balance()
    total_balance = Handlers().total_income_expenses()
    return render_template(
        "dashboard.html",
        accounts=account_details,
        total_balance=total_balance["Balance"],
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
    account_details, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_expense.html",
        account_details=account_details,
        categories=categories,
        total_balance=total_balance,
    )


@app.route("/transaction/expense/entry", methods=["GET", "POST"])
def transaction_expense_entry():
    status = Handlers().handle_expense_transaction()
    account_details, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_expense.html",
        account_details=account_details,
        categories=categories,
        total_balance=total_balance,
    )


@app.route("/transaction/income")
def add_transaction_income():
    account_details, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_income.html",
        categories=categories,
        account_details=account_details,
        total_balance=total_balance,
    )


@app.route("/transaction/income/entry", methods=["GET", "POST"])
def transaction_income_entry():
    status = Handlers().handle_income_transaction()
    account_details, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_income.html",
        categories=categories,
        account_details=account_details,
        total_balance=total_balance,
    )


@app.route("/transaction/transfer")
def add_transaction_transfer():
    account_details, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_transfer.html",
        categories=categories,
        account_details=account_details,
        total_balance=total_balance,
    )


@app.route("/transaction/transfer/entry", methods=["GET", "POST"])
def transaction_transfer_entry():
    status = Handlers().handle_transfer_transaction()
    account_details, total_balance = account_details_total_balance()
    return render_template(
        "add_transaction_transfer.html",
        categories=categories,
        account_details=account_details,
        total_balance=total_balance,
    )


@app.route("/settings")
def settings():
    return render_template("settings.html")


@app.route("/settings/delete", methods=["GET", "POST"])
def settings_delete():
    status = Handlers().delete_all_entries()
    account_details, total_balance = account_details_total_balance()
    return render_template(
        "dashboard.html",
        status=status,
        total_balance=total_balance,
        accounts=account_details,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=2025, debug=True)
