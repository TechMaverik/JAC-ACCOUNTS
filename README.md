# JAC-Accounts

Personal accounts dashboard (Flask) with Babayo, a chatbot that answers
questions about your data through Ollama.

## Setup

1. Create a virtualenv and install the dependencies:

       python3 -m venv .venv
       .venv/bin/pip install -r requirements.txt

2. Put the MongoDB settings in a `.env` file in the project root:

       MONGOHOST=localhost
       MONGOPORT=27017
       MONGOUSER=developer
       MONGOPASSWORD=secret
       MONGOAUTH=admin
       # optional, defaults to jac_accounts
       MONGODATABASE=jac_accounts

3. Start the app with `./launcher.sh` (or `launcher.bat` on Windows) and
   open http://localhost:2026.

The collections and indexes are created on first use, so a fresh database
needs no extra setup. Documents keep an integer `id` like the SQLite rows the
data was first exported from; `tools/excel_converter.py` writes every
collection to CSV.
