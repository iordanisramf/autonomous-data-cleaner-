import pandas as pd
import sqlite3
import os
import shutil
import logging
import glob
from datetime import datetime

# Setup Logging
os.makedirs('data', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data/pipeline.log'),
        logging.StreamHandler()
    ]
)

# Stage 1: Header Validation
def validate_headers(df):
    required_columns = ['product_id', 'sale_date', 'units_sold', 'sale_price']

    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        raise ValueError(f"Strict Schema Validation Error: Missing required columns: {', '.join(missing_columns)}. "
                         f"Headers must exactly match: {', '.join(required_columns)}")

    return df[required_columns].copy()

# Stage 2: Vectorized Cleaning
def clean_data(df):
    # product_id
    df['product_id'] = df['product_id'].astype(str).str.strip().str.upper()
    df.loc[df['product_id'] == 'NAN', 'product_id'] = pd.NA
    df.loc[df['product_id'] == '<NA>', 'product_id'] = pd.NA
    df.loc[df['product_id'] == '', 'product_id'] = pd.NA

    # sale_date
    df['sale_date'] = pd.to_datetime(df['sale_date'], format='mixed', dayfirst=True, errors='coerce')

    # units_sold
    # Strip non-numeric characters except dots and commas (and minus signs)
    # Check if type is object or string to perform string operations
    if df['units_sold'].dtype == 'object' or pd.api.types.is_string_dtype(df['units_sold']):
        df['units_sold'] = df['units_sold'].astype(str).str.replace(r'[^\d\.\,\-]', '', regex=True)
        df['units_sold'] = df['units_sold'].str.replace(',', '.')
    df['units_sold'] = pd.to_numeric(df['units_sold'], errors='coerce')

    # sale_price
    # Strip currency symbols and non-numeric characters except dots and commas
    if df['sale_price'].dtype == 'object' or pd.api.types.is_string_dtype(df['sale_price']):
        df['sale_price'] = df['sale_price'].astype(str).str.replace(r'[^\d\.\,\-]', '', regex=True)
        df['sale_price'] = df['sale_price'].str.replace(',', '.')
    df['sale_price'] = pd.to_numeric(df['sale_price'], errors='coerce')

    return df

# Stage 3: Boolean Masking & Isolation
def isolate_data(df):
    today = pd.Timestamp.now().normalize()

    mask_product_id = df['product_id'].notna() & (df['product_id'] != '')
    mask_sale_date = df['sale_date'].notna() & (df['sale_date'] <= today)

    # Check if units_sold is not NaN, > 0, and strictly integer
    mask_units_sold = df['units_sold'].notna() & (df['units_sold'] > 0) & (df['units_sold'] == df['units_sold'].apply(lambda x: int(x) if pd.notna(x) else x))

    mask_sale_price = df['sale_price'].notna() & (df['sale_price'] > 0)

    valid_mask = mask_product_id & mask_sale_date & mask_units_sold & mask_sale_price

    clean_df = df[valid_mask].copy()
    rejected_df = df[~valid_mask].copy()

    # Determine rejection reasons
    reasons = []
    for idx, row in rejected_df.iterrows():
        reason_list = []
        if not (pd.notna(row['product_id']) and row['product_id'] != ''):
            reason_list.append("Invalid product_id")
        if not pd.notna(row['sale_date']):
            reason_list.append("Invalid sale_date")
        elif row['sale_date'] > today:
            reason_list.append("Future sale_date")

        if pd.notna(row['units_sold']):
            if row['units_sold'] <= 0:
                reason_list.append("units_sold <= 0")
            elif row['units_sold'] != int(row['units_sold']):
                reason_list.append("units_sold not integer")
        else:
            reason_list.append("Invalid units_sold")

        if not (pd.notna(row['sale_price']) and row['sale_price'] > 0):
            reason_list.append("Invalid sale_price")

        reasons.append("; ".join(reason_list))

    rejected_df['rejection_reason'] = reasons

    # Format date for clean_df
    clean_df['sale_date'] = clean_df['sale_date'].dt.strftime('%Y-%m-%d')
    clean_df['units_sold'] = clean_df['units_sold'].astype(int)

    return clean_df, rejected_df

