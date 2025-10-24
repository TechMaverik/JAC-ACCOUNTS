from menus import categories, banks
from flask import Flask, render_template, request


app = Flask(__name__)


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/account")
def add_account():
    return render_template("add_account.html")


@app.route("/account/entry", methods=["POST"])
def account_entry():
    return render_template("add_account.html")


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=2025, debug=True)
