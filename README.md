# BBG OPC Dashboard

Standalone production dashboard for your OPC UA MySQL collector.

This app is intentionally **not integrated** with your existing BST/RLM dashboard. It runs as its own website on port `8000` and connects directly to the existing OPC MySQL tables:

- `opc_machines`
- `opc_tags`
- `opc_poll_cycles`
- `opc_tag_values`
- `opc_tag_latest`

The dashboard adds its own tables for layout, recipes, tag visibility, active recipe selection, and persistent alerts.

## What this app does

- Shows one machine at a time.
- Loads the full machine image from `opc_machines.main_image_path`.
- Lets you draw and save clickable boxes over the full machine image.
- Groups OPC variables by the section parsed from `opc_tags.opc_path`.
- Shows selected-section photo and live values.
- Shows only `display_name` and current value on the live production panel.
- Loads last-hour history automatically when a section is selected.
- Lets you check/uncheck numeric variables in the chart legend.
- Lets you create recipes and numeric min/max limits.
- Marks machine sections green/red/orange depending on recipe limits and open alerts.
- Creates persistent MySQL alert events when a live value is outside the active recipe limits.
- Alerts stay in MySQL forever. Acknowledging an alert hides it from the active dashboard but does not delete it.

## Technology stack

Backend:

- Python
- FastAPI
- Uvicorn
- PyMySQL
- Raw SQL with a small connection pool

Frontend:

- React
- TypeScript
- Vite
- TanStack Query
- Apache ECharts
- CSS Grid/Flexbox full-page layout

Deployment:

- Windows VM
- No Docker
- Runs on port `8000`

---

# Installation on Windows VM

Open **Command Prompt** as the normal user that will run the app.

In the examples below, this app is placed at:

```bat
C:\bbg_opc_dashboard
```

You can use another folder if you want.

---

## Step 1 - Copy the project folder to the VM

Copy the extracted `bbg_opc_dashboard` folder to:

```bat
C:\bbg_opc_dashboard
```

Then open Command Prompt and go into that folder:

```bat
cd /d C:\bbg_opc_dashboard
```

This puts your command prompt inside the dashboard project.

---

## Step 2 - Update `opc_machines` in MySQL Workbench

Open **MySQL Workbench** and run this SQL against your OPC collector database.

If the column already exists, skip this step.

```sql
ALTER TABLE opc_machines
ADD COLUMN main_image_path VARCHAR(500) NULL AFTER endpoint_url;
```

This gives each machine one full machine image path.

Now set the main image path for your first machine. Change `machine_id = 1` if your machine id is different.

```sql
UPDATE opc_machines
SET main_image_path = 'opc_photos/Main_bbg.jpeg'
WHERE machine_id = 1;
```

The path above means the image file should be placed here in this project:

```bat
C:\bbg_opc_dashboard\backend\app\static\opc_photos\Main_bbg.jpeg
```

---

## Step 3 - Create the dashboard tables in MySQL Workbench

Open this file in MySQL Workbench:

```bat
C:\bbg_opc_dashboard\migrations\dashboard_tables.sql
```

Run the whole file against your OPC collector database.

This creates these dashboard-specific tables:

- `opc_machine_sections`
- `opc_tag_display_config`
- `opc_recipes`
- `opc_recipe_limits`
- `opc_machine_active_recipe`
- `opc_alert_events`

These tables do not replace your collector tables.

---

## Step 4 - Copy your photos

Put the full machine image and section images here:

```bat
C:\bbg_opc_dashboard\backend\app\static\opc_photos
```

Example:

```bat
C:\bbg_opc_dashboard\backend\app\static\opc_photos\Main_bbg.jpeg
C:\bbg_opc_dashboard\backend\app\static\opc_photos\020 - Unwinder.jpeg
C:\bbg_opc_dashboard\backend\app\static\opc_photos\080 - Dancer.jpeg
C:\bbg_opc_dashboard\backend\app\static\opc_photos\290 - Storage Cylinder.jpeg
```

Section photo names are matched loosely against the section name parsed from `opc_tags.opc_path`.

For example this OPC path:

```text
Global PV/020 - unwinder/state/state
```

becomes this section key:

```text
020 - unwinder
```

A photo named any of these should match:

