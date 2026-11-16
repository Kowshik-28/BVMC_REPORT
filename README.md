# Boson Motor — Fleet Mission Reports Customer & Owner Web Application

A production-style Fleet Mission Reports web application featuring a **public Customer Portal** for viewing mission reports and a **secure Owner Portal** with authentication for configuring fleet data and publishing reports.

---

## 🌟 Application Architecture

### 1. Customer Dashboard (`/` or `/customer`)
* **Public Access**: No login or credentials required.
* **Date-wise Reports Library**: Dynamically lists published Fleet Mission HTML reports in date order (**newest first**).
* **Fidelity & Branding**: Reports render with the exact HTML styling, issue summary, diagnostics, and Boson Motor branding.
* **Clean Isolation**: Customers cannot access Python logic, generation endpoints, or administrative controls.

### 2. Owner Dashboard (`/owner`)
* **Secure Authentication**: Protected by login credentials (`/login`).
* **Preserved Workflow & UI**: The existing Python application interface (`vehicle_mission_report-4.html`) remains unchanged in styling, colors, layout, and controls.
* **One New Button**:
  * **`Upload / Add Mission Report`**: Automates running the Python report generation engine, saving the HTML report to disk, registering metadata (Vehicles summary, Date range, Timestamp), and immediately publishing it to the Customer Dashboard in the correct chronological order.

---

## 🔑 Default Credentials

| Portal | URL | Username | Password |
|---|---|---|---|
| **Customer Portal** | `http://localhost:8000/` | *None (Public)* | *None (Public)* |
| **Owner Portal** | `http://localhost:8000/owner` | `admin` | `boson2026` |

*(Credentials can also be customized via `.env` with `OWNER_USERNAME` and `OWNER_PASSWORD`).*

---

## 🚀 Getting Started

### Windows (PowerShell)

Create and activate a virtual environment, then install the project dependencies:

```powershell
py -3.13 -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

With the virtual environment active, start the web server:

```powershell
python app.py
```

### 1. Start the Web Server

You can run the application using any of the following commands:

```bash
# Option A: Run using the main application script
python3 vehicle_mission_report-4.py

# Option B: Run app.py directly
python3 app.py

# Option C: Run with Uvicorn
uvicorn app:app --host 0.0.0.0 --port 8000
```

The server will start on port `8000` (or the port specified by the `PORT` environment variable).

### 2. Access the Applications

* **Customer Portal**: Open [http://localhost:8000/](http://localhost:8000/) in your browser.
* **Owner Portal**: Open [http://localhost:8000/owner](http://localhost:8000/owner) (will prompt for login if not signed in).

### Deploying on Vercel

Vercel functions do not provide a persistent writable project filesystem. For a Vercel deployment, provision a PostgreSQL database and set `DATABASE_URL` in the Vercel project's Environment Variables for each environment you deploy. Use the provider's PostgreSQL connection URL; keep it private and do not commit it to the repository.

When `DATABASE_URL` points to PostgreSQL, fleet state, report metadata, and generated report HTML are stored in the database. After setting the variable, redeploy and check `/api/status`; it should report `"type": "PostgreSQL"` and `"connected": true`. The local SQLite database remains the default when `DATABASE_URL` is unset.

---

## 🧾 Issue Fields, Component Grouping & Customer Feedback

### Issue fields (Owner Dashboard)
For every issue of a vehicle (status **Issues** or **MDM Issue**) the owner enters:

| Field | Type | Required |
|---|---|---|
| Issue | Short title | Yes |
| Description | Text | Yes |
| Period | Text, e.g. `29 and 30 September 2026` | No |
| Occurrences | Text, e.g. `2` or `Continuous` | No |
| Component | BMS, Motor, DCDC, EPAS, MDM, Other | No (default: Other) |
| Issue Reported By | Text | No |
| Severity | Low, Medium, High, Critical | No (default: Medium) |
| RCA | Text | No |
| Responsible Team | Text | No |
| Customer Feedback | Typed by the owner (optional, up to 1000 characters) | No |
| Grafana Link | `http(s)://` address for this issue (shown as an "Open" link in the report, last column of the CSV) | No |

The fields are stored in `issue_details` next to the original `issues` list (`fleet_state.json`, the SQLite/PostgreSQL `fleet_state` and `reports` tables, and `reports.json`). Old reports without these fields still open and render exactly as before.

