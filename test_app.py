#!/usr/bin/env python3
"""
Test suite for Boson Motor Web Application (Customer & Owner Portals)
"""

import os
import re
import csv
import time
import sqlite3
import io
import json
import shutil
import tempfile
import subprocess
import importlib.util
import contextlib
from fastapi.testclient import TestClient
import app as app_module
import issue_report
from app import app, OWNER_USERNAME, OWNER_PASSWORD, REPORTS_DIR

client = TestClient(app)

def test_customer_portal_public_access():
    """Customer portal should be publicly accessible without authentication."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Boson Motor" in response.text
    assert "Fleet Mission Reports" in response.text
    assert "Report Periods" in response.text

def test_api_reports_list():
    """Reports API should return array sorted newest first."""
    response = client.get("/api/reports")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    # Verify sorting
    if len(data) >= 2:
        assert data[0]["sort_date"] >= data[1]["sort_date"]

def test_owner_portal_protected():
    """Owner portal should require authentication and redirect to login."""
    response = client.get("/owner", follow_redirects=False)
    assert response.status_code == 303
    assert "/login" in response.headers["location"]

def test_login_page_renders():
    """Login page should render properly with Boson branding."""
    response = client.get("/login")
    assert response.status_code == 200
    assert "Owner Dashboard" in response.text
    assert "Sign In to Owner Portal" in response.text

def test_login_invalid_credentials():
    """Invalid credentials should return 401."""
    response = client.post("/api/login", json={"username": "wrong", "password": "bad"})
    assert response.status_code == 401
    assert response.json()["status"] == "error"

def test_login_valid_and_owner_access():
    """Valid credentials should set session cookie and allow access to owner dashboard."""
    login_res = client.post("/api/login", json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD})
    assert login_res.status_code == 200
    assert login_res.json()["status"] == "success"
    
    # Access owner dashboard
    owner_res = client.get("/owner")
    assert owner_res.status_code == 200
    assert "Customer Vehicles Mission Report Builder" in owner_res.text
    assert "Upload / Add Mission Report" in owner_res.text
    assert "Customer Portal" in owner_res.text
    assert "Logout" in owner_res.text

def test_publish_mission_report():
    """Publish / Upload report should generate HTML, save file, and update library."""
    # Login first
    client.post("/api/login", json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD})
    
    test_payload = {
        "global_duration": "16-08-2026 to 24-08-2026",
        "vehicles": {
            "MD9GBUE27DC341003": {
                "vin": "MD9GBUE27DC341003",
                "nickname": "US HC Fargo",
                "location": "Not Available",
                "mode": "Autonomous",
                "status": "healthy",
                "distance": "45.2",
                "duration": "3 hours 10 mins",
                "issues": []
            },
            "MD9GBUE27DC341048": {
                "vin": "MD9GBUE27DC341048",
                "nickname": "P1 Vehicle",
                "location": "Not Available",
                "mode": "Autonomous",
                "status": "unhealthy",
                "distance": "12.8",
                "duration": "1 hour",
                "issues": ["BMS cell voltage imbalance"],
                "grafana_url": "https://grafana.bosonmotors.com/d/test-dashboard"
            }
        }
    }
    
    pub_res = client.post("/api/publish_report", json=test_payload)
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["status"] == "success"
    
    report_info = pub_data["report"]
    assert report_info["range"] == "16-08-2026 to 24-08-2026"
    assert report_info["sort_date"] == "2026-08-24"
    assert report_info["vehicles_count"] == 2
    
    # Verify report is now in /api/reports
    reps_res = client.get("/api/reports")
    reps = reps_res.json()
    assert any(r.get("range") == "16-08-2026 to 24-08-2026" for r in reps)
    
    # Verify report HTML file can be served with Grafana link
    file_rel = report_info["file"]
    file_res = client.get(f"/{file_rel}")
    assert file_res.status_code == 200
    assert "USHC Fargo" in file_res.text or "US HC Fargo" in file_res.text
    assert "BMS cell voltage imbalance" in file_res.text
    assert "https://grafana.bosonmotors.com/d/test-dashboard" in file_res.text
    assert "Grafana link" in file_res.text

def test_delete_report():
    """Delete report endpoint should remove report from library."""
    client.post("/api/login", json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD})
    
    # Delete the test report published earlier
    del_res = client.post("/api/delete_report", json={"range": "16-08-2026 to 24-08-2026"})
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"
    
    # Verify report is no longer in /api/reports
    reps_res = client.get("/api/reports")
    reps = reps_res.json()
    assert not any(r.get("range") == "16-08-2026 to 24-08-2026" for r in reps)

def test_status_endpoint():
    """Status endpoint should report database connection status."""
    res = client.get("/api/status")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
    assert "database" in res.json()

def test_logo_endpoint():
    """Logo endpoint should serve Boson_logo.png successfully."""
    for path in [
        "/Boson_logo.png",
        "/static/Boson_logo.png",
        "/static/images/Boson_logo.png",
        "/fleet-mission-reports/Boson_logo.png",
        "/reports/Boson_logo.png",
    ]:
        res = client.get(path)
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        assert len(res.content) > 1000



# ==========================================================
# NEW: issue fields, grouping by Component, category tables,
# customer feedback and CSV export
# ==========================================================

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


@contextlib.contextmanager
def sandboxed_state(seed=False):
    """Run a test against a temporary copy of the data files so that the real
    fleet state, reports and database are never touched.  With seed=True the
    temporary folder starts as a full copy of the project data (used for the
    older tests); otherwise it starts empty."""
    tmp = tempfile.mkdtemp(prefix="boson_test_")
    names = ["DIR_PATH", "REPORTS_DIR", "FLEET_REPORTS_DIR", "REPORTS_JSON_PATH",
             "FLEET_STATE_JSON_PATH", "DB_PATH"]
    saved = {n: getattr(app_module, n) for n in names}
    try:
        shutil.copy(os.path.join(PROJECT_DIR, "vehicle_mission_report-4.html"), tmp)
        app_module.DIR_PATH = tmp
        app_module.REPORTS_DIR = os.path.join(tmp, "reports")
        app_module.FLEET_REPORTS_DIR = os.path.join(tmp, "fleet-mission-reports", "reports")
        app_module.REPORTS_JSON_PATH = os.path.join(tmp, "reports.json")
        app_module.FLEET_STATE_JSON_PATH = os.path.join(tmp, "fleet_state.json")
        app_module.DB_PATH = os.path.join(tmp, "fleet_state.db")
        if seed:
            for name in ("login.html", "Boson_logo.png", "reports.json", "fleet_state.json", "fleet_state.db"):
                if os.path.exists(os.path.join(PROJECT_DIR, name)):
                    shutil.copy(os.path.join(PROJECT_DIR, name), tmp)
            for folder in ("reports", "fleet-mission-reports", "static"):
                if os.path.isdir(os.path.join(PROJECT_DIR, folder)):
                    shutil.copytree(os.path.join(PROJECT_DIR, folder), os.path.join(tmp, folder), dirs_exist_ok=True)
        os.makedirs(app_module.REPORTS_DIR, exist_ok=True)
        os.makedirs(app_module.FLEET_REPORTS_DIR, exist_ok=True)
        app_module.init_db()
        yield tmp
    finally:
        for n, v in saved.items():
            setattr(app_module, n, v)
        shutil.rmtree(tmp, ignore_errors=True)


try:
    import pytest

    @pytest.fixture(autouse=True)
    def _never_touch_real_data():
        """Every test (old and new) runs against a temporary copy of the data
        files, so running pytest can never overwrite fleet_state.json,
        reports.json, fleet_state.db or the published reports."""
        with sandboxed_state(seed=True):
            yield
except ImportError:      # plain `python test_app.py` run (it restores the data itself)
    pass


def login(c=client):
    res = c.post("/api/login", json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD})
    assert res.status_code == 200


def detail(issue_id, **kw):
    base = {"id": issue_id, "issue": f"Issue {issue_id}", "description": f"Description {issue_id}",
            "period": "29 and 30 September 2026", "occurrences": "2", "component": "BMS",
            "reported_by": "PTE team", "severity": "High", "rca": "Cell ageing",
            "responsible_team": "BMS Team"}
    base.update(kw)
    return base


def vehicle(vin, nickname, status="unhealthy", details=None, **kw):
    v = {"vin": vin, "nickname": nickname, "location": "India", "mode": "Autonomous",
         "status": status, "distance": "10", "duration": "1 hour",
         "issues": [d["issue"] for d in (details or [])], "issue_details": details or [],
         "timestamp": "", "vt_box_time": "", "grafana_url": ""}
    v.update(kw)
    return v


# VINs are listed in sorted order, which is the order used in the report
VIN_A, VIN_B, VIN_C, VIN_D, VIN_E = ("MD9GBUE20FC341024", "MD9GBUE22FC341025", "MD9GBUE24FC341026",
                                     "MD9GBUE26FC341027", "MD9GBUE28FC341031")


def sample_fleet():
    return {
        # P40: BMS + Motor
        VIN_A: vehicle(VIN_A, "P40 Vehicle", details=[
            detail("a1", component="BMS", severity="Low"),
            detail("a2", component="Motor", severity="Critical")]),
        # P52: BMS + DCDC + EPAS
        VIN_B: vehicle(VIN_B, "P52 Vehicle", details=[
            detail("b1", component="BMS", severity="Medium"),
            detail("b2", component="DCDC"),
            detail("b3", component="EPAS")]),
        # P60: MDM x2
        VIN_C: vehicle(VIN_C, "P60 Vehicle", status="mdm_issue", details=[
            detail("c1", component="MDM", issue="MDM data missing", description="MDM data missing",
                   period="01-07, 08-14 Sept"),
            detail("c2", component="MDM", issue="Telemetry gap", description="Telemetry gap",
                   period="10-12 Sept")], vt_box_time="10:00"),
        # P61: healthy
        VIN_D: vehicle(VIN_D, "P61 Vehicle", status="healthy"),
        # P62: only an "Other" issue
        VIN_E: vehicle(VIN_E, "P62 Vehicle", details=[detail("e1", component="Other")]),
    }


def summary_table(html_text):
    """Only the (old style) Issue Summary table, without the two new tables."""
    return html_text[html_text.index('id="issue-summary"'):]


def category_section(html_text):
    """The two new tables, which are placed above the Issue Summary table."""
    start = html_text.index('id="issue-category-summary"')
    return html_text[start:html_text.index('id="issue-summary"')]


def save_fleet(fleet, duration="16-09-2026 to 30-09-2026"):
    return client.post("/api/save", json={"global_duration": duration, "vehicles": fleet})


def test_new_fields_saved_and_kept_when_published():
    with sandboxed_state():
        login()
        fleet = sample_fleet()
        assert save_fleet(fleet).status_code == 200

        # fleet_state.json, the API and the SQLite database all keep the new fields
        for source in (
            json.load(open(app_module.FLEET_STATE_JSON_PATH))["vehicles"],
            client.get("/api/fleet_state").json()["vehicles"],
        ):
            d = source[VIN_A]["issue_details"][0]
            assert d["issue"] == "Issue a1" and d["description"] == "Description a1"
            assert d["period"] == "29 and 30 September 2026" and d["occurrences"] == "2"
            assert d["component"] == "BMS" and d["reported_by"] == "PTE team"
            assert d["severity"] == "Low" and d["rca"] == "Cell ageing"
            assert d["responsible_team"] == "BMS Team"
        conn = app_module.get_db_connection()
        row = conn.execute("SELECT vehicles_json FROM fleet_state WHERE id = 1").fetchone()
        conn.close()
        assert json.loads(row[0])[VIN_A]["issue_details"][1]["component"] == "Motor"

        # publish: reports.json and the reports table keep them too, and the report shows them
        pub = client.post("/api/publish_report", json={"global_duration": "16-09-2026 to 30-09-2026", "vehicles": fleet})
        assert pub.status_code == 200
        rj = json.load(open(app_module.REPORTS_JSON_PATH))
        assert rj[0]["vehicles"][VIN_B]["issue_details"][2]["component"] == "EPAS"
        conn = app_module.get_db_connection()
        row = conn.execute("SELECT vehicles_json FROM reports").fetchone()
        conn.close()
        assert json.loads(row[0])[VIN_B]["issue_details"][0]["severity"] == "Medium"
        conn = app_module.get_db_connection()
        row = conn.execute("SELECT report_html FROM reports").fetchone()
        conn.close()
        assert row and "Issue a1" in row[0]
        report = client.get("/" + pub.json()["report"]["file"]).text
        for text in ("Issue a1", "Description a1", "29 and 30 September 2026", "Cell ageing", "BMS Team", "PTE team"):
            assert text in report

        # the saved report can be loaded again from the library
        reps = client.get("/api/reports").json()
        assert reps[0]["vehicles"][VIN_A]["issue_details"][0]["id"] == "a1"


def test_old_reports_without_new_fields_still_work():
    with sandboxed_state():
        login()
        old = {
            VIN_A: {"vin": VIN_A, "nickname": "P40 Vehicle", "location": "India", "mode": "Autonomous",
                    "status": "unhealthy", "distance": "5", "duration": "1h",
                    "issues": ["BMS cell voltage imbalance"]},
            VIN_B: {"vin": VIN_B, "nickname": "P52 Vehicle", "location": "India", "mode": "Autonomous",
                    "status": "mdm_issue", "distance": "Nil", "duration": "1h", "issues": [],
                    "vt_box_time": "09:00"},
            VIN_D: {"vin": VIN_D, "nickname": "P61 Vehicle", "location": "India", "mode": "Autonomous",
                    "status": "healthy", "distance": "5", "duration": "1h", "issues": []},
        }
        assert save_fleet(old).status_code == 200
        assert client.get("/owner").status_code == 200
        html_text = app_module.generate_html_report_content(old, "01-08-2026 to 15-08-2026")
        assert "BMS / Motor Faults" in html_text and "BMS cell voltage imbalance" in html_text
        assert "MDM ON but No Data Received" in html_text and "VT_BOX online: 09:00" in html_text
        # old reports are shown in the existing tables only
        assert "issue-category-summary" not in html_text
        assert "Issue Category Summary" not in html_text


def test_required_issue_fields_are_validated():
    with sandboxed_state():
        login()
        fleet = {VIN_A: vehicle(VIN_A, "P40 Vehicle", details=[detail("a1", description="")])}
        res = save_fleet(fleet)
        assert res.status_code == 400
        assert "Description" in res.json()["detail"]
        fleet = {VIN_A: vehicle(VIN_A, "P40 Vehicle", details=[detail("a1", issue="")])}
        assert client.post("/api/publish_report", json={"global_duration": "x", "vehicles": fleet}).status_code == 400


def test_grouping_bms_motor_dcdc_in_one_row_and_mdm_row():
    html_text = app_module.get_issue_summary_section(sample_fleet(), "16-09-2026 to 30-09-2026")
    table = summary_table(html_text)
    # one single "BMS / Motor Faults" row, never split into BMS / Motor / DCDC rows
    assert table.count("✗ BMS / Motor Faults") == 1
    assert table.count("<td style=\"padding: 12px; border-bottom: 1px solid #f1f5f9; color: #dc2626; font-weight: 600; vertical-align: top;\">") == 1
    bms_row = table[table.index("✗ BMS / Motor Faults"):]
    bms_row = bms_row[:bms_row.index("</tr>")]
    assert "P40" in bms_row and "P52" in bms_row                   # two vehicles with BMS, same row
    for title in ("Issue a1", "Issue a2", "Issue b1", "Issue b2"):  # BMS, Motor and DCDC issues
        assert title in bms_row
    # EPAS / Other have no row of their own in the Issue Summary: like before, an unhealthy
    # vehicle is shown in the default "BMS / Motor Faults" row so that it is never lost
    assert "Issue b3" in bms_row
    assert "P62" in bms_row                                         # "Other" issue: default row
    assert re.search(r">3</span>", bms_row)                         # Count badge = 3 vehicles (P40, P52, P62)
    assert "#vin-" + VIN_A in bms_row and "Grafana" not in bms_row  # vehicle link kept
    # MDM row
    mdm_row = table[table.index("⚠ MDM ON but No Data Received"):]
    mdm_row = mdm_row[:mdm_row.index("</tr>")]
    assert "P60" in mdm_row and "MDM data missing" in mdm_row and "Telemetry gap" in mdm_row
    # other existing rows stay
    assert "✓ OK / No Issues" in table and "Charging Issues (Plug State 4)" in table
    assert "Total Vehicles" in table


def test_grouping_keeps_vehicle_fields_links_and_badges():
    fleet = {VIN_A: vehicle(VIN_A, "P40 Vehicle", grafana_url="https://grafana.example.com/d/p40", details=[
        detail("a1", component="Motor", severity="Critical", issue="Motor <b>overheat</b>")])}
    html_text = app_module.get_issue_summary_section(fleet, "x")
    assert "Grafana link" in html_text and "https://grafana.example.com/d/p40" in html_text
    # Detailed RCA/Period/Occurrences fields are not in the summary table
    for label in ("Description:", "Period:", "Occurrences:", "RCA:", "Responsible Team:"):
        assert label not in html_text
    # But they are present in the full report diagnostics section
    full_report = app_module.generate_html_report_content(fleet, "x")
    for label in ("Description", "Period", "Occurrences", "RCA", "Team"):
        assert label in full_report
    assert "Motor &lt;b&gt;overheat&lt;/b&gt;" in html_text and "<b>overheat</b>" not in html_text  # escaped
    # one badge colour per severity
    expected = {"Low": "#dcfce7", "Medium": "#ffedd5", "High": "#fee2e2", "Critical": "#991b1b"}
    for sev, colour in expected.items():
        out = app_module.get_issue_summary_section(
            {VIN_A: vehicle(VIN_A, "P40 Vehicle", details=[detail("a1", severity=sev)])}, "x")
        assert f"background-color: {colour}; color:" in out and f">{sev}</span>" in out
    assert "color: #16a34a; text-transform: uppercase;\">Low" in issue_report.severity_badge("Low")
    assert "#ea580c; text-transform: uppercase;\">Medium" in issue_report.severity_badge("Medium")
    assert "#dc2626; text-transform: uppercase;\">High" in issue_report.severity_badge("High")
    assert "#ffffff; text-transform: uppercase;\">Critical" in issue_report.severity_badge("Critical")


def test_category_tables_counts_vehicles_and_total():
    html_text = app_module.get_issue_summary_section(sample_fleet(), "x")
    section = category_section(html_text)
    assert "Issue Category Summary" in section and "Data / Telemetry Issues" in section
    # side by side: both tables are in one table row, each in its own cell
    assert section.index("Issue Category Summary") < section.index("Data / Telemetry Issues")
    assert section.count('class="stack-col"') == 2
    assert "flex" not in section and "<img" not in section and "<script" not in section

    data = issue_report.category_data(sample_fleet())
    assert data["counts"] == {"BMS": 2, "EPAS": 1, "DCDC": 1, "Motor": 1, "MDM": 2}
    assert data["affected"]["BMS"] == ["P40", "P52"]
    assert data["affected"]["Motor"] == ["P40"]
    assert data["affected"]["MDM"] == ["P60"]                       # no duplicates

    def row(label):
        m = re.search(label + r".*?</td><td[^>]*>(\d+)</td><td[^>]*>(.*?)</td></tr>", section, re.S)
        return m.group(1), m.group(2)

    assert row("BMS Issues")[0] == "2"
    assert "P40" in row("BMS Issues")[1] and "P52" in row("BMS Issues")[1]
    assert VIN_A in row("BMS Issues")[1] and VIN_B in row("BMS Issues")[1]
    assert row("EPAS Issues")[0] == "1"
    assert "P52" in row("EPAS Issues")[1] and VIN_B in row("EPAS Issues")[1]
    assert row("DCDC Issues")[0] == "1"
    assert "P52" in row("DCDC Issues")[1] and VIN_B in row("DCDC Issues")[1]
    assert row("Motor Faults")[0] == "1"
    assert "P40" in row("Motor Faults")[1] and VIN_A in row("Motor Faults")[1]
    assert row("Data / Telemetry Issues</td>")[0] == "2"
    assert "P60" in row("Data / Telemetry Issues</td>")[1] and VIN_C in row("Data / Telemetry Issues</td>")[1]
    # a vehicle with several categories is listed in each of them; "Other" is not a category
    assert "Other" not in section.split("Total Issues")[0]
    total = re.search(r"Total Issues</td><td[^>]*>(\d+)</td>", section)
    assert total.group(1) == "7"
    # coloured icon boxes
    for colour in ("#dc2626", "#ea580c", "#7c3aed", "#2563eb", "#0d9488"):
        assert f'bgcolor="{colour}"' in section


def test_category_table_hides_zero_rows_and_duplicates():
    fleet = {
        VIN_A: vehicle(VIN_A, "P40 Vehicle", details=[detail("a1"), detail("a2"), detail("a3")]),
        VIN_B: vehicle(VIN_B, "P52 Vehicle", details=[detail("b1")]),
    }
    section = category_section(app_module.get_issue_summary_section(fleet, "x"))
    assert "BMS Issues" in section
    for hidden in ("EPAS Issues", "DCDC Issues", "Motor Faults"):
        assert hidden not in section
    assert "P40" in section and "P52" in section
    assert section.count(f"#vin-{VIN_A}") == 1
    assert re.search(r"BMS Issues.*?>4</td>", section, re.S)           # a1, a2, a3 and b1
    assert re.search(r"Total Issues</td><td[^>]*>4</td>", section)


def test_telemetry_table_lists_only_mdm_vehicles():
    section = category_section(app_module.get_issue_summary_section(sample_fleet(), "x"))
    telemetry = section[section.index("Data / Telemetry Issues</h3>"):]
    assert ">Vehicle(s)<" in telemetry and ">Issue Count<" in telemetry and ">Description<" in telemetry
    assert "P60" in telemetry and "MDM data missing (01-07, 08-14 Sept)" in telemetry
    assert "Telemetry gap (10-12 Sept)" in telemetry
    assert re.search(r"P60</a>.*?</td><td[^>]*>2</td>", telemetry, re.S)          # issue count of that vehicle
    assert "P40" not in telemetry and "P52" not in telemetry       # only MDM vehicles
    # no MDM issues -> message
    no_mdm = {VIN_A: vehicle(VIN_A, "P40 Vehicle", details=[detail("a1")])}
    out = category_section(app_module.get_issue_summary_section(no_mdm, "x"))
    assert "No telemetry issues reported." in out


def test_report_contains_tables_and_old_summary_in_all_outputs():
    html_text = app_module.generate_html_report_content(sample_fleet(), "16-09-2026 to 30-09-2026")
    assert "Issue Category Summary" in html_text and "Data / Telemetry Issues" in html_text
    assert "Vehicles description" in html_text          # existing summary table is still there
    assert "Customer Feedback" in html_text              # column in the vehicle table
    assert "@media only screen" in html_text             # tables stack on narrow screens


def test_standalone_script_matches_app():
    spec = importlib.util.spec_from_file_location(
        "vehicle_mission_report_4", os.path.join(PROJECT_DIR, "vehicle_mission_report-4.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fleet = sample_fleet()
    assert mod.get_issue_summary_section(fleet, "d") == app_module.get_issue_summary_section(fleet, "d")


def test_javascript_summary_matches_python():
    """The dashboard JavaScript must produce the same Issue Summary as Python."""
    if shutil.which("node") is None:
        import pytest
        pytest.skip("node is not installed")
    page = open(os.path.join(PROJECT_DIR, "vehicle_mission_report-4.html"), encoding="utf-8").read()
    start = page.rindex("    // ====", 0, page.index("    // ISSUE SUMMARY HELPERS"))
    block = page[start:page.index("    // ACTIVE SESSION VEHICLE LIST")]
    legacy = {VIN_A: {"vin": VIN_A, "nickname": "P40 Vehicle", "status": "unhealthy", "issues": ["Data loss on x"]},
              VIN_D: {"vin": VIN_D, "nickname": "P61 Vehicle", "status": "healthy", "issues": []}}
    fleets = [sample_fleet(), legacy]
    script = block + "\nconst f = JSON.parse(process.argv[2]);\nconsole.log(JSON.stringify(f.map(x => buildIssueSummaryHTML(x, 'd'))));"
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "check.js")
        open(path, "w", encoding="utf-8").write(script)
        out = subprocess.check_output(["node", path, json.dumps(fleets)], cwd=tmp)
    norm = lambda s: re.sub(r"> <", "><", re.sub(r"\s+", " ", s)).strip()
    for fleet, js_html in zip(fleets, json.loads(out)):
        assert norm(js_html) == norm(app_module.get_issue_summary_section(fleet, "d"))


# ---------------- customer feedback ----------------

def publish_sample():
    login()
    fleet = sample_fleet()
    assert save_fleet(fleet).status_code == 200
    pub = client.post("/api/publish_report", json={"global_duration": "16-09-2026 to 30-09-2026", "vehicles": fleet})
    assert pub.status_code == 200
    return pub.json()["report"]["file"]


def test_customer_feedback_is_typed_by_the_owner_and_saved_everywhere():
    with sandboxed_state():
        login()
        fleet = sample_fleet()
        fleet[VIN_A]["issue_details"][0]["customer_feedback"] = "Fixed on 5 Oct <script>alert(1)</script>"
        assert save_fleet(fleet).status_code == 200
        # saved in fleet_state.json (and so in the dashboard state)
        state = json.load(open(app_module.FLEET_STATE_JSON_PATH))["vehicles"]
        assert state[VIN_A]["issue_details"][0]["customer_feedback"].startswith("Fixed on 5 Oct")

        # published: stored in the report file, in reports.json and in the database, escaped in the HTML
        pub = client.post("/api/publish_report", json={"global_duration": "16-09-2026 to 30-09-2026", "vehicles": fleet})
        assert pub.status_code == 200
        page = TestClient(app).get("/" + pub.json()["report"]["file"]).text
        assert "Fixed on 5 Oct &lt;script&gt;alert(1)&lt;/script&gt;" in page
        assert "<script>alert(1)</script>" not in page
        assert "Fixed on 5 Oct" in open(app_module.REPORTS_JSON_PATH, encoding="utf-8").read()
        conn = sqlite3.connect(app_module.DB_PATH)
        row = conn.execute("SELECT vehicles_json FROM reports ORDER BY rowid DESC LIMIT 1").fetchone()
        conn.close()
        assert "Fixed on 5 Oct" in row[0]


def test_customer_feedback_defaults_and_length_limit():
    with sandboxed_state():
        login()
        fleet = sample_fleet()
        fleet[VIN_B]["issue_details"][0]["customer_feedback"] = "x" * 1500
        assert save_fleet(fleet).status_code == 200
        state = json.load(open(app_module.FLEET_STATE_JSON_PATH))["vehicles"]
        assert len(state[VIN_B]["issue_details"][0]["customer_feedback"]) == 1000
        assert state[VIN_A]["issue_details"][0]["customer_feedback"] == ""     # optional, empty by default
        assert "—" in app_module.generate_html_report_content(sample_fleet(), "x")


def test_public_feedback_endpoint_is_gone():
    anonymous = TestClient(app)
    body = {"vin": VIN_A, "issue_id": "a1", "feedback": "hello"}
    assert anonymous.post("/api/feedback", json=body).status_code in (404, 405)
    assert anonymous.get("/api/feedback").status_code in (404, 405)


def test_served_report_has_no_public_feedback_form():
    with sandboxed_state():
        report_file = publish_sample()
        served = TestClient(app).get("/" + report_file).text
        assert "<textarea" not in served and "<script" not in served and "Submit" not in served


# ---------------- CSV export ----------------

def test_export_csv_columns_and_rows():
    with sandboxed_state():
        publish_sample()
        assert TestClient(app).get("/api/export_csv").status_code == 401
        fleet = sample_fleet()
        fleet[VIN_A]["issue_details"][0]["rca"] = "=HYPERLINK(\"http://evil\")"
        fleet[VIN_A]["issue_details"][0]["customer_feedback"] = "Thanks, <b>done</b>"
        assert save_fleet(fleet).status_code == 200

        res = client.get("/api/export_csv")
        assert res.status_code == 200 and "text/csv" in res.headers["content-type"]
        assert "attachment" in res.headers["content-disposition"]
        rows = list(csv.reader(io.StringIO(res.text.lstrip("﻿"))))
        assert rows[0] == ["S.No.", "VIN", "Nickname", "Location", "Issue", "Description", "Period",
                           "Occurrences", "Component", "Issue Reported By", "Severity", "RCA",
                           "Responsible Team", "Customer Feedback", "Grafana Link"]
        assert len(rows) == 1 + 8                                    # 2 + 3 + 2 + 1 issues (healthy vehicle excluded)
        first = rows[1]
        assert first[0] == "1" and first[1] == VIN_A and first[2] == "P40 Vehicle" and first[3] == "India"
        assert first[4] == "Issue a1" and first[5] == "Description a1"
        assert first[6] == "29 and 30 September 2026" and first[7] == "2" and first[8] == "BMS"
        assert first[9] == "PTE team" and first[10] == "Low"
        assert first[11].startswith("'=")                            # spreadsheet formulas are neutralised
        assert first[12] == "BMS Team" and first[13] == "Thanks, <b>done</b>"
        assert [r[0] for r in rows[1:]] == [str(i) for i in range(1, 9)]


def test_category_tables_come_before_the_issue_summary():
    out = app_module.get_issue_summary_section(sample_fleet(), "x")
    assert out.index('id="issue-category-summary"') < out.index('id="issue-summary"')
    # old reports (no Component) are unchanged: no category tables at all
    old = {VIN_A: vehicle(VIN_A, "P40 Vehicle", details=[], issues=["BMS fault"])}
    assert 'id="issue-category-summary"' not in app_module.get_issue_summary_section(old, "x")


def test_grafana_link_per_issue():
    with sandboxed_state():
        login()
        fleet = sample_fleet()
        fleet[VIN_A]["issue_details"][0]["grafana_url"] = "https://grafana.bosonmotors.com/d/abc?x=1&y=2"
        fleet[VIN_A]["issue_details"][1]["grafana_url"] = "javascript:alert(1)"      # not allowed
        assert save_fleet(fleet).status_code == 200
        state = json.load(open(app_module.FLEET_STATE_JSON_PATH))["vehicles"][VIN_A]["issue_details"]
        assert state[0]["grafana_url"].startswith("https://grafana.bosonmotors.com/d/abc")
        assert state[1]["grafana_url"] == ""
        html_text = app_module.generate_html_report_content(fleet, "x")
        assert 'href="https://grafana.bosonmotors.com/d/abc?x=1&amp;y=2"' in html_text
        assert "javascript:alert" not in html_text and ">Grafana</th>" in html_text
        rows = list(csv.reader(io.StringIO(client.get("/api/export_csv").text.lstrip("\ufeff"))))
        assert rows[0][-1] == "Grafana Link" and rows[1][-1].startswith("https://grafana")


def test_publishing_a_period_again_replaces_it_and_deleting_old_keeps_new():
    with sandboxed_state():
        login()
        fleet = sample_fleet()
        period = "01-11-2026 to 15-11-2026"
        first = client.post("/api/publish_report", json={"global_duration": period, "vehicles": fleet}).json()["report"]
        time.sleep(1.1)                       # report ids contain the publish time in seconds
        fleet[VIN_A]["issue_details"][0]["issue"] = "Edited issue"
        fleet[VIN_A]["issues"][0] = "Edited issue"
        second = client.post("/api/publish_report", json={"global_duration": period, "vehicles": fleet}).json()["report"]
        listed = [r for r in client.get("/api/reports").json() if r["range"] == period]
        assert len(listed) == 1 and listed[0]["id"] == second["id"]             # no duplicate
        assert "Edited issue" in TestClient(app).get("/" + second["file"]).text
        # deleting the old id must never remove the new report
        client.post("/api/delete_report", json={"report_id": first["id"], "range": period})
        listed = [r for r in client.get("/api/reports").json() if r["range"] == period]
        assert len(listed) == 1
        assert TestClient(app).get("/" + second["file"]).status_code == 200


def test_dashboard_adds_a_typed_but_not_added_issue_when_saving_the_vehicle():
    page = open(os.path.join(PROJECT_DIR, "vehicle_mission_report-4.html"), encoding="utf-8").read()
    assert "typed in the form but not added yet" in page
    assert page.index("typed in the form but not added yet") < page.index("Please add at least one issue if status is set to Issues Detected")


def test_owner_text_cannot_break_the_dashboard_page():
    with sandboxed_state():
        login()
        fleet = {VIN_A: vehicle(VIN_A, "P40 Vehicle", details=[detail("a1", rca="</script><b>x</b>")])}
        assert save_fleet(fleet).status_code == 200
        page = client.get("/owner").text
        assert "</script><b>x</b>" not in page
        state = page[page.index('id="vehicles-json-state">'):]
        state = state[state.index(">") + 1:state.index("</script>")]
        assert json.loads(state)["vehicles"][VIN_A]["issue_details"][0]["rca"] == "</script><b>x</b>"


def test_dashboard_has_new_form_fields_and_export_button():
    login()
    page = client.get("/owner").text
    for element in ("issue-title-input", "issue-description-input", "issue-period-input",
                    "issue-occurrences-input", "issue-component-select", "issue-reported-by-input",
                    "issue-severity-select", "issue-rca-input", "issue-team-input", "issue-grafana-input", "Export CSV"):
        assert element in page
    for option in ("BMS", "Motor", "DCDC", "EPAS", "MDM", "Other", "Low", "Medium", "High", "Critical"):
        assert f'<option value="{option}"' in page
    assert "issue-feedback-input" in page and "Customer Feedback" in page   # typed by the owner


_LEGACY_TESTS = {
    "test_customer_portal_public_access", "test_api_reports_list", "test_owner_portal_protected",
    "test_login_page_renders", "test_login_invalid_credentials", "test_login_valid_and_owner_access",
    "test_publish_mission_report", "test_delete_report", "test_status_endpoint", "test_logo_endpoint",
}

if __name__ == "__main__":
    # Backup active state before test
    orig_state = None
    orig_reports = None
    try:
        with open("fleet_state.json") as f:
            orig_state = json.load(f)
        with open("reports.json") as f:
            orig_reports = json.load(f)
    except Exception:
        pass

    try:
        test_customer_portal_public_access()
        print("✓ Customer Portal Public Access test passed")
        test_logo_endpoint()
        print("✓ Boson Logo Serving test passed")
        test_api_reports_list()
        print("✓ API Reports List test passed")
        test_owner_portal_protected()
        print("✓ Owner Portal Protection test passed")
        test_login_page_renders()
        print("✓ Login Page Renders test passed")
        test_login_invalid_credentials()
        print("✓ Login Invalid Credentials test passed")
        test_login_valid_and_owner_access()
        print("✓ Login Valid and Owner Access test passed")
        test_publish_mission_report()
        print("✓ Publish Mission Report test passed")
        test_delete_report()
        print("✓ Delete Mission Report test passed")
        test_status_endpoint()
        print("✓ Status Endpoint test passed")
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and name not in _LEGACY_TESTS and callable(fn):
                fn()
                print(f"✓ {name} passed")
    finally:
        # Restore active 57-vehicle fleet state
        if orig_state:
            import app
            app.save_state_to_db(orig_state["vehicles"], orig_state["global_duration"])
            app.save_state_to_json(orig_state["vehicles"], orig_state["global_duration"])
            app.save_state_to_builder(orig_state["vehicles"], orig_state["global_duration"])
            app.generate_html_report(orig_state["vehicles"], orig_state["global_duration"])
        if orig_reports:
            import sqlite3
            with open("reports.json", "w", encoding="utf-8") as f:
                json.dump(orig_reports, f, indent=2)
            try:
                conn = sqlite3.connect("fleet_state.db")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM reports")
                for item in orig_reports:
                    v_str = json.dumps(item["vehicles"]) if item.get("vehicles") else None
                    cursor.execute("""
                        INSERT INTO reports (id, label, date_range, sort_date, timestamp, vehicles_count, vehicles_label, file_path, vehicles_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """, (item["id"], item.get("label", ""), item.get("range", ""), item.get("sort_date", ""), item.get("timestamp", ""), item.get("vehicles_count", 0), item.get("vehicles_label", ""), item.get("file", ""), v_str))
                conn.commit()
                conn.close()
            except Exception:
                pass

    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY (State restored to full 57 vehicles)!")
