# PageTurn Library System — SQLite Edition

A Flask library management system with a responsive catalog, member accounts, borrowing requests, and an admin dashboard. This edition uses Python's built-in SQLite support, so **you do not need Aiven, MySQL, PostgreSQL, or a separate database server**.

## Features
- Search books by title, author, or ISBN and filter by category.
- Member registration and secure password hashing.
- Book details and borrow requests.
- Members can track their borrowing statuses.
- Admin dashboard for request review and book catalog management.
- Sample books are seeded automatically when the database is empty.
- `/health` endpoint for Render health checks.

## Run locally
1. Install Python 3.10 or newer.
2. Open a terminal in the project folder.
3. Install dependencies:
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt
   python app.py
   ```
4. Open `http://127.0.0.1:5000`.

The SQLite file `library.db` is created automatically in the project folder.

## Create an admin account
Register a normal account through the website, then promote it by running:
```bash
flask --app app shell
```
In the shell:
```python
from app import query_db
query_db("UPDATE users SET role='admin' WHERE email=?", ("your-email@example.com",), fetch=False)
```
Then sign out and sign in again. The Admin link will appear.

Or set `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables and run:
```bash
flask --app app create-admin
```
The admin email is the value of `ADMIN_USERNAME` if it contains `@`, otherwise it will be `<username>@library.local`.

## Deploy on Render without an external database
1. Push the extracted project folder to GitHub.
2. In Render choose **New + → Blueprint** and connect the repository, or create a Web Service manually.
3. The included `render.yaml` uses `gunicorn app:app`; there is no external database service to create.
4. Set a strong `ADMIN_PASSWORD` and a unique `SECRET_KEY` in Render environment settings. The blueprint generates `SECRET_KEY` automatically.
5. In Render, enter a strong password (at least 8 characters) for `ADMIN_PASSWORD`. The app creates/updates the admin account on startup.
6. Deploy. The sample catalog is initialized at startup.

Sign in as admin using `ADMIN_USERNAME` as the email if it contains `@`. Otherwise, the email is `<ADMIN_USERNAME>@library.local`.

### Important note about SQLite on Render
A regular Render web service has an ephemeral filesystem. This means `library.db` and any new books, accounts, and borrowing records **can be lost when the service restarts, redeploys, or the instance is replaced**. This version is ideal for demos/class projects where avoiding an external database is the priority. If you need the data to persist, attach a Render persistent disk and set `DATABASE_PATH` to a path on that disk (for example `/var/data/library.db`); persistent disks may require a paid service plan. Do not store important production data in the default ephemeral location.

## Security notes
- Passwords are stored as hashes.
- Do not commit secrets or personal data to GitHub.
- Change the secret key for any real deployment.
- This is a classroom/demo starter, not a hardened production system.