```text
020 - unwinder.jpeg
020 - Unwinder.jpeg
020_unwinder.png
```

If a section photo is missing, the app will still work. It will show the live values and display a missing-photo placeholder.

---

## Step 5 - Create your `.env` file

Copy `.env.example` to `.env`.

Command Prompt:

```bat
copy .env.example .env
```

Now edit `.env` with Notepad:

```bat
notepad .env
```

Update these values:

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=opc_collector
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
DEFAULT_MACHINE_ID=1
```

`DEFAULT_MACHINE_ID` must match the `machine_id` in `opc_machines` that you want to load by default.

Leave this as-is unless you want a different port:

```env
APP_PORT=8000
```

---

## Step 6 - Install Python 3.11 or newer

Check Python:

```bat
py --version
```

You should see Python 3.11 or newer.

If Windows says `py` is not recognized, install Python from python.org and make sure Python is added to PATH.

---

## Step 7 - Install Node.js LTS

Check Node.js:

```bat
node --version
```

Check npm:

```bat
npm --version
```

If those commands fail, install Node.js LTS from nodejs.org.

Node.js is needed to build the React/TypeScript frontend.

---

## Step 8 - Create the Python virtual environment and install backend packages

Run:

```bat
scripts\install_backend.bat
```

What this does:

1. Creates a Python virtual environment in `.venv`.
2. Upgrades pip.
3. Installs FastAPI, Uvicorn, PyMySQL, and required Python packages.

---

## Step 9 - Install frontend packages

Run:

```bat
scripts\install_frontend.bat
```

What this does:

1. Goes into the `frontend` folder.
2. Runs `npm install`.
3. Downloads React, TypeScript, Vite, TanStack Query, ECharts, and frontend build tools.

---

## Step 10 - Build the frontend

Run:

```bat
scripts\build_frontend.bat
```

What this does:

1. Compiles TypeScript.
2. Builds the React app.
3. Creates the production frontend in:

```bat
C:\bbg_opc_dashboard\frontend\dist
```

FastAPI serves this built frontend automatically.

---

## Step 11 - Start the dashboard

Run:

```bat
scripts\run_backend.bat
```

This starts the backend and serves the built frontend on port `8000`.

Open a browser on the VM:

```text
http://localhost:8000
```

From another computer on the network, use:

```text
http://VM-IP-ADDRESS:8000
```

Example:

```text
http://192.168.11.50:8000
```

You may need to allow port `8000` through Windows Firewall.

---

# First-time setup inside the dashboard

## 1 - Confirm the main dashboard loads

Open:

```text
http://localhost:8000
```

The app should show **BBG OPC Dashboard**.

If the main image does not show, confirm:

1. `opc_machines.main_image_path` is set to `opc_photos/Main_bbg.jpeg`.
2. The file exists at `backend\app\static\opc_photos\Main_bbg.jpeg`.

---

## 2 - Go to Machine Layout

Click **Machine Layout** in the sidebar.

The app will auto-sync sections from `opc_tags.opc_path`.

For each active tag, it parses the section from paths like:

```text
Global PV/290 - storage cylinder/para/offset
```

The section becomes:

```text
290 - storage cylinder
```

---

## 3 - Draw clickable boxes

On the Machine Layout page:

1. Select a section from the section list.
2. Click **Draw / Replace Box**.
3. Drag a rectangle over the machine image.
4. Release the mouse.

The box is saved to MySQL as percentage coordinates:

- `box_x_pct`
- `box_y_pct`
- `box_w_pct`
- `box_h_pct`

This means the boxes scale correctly on different screen sizes.

---

## 4 - Hide or show sections

Still on the Machine Layout page, select a section and use:

```text
Show this section on dashboard
```

Hidden sections stay in MySQL but do not appear as clickable production boxes.

---

## 5 - Go to Recipes

Click **Recipes** in the sidebar.

Use **New Recipe** to create a recipe/job profile.

Then:

1. Select the recipe.
2. Select a section.
3. Set min/max limits for numeric variables.
4. Turn limit checks on/off.
5. Hide/show variables as needed.
6. Click **Save Limits**.
7. Click **Load Selected Recipe**.

Only numeric values are used for min/max limit checks.

---

## 6 - Return to Live Dashboard

Click **Live Dashboard**.

You should see:

- full machine image
- clickable saved boxes
- selected recipe
- active alerts panel

By default, no section is selected.

Click a machine box to load:

- section photo
- live display name/current value table
- last-hour history chart
- numeric variable checkboxes

---

# Alert behavior

The dashboard checks recipe limits every minute.

If a numeric live value goes outside the active recipe's min/max range, it creates an alert row in `opc_alert_events`.

The alert stores:

- machine
- recipe
- section key
- tag id
- display name
- min value
- max value
- trigger value
- current value
- triggered time
- whether it is still out of range
- acknowledge information

If the value returns inside the range, the alert remains open but changes to a returned-to-range state.

If someone acknowledges it, it disappears from the active alert panel but stays in MySQL forever.

---

# Developer mode

You normally do not need this for production.

If you want to run the frontend development server:

1. Start the backend:

```bat
scripts\run_backend.bat
```

2. Open a second Command Prompt:

```bat
cd /d C:\bbg_opc_dashboard
scripts\run_frontend_dev.bat
```

3. Open:

```text
http://localhost:5173
```

Vite will proxy `/api` and `/static` requests to the backend on port `8000`.

---

# Troubleshooting

## The website opens but says frontend build not found

Run:

```bat
scripts\install_frontend.bat
scripts\build_frontend.bat
```

Then restart:

```bat
scripts\run_backend.bat
```

## MySQL connection fails

Check `.env`:

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=opc_collector
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
```

