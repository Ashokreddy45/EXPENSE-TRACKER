<div align="center">

# FinTrack
### Personal Finance & Expense Tracker

**Track smarter. Budget better. Build financial clarity.**

A Django-powered web application to manage expenses, income, budgets, savings goals, and financial insights in one place.

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.1-092E20?style=for-the-badge&logo=django&logoColor=white)
![Frontend](https://img.shields.io/badge/Frontend-HTML%20%7C%20CSS%20%7C%20JavaScript-E34F26?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active%20Development-orange?style=for-the-badge)

</div>

---

## Overview

**FinTrack** is a personal finance management application built with Python and Django. It brings everyday financial activities into one place, helping users organize transactions, monitor budgets, track savings goals, and understand spending patterns.

This project is developed as a practical application of web development, database management, application security, and software testing.

## Features

- **Financial dashboard** — review key financial information in one place.
- **Expense management** — record, categorize, edit, and delete expenses.
- **Income tracking** — maintain income records.
- **Budget management** — create and review budgets.
- **Savings goals** — set financial goals and monitor progress.
- **Transaction history** — review recorded financial activity.
- **Financial analytics** — explore summaries and spending patterns.
- **Tax estimation** — estimate tax using the application's supported calculation rules.
- **User accounts and profiles** — manage individual accounts and profile details.
- **Responsive interface** — use the application through a modern web interface.
- **Security-conscious configuration** — use environment variables for deployment settings and secrets.

> Features and availability may evolve as development continues.

## Technology Stack

| Area | Technology |
|---|---|
| Language | Python |
| Web framework | Django |
| Frontend | HTML, CSS, JavaScript |
| UI styling | Tailwind CSS and project stylesheets |
| Local database | MySQL |
| Optional deployment database | SQLite |
| Static-file serving | WhiteNoise |
| WSGI server | Gunicorn |
| Testing | Django test framework |
| Version control | Git and GitHub |
| Deployment target | Render |

## Project Structure

```text
EXPENSE-TRACKER/
├── expense_tracker_ashok/   # Django project settings and URLs
├── home/
│   ├── migrations/          # Database migrations
│   ├── static/home/         # Application static assets
│   ├── templates/home/      # HTML templates
│   ├── forms.py             # Form definitions
│   ├── models.py            # Data models
│   ├── tests.py             # Automated tests
│   ├── urls.py              # Application routes
│   └── views.py             # Request handling and business logic
├── manage.py
├── requirements.txt
├── build.sh
├── .env.example
├── .gitignore
└── README.md
```

## Run Locally

### Prerequisites

- Python 3.12 or a compatible version
- MySQL Server for the existing local MySQL setup
- Git

### 1. Clone the repository

```bash
git clone https://github.com/Ashokreddy45/EXPENSE-TRACKER.git
cd EXPENSE-TRACKER
```

### 2. Create and activate a virtual environment

**macOS / Linux**

```bash
python3 -m venv env
source env/bin/activate
```

**Windows PowerShell**

```powershell
py -m venv env
env\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local environment file:

```bash
cp .env.example .env
```

Edit `.env` with your own settings. For a local MySQL setup, the relevant values will look similar to:

```dotenv
SECRET_KEY=replace-with-a-strong-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_ENGINE=mysql
DB_NAME=expense_tracker
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306
```

Keep any existing email and WebAuthn settings from `.env.example` and configure them if you use those features.

**Never commit `.env`, passwords, secret keys, database dumps, or private user data to GitHub.**

### 5. Prepare the database

For a fresh local installation, create the MySQL database configured in `.env`. Then run:

```bash
python manage.py migrate
```

If you already have a working local database, do not create or replace it unnecessarily. Back up your data before making schema changes.

### 6. Create an administrator

```bash
python manage.py createsuperuser
```

Follow the prompts to create an administrator account.

### 7. Start the development server

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.

## Testing and Quality Checks

Run the automated tests:

```bash
python manage.py test
```

Check the Django configuration:

```bash
python manage.py check
```

Both commands should complete successfully before deployment.

## Deployment

The planned student-project deployment uses **Render's free web service with SQLite** to avoid requiring a separate managed MySQL database.

The deployment configuration must explicitly select SQLite through the `DB_ENGINE` environment variable. The existing local configuration continues to use MySQL when `DB_ENGINE=mysql`.

### Deployment checklist

- [ ] Configure the Render service and select the Free instance.
- [ ] Set production environment variables, including a strong `SECRET_KEY`.
- [ ] Set `DEBUG=False` and configure `ALLOWED_HOSTS`.
- [ ] Configure the production domain in `CSRF_TRUSTED_ORIGINS` if required.
- [ ] Configure SQLite for the deployed service.
- [ ] Install dependencies and collect static files.
- [ ] Apply Django migrations.
- [ ] Verify registration, login, expenses, income, budgets, goals, and analytics.
- [ ] Confirm the limitations of the deployment's storage.

### Important: SQLite and Render storage

Render's free web-service filesystem is ephemeral. A SQLite database stored on that filesystem **can be lost when the service restarts, redeploys, or its instance is replaced**. It is therefore suitable for a student demonstration, testing, or temporary data—not as the only copy of important financial records.

Keep your local MySQL database and backups intact. Do not migrate or delete your existing data just to deploy a demonstration version. Persistent storage and backup arrangements would need to be considered if deployed data must survive restarts.

No production URL is listed until the deployment has been completed and verified.

## Security

- Keep secrets and credentials out of source control.
- Use a unique, strong `SECRET_KEY` in production.
- Set `DEBUG=False` in production.
- Restrict `ALLOWED_HOSTS` to the intended hostnames.
- Configure CSRF trusted origins correctly for HTTPS deployment.
- Use appropriate database permissions.
- Keep independent backups of important data.
- Do not store sensitive financial information in a temporary deployment database.

## Roadmap

- [ ] Deploy the application for demonstration.
- [ ] Verify core workflows on the hosted version.
- [ ] Add screenshots of the application.
- [ ] Improve documentation and automated test coverage.
- [ ] Evaluate persistent storage if the application needs durable hosted data.

## Contributing

Suggestions and bug reports are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Run the relevant tests.
5. Submit a pull request describing your changes.

## License

No license has been specified yet. Until a license is added, the project remains subject to the applicable copyright rules; do not assume it is open for unrestricted reuse or redistribution.

---

<div align="center">

**Built with Python and Django.**

</div>
