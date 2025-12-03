import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import os

# Load the CSV file
df = pd.read_csv(r"exported_documents\expense.csv")

# Data cleaning and validation (COMPLETE SECTION)
print("=== DATA VALIDATION ===")
print("Raw data shape:", df.shape)
print("Columns:", list(df.columns))
print("\nFirst 5 rows:")
print(df.head())

# Convert columns FIRST (before creating df_clean)
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

# Remove invalid rows (NOW df_clean is defined)
df_clean = df.dropna(subset=["date", "amount"])
print(f"\nClean data shape: {df_clean.shape}")

if df_clean.empty:
    print("ERROR: No valid data after cleaning!")
    exit()

# === LINE GRAPH 1: DAILY EXPENSES ===
plt.figure(figsize=(14, 8))
daily_expenses = df_clean.groupby("date")["amount"].sum()
daily_expenses.plot(kind="line", marker="o", linewidth=2, markersize=4, color="blue")
plt.title("Daily Expenses Trend", fontsize=16, fontweight="bold")
plt.xlabel("Date")
plt.ylabel("Daily Amount (₹)")
plt.xticks(rotation=45)
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("visualization/daily_expenses.png", dpi=300, bbox_inches="tight")
plt.show()

# === LINE GRAPH 2: MONTHLY TREND ===
plt.figure(figsize=(12, 7))
df_clean["month"] = df_clean["date"].dt.to_period("M")
monthly = df_clean.groupby("month")["amount"].sum()
monthly.plot(kind="line", marker="o", linewidth=3, markersize=10, color="green")
plt.title("Monthly Expenses Trend", fontsize=16, fontweight="bold")
plt.xlabel("Month")
plt.ylabel("Total Amount (₹)")
plt.xticks(rotation=45)
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("visualization/monthly_trend.png", dpi=300, bbox_inches="tight")
plt.show()

print("\n✅ Line graphs saved!")
print(f"Total expenses: ₹{df_clean['amount'].sum():,.2f}")
