# StockSense API

Base URL: `http://127.0.0.1:8765`

All protected requests use `Authorization: Bearer <token>`.

## Authentication

- `POST /api/login` — sign in and receive a token
- `POST /api/logout` — invalidate the current token
- `GET /api/me` — read the authenticated user

## Products and inventory

- `GET /api/products` — list products; staff responses omit cost price
- `GET /api/products/:id` — get one product with role-filtered fields
- `POST /api/products` — create a product; manager only
- `PATCH /api/products/:id` — update product data or prices; manager only
- `POST /api/prices` — update selling price; manager only

## Stock and history

- `POST /api/movements` — stock in, sale, damaged, or adjustment
- `GET /api/history` — movement history
- `GET /api/dashboard` — persisted inventory totals and recent activity

Send a unique `Idempotency-Key` header with important stock requests. Reusing a key returns `409` and does not change stock twice.

## AI assistant and proposals

- `POST /api/chat` — grounded stock questions and change preparation
- `GET /api/proposals` — list proposals allowed for the current role
- `POST /api/proposals/:id` with `{ "action": "confirm" }` — atomically apply once
- `POST /api/proposals/:id` with `{ "action": "cancel" }` — cancel with zero stock changes

## Manager APIs

- `GET /api/reports` — seven-day sales, revenue, profit, and category totals
- `GET /api/users` — list users
- `POST /api/users` — create a manager or staff account

## Start and Postman

Run `python app.py` or double-click `Start-StockSense.bat`.

Import both files from `postman/` into Postman, select the **StockSense Local** environment, then run **Manager Login** and **Staff Login**. These requests save the tokens automatically. The collection includes positive tests and failure tests for authentication, staff permissions, cost privacy, duplicate stock operations, and insufficient stock.
