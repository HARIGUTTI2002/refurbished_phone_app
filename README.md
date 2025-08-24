# Refurbished Phone Selling — Demo App (Flask)

This is a demo application to manage and sell refurbished phones across three dummy platforms (X, Y, Z).

## Features

- Inventory management (Add/Update/Delete)
- Bulk CSV upload
- Search & filters
- Platform-specific price calculation and mock listing
- Condition mapping per platform
- Prevent listing out-of-stock or discontinued items
- Profitability check (avoid unprofitable listings due to high fees)
- Manual price overrides per platform
- Mock authentication (admin login)

## Platform Fees

- X: 10% fee
- Y: 8% fee + $2
- Z: 12% fee

Auto listing price is computed so that after fees, you get the base price (your net revenue).

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 and log in:

- **Username:** hari
- **Password:** hari123

## CSV format

Headers must be exactly:

```
brand,model,storage,color,condition,base_price,stock,tags
```

Example row:

```
Apple,iPhone 12,128GB,Black,Good,400,5,refurbished
```

## Notes

- SQLite DB file is created automatically (`phones.db`).
- First run seeds one sample phone if DB is empty via `flask init-db` CLI as well.
- This is a dummy integration; no real e-commerce APIs are called.
