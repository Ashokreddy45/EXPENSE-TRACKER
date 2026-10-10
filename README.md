# FinTrack — Personal Finance & Expense Tracker

<p align="center">
  <strong>Track smarter. Budget better. Build financial clarity.</strong>
</p>

<p align="center">
  A Django-powered personal finance application for managing expenses, income, budgets, savings goals, and financial insights in one place.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Django-5.1-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django">
  <img src="https://img.shields.io/badge/Database-MySQL-4479A1?style=for-the-badge&logo=mysql&logoColor=white" alt="MySQL">
  <img src="https://img.shields.io/badge/Status-In%20Development-orange?style=for-the-badge" alt="In development">
</p>

---

## Overview

**FinTrack** is a web-based personal finance management application built with Django. It helps users record financial transactions, organize spending, manage budgets, monitor savings goals, and understand their financial activity through a centralized dashboard.

The project focuses on practical financial management, a user-friendly interface, and maintainable backend architecture.

## Features

- **Dashboard:** View an overview of your financial activity.
- **Expense management:** Record, edit, categorize, and delete expenses.
- **Income management:** Track income and review financial records.
- **Budget planning:** Create and manage budgets.
- **Savings goals:** Set financial goals and monitor progress.
- **Transaction history:** Review and manage recorded transactions.
- **Financial analytics:** Explore spending patterns and summaries.
- **Tax estimation:** Estimate tax using supported tax-calculation rules.
- **User accounts:** Register, sign in, and manage your profile.
- **Responsive interface:** Access the application through a modern web interface.
- **Security-conscious configuration:** Load secrets and deployment settings through environment variables.

> Features and availability may vary as development continues.

## Technology Stack

| Layer | Technologies |
|---|---|
| Backend | Python, Django |
| Database | MySQL |
| Frontend | HTML, CSS, JavaScript, Tailwind CSS |
| Static files | WhiteNoise |
| Database driver | mysqlclient |
| Application server | Gunicorn |
| Testing | Django test framework |
| Version control | Git and GitHub |
| Deployment target | Render |

## Project Structure

```text
EXPENSE-TRACKER/
├── expense_tracker_ashok/   # Django project configuration
├── home/
│   ├── migrations/          # Database schema migrations
│   ├── static/home/css/     # Application stylesheets
│   ├── templates/home/      # HTML templates
│   ├── forms.py             # Django forms
│   ├── models.py            # Data models
│   ├── tests.py             # Automated tests
│   ├── urls.py              # Application routes
│   └── views.py             # Application views
├── static/                  # Project-level static assets
├── manage.py                # Django management utility
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.12
- MySQL Server
- Git
- A terminal and code editor

### 1. Clone the repository

```bash
git clone https://github.com/Ashokreddy45/EXPENSE-TRACKER.git
cd EXPENSE-TRACKER
```

### 2. Create a virtual environment

**macOS / Linux**

```bash
python3 -m venv env
source env/bin/activate
```

**Windows**

```powershell
py -m venv env
env\Scripts\activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure the environment

Create a local `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Edit `.env` and provide your local configuration. For example:

```dotenv
SECRET_KEY=replace-with-a-secure-random-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=expense_tracker
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306

EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=

WEBAUTHN_ORIGIN=http://localhost:8000
WEBAUTHN_RP_ID=localhost
WEBAUTHN_RP_NAME=FinTrack

SECURE_SSL_REDIRECT=False
SECURE_HSTS_SECONDS=0
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
CSRF_TRUSTED_ORIGINS=
```

Use values appropriate to your local setup. Never commit `.env`, production secrets, database passwords, or database dumps to GitHub.

### 5. Prepare the database

Create a MySQL database named `expense_tracker` if you are setting up a fresh local installation. Configure the database credentials in `.env`.

Then apply the Django migrations:

```bash
python manage.py migrate
```

### 6. Create an administrator account

```bash
python manage.py createsuperuser
```

Follow the prompts to create your account.

### 7. Run the development server

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.

## Running Tests

Run the project's automated tests with:

```bash
python manage.py test
```

Run Django's configuration checks with:

```bash
python manage.py check
```

## Deployment

FinTrack is being prepared for deployment using **Render** for the Django web service and a separate production database provider.

The deployment process includes:

1. Configuring production environment variables.
2. Provisioning a compatible managed MySQL database.
3. Migrating the existing database data safely, if required.
4. Installing Python dependencies.
5. Collecting static files.
6. Applying migrations in the production environment.
7. Configuring HTTPS, allowed hosts, and CSRF trusted origins.
8. Verifying login, transactions, budgets, and other core workflows.

**Important:** Render's web-service filesystem is ephemeral by default. Uploaded media requires persistent storage or an external storage service. Keep local database backups until the production migration has been verified.

Deployment is a work in progress; no production URL is published here yet.

## Security Notes

- Keep `.env` out of version control.
- Use a unique, strong `SECRET_KEY` in production.
- Set `DEBUG=False` in production.
- Configure `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` for the actual deployment domain.
- Use a database account with appropriate privileges rather than a root account.
- Back up data before database migrations or imports.
- Never publish credentials, private user data, or database dumps.

## Roadmap

- [ ] Complete production deployment.
- [ ] Configure and verify the production database.
- [ ] Verify all core workflows in production.
- [ ] Configure persistent media storage if needed.
- [ ] Add application screenshots.
- [ ] Expand documentation and test coverage.

## Contributing

Suggestions and bug reports are welcome. For code contributions:

1. Fork the repository.
2. Create a feature branch.
3. Make and test your changes.
4. Submit a pull request describing the changes.

## License

No license has been specified yet. Unless a license is added to this repository, reuse and redistribution remain subject to the applicable copyright rules.

---

<p align="center">
  Built with Python and Django.
</p>