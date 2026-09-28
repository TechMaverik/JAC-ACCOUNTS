from datetime import date as date_module

from flask import Flask, jsonify, redirect, render_template, request

from handlers import Handlers
from menus import categories, currencies

app = Flask(__name__)

app.jinja_env.filters["money"] = currencies.format_amount
app.jinja_env.globals["currencies"] = currencies


def sidebar_context(handlers):
    """Balances shown on every page, each account in its own currency."""
    summary = handlers.fetch_account_summary()
    return {
        "accounts": summary["accounts"],
        "account_details": {
            account["name"]: account["balance"] for account in summary["accounts"]
        },
        "totals_by_currency": summary["totals_by_currency"],
        "total_balance": summary["total_balance"],
        "display_currency": summary["display_currency"],
        "missing_rates": summary["missing_rates"],
        "rates": handlers.fetch_rate_lookup_table(),
    }


def transaction_form_context(handlers):
    """Everything the add-transaction forms need to show the right currency."""
    accounts = handlers.fetch_accounts()
    return {
        "accounts": accounts,
        "account_details": [account["name"] for account in accounts],
        "account_currencies": {
            account["name"]: {
                "code": account["currency"],
                "symbol": account["symbol"],
            }
            for account in accounts
        },
        "rates": handlers.fetch_rate_lookup_table(),
        "categories": categories,
        "display_currency": handlers.fetch_display_currency(),
        "today": date_module.today().isoformat(),
    }


@app.route("/")
def dashboard():
    handlers = Handlers()
    expensesitems, incomeitems, transferitems = handlers.fetch_all_transaction_items()
    return render_template(
        "dashboard.html",
        expensesitems=expensesitems,
        incomeitems=incomeitems,
        transferitems=transferitems,
        trend=handlers.fetch_income_expense_trend(),
        totals=handlers.total_income_expenses(),
        **sidebar_context(handlers),
    )


@app.route("/expenses")
def expenses():
    handlers = Handlers()
    expensesitems, incomeitems, transferitems = handlers.fetch_all_transaction_items()
    return render_template(
        "all_expense.html",
        expensesitems=expensesitems,
        **sidebar_context(handlers),
    )


@app.route("/incomes")
def incomes():
    handlers = Handlers()
    expensesitems, incomeitems, transferitems = handlers.fetch_all_transaction_items()
    return render_template(
        "all_income.html",
        incomeitems=incomeitems,
        **sidebar_context(handlers),
    )


@app.route("/transfers")
def transfers():
    handlers = Handlers()
    expensesitems, incomeitems, transferitems = handlers.fetch_all_transaction_items()
    return render_template(
        "all_transfers.html",
        transferitems=transferitems,
        **sidebar_context(handlers),
    )


@app.route("/account")
def add_account():
    handlers = Handlers()
    return render_template(
        "add_account.html",
        default_currency=handlers.fetch_display_currency(),
    )


@app.route("/account/entry", methods=["GET", "POST"])
def account_entry():
    handlers = Handlers()
    response = handlers.handle_account_entry()
    return render_template(
        "add_account.html",
        status=response,
        default_currency=handlers.fetch_display_currency(),
    )


def debt_page(handlers, status=None):
    summary = handlers.fetch_debt_summary()
    return render_template(
        "debt.html",
        status=status,
        debts=summary["debts"],
        payments=summary["payments"],
        outstanding_by_currency=summary["outstanding_by_currency"],
        open_count=summary["open_count"],
        closed_count=summary["closed_count"],
        today=date_module.today().isoformat(),
        **sidebar_context(handlers),
    )


@app.route("/debt")
def debts():
    return debt_page(Handlers())


@app.route("/debt/entry", methods=["GET", "POST"])
def debt_entry():
    handlers = Handlers()
    return debt_page(handlers, handlers.handle_debt_entry())


@app.route("/debt/pay", methods=["POST"])
def debt_pay():
    handlers = Handlers()
    return debt_page(handlers, handlers.handle_debt_payment())


