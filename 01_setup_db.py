import sqlite3
import os

def setup_database():
    db_path = 'data/company_finance.db'

    # Ensure data directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Connect to database (creates it if it doesn't exist)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Create products table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        product_id TEXT PRIMARY KEY,
        product_name TEXT,
        unit_cost REAL
    )
    """)

    # Create clean_sales table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clean_sales (
        sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_date TEXT NOT NULL,
        product_id TEXT NOT NULL,
        units_sold INTEGER NOT NULL,
        sale_price REAL NOT NULL,
        FOREIGN KEY(product_id) REFERENCES products(product_id)
    )
    """)

    conn.commit()
    conn.close()

    print(f"Database setup complete at {db_path}")

if __name__ == "__main__":
    setup_database()
