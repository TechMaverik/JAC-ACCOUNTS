from handlers import Handlers
from menus import categories, banks
from flask import Flask, render_template, request


app = Flask(__name__)


@app.route("/")
def dashboard():
    Handlers().create_tables()
    account_details = Handlers().fetch_all_accounts()
    current_balance = 0
    for balance in account_details:
        current_balance = current_balance + float(balance[2])

    return render_template(
        "dashboard.html",
        accounts=account_details,
        current_balance=current_balance,
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
    return render_template(
        "add_transaction_expense.html", categories=categories, banks=banks
    )


@app.route("/transaction/income")
def add_transaction_income():
    return render_template(
        "add_transaction_income.html", categories=categories, banks=banks
    )


@app.route("/transaction/transfer")
def add_transaction_transfer():
    return render_template(
        "add_transaction_transfer.html", categories=categories, banks=banks
    )


@app.route("/settings")
def settings():
    return render_template("settings.html")


@app.route("/settings/delete", methods=["GET", "POST"])
def settings_delete():
    status = Handlers().delete_all_entries()
    account_details = Handlers().fetch_all_accounts()
    current_balance = 0
    for balance in account_details:
        current_balance = current_balance + float(balance[2])

    print(status)

    return render_template(
        "dashboard.html",
        status=status,
        current_balance=current_balance,
        accounts=account_details,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=2025, debug=True)
