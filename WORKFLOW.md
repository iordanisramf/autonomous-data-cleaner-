# Financial Data Cleaning Pipeline - Workflow

This document provides a detailed, step-by-step overview of how the data pipeline operates. The system consists of two main scripts: database setup (`01_setup_db.py`) and the data cleaner pipeline (`02_cleaner.py`).

## 1. Database Initialization (`01_setup_db.py`)

Before processing any data, the database schema must be initialized.
- **Action:** Creates an SQLite database locally at `data/company_finance.db`.
- **Tables Created:**
  - `products`: Contains the reference data for all valid products (`product_id`, `product_name`, `unit_cost`).
  - `clean_sales`: The main destination table for valid sales data. It expects columns matched by name (`sale_id` [Auto-increment], `sale_date`, `product_id`, `units_sold`, `sale_price`) and enforces a Foreign Key constraint ensuring every `product_id` entered here exists in the `products` table.

## 2. Data Cleaning Pipeline (`02_cleaner.py`)

This is the main engine of the program. It reads a raw Excel file (`data/raw_sales.xlsx`) and processes it purely in memory before pushing the valid results to the database. It operates in 4 strict stages.

### Stage 1: Header Validation
- **Action:** The system inspects the incoming Excel dataframe columns.
- **Rules:** It explicitly checks for the exact English headers: `product_id`, `sale_date`, `units_sold`, and `sale_price`.
- **Outcome:**
  - If headers are mismatched, in Greek, or completely missing, the system immediately halts the pipeline and throws a `ValueError` (Strict Schema Validation Error).
  - If they match exactly, it extracts the data and proceeds. (Note: column order does not matter; Pandas aligns data by column name).

### Stage 2: Vectorized Cleaning
- **Action:** The dataframe undergoes rapid string and numeric manipulations to normalize the data types.
- **Transformations:**
  - `product_id`: Cast to uppercase string, strips any trailing/leading whitespace. Treats empty strings or "NAN" as missing values (`pd.NA`).
  - `sale_date`: Parses string dates to valid Datetime objects via `pd.to_datetime()`. Failed parses safely convert to `NaT` (Not a Time).
  - `units_sold` & `sale_price`: Uses Regular Expressions (regex) to strip away all currency symbols (e.g., €, $), spaces, and random characters. It allows minus signs, dots, and commas. It then replaces European comma decimals (e.g., `20,00`) with dot notation (`20.00`) and converts the final string into purely numeric/float values.

### Stage 3: Boolean Masking & Isolation
- **Action:** The clean dataframe is rigorously tested against business rules using vectorized boolean conditions (masks).
- **Rules:**
  - `product_id`: Must not be null/empty.
  - `sale_date`: Must be a valid date, and cannot be a future date relative to the system's current date.
  - `units_sold`: Must be a positive number (`> 0`) and strictly an integer (no fractions allowed).
  - `sale_price`: Must be a positive number (`> 0`).
- **Outcome:**
  - The data is split into two separate buckets: `clean_df` (passed all tests) and `rejected_df` (failed one or more tests).
  - The script iterates over the rejected bucket, logging exactly why the row failed into a new column called `rejection_reason`.
  - Finally, the `sale_date` in the valid bucket (`clean_df`) is strictly formatted into the standard ISO format (`YYYY-MM-DD`).

### Stage 4: Database Ingestion
- **Action:** The system connects to `data/company_finance.db` to finalize the process.
- **Foreign Key Graceful Validation:**
  - Before blindly inserting into the database and risking a crash, the pipeline queries the `products` table for all existing valid `product_id`s.
  - It filters `clean_df` one last time. If a row passed all Stage 3 tests but its `product_id` does not exist in the database, it gets flagged.
  - These flagged rows are appended to the `rejected_df` bucket with the reason: *"Foreign key violation: product_id not in products"*.
- **Final Output:**
  - **Quarantine:** All records in `rejected_df` (from Stage 3 and Stage 4) are exported and saved to an Excel file: `data/quarantine.xlsx`. If the file already exists, the new rejected rows are seamlessly appended to it.
  - **Database Insert:** The surviving, pristine records in `clean_df` are inserted into the `clean_sales` SQL table using `pandas.DataFrame.to_sql()`. The dataframe columns map directly to the SQL column names dynamically.
