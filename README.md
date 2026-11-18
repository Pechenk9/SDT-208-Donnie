# Donnie Donut Market

A web-based donut shop prototype built with **Python, FastAPI, and PostgreSQL**. The application allows customers to browse donuts, add products to a shopping cart, select a branch, and place orders online.

## Project Structure

```text
Donnie-Donut-Market/
│
├── app/
│   ├── main.py
│   ├── models.py
│   ├── config.py
│   ├── seed.py
│   ├── templates/
│   └── static/
│       ├── css/
│       ├── js/
│       └── images/
│
├── alembic/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
└── README.md
```

## Technologies

- **Python** — main programming language
- **FastAPI** — backend framework
- **PostgreSQL** — relational database
- **SQLAlchemy** — ORM and database operations
- **Alembic** — database migrations
- **Jinja2** — HTML templating
- **HTML, CSS, JavaScript** — frontend

## Getting Started

Follow these steps to run the project locally.

### 1. Clone the repository

```bash
git clone <repository-url>
cd Donnie-Donut-Market
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
```

On Windows:

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root directory by copying `.env.example`.

```bash
copy .env.example .env
```

Open `.env` and enter your local PostgreSQL connection details, including the database name, username, and password.

Make sure the database exists before proceeding.

### 5. Apply database migrations

```bash
alembic upgrade head
```

### 6. Populate the database

Run the seed script to insert the initial data, including products, ingredients, recipes, branches, and branch-specific product assortments.

```bash
python -m app.seed
```

### 7. Create the initial accounts

After applying migrations, run the account seeder:

```bash
python -m app.seed_users
```

For each account, enter a unique email address, first and last name, and password when prompted. Passwords are read with hidden input and stored only as scrypt hashes. The script creates one owner and two customers, and reports when an entered email already exists. Existing accounts keep their password; their role is set to the requested initial role.

### 8. Start the application

```bash
uvicorn app.main:app --reload
```

The application will be available at:

```text
http://127.0.0.1:8000
```

Open `/login` to sign in. Successful login redirects to the Store; invalid credentials show a generic error. Submit a POST request to `/logout` to invalidate the server-side session and clear the cookie. The session cookie is HTTP-only, uses SameSite=Lax, and lasts 12 hours by default.

Configure cookie behavior with `SESSION_LIFETIME_SECONDS` and `SESSION_COOKIE_SECURE`. By default, the cookie is secure when `ENVIRONMENT=production` (or `APP_ENV=production`) and not secure during local development. Set `SESSION_COOKIE_SECURE=true` explicitly when serving over production HTTPS.

## Current Features

- Browse the donut catalogue with selected-branch prices and availability when a valid `selected_branch` cookie is present. Without a selected branch, show base prices and mark availability as unknown.
- View product recipes and branch-specific prices and availability when a valid `selected_branch` cookie is present.
- Add products to the shopping cart and manage quantities.
- Select a branch for an order.
- Choose between pickup and delivery.
- Submit orders through the checkout form.
- Validate customer and order information.
- Calculate order totals using prices stored in the database.
- Save orders and their items in PostgreSQL.
- Register customer accounts, sign in, and view a personal profile.
- Network owners can assign branch managers and manage the shared product and ingredient catalogues from the Owner Panel.
- Branch managers can manage product and ingredient availability only for their assigned branches; globally deactivated items are clearly flagged but remain manageable at branch level.

## Project Goal

Donnie aims to provide a convenient online ordering experience for a donut shop network operating across multiple cities. The project is being developed as a team prototype, with plans to expand its functionality with custom donut creation, customer accounts, and branch management.