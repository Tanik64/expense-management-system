# Expense Management System

A Flask + SQLite web app for tracking personal and trip expenses, with budgets, categories, reports, and admin controls.

## Features

- User signup/login with hashed passwords
- Expense tracking with categories, monthly budget, and reports
- Receipt scanning (OCR) to auto-fill expense details from a photo
- Trip management: create trips, start/complete them, and log trip-specific expenses
- **Admin-controlled expense window**: trip expenses can only be added within 20 days before/after the trip dates. Anything outside that window is sent to the admin as a request and only becomes a real expense once approved
- **Admin dashboard**: a "Registered Users" list (with role and signup date) and an "Expense Requests" page to approve/reject out-of-window trip expenses

## Tech stack

- Python 3 / Flask
- SQLite (single file database, no separate server needed)
- Jinja2 templates, vanilla CSS/JS (no frontend build step)
- Optional: Tesseract OCR (via `pytesseract`) for receipt scanning

## Project structure

```
expense-management-system/
├── app.py                  # All routes, DB setup/migrations, and app logic
├── requirements.txt
├── database.db              # SQLite database (auto-created on first run if missing)
├── database/
│   └── schema.sql            # Reference schema (informational — app.py creates/migrates the real tables at startup)
├── static/
│   ├── css/
│   └── js/
└── templates/                # Jinja2 HTML templates
```

## Local setup

### 1. Prerequisites

- Python 3.10+ (3.13 works fine)
- pip

### 2. Get the code

Unzip the project and move into it:

```bash
unzip expense-management-system.zip
cd expense-management-system
```

### 3. Create a virtual environment (recommended)

Keeping this in its own virtual environment avoids version clashes with any other Python packages you already have installed.

```bash
python3 -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

This installs Flask, Werkzeug, and Pillow/pytesseract (for receipt OCR).

> **Optional — enabling receipt scanning:** `pytesseract` is just a Python wrapper; it needs the actual Tesseract OCR engine installed on your machine too.
> - macOS: `brew install tesseract`
> - Ubuntu/Debian: `sudo apt install tesseract-ocr`
> - Windows: install from the [Tesseract releases page](https://github.com/UB-Mannheim/tesseract/wiki) and make sure it's on your PATH
>
> If you skip this, the app still runs fine — the "scan receipt" feature just won't work.

### 5. Run the app

```bash
python app.py
```

The dev server starts at **http://127.0.0.1:5000**. On first run, `database.db` and all tables are created automatically (including a default admin account — see below).

### 6. Log in

A default admin account is seeded automatically:

- **Username:** `admin`
- **Password:** `admin123`

Change this password (or the account) before using this anywhere beyond your own machine. You can also sign up as a regular user from the login page.

## Notes

- The database file (`database.db`) is created and migrated automatically by `app.py` on startup — you don't need to run any SQL manually. `database/schema.sql` is kept for reference only.
- The app runs in Flask's debug/dev server by default (`app.run(debug=True)`), which is fine for local use but **not** meant for production. For production, run it behind a real WSGI server (e.g. gunicorn) and set a proper `secret_key` via an environment variable instead of the hardcoded one in `app.py`.
