# Shared Expenses Application

A Django 5.x project designed for splitting expenses, managing group balances, and resolving settlements with high traceability.

## Technology Stack
- **Core**: Django 5.x, Django REST Framework
- **Database**: PostgreSQL (via `psycopg2-binary`)
- **Environment**: `.env`-based settings using `django-environ`

## Project Structure
The project is decoupled into independent, self-contained Django apps:
- `core`: Shared base components, global validators, and common utilities.
- `accounts`: User authentication, identity, and profile management.
- `groups`: Expense sharing groups and member tracking.
- `expenses`: Expense entry details and splitting strategies.
- `balances`: Real-time ledger calculations for net member obligations.
- `settlements`: Verification and lifecycle of settlements/repayments.
- `imports`: Importing external data (e.g. CSV logs) with ledger traceability.

## Installation & Setup

1. **Clone the repository** and navigate to the root directory.
2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure the Environment**:
   - Copy `.env.example` to `.env`.
   - Update `DATABASE_URL` with your local PostgreSQL credentials.
   - (Optional) If `DATABASE_URL` is omitted, the project defaults to a local SQLite database for easy testing.
5. **Run Migrations & Start Server**:
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```
