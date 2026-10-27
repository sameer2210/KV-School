# Fee Management System

A web-based fee management application built to help educational institutions maintain student fee records, track payments, and generate clear fee receipts. The project is designed around the fee-management workflow rather than a specific school, organization, or individual.

## Overview

The application provides a central place to manage student information related to fee collection, record payments, review fee status, and keep payment documentation organized. It is built with Flask and can use SQLite for local development or PostgreSQL through a configured database URL.

## Key Features

### Student Fee Records
- Maintain student profiles required for fee administration.
- Associate fee records with a student and their class or academic session.
- Store parent/guardian and contact details where required.
- Keep student identifiers and enrollment details organized.

### Fee Structure and Charges
- Organize fee heads such as:
  - Tuition fee
  - Admission or re-admission fee
  - Annual or development fee
  - Computer or laboratory fee
  - Library fee or fine
  - Examination fee
  - Transport fee
  - Sports or activity fee
  - Late-payment fee
  - Other institution-defined charges
- Support fee periods such as monthly, quarterly, half-yearly, or annually, according to the institution's configured workflow.
- Keep individual fee components visible instead of showing only one combined amount.

> The available fee heads and fee periods should be confirmed against the application's current screens and database configuration before being treated as enabled features.

### Payment Tracking
- Record fee payments against the relevant student and fee period.
- Keep payment dates, transaction/reference numbers, payment methods, and amounts together.
- Review paid, partially paid, and outstanding amounts where supported by the configured fee workflow.
- Maintain a history of recorded payments for reference and reconciliation.

### Fee Receipts
- Generate a readable fee receipt for a recorded payment.
- Include relevant receipt details such as:
  - Receipt number
  - Student name and student ID
  - Parent/guardian name, if recorded
  - Class or grade and academic session
  - Fee period
  - Payment date
  - Transaction/reference number
  - Fee-head-wise breakdown
  - Total amount paid
  - Payment mode
  - Remaining balance, when applicable
  - Receipt generation date
- Provide a print-friendly receipt layout; PDF receipt output can be used where implemented.
- Keep the receipt focused on the transaction and avoid displaying unnecessary personal information.

A receipt should represent a payment that has actually been recorded. If a payment is pending or has failed, it should not be presented as successfully paid.

### Reports and Exports
- Review fee collection and payment records.
- Use date, class, student, or fee-period filters where supported.
- Export tabular records for administrative review where export functionality is enabled.
- Use payment records to help identify outstanding dues and reconcile collections.

### Access and Administration
- Provide authenticated access to protected administrative pages.
- Keep student and payment-management actions within the relevant application routes and permissions.
- Configure administrator account details through environment variables rather than hard-coding real credentials.

## Technology Stack

- **Backend:** Python, Flask
- **Database layer:** Flask-SQLAlchemy, SQLAlchemy
- **Database options:** SQLite for local development; PostgreSQL when `DATABASE_URL` is configured
- **Authentication and forms:** Flask-Login, Flask-WTF
- **Migrations:** Flask-Migrate
- **Receipt and document generation:** ReportLab (if used by the active receipt workflow)
- **Spreadsheet processing:** OpenPyXL (for supported spreadsheet import/export workflows)
- **Environment configuration:** python-dotenv
- **Testing:** pytest

## Project Structure

```text
school/
├── app/
│   ├── __init__.py
│   ├── config.py
│   └── ... application routes, models, templates, and static assets
├── instance/
├── tests/
├── run.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

The exact folders and files may differ slightly depending on the current checkout.

## Prerequisites

- Python installed on your system
- pip
- Git, if cloning the repository
- A database configuration:
  - SQLite for a local setup, or
  - PostgreSQL/Supabase credentials for a configured remote database

## Local Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd <project-folder>
```

### 2. Create a virtual environment