### Grouping in the Issue Summary
* **BMS, Motor and DCDC** issues appear together in one row: `✗ BMS / Motor Faults`.
* **MDM** issues appear in `⚠ MDM ON but No Data Received`.
* EPAS / Other issues of an unhealthy vehicle fall back to the default `✗ BMS / Motor Faults` row (or Data Loss / Charging, based on the title), so a vehicle is never lost.
* Severity is shown as a badge: Low = green, Medium = orange, High = red, Critical = dark red.

### Issue Category Summary and Data / Telemetry Issues
Two email-safe tables (HTML tables with inline styles, side by side, stacking on narrow screens) are placed at the top, above the Issue Summary table. They are built from the selected Component. Categories with zero issues are hidden. They are not shown for old reports that have no Component data.

### Customer feedback
* Customer Feedback is a normal owner field: type it in the **Customer Feedback** box of the issue form. There is no public feedback form.
* It is saved with the other issue fields (`activeFleet`, `fleet_state.json`, SQLite and `reports.json`), shown in the **Customer Feedback** column of the report (HTML-escaped) and included in the CSV export.

### Publishing the same period again
Publishing a period that already exists **replaces** it (one report per period). Deleting a report never removes a file that another listed report still uses.

### Export CSV
The **Export CSV** button (`GET /api/export_csv`, owner only) downloads every logged issue with the columns: S.No., VIN, Nickname, Location, Issue, Description, Period, Occurrences, Component, Issue Reported By, Severity, RCA, Responsible Team, Customer Feedback.

### Shared code
`issue_report.py` (standard library only) holds the grouping, the two tables, the issue table and the CSV rows. `app.py` and `vehicle_mission_report-4.py` both call it, and the JavaScript in `vehicle_mission_report-4.html` is a line-by-line port. Keep all three in sync (`test_app.py` checks this).

---

## 🛠️ Key Features & Endpoints

| Endpoint | Method | Access | Description |
|---|---|---|---|
| `/` | `GET` | Public | Customer Dashboard (Mission report viewer) |
| `/login` | `GET` | Public | Owner Authentication login page |
| `/api/login` | `POST` | Public | Validates owner credentials and establishes session |
| `/logout` | `GET` / `POST` | Owner | Clears owner session and redirects to login |
| `/owner` | `GET` | Protected | Owner Dashboard (Fleet mission report builder) |
| `/api/reports` | `GET` | Public | Returns JSON list of published reports (sorted newest first) |
| `/api/publish_report` | `POST` | Protected | Generates HTML report, saves to disk, and publishes to Customer Portal |
| `/api/save` | `POST` | Protected | Saves active fleet state to database & JSON backup |
| `/api/export_csv` | `GET` | Protected | Downloads all logged issues as CSV |
| `/api/status` | `GET` | Public | Database connection health status |
| `/reports/{filename}` | `GET` | Public | Serves individual mission report HTML files |
| `/health` | `GET` | Public | Health check endpoint |

---

## 📁 Project File Structure

```text
web_site_BOSON/
├── app.py                            # Production web application (FastAPI + report generation + auth)
├── vehicle_mission_report-4.py       # Main entry point & Python report generator
├── issue_report.py                   # Shared Issue Summary / category tables / CSV logic
├── vehicle_mission_report-4.html     # Owner Dashboard interface (with "Upload / Add Mission Report" button)
├── login.html                        # Owner authentication login page
├── fleet-mission-reports/            # Customer Portal static assets
│   ├── index.html                    # Customer Dashboard (Dynamic reports sidebar + iframe viewer)
│   └── reports/                      # Customer reports repository
├── reports/                          # Published reports directory
│   ├── report_01-09-2026_15-09-2026.html
│   ├── report_01-08-2026_31-08-2026.html
│   └── report_2026-08-01_2026-08-15.html
├── reports.json                      # Published reports metadata registry
├── fleet_state.db                    # SQLite database (State & Report records)
├── fleet_state.json                  # Active fleet configuration backup
├── test_app.py                       # Automated test suite
└── README.md                         # Project documentation
```

---

## 🧪 Running Tests

To verify all customer and owner workflows:

```bash
pip install -r requirements.txt
python3 test_app.py        # or: pytest -q test_app.py
```

All tests run against a temporary copy of the data files, so your real fleet state, reports and database are not changed.