Also confirm that the MySQL user can read/write these tables:

- `opc_machines`
- `opc_tags`
- `opc_tag_latest`
- `opc_tag_values`
- dashboard tables from `migrations\dashboard_tables.sql`

## Main image does not show

Confirm the database value:

```sql
SELECT machine_id, machine_name, main_image_path
FROM opc_machines;
```

Expected example:

```text
opc_photos/Main_bbg.jpeg
```

Confirm the actual file exists here:

```bat
backend\app\static\opc_photos\Main_bbg.jpeg
```

## Section photo does not show

The app keeps working if a section image is missing.

To make it show, put a matching photo in:

```bat
backend\app\static\opc_photos
```

Example section key:

```text
020 - unwinder
```

Matching file examples:

```text
020 - Unwinder.jpeg
020 - unwinder.png
020_unwinder.jpg
```

## No sections appear

Confirm `opc_tags` has active tags for the selected machine:

```sql
SELECT machine_id, COUNT(*)
FROM opc_tags
WHERE is_active = 1
GROUP BY machine_id;
```

Also confirm `.env` has the correct machine:

```env
DEFAULT_MACHINE_ID=1
```

Then click **Machine Layout** and press **Sync Sections**.

## No live values appear

Confirm `opc_tag_latest` has rows:

```sql
SELECT COUNT(*) FROM opc_tag_latest;
```

Confirm tags are linked to the selected machine:

```sql
SELECT COUNT(*)
FROM opc_tags t
JOIN opc_tag_latest l ON l.tag_id = t.tag_id
WHERE t.machine_id = 1;
```

Change `1` to your machine id if needed.

## History chart is blank

History only charts numeric rows from `opc_tag_values` where:

```text
value_kind = 1
value_num IS NOT NULL
```

Check:

```sql
SELECT COUNT(*)
FROM opc_tag_values v
JOIN opc_tags t ON t.tag_id = v.tag_id
WHERE t.machine_id = 1
  AND v.value_kind = 1
  AND v.value_num IS NOT NULL;
```

## Alerts are not being created

Confirm:

1. A recipe is created.
2. The recipe is loaded on the dashboard.
3. Limits are enabled.
4. Min or max is set.
5. The current value is numeric.
6. The current value is outside the min/max range.

You can check active recipe:

```sql
SELECT * FROM opc_machine_active_recipe;
```

You can check alert history:

```sql
SELECT * FROM opc_alert_events ORDER BY triggered_at DESC;
```

---

# Later Windows service setup

This package does not install a Windows service automatically.

When you are ready, use NSSM or another Windows service wrapper to run:

```bat
C:\bbg_opc_dashboard\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Set the working directory to:

```bat
C:\bbg_opc_dashboard
```
