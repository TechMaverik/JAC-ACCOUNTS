"""Export every JAC Accounts collection from MongoDB to one CSV file each.

Run from the project root so the .env settings are found:

    python tools/excel_converter.py
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import mongo  # noqa: E402 - needs the project root on sys.path


def mongo_to_csv(output_folder="exported_documents"):
    os.makedirs(output_folder, exist_ok=True)
    db = mongo.get_db()

    for name in mongo.DATA_COLLECTIONS:
        documents = list(db[name].find({}, {"_id": 0}).sort("id", 1))
        columns = list(mongo.FIELDS.get(name, {}))
        df = pd.DataFrame(documents, columns=columns or None)

        csv_path = os.path.join(output_folder, f"{name}.csv")
        df.to_csv(csv_path, index=False)
        print(f"Written collection '{name}' ({len(df)} rows) to: {csv_path}")

    print("\nAll collections exported successfully.")


if __name__ == "__main__":
    mongo_to_csv()
