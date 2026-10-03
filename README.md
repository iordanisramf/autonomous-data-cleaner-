# Automated Financial Data Cleaning Pipeline

An automated, strict, in-memory data cleaning pipeline built with Python (`pandas`, `sqlite3`).

The pipeline expects Excel sales data in the `data/incoming/` directory. It processes the files by rigorously validating the headers, casting the data types, handling missing values, and validating business rules (Boolean Masking).
Invalid data is quarantined in `data/quarantine.xlsx` with detailed rejection reasons. Clean data is inserted into an SQLite database (`data/company_finance.db`). Processed files are moved to `data/archive/` and detailed logs are available in `data/pipeline.log`.

## Running Locally

1. Create the database: `python 01_setup_db.py`
2. Place your raw Excel files into `data/incoming/`.
3. Process the files: `python 02_cleaner.py`

## Running with Docker

The pipeline is fully containerized. You do not need Python installed on your local machine to run it, only Docker.

1. Ensure Docker and Docker Compose are installed.
2. Place your raw Excel files into the `data/incoming/` folder on your machine.
3. In your terminal, run:
   ```bash
   docker-compose up --build
   ```
4. The container will automatically set up the database (if it doesn't exist) and process any files in the incoming folder.
5. You can view your results (quarantine file, SQLite db, and logs) in your local `data/` folder, as they are mapped as a Docker Volume.