**Windows PowerShell:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows Git Bash:**
```bash
python -m venv venv
source venv/Scripts/activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file from `.env.example` if the project provides one. Add the values required by your own setup.

Typical variables may include:

```env
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=your-database-connection-url
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-with-a-strong-password
GEMINI_API_KEY=optional-if-an-enabled-feature-uses-it
```

Only define variables that the current application actually uses. Do not commit `.env` or place real credentials in this README, source control, screenshots, or issue reports. For SQLite development, follow the application's current configuration logic; merely setting a `USE_SQLITE` variable will not change the database unless the code explicitly supports it.

### 5. Run the application

From the project root, with the virtual environment activated:

```bash
python run.py
```

Open:

- Home page: `http://127.0.0.1:5000/`
- Login page: `http://127.0.0.1:5000/login`

Keep the terminal open while using the local application. Stop the development server with `Ctrl+C`.

## Running Tests

If the repository's test suite is installed and configured:

```bash
python -m pytest
```

Run tests after changing fee calculations, payment status handling, receipt generation, or database models.

## Suggested Fee Receipt Data Model

A receipt can use the following fields as a practical design reference. Add only fields that fit the application's actual workflow.

| Field | Purpose |
|---|---|
| Receipt number | Unique identifier for the receipt |
| Student ID | Links the payment to a student record |
| Student name | Identifies the student |
| Class/grade | Shows the student's class at the time of payment |
| Academic year | Identifies the relevant academic session |
| Fee period | Month, quarter, term, or year covered |
| Fee breakdown | Individual fee heads and amounts |
| Total due | Total fee expected for the selected period |
| Previous balance | Any outstanding amount carried forward |
| Discount/concession | Approved reduction, if applicable |
| Late fee | Penalty, if applicable |
| Amount paid | Amount received in this transaction |
| Balance after payment | Amount remaining after this transaction |
| Payment mode | Cash, bank transfer, UPI, card, or other supported method |
| Transaction reference | Bank/payment reference, if applicable |
| Payment date | Date payment was received |
| Received by | Staff member who recorded the payment, if applicable |
| Notes | Optional administrative note |

### Example fee calculation

```text
Current period fees       ₹3,150
Previous outstanding      ₹  500
Approved concession       ₹  200
Total payable             ₹3,450
Amount received           ₹2,000
Balance remaining         ₹1,450
```

This is an illustrative example only. The application's actual calculations and fields depend on its implemented fee rules.

## Recommended Fee Management Workflow

1. Add or locate the student record.
2. Select the academic year and fee period.
3. Review the applicable fee heads and outstanding balance.
4. Record the payment amount, payment mode, date, and reference number.
5. Validate the amount and update the student's fee ledger.
6. Generate a receipt only after the payment record is saved successfully.
7. Make the receipt available for printing or PDF download, where supported.
8. Review collection reports and reconcile payment references periodically.

## Data and Payment Integrity

- Use a unique receipt number for each recorded payment.
- Do not overwrite previous payment transactions when a student makes another payment.
- Keep a transaction history for corrections, refunds, or reversals.
- Validate amounts on the server; do not rely only on browser-side validation.
- Use database transactions for payment recording and receipt creation where appropriate.
- Restrict administrative routes to authenticated, authorized users.
- Avoid storing payment-card credentials or other unnecessary sensitive payment information.
- Back up the database and test restore procedures before relying on the application for operational records.

## Deployment Notes

For production deployment:

- Set a strong, unique `SECRET_KEY`.
- Configure the production `DATABASE_URL` securely.
- Store secrets in the hosting provider's environment-variable settings.
- Use HTTPS.
- Use a production WSGI server such as Gunicorn where supported by the deployment platform.
- Apply database migrations through the project's migration workflow when the schema changes.
- Verify that receipt downloads, authentication, and database writes work in the deployed environment.
- Do not rely on SQLite local files for multi-instance production deployments unless the architecture explicitly supports that setup.

## Current Local Verification

The latest local run notes supplied for this project reported:

- Application home page returned HTTP `200`.
- Login page returned HTTP `200`.
- Protected admin dashboard redirected unauthenticated requests to the login page.
- The test suite reported `18 passed`.
- A database connection check to the configured PostgreSQL database succeeded.

These results describe the reported test run and may change after code, environment, or database updates.

## Scope

The primary focus of this project is **student fee management, payment tracking, and fee receipt generation**. Any feature described above that is marked as conditional or suggested should be verified against the active implementation before being advertised as fully available.

## License

Add the license and usage terms appropriate for this project before distributing it publicly.