# The section used to be called Liabilities; keep old links working.
@app.route("/liability")
def add_liability():
    return redirect("/debt")


@app.route("/liability/entry", methods=["GET", "POST"])
def liability_entry():
    return redirect("/debt")


@app.route("/transaction/expense")
def add_transaction():
    handlers = Handlers()
    return render_template(
        "add_transaction_expense.html",
        **transaction_form_context(handlers),
    )


@app.route("/transaction/expense/entry", methods=["GET", "POST"])
def transaction_expense_entry():
    handlers = Handlers()
    status = handlers.handle_expense_transaction()
    return render_template(
        "add_transaction_expense.html",
        status=status,
        **transaction_form_context(handlers),
    )


@app.route("/transaction/income")
def add_transaction_income():
    handlers = Handlers()
    return render_template(
        "add_transaction_income.html",
        **transaction_form_context(handlers),
    )


@app.route("/transaction/income/entry", methods=["GET", "POST"])
def transaction_income_entry():
    handlers = Handlers()
    status = handlers.handle_income_transaction()
    return render_template(
        "add_transaction_income.html",
        status=status,
        **transaction_form_context(handlers),
    )


@app.route("/transaction/transfer")
def add_transaction_transfer():
    handlers = Handlers()
    return render_template(
        "add_transaction_transfer.html",
        **transaction_form_context(handlers),
    )


@app.route("/transaction/transfer/entry", methods=["GET", "POST"])
def transaction_transfer_entry():
    handlers = Handlers()
    status = handlers.handle_transfer_transaction()
    return render_template(
        "add_transaction_transfer.html",
        status=status,
        **transaction_form_context(handlers),
    )


@app.route("/exchange")
def exchange_rates():
    handlers = Handlers()
    return render_template(
        "exchange_rates.html",
        exchange_rates=handlers.fetch_exchange_rates(),
        today=date_module.today().isoformat(),
        **sidebar_context(handlers),
    )


@app.route("/exchange/entry", methods=["POST"])
def exchange_rate_entry():
    handlers = Handlers()
    status = handlers.handle_exchange_rate_entry()
    return render_template(
        "exchange_rates.html",
        status=status,
        exchange_rates=handlers.fetch_exchange_rates(),
        today=date_module.today().isoformat(),
        **sidebar_context(handlers),
    )


@app.route("/exchange/delete", methods=["POST"])
def exchange_rate_delete():
    handlers = Handlers()
    status = handlers.handle_exchange_rate_delete()
    return render_template(
        "exchange_rates.html",
        status=status,
        exchange_rates=handlers.fetch_exchange_rates(),
        today=date_module.today().isoformat(),
        **sidebar_context(handlers),
    )


@app.route("/settings/display-currency", methods=["POST"])
def settings_display_currency():
    Handlers().handle_display_currency()
    destination = request.form.get("next") or "/"
    if not destination.startswith("/"):
        destination = "/"
    return redirect(destination)


@app.route("/settings")
def settings():
    handlers = Handlers()
    return render_template(
        "settings.html",
        display_currency=handlers.fetch_display_currency(),
        rates=handlers.fetch_rate_lookup_table(),
    )


@app.route("/settings/delete", methods=["GET", "POST"])
def settings_delete():
    handlers = Handlers()
    status = handlers.delete_all_entries()
    return render_template(
        "settings.html",
        status=status,
        display_currency=handlers.fetch_display_currency(),
        rates=handlers.fetch_rate_lookup_table(),
    )


@app.route("/babayo/ask", methods=["POST"])
def babayo_ask():
    """Chat endpoint for Babayo, the dashboard chatbot. Expects JSON {"question": ...}."""
    handlers = Handlers()
    response = handlers.handle_babayo_question()
    return jsonify(response), (400 if "error" in response else 200)


@app.route("/babayo/reset", methods=["POST"])
def babayo_reset():
    handlers = Handlers()
    return jsonify(handlers.handle_babayo_reset())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=2026, debug=True)
