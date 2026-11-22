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

## Online payment (LiqPay)

Online orders are paid through [LiqPay](https://www.liqpay.ua/en/doc). Donnie builds the checkout `data` (base64 JSON: amount in USD, a unique `order_id` per attempt, `result_url`, `server_url`) and its `signature` (`base64(sha1(private_key + data + private_key))`), and the browser posts both to the LiqPay checkout. The result comes from the signed callback to `server_url` or from a `status` request when the guest returns. Managers refund with the `refund` action.

Settings in `.env` (see `.env.exmple`):

- `PAYMENT_PROVIDER=demo` (default): a built-in emulator of the LiqPay checkout. No keys, no card details, no real money. The guest sees a demo checkout with LiqPay's sandbox test cards: `4242 4242 4242 4242` pays, `4000 0000 0000 0002` is declined.
- `PAYMENT_PROVIDER=liqpay` with `LIQPAY_PUBLIC_KEY` / `LIQPAY_PRIVATE_KEY`: the real LiqPay. Use the sandbox keys from your LiqPay account (prefix `sandbox_`); LiqPay's sandbox moves no money. Callbacks need a public address in `PUBLIC_BASE_URL`; on localhost the status is requested when the guest returns.

## Payment receipts by email

When LiqPay confirms an online payment, Donnie emails the receipt (items, extras, tip, total, LiqPay payment id and a link to track the order) to the email given at checkout. A signed-in guest who left the field empty gets it at their account address. The letter's link carries the order's access token (`?t=...`), so it opens on any device. Each order gets one letter: `orders.receipt_emailed_at` is set before sending, so the LiqPay callback and the guest's return never both send it. If the mail server fails, the payment is unaffected and the next trigger (for example opening the receipt page) tries again. Pay-on-receipt orders get no email.

- `EMAIL_PROVIDER=console` (default): nothing is sent. Each letter is saved as an `.eml` file in `./outbox` (or `OUTBOX_DIR`); open it in any mail app to see it as the guest would.
- `EMAIL_PROVIDER=smtp` with `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and `MAIL_FROM`: a real mail server. For Gmail use `smtp.gmail.com`, port `587` and an app password; for testing, Mailtrap's sandbox inbox catches every letter.

Tests always use the console mode with a temporary outbox. Run `alembic upgrade head` to add the `receipt_emailed_at` column; orders paid before this change are marked as already emailed.

## Who can open an order

Order numbers are sequential, so the receipt, payment and status pages (`/orders/{id}/receipt`, `/pay`, `/status`) never open on the number alone; anyone else gets a 404. They open for:

- the browser that placed the order: `POST /orders` sets an http-only cookie `donnie_order_{id}` with the order's `access_token` (path `/orders/{id}`, 30 days);
- anyone with the emailed link or the pickup QR (`?t=<access_token>`); opening it also sets the cookie;
- the account that placed the order, the owner and the managers of the order's branch.

LiqPay's `result_url` includes the token too, so the guest gets the receipt back even if the cookie was lost on the way through LiqPay. The return page itself shows nothing and needs no token. `alembic upgrade head` gives existing orders their own random token (PostgreSQL 13+).
