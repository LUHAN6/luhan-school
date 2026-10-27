# Luhan ERP Inventory Module

A self-contained Django 6 inventory module for a school. It is intentionally isolated from the existing admin portal.

## Features
- Inventory dashboard with stock value, low-stock alerts and recent activity
- Categories and suppliers
- Items with SKU, unit, reorder level, location, purchase price and selling/value price
- Stock IN, OUT and ADJUSTMENT movements
- Negative-stock protection
- Purchase orders with line items and receiving workflow
- Asset register
- Search and filtering
- CSV export
- Admin registration
- Responsive, modern UI
- Uses Django ORM and transactions; no third-party package required

## Integration
1. Copy the `inventory` folder into the Django project root.
2. Add `inventory` to `INSTALLED_APPS`.
3. Add `path("inventory/", include("inventory.urls"))` to the main URL configuration.
4. Run migrations.
5. If the main project already has a global `base.html`, you can later change `inventory/templates/inventory/layout.html` to extend it. The module currently uses its own layout so it can run independently.

## Important
This module does not modify or depend on the existing admin portal code.
