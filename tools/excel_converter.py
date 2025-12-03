import sqlite3
import pandas as pd
import os


def sqlite_to_csv(sqlite_file, output_folder="exported_documents"):
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Connect to SQLite database
    conn = sqlite3.connect(sqlite_file)

    # Get all table names using SQLite metadata (correct approach)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    for (table_name,) in tables:
        # Skip system tables if needed
        if table_name.startswith("sqlite_"):
            continue

        # Read table into DataFrame
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

        # Build CSV file path
        csv_path = os.path.join(output_folder, f"{table_name}.csv")

        # Write to CSV
        df.to_csv(csv_path, index=False)
        print(f"Written table '{table_name}' to: {csv_path}")

    conn.close()
    print("\nAll tables exported successfully.")


# Usage example (fix Windows path separator)
sqlite_to_csv(r"database\jac_accounts.db")
