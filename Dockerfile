# Use a lightweight version of Python
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the python scripts
COPY 01_setup_db.py .
COPY 02_cleaner.py .

# Command to execute when the container starts
CMD ["sh", "-c", "python 01_setup_db.py && python 02_cleaner.py"]
