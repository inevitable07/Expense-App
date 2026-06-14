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
