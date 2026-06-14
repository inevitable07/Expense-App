# Shared Expense Tracker (ExpenseApp)

A modern, resilient multi-currency expense sharing application designed to calculate, simplify, and track balances within groups, featuring time-bound memberships, automated anomaly detection, and a review-approval workflow for CSV imports.

---

## Technical Architecture Overview

The system is built on **Django 5.2** and structured into the following applications:
- **`accounts`**: Implements a custom `User` model using `email` as the unique identifier.
- **`core`**: Contains system-wide models like `FXRate` to handle daily currency exchange rates (USD to INR).
- **`groups`**: Models `Group` and `GroupMembership` (supporting historical time-bound join/leave intervals).
- **`expenses`**: Handles `Expense` tracking and `ExpenseSplit` calculations (supporting Equal, Exact, Percentage, and Shares distribution models).
- **`settlements`**: Manages direct peer-to-peer `Settlement` transactions to clear outstanding balances.
- **`balances`**: Houses the financial calculation engine (`balances/engine.py`) which computes net positions, line-by-line audit breakdowns, and simplifies debts.
- **`imports`**: Manages the CSV upload pipeline, automated scans using 15 custom `AnomalyDetector` subclasses, audit logging, and manual reconciliation before applying records.

---

## Local Setup Instructions

### Prerequisites
- Python 3.12+
- PostgreSQL (or fallback local SQLite)
- Virtual Environment tool (`venv`)

### 1. Set Up Environment Variables
Create a `.env` file in the root directory `e:\ExpenseApp` by copying `.env.example`:
```ini
SECRET_KEY=your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgresql://db_user:db_password@localhost:5432/expense_db
```
*Note: If `DATABASE_URL` is omitted, the application will automatically fall back to using a local SQLite database (`db.sqlite3`).*

### 2. Configure Virtual Environment and Dependencies
In your terminal/PowerShell, run:
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### 3. Run Migrations
Generate and apply database migrations:
```powershell
python manage.py migrate
```

### 4. Seed Foreign Exchange (FX) Rates
If you are planning to test USD transaction imports, you must seed exchange rates in the database. 
1. Create a superuser:
   ```powershell
   python manage.py createsuperuser
   ```
2. Run the development server:
   ```powershell
   python manage.py runserver
   ```
3. Navigate to `http://127.0.0.1:8000/admin/`, log in, and add rates under the **Core** -> **FX Rates** section (e.g. `USD` to `INR` rate for transaction dates).

### 5. Running the Test Suite
To run all automated unit and integration tests:
```powershell
# To run tests on default database
python manage.py test

# To run tests locally on SQLite (extremely fast)
$env:DATABASE_URL="sqlite://"; python manage.py test
```

---

## Production Deployment on Render

Follow these instructions to deploy the application to Render:

### 1. Provision a PostgreSQL Database
- In the Render Dashboard, click **New** -> **PostgreSQL**.
- Give it a name and click **Create Database**.
- Note the **Internal Database URL** (e.g. `postgresql://user:pass@host/db`).

### 2. Configure the Web Service
- Click **New** -> **Web Service** and connect your GitHub repository.
- Configure the environment settings:
  - **Runtime**: `Python`
  - **Build Command**: 
    ```bash
    pip install -r requirements.txt && python manage.py migrate --noinput && python manage.py collectstatic --noinput
    ```
  - **Start Command**: 
    ```bash
    gunicorn shared_expenses.wsgi --log-file -
    ```

### 3. Add Environment Variables
Add the following key-value pairs in the **Environment** settings tab of your Web Service:
- `DEBUG`: `False` (Important: Disables developer logging and error pages)
- `SECRET_KEY`: `[a-secure-randomly-generated-key]`
- `DATABASE_URL`: `[paste-the-internal-database-url-here]`
- `ALLOWED_HOSTS`: `[your-app-subdomain].onrender.com,localhost`

---

## AI Tools Used
This project was developed in partnership with **Antigravity**, Google DeepMind's agentic coding assistant, utilizing advanced terminal control, file modification systems, and autonomous verification.

---

## Deployed Application
The application is deployed and available at: [https://tracker-db-el1c.onrender.com](https://tracker-db-el1c.onrender.com) (Placeholder)