# Stage 4: Database Ingestion
def ingest_data(clean_df, rejected_df):
    db_path = 'data/company_finance.db'
    if not os.path.exists(db_path):
        logging.error(f"Database {db_path} does not exist.")
        return

    conn = sqlite3.connect(db_path)

    # Get valid product IDs
    try:
        valid_products = pd.read_sql_query("SELECT product_id FROM products", conn)
        valid_product_ids = set(valid_products['product_id'])
    except sqlite3.Error as e:
         logging.error(f"Error reading products table: {e}")
         conn.close()
         return

    # Filter clean_df by valid product IDs
    mask_valid_fk = clean_df['product_id'].isin(valid_product_ids)

    final_clean_df = clean_df[mask_valid_fk].copy()
    invalid_fk_df = clean_df[~mask_valid_fk].copy()

    if not invalid_fk_df.empty:
        invalid_fk_df['rejection_reason'] = "Foreign key violation: product_id not in products"
        rejected_df = pd.concat([rejected_df, invalid_fk_df], ignore_index=True)

    # Export rejected
    quarantine_path = 'data/quarantine.xlsx'

    # Append if exists, otherwise create
    if os.path.exists(quarantine_path):
        try:
            existing_rejected = pd.read_excel(quarantine_path)
            rejected_df = pd.concat([existing_rejected, rejected_df], ignore_index=True)
        except Exception as e:
            logging.error(f"Error reading existing quarantine file: {e}")

    if not rejected_df.empty:
        rejected_df.to_excel(quarantine_path, index=False)
        logging.info(f"Exported {len(rejected_df)} rejected rows to {quarantine_path}")

    # Ingest clean
    if not final_clean_df.empty:
        try:
            final_clean_df.to_sql('clean_sales', conn, if_exists='append', index=False)
            logging.info(f"Successfully ingested {len(final_clean_df)} rows into clean_sales.")
        except sqlite3.Error as e:
            logging.error(f"Database error during ingestion: {e}")
    else:
        logging.info("No valid rows to ingest.")

    conn.close()

def process_file(filepath):
    logging.info(f"--- Starting processing for {filepath} ---")

    try:
        df = pd.read_excel(filepath)
    except Exception as e:
        logging.error(f"Error reading {filepath}: {e}")
        return False

    logging.info("Stage 1: Header Validation...")
    try:
        df = validate_headers(df)
    except ValueError as e:
        logging.error(e)
        return False

    logging.info("Stage 2: Vectorized Cleaning...")
    df = clean_data(df)

    logging.info("Stage 3: Boolean Masking & Isolation...")
    clean_df, rejected_df = isolate_data(df)

    logging.info("Stage 4: Database Ingestion...")
    ingest_data(clean_df, rejected_df)

    return True

def main():
    incoming_dir = 'data/incoming'
    archive_dir = 'data/archive'

    os.makedirs(incoming_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    excel_files = glob.glob(os.path.join(incoming_dir, '*.xlsx'))

    if not excel_files:
        logging.info(f"No Excel files found in {incoming_dir}. Pipeline exiting.")
        return

    for filepath in excel_files:
        success = process_file(filepath)

        if success:
            filename = os.path.basename(filepath)
            name, ext = os.path.splitext(filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_filename = f"{name}_processed_{timestamp}{ext}"

            archive_path = os.path.join(archive_dir, new_filename)
            shutil.move(filepath, archive_path)
            logging.info(f"Successfully archived {filename} to {archive_path}")
        else:
            logging.error(f"Processing failed for {filepath}. File left in incoming folder.")

    logging.info("--- Batch processing complete ---")

if __name__ == "__main__":
    main()
