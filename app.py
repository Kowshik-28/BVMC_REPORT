#!/usr/bin/env python3
"""
Boson Motor - Fleet Mission Reports Customer & Owner Web Application
Converted from existing Fleet Mission Report Generator into a production web app
with a public Customer Portal and a secure Owner Portal.
"""

import os
import sys
import json
import re
import time
import datetime
import hashlib
import secrets
import sqlite3
import uvicorn
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import csv
import io

import issue_report

# Directory paths
DIR_PATH = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(DIR_PATH, "reports")
FLEET_REPORTS_DIR = os.path.join(DIR_PATH, "fleet-mission-reports", "reports")
STATIC_DIR = os.path.join(DIR_PATH, "fleet-mission-reports")
REPORTS_JSON_PATH = os.path.join(DIR_PATH, "reports.json")
FLEET_STATE_JSON_PATH = os.path.join(DIR_PATH, "fleet_state.json")
DB_PATH = os.path.join(DIR_PATH, "fleet_state.db")

# Ensure necessary directories exist
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(FLEET_REPORTS_DIR, exist_ok=True)


def uses_postgres() -> bool:
    db_url = os.environ.get("DATABASE_URL", "")
    return bool(db_url and not db_url.startswith("sqlite"))


# Authentication & Configuration
SECRET_KEY = os.environ.get(
    "SECRET_KEY", "bvmc-boson-secret-key-super-secure-production-2026")
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "admin")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "boson2026")
SESSION_COOKIE_NAME = "bvmc_owner_session"

# Active in-memory session tokens
ACTIVE_SESSIONS = set()

# Predefined Vehicles dictionary (Exact match from original script)
PREDEFINED_VEHICLES = {
    # Non-Autonomous
    "MD9GBUE28DC341009": {"nickname": "Green HC(PST)", "location": "PST", "mode": "Non-Autonomous"},
    "MD9GBUE27DC341051": {"nickname": "P2 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE22DC341054": {"nickname": "P3 Vehicle (P4 to P3)", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE28DC341057": {"nickname": "P4 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE28DC341060": {"nickname": "P5 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE23DC341063": {"nickname": "P6 Vehicle (14-12-2025)", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE25DC341064": {"nickname": "P7 Vehicle", "location": "India", "mode": "Non-Autonomous"},
    "MD9GBUE29DC341066": {"nickname": "P9 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE22DC341068": {"nickname": "P11 Vehicle(IST)", "location": "IST", "mode": "Non-Autonomous"},
    "MD9GBUE20DC341070": {"nickname": "P13 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE22DC341071": {"nickname": "P14 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE28DC341074": {"nickname": "P17 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE2XDC341075": {"nickname": "P18 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE21DC341076": {"nickname": "P19 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE23DC341077": {"nickname": "P20 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE25DC341078": {"nickname": "P21 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE27DC341079": {"nickname": "P22 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE23DC341080": {"nickname": "P23 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE27DC341082": {"nickname": "P25 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE25DC341081": {"nickname": "P24 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE2XFC341001": {"nickname": "P26 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE21FC341002": {"nickname": "P27 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE23FC341003": {"nickname": "P28 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE25FC341004": {"nickname": "P29 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE27FC341005": {"nickname": "P30 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE29FC341006": {"nickname": "P31 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE20FC341007": {"nickname": "P32 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE22FC341008": {"nickname": "P33 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE24FC341009": {"nickname": "P34 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE20FC341010": {"nickname": "P35 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE22FC341011": {"nickname": "P36 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE24FC341012": {"nickname": "P37 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE26FC341013": {"nickname": "P38 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE28FC341014": {"nickname": "P39 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE2XFC341015": {"nickname": "P40 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE21FC341016": {"nickname": "P41 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE23FC341017": {"nickname": "P42 Vehicle (15-12-2025)", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE25FC341018": {"nickname": "P43 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE27FC341019": {"nickname": "P44 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE23FC341020": {"nickname": "P45 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE25FC341021": {"nickname": "P46 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE27FC341022": {"nickname": "P47 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE29FC341023": {"nickname": "P48 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE20FC341024": {"nickname": "P49 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE22FC341025": {"nickname": "P50 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE24FC341026": {"nickname": "P51 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE26FC341027": {"nickname": "P52 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE2XFC341029": {"nickname": "P54 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE26FC341030": {"nickname": "P55 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE28FC341031": {"nickname": "P56 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE2XFC341032": {"nickname": "P57 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE21FC341033": {"nickname": "P58 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE23FC341034": {"nickname": "P59 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE25FC341035": {"nickname": "P60 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE27FC341036": {"nickname": "P61 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE29FC341037": {"nickname": "P62 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE20FC341038": {"nickname": "P63 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE22FC341039": {"nickname": "P64 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE29FC341040": {"nickname": "P65 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE2XDC341027": {"nickname": "T4 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE26DC341039": {"nickname": "T10 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    "MD9GBUE26DC341042": {"nickname": "T11 Vehicle", "location": "Not Available", "mode": "Non-Autonomous"},
    # Autonomous
    "MD9GBUE27DC341003": {"nickname": "US HC Fargo", "location": "Not Available", "mode": "Autonomous"},
    "MD9GBUE22DC341006": {"nickname": "US HC Yuba", "location": "Not Available", "mode": "Autonomous"},
    "MD9GBUE27DC341048": {"nickname": "P1 Vehicle", "location": "Not Available", "mode": "Autonomous"},
    "MD9GBUE24DC341069": {"nickname": "P12 Vehicle", "location": "Not Available", "mode": "Autonomous"},
    "MD9GBUE24DC341072": {"nickname": "P15 Vehicle", "location": "Not Available", "mode": "Autonomous"},
    "MD9GBUE20DC341036": {"nickname": "T7 Vehicle", "location": "Not Available", "mode": "Autonomous"},
    "MD9GBUE25DC341033": {"nickname": "T6 Vehicle", "location": "Not Available", "mode": "Autonomous"},
    "MD9GBUE22DC341037": {"nickname": "T8 Vehicle", "location": "Not Available", "mode": "Autonomous"},
    "MD9GBUE24DC341038": {"nickname": "T9 Vehicle(HMI)", "location": "Not Available", "mode": "Autonomous"},
    "MD9GBUE28FC341028": {"nickname": "P53 Vehicle", "location": "IST", "mode": "Autonomous"},
    "MD9GBUE2XDC341030": {"nickname": "Black Dragon", "location": "Not Available", "mode": "Autonomous"},
    "MD9GBUE28DC341012": {"nickname": "Yellow Dragon", "location": "Not Available", "mode": "Autonomous"}
}


# ==========================================
# DATABASE & PERSISTENCE HELPERS
# ==========================================

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    if uses_postgres():
        import psycopg2
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        if "sslmode=" not in db_url:
            db_url += "&sslmode=require" if "?" in db_url else "?sslmode=require"
        return psycopg2.connect(db_url)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    is_postgres = uses_postgres()

    # 1. fleet_state table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fleet_state (
            id INTEGER PRIMARY KEY,
            global_duration TEXT,
            vehicles_json TEXT
        );
    """)

    # 2. reports table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            label TEXT,
            date_range TEXT,
            sort_date TEXT,
            timestamp TEXT,
            vehicles_count INTEGER,
            vehicles_label TEXT,
            file_path TEXT,
            vehicles_json TEXT,
            report_html TEXT,
            created_at TEXT
        );
    """)

    if is_postgres:
        cursor.execute(
            "ALTER TABLE reports ADD COLUMN IF NOT EXISTS vehicles_json TEXT")
        cursor.execute(
            "ALTER TABLE reports ADD COLUMN IF NOT EXISTS report_html TEXT")
    else:
        cursor.execute("PRAGMA table_info(reports)")
        columns = {row[1] for row in cursor.fetchall()}
        for column in ("vehicles_json", "report_html"):
            if column not in columns:
                cursor.execute(f"ALTER TABLE reports ADD COLUMN {column} TEXT")

    conn.commit()
    conn.close()

    # Ensure initial reports in reports.json are seeded into database if empty
    seed_initial_reports_to_db()


def save_state_to_db(vehicles: dict, global_duration: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    vehicles_json = json.dumps(vehicles)
    is_sqlite = not (os.environ.get("DATABASE_URL") and not os.environ.get(
        "DATABASE_URL").startswith("sqlite"))
    placeholder = "?" if is_sqlite else "%s"

    cursor.execute("SELECT id FROM fleet_state WHERE id = 1")
    if cursor.fetchone():
        query = f"UPDATE fleet_state SET global_duration = {placeholder}, vehicles_json = {placeholder} WHERE id = 1"
        cursor.execute(query, (global_duration, vehicles_json))
    else:
        query = f"INSERT INTO fleet_state (id, global_duration, vehicles_json) VALUES (1, {placeholder}, {placeholder})"
        cursor.execute(query, (global_duration, vehicles_json))

    conn.commit()
    conn.close()


def save_state_to_json(vehicles: dict, global_duration: str):
    try:
        state_data = {
            "global_duration": global_duration,
            "vehicles": vehicles
        }
        with open(FLEET_STATE_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warning: Could not save state to fleet_state.json ({e})")


def load_previous_vehicles() -> dict:
    if uses_postgres():
        try:
            init_db()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT global_duration, vehicles_json FROM fleet_state WHERE id = 1")
            row = cursor.fetchone()
            conn.close()
            if row:
                global_duration, vehicles_json = row
                vehicles = json.loads(vehicles_json) if vehicles_json else {}
                if vehicles:
                    return {"global_duration": global_duration or "", "vehicles": vehicles}
        except Exception as e:
            print(f"⚠️ Warning: Could not load state from database: {e}")
            if uses_postgres():
                raise

    # 1. Try JSON backup file first
    if not uses_postgres() and os.path.exists(FLEET_STATE_JSON_PATH):
        try:
            with open(FLEET_STATE_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "vehicles" in data and data["vehicles"]:
                    try:
                        init_db()
                        save_state_to_db(data.get("vehicles", {}),
                                         data.get("global_duration", ""))
                    except Exception:
                        pass
                    return data
        except Exception as e:
            print(f"⚠️ Warning: Could not load from fleet_state.json: {e}")

    # 2. Try database
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT global_duration, vehicles_json FROM fleet_state WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            global_duration, vehicles_json = row
            vehicles = json.loads(vehicles_json) if vehicles_json else {}
            if vehicles:
                return {"global_duration": global_duration or "", "vehicles": vehicles}
    except Exception as e:
        print(f"⚠️ Warning: Could not load state from database: {e}")

    return {"global_duration": "", "vehicles": {}}


def save_state_to_builder(vehicles: dict, global_duration: str):
    try:
        save_state_to_db(vehicles, global_duration)
    except Exception as e:
        print(f"⚠️ Warning: Could not save state to DB: {e}")
        if uses_postgres():
            raise

    if uses_postgres():
        return

    save_state_to_json(vehicles, global_duration)

    builder_file = os.path.join(DIR_PATH, "vehicle_mission_report-4.html")
    if not os.path.exists(builder_file):
        return

    try:
        with open(builder_file, "r", encoding="utf-8") as f:
            content = f.read()

        state_data = {
            "global_duration": global_duration,
            "vehicles": vehicles
        }
        # "</" is escaped so owner-typed text can never close the <script> block
        json_str = json.dumps(state_data, indent=2).replace("</", "<\\/")

        start_tag = '<script type="application/json" id="vehicles-json-state">'
        end_tag = '</script>'
        start_idx = content.find(start_tag)
        if start_idx != -1:
            end_idx = content.find(end_tag, start_idx)
            if end_idx != -1:
                new_content = (
                    content[:start_idx + len(start_tag)] +
                    "\n  " + json_str + "\n  " +
                    content[end_idx:]
                )
                with open(builder_file, "w", encoding="utf-8") as f:
                    f.write(new_content)
    except Exception as e:
        print(f"⚠️ Warning: Could not save state back to HTML builder ({e})")


# ==========================================
# REPORT LIBRARY MANAGEMENT HELPERS
# ==========================================

def parse_sort_date(date_str: str) -> str:
    """Extract a sortable YYYY-MM-DD date from various date string formats."""
    if not date_str:
        return datetime.date.today().isoformat()

    # Check for YYYY-MM-DD
    matches_iso = re.findall(r'(\d{4})-(\d{2})-(\d{2})', date_str)
    if matches_iso:
        y, m, d = matches_iso[-1]
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"

    # Check for DD-MM-YYYY
    matches_dmy = re.findall(r'(\d{1,2})-(\d{1,2})-(\d{4})', date_str)
    if matches_dmy:
        d, m, y = matches_dmy[-1]
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"

    # Check for YYYY_MM_DD
    matches_und = re.findall(r'(\d{4})_(\d{2})_(\d{2})', date_str)
    if matches_und:
        y, m, d = matches_und[-1]
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"

    return datetime.date.today().isoformat()


def derive_month_label(date_range: str) -> str:
    """Generate a clean friendly label like 'August 2026' from date range."""
    month_names = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]

    # Look for month number and year
    matches_dmy = re.findall(r'(\d{1,2})-(\d{1,2})-(\d{4})', date_range)
    if matches_dmy:
        _, m, y = matches_dmy[0]
        m_int = int(m)
        if 1 <= m_int <= 12:
            return f"{month_names[m_int - 1]} {y}"

    matches_iso = re.findall(r'(\d{4})-(\d{1,2})-(\d{1,2})', date_range)
    if matches_iso:
        y, m, _ = matches_iso[0]
        m_int = int(m)
        if 1 <= m_int <= 12:
            return f"{month_names[m_int - 1]} {y}"

    return date_range if date_range else "Mission Report"


def get_all_reports() -> List[Dict[str, Any]]:
    """Retrieve all reports sorted newest first."""
    reports = []

    # 1. Try DB
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, label, date_range, sort_date, timestamp, vehicles_count, vehicles_label, file_path, vehicles_json FROM reports")
        rows = cursor.fetchall()
        conn.close()

        if rows:
            for r in rows:
                v_data = None
                if len(r) > 8 and r[8]:
                    try:
                        v_data = json.loads(r[8]) if isinstance(
                            r[8], str) else r[8]
                    except Exception:
                        pass
                reports.append({
                    "id": r[0],
                    "label": r[1],
                    "range": r[2],
                    "sort_date": r[3],
                    "timestamp": r[4],
                    "vehicles_count": r[5],
                    "vehicles_label": r[6],
                    "file": r[7],
                    "vehicles": v_data
                })
    except Exception as e:
        print(f"⚠️ Warning: Could not query reports from DB ({e})")
        if uses_postgres():
            raise

    # 2. Fallback to reports.json
    if not reports and os.path.exists(REPORTS_JSON_PATH):
        try:
            with open(REPORTS_JSON_PATH, "r", encoding="utf-8") as f:
                reports = json.load(f)
        except Exception as e:
            print(f"⚠️ Warning: Could not read reports.json ({e})")

    # If vehicles is missing for current active period, attach from fleet_state.json if matching
    if os.path.exists(FLEET_STATE_JSON_PATH):
        try:
            with open(FLEET_STATE_JSON_PATH, "r", encoding="utf-8") as f:
                current_fs = json.load(f)
            fs_range = current_fs.get("global_duration", "").strip()
            fs_vehicles = current_fs.get("vehicles", {})
            for r in reports:
                if not r.get("vehicles") and r.get("range", "").strip() == fs_range:
                    r["vehicles"] = fs_vehicles
        except Exception:
            pass

    # Ensure all report objects have sort_date
    for r in reports:
        if not r.get("sort_date"):
            r["sort_date"] = parse_sort_date(
                r.get("range", "") or r.get("timestamp", ""))

    # Sort descending by sort_date, then timestamp
    reports.sort(key=lambda x: (x.get("sort_date", ""),
                 x.get("timestamp", "")), reverse=True)
    return reports


def save_report_entry(
    report_data: Dict[str, Any],
    vehicles: Optional[dict] = None,
    report_html: Optional[str] = None,
):
    """Save report metadata and content to the database."""
    vehicles_str = None
    v_dict = vehicles or report_data.get("vehicles")
    if v_dict:
        vehicles_str = json.dumps(v_dict) if isinstance(
            v_dict, dict) else str(v_dict)
        report_data["vehicles"] = v_dict

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        is_sqlite = not uses_postgres()
        placeholder = "?" if is_sqlite else "%s"

        # One report per period: publishing a period again replaces the older
        # entry instead of leaving a duplicate that shares the same file.
        cursor.execute(
            f"DELETE FROM reports WHERE date_range = {placeholder} AND id != {placeholder}",
            (report_data["range"], report_data["id"]))

        # Upsert into reports table
        cursor.execute(
            f"SELECT id FROM reports WHERE id = {placeholder}", (report_data["id"],))
        if cursor.fetchone():
            query = f"""
                UPDATE reports SET label = {placeholder}, date_range = {placeholder}, sort_date = {placeholder}, 
                timestamp = {placeholder}, vehicles_count = {placeholder}, vehicles_label = {placeholder}, 
                file_path = {placeholder}, vehicles_json = {placeholder}, report_html = {placeholder},
                created_at = {placeholder} WHERE id = {placeholder}
            """
            cursor.execute(query, (
                report_data["label"], report_data["range"], report_data["sort_date"],
                report_data["timestamp"], report_data["vehicles_count"], report_data["vehicles_label"],
                report_data["file"], vehicles_str, report_html, datetime.datetime.now(
                ).isoformat(), report_data["id"]
            ))
        else:
            query = f"""
                INSERT INTO reports (id, label, date_range, sort_date, timestamp, vehicles_count, vehicles_label, file_path, vehicles_json, report_html, created_at)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """
            cursor.execute(query, (
                report_data["id"], report_data["label"], report_data["range"], report_data["sort_date"],
                report_data["timestamp"], report_data["vehicles_count"], report_data["vehicles_label"],
                report_data["file"], vehicles_str, report_html, datetime.datetime.now(
                ).isoformat()
            ))
        conn.commit()
        conn.close()
    except Exception as db_err:
        print(f"⚠️ Warning: DB save report error ({db_err})")
        raise

    if uses_postgres():
        return

    # Keep the JSON registry in sync for local SQLite deployments.
    try:
        existing_json = []
        if os.path.exists(REPORTS_JSON_PATH):
            with open(REPORTS_JSON_PATH, "r", encoding="utf-8") as f:
                existing_json = json.load(f)

        existing_json = [item for item in existing_json
                         if item.get("id") != report_data["id"] and item.get("range") != report_data["range"]]
        existing_json.append(report_data)

        existing_json.sort(key=lambda x: (
            x.get("sort_date", ""), x.get("timestamp", "")), reverse=True)
        with open(REPORTS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(existing_json, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warning: Could not sync reports.json: {e}")


def delete_report_entry(report_identifier: str) -> bool:
    """Delete a report by id or date range from the database and local files."""
    file_to_delete = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        is_sqlite = not uses_postgres()
        placeholder = "?" if is_sqlite else "%s"
        cursor.execute(f"SELECT file_path FROM reports WHERE id = {placeholder} OR date_range = {placeholder}", (
            report_identifier, report_identifier))
        row = cursor.fetchone()
        if row and row[0]:
            file_to_delete = row[0]
        cursor.execute(f"DELETE FROM reports WHERE id = {placeholder} OR date_range = {placeholder}", (
            report_identifier, report_identifier))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Warning: DB delete report error ({e})")
        if uses_postgres():
            raise

    if uses_postgres():
        return True

    try:
        if os.path.exists(REPORTS_JSON_PATH):
            with open(REPORTS_JSON_PATH, "r", encoding="utf-8") as f:
                existing_json = json.load(f)
            for r in existing_json:
                if (r.get("id") == report_identifier or r.get("range") == report_identifier) and not file_to_delete:
                    file_to_delete = r.get("file")
            new_json = [r for r in existing_json if r.get(
                "id") != report_identifier and r.get("range") != report_identifier]
            with open(REPORTS_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(new_json, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warning: Could not update reports.json on delete: {e}")

    # Remove physical HTML report files from disk, unless another report
    # that is still listed uses the same file
    still_used = False
    if file_to_delete:
        try:
            still_used = any(os.path.basename(r.get("file") or "") == os.path.basename(file_to_delete)
                             for r in get_all_reports())
        except Exception:
            still_used = False
    if file_to_delete and not still_used:
        filename = os.path.basename(file_to_delete)
        for target_dir in [REPORTS_DIR, FLEET_REPORTS_DIR]:
            target_path = os.path.join(target_dir, filename)
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception as e:
                    print(f"⚠️ Warning: Could not delete report file {target_path}: {e}")

    return True


def seed_initial_reports_to_db():
    """Seed existing reports if table is empty."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM reports")
        count = cursor.fetchone()[0]

        if count == 0 and os.path.exists(REPORTS_JSON_PATH):
            with open(REPORTS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                is_sqlite = not uses_postgres()
                placeholder = "?" if is_sqlite else "%s"

                for item in data:
                    v_str = json.dumps(item["vehicles"]) if item.get(
                        "vehicles") else None
                    cursor.execute(
                        f"SELECT id FROM reports WHERE id = {placeholder}", (item["id"],))
                    if cursor.fetchone():
                        continue
                    cursor.execute(f"""
                        INSERT INTO reports (id, label, date_range, sort_date, timestamp, vehicles_count, vehicles_label, file_path, vehicles_json, created_at)
                        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                    """, (
                        item["id"], item.get("label", ""), item.get(
                            "range", ""), item.get("sort_date", ""),
                        item.get("timestamp", ""), item.get(
                            "vehicles_count", 0), item.get("vehicles_label", ""),
                        item.get(
                            "file", ""), v_str, datetime.datetime.now().isoformat()
                    ))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Warning: Could not seed reports into DB: {e}")


# ==========================================
# REPORT GENERATION LOGIC (Preserving 100% Original Logic)
# ==========================================

def get_short_nickname(nickname: str) -> str:
    return issue_report.get_short_nickname(nickname)


def get_issue_summary_section(vehicles: dict, global_duration: str) -> str:
    """Issue Summary table (grouped by Component) plus the Issue Category
    Summary / Data / Telemetry Issues tables.  The logic lives in
    issue_report.py so that every Python copy behaves identically."""
    return issue_report.get_issue_summary_section(vehicles, global_duration)


def compress_html(html: str) -> str:
    html = re.sub(r'<script type="application/json" id="vehicles-json-state-report">.*?</script>',
                  '', html, flags=re.DOTALL)
    lines = [line.strip() for line in html.splitlines() if line.strip()]
    return "\n".join(lines)


def generate_html_report_content(vehicles: dict, global_duration: str) -> str:
    # Clean and align the issue fields (incl. the owner's Customer Feedback)
    vehicles = issue_report.normalize_vehicles(vehicles)
    html_out = """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <title>Fleet Mission Report Summary</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <style type="text/css">
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: #f1f5f9;
      color: #1e293b;
      margin: 0;
      padding: 0;
      -webkit-text-size-adjust: 100%;
      -ms-text-size-adjust: 100%;
    }
    table {
      border-collapse: collapse;
      mso-table-lspace: 0pt;
      mso-table-rspace: 0pt;
    }
    p {
      margin: 0 0 10px 0;
      line-height: 1.5;
    }
    @media only screen and (max-width: 620px) {
      .stack-col {
        display: block !important;
        width: 100% !important;
        padding: 0 0 16px 0 !important;
        box-sizing: border-box !important;
      }
    }
    .vehicle-link {
      color: #2563eb;
      text-decoration: underline;
      text-underline-offset: 3px;
      font-weight: 600;
      cursor: pointer;
    }
    .vehicle-link:hover {
      color: #1d4ed8;
      text-decoration-thickness: 2px;
    }
    .vehicle-link:focus-visible {
      outline: 2px solid #2563eb;
      outline-offset: 3px;
      border-radius: 3px;
    }
  </style>
</head>
<body style="margin: 0; padding: 20px 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">

  <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 800px; background-color: #ffffff; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); overflow: hidden; border: 1px solid #e2e8f0;">
    
    <!-- HEADER -->
    <tr>
      <td bgcolor="#1e293b" style="padding: 30px 24px; text-align: center;">
        <img src="/Boson_logo.png?v=20260826" alt="Boson Motor" style="height: 76px; width: auto; max-width: 320px; object-fit: contain; display: block; margin: 0 auto 14px auto;">
        <p style="margin: 6px 0 0 0; color: #94a3b8; font-size: 14px; font-weight: 500;">Customer Vehicles Mission Report</p>
      </td>
    </tr>
"""

    if not vehicles:
        html_out += """
    <!-- EMPTY STATE -->
    <tr>
      <td style="padding: 40px 24px; text-align: center;">
        <div style="font-size: 48px; margin-bottom: 16px;">🏢</div>
        <h2 style="margin: 0 0 8px 0; font-size: 18px; font-weight: 600; color: #0f172a;">No Vehicles Logged</h2>
        <p style="font-size: 13px; color: #64748b; margin-bottom: 0;">
          Please enter vehicle details to populate this report.
        </p>
      </td>
    </tr>
"""
    else:
        html_out += get_issue_summary_section(vehicles, global_duration)

        has_issue_cards = any(v.get("status") not in [
                              "healthy", "inactive"] for v in vehicles.values())
        if has_issue_cards:
            html_out += """
    <!-- VEHICLE DETAILS SECTION -->
    <tr>
      <td style="padding: 16px 20px; background-color: #fafbfc; border-top: 1px solid #e2e8f0;">
        <h2 style="margin: 0 0 12px 0; font-size: 16px; font-weight: 600; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px;">
          🔍 Detailed Vehicle Diagnostics
        </h2>
"""

            for vin in sorted(vehicles.keys()):
                val = vehicles[vin]
                status_val = val.get("status", "healthy")
                if status_val in ['healthy', 'inactive']:
                    continue

                versions = val.get("versions", {})
                versions_html = ""
                if versions:
                    cells = []
                    for k, v in sorted(versions.items()):
                        if v.strip():
                            cells.append(
                                f'<span style="color: #475569; font-weight: 600;">{k}:</span> <span style="color: #0f172a; margin-right: 15px;">{v}</span>')
                    if cells:
                        joined_cells = " &nbsp;|&nbsp; ".join(cells)
                        versions_html = f"""
                        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; margin-bottom: 8px; font-size: 10px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                          {joined_cells}
                        </div>
                        """

                card_border_color = "#22c55e"
                status_header = '<span style="color: #16a34a; font-weight: bold;">HEALTHY</span>'

                if status_val == 'unhealthy':
                    card_border_color = "#ef4444"
                    status_header = '<span style="color: #dc2626; font-weight: bold;">ISSUE DETECTED</span>'
                elif status_val == 'inactive':
                    card_border_color = "#64748b"
                    status_header = '<span style="color: #64748b; font-weight: bold;">NOT ACTIVE</span>'
                elif status_val == 'mdm_issue':
                    card_border_color = "#ea580c"
                    status_header = '<span style="color: #ea580c; font-weight: bold;">MDM ISSUE</span>'

                if status_val == 'inactive':
                    timestamp_str = val.get("timestamp") or "Not Available"
                    anomalies_section = f"""
                        <div style="background-color: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; color: #475569; font-size: 11px; font-weight: 500;">
                          ⊘ Vehicle is currently Not Active / Not Available. Last active timestamp: <strong>{timestamp_str}</strong>
                        </div>
                    """
                elif status_val == 'mdm_issue':
                    vt_box_time = val.get("vt_box_time") or "Not Available"
                    anomalies_section = f"""
                        <div style="background-color: #fff7ed; border: 1px solid #ffedd5; border-radius: 6px; padding: 12px; color: #c2410c; font-size: 11px; font-weight: 500;">
                          ⚠ MDM Issue: Monitoring flag is True, but no data came. VT_BOX came online at: <strong>{vt_box_time}</strong>
                        </div>
                    """
                    mdm_detail_table = issue_report.build_issue_detail_table(vin, val)
                    if mdm_detail_table:
                        anomalies_section += f'<div style="margin-top: 8px;">{mdm_detail_table}</div>'
                elif issue_report.build_issue_detail_table(vin, val):
                    anomalies_section = issue_report.build_issue_detail_table(vin, val)
                else:
                    table_rows = ""
                    for idx, issue in enumerate(val.get("issues", []), start=1):
                        table_rows += f"""
                        <tr style="border-bottom: 1px solid #e2e8f0;">
                          <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; color: #0f172a; font-family: monospace; text-align: left;">{idx:03d}</td>
                          <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; color: #475569; font-weight: 600; text-align: left;">User Reported</td>
                          <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; color: #0f172a; text-align: left;">{issue}</td>
                          <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; text-align: left;"><span style="display: inline-block; padding: 3px 8px; font-size: 10px; font-weight: bold; border-radius: 12px; background-color: #fee2e2; color: #dc2626; text-transform: uppercase;">Critical</span></td>
                          <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; color: #475569; text-align: left;">Inspect vehicle diagnostics</td>
                        </tr>
                        """
                    anomalies_section = f"""
                        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="font-size: 11px; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;">
                          <thead>
                            <tr bgcolor="#f8fafc">
                              <th style="padding: 8px 10px; font-weight: 600; text-align: left; border-bottom: 1px solid #e2e8f0; color: #475569; width: 45px;">ID</th>
                              <th style="padding: 8px 10px; font-weight: 600; text-align: left; border-bottom: 1px solid #e2e8f0; color: #475569; width: 110px;">System</th>
                              <th style="padding: 8px 10px; font-weight: 600; text-align: left; border-bottom: 1px solid #e2e8f0; color: #475569;">Description</th>
                              <th style="padding: 8px 10px; font-weight: 600; text-align: left; border-bottom: 1px solid #e2e8f0; color: #475569; width: 85px;">Severity</th>
                              <th style="padding: 8px 10px; font-weight: 600; text-align: left; border-bottom: 1px solid #e2e8f0; color: #475569; width: 180px;">Recommended Action</th>
                            </tr>
                          </thead>
                          <tbody style="background-color: #ffffff;">
                            {table_rows}
                          </tbody>
                        </table>
                    """

                dist_val = f"{val['distance']} km" if status_val != 'inactive' else "Nil"
                dur_val = val['duration'] if status_val != 'inactive' else "Nil"

                extra_kpi_row = ""
                if status_val == 'mdm_issue':
                    extra_kpi_row = f"""
                    <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom: 16px;">
                      <tr>
                        <td>
                          <div style="background-color: #fff7ed; border: 1px solid #ffedd5; border-radius: 6px; padding: 10px;">
                            <span style="font-size: 8px; color: #ea580c; text-transform: uppercase; font-weight: bold; display: block; margin-bottom: 2px;">VT_BOX Online Time</span>
                            <span style="font-size: 11px; font-weight: 700; color: #c2410c;">{val.get('vt_box_time', 'Not Available')}</span>
                          </div>
                        </td>
                      </tr>
                    </table>
                    """

                html_out += f"""
            <!-- VEHICLE CARD: {vin} -->
            <div id="vin-{vin}" style="background-color: #ffffff; border: 1px solid #e2e8f0; border-left: 4px solid {card_border_color}; border-radius: 6px; padding: 12px; margin-bottom: 14px; box-shadow: 0 1px 4px rgba(0,0,0,.05);">
              
              <!-- Card Header -->
              <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom: 8px;">
                <tr>
                  <td>
                    <span style="font-size: 14px; font-weight: 700; color: #0f172a; font-family: Courier, monospace;">VIN: {vin}</span>
                    <div style="font-size: 9px; color: #64748b; margin-top: 2px;line-height:1.3;">Nickname: <strong><a href="#vin-{vin}" class="vehicle-link" style="color: #2563eb; text-decoration: underline; text-underline-offset: 3px; font-weight: 600; cursor: pointer;">{val['nickname']}</a></strong> &nbsp;|&nbsp; Location: <strong>{val['location']}</strong></div>
                  </td>
                  <td style="text-align: right; vertical-align: top;">
                    {status_header}
                  </td>
                </tr>
              </table>

              {f'''<div style="margin-bottom: 8px;"><a href="{val.get('grafana_url')}" target="_blank" style="display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px; font-size: 10px; font-weight: 600; color: #ffffff; background-color: #ea580c; border-radius: 4px; text-decoration: none;"><span>📊</span> Open Grafana Telemetry Dashboard ↗</a></div>''' if val.get('grafana_url') else ''}

              <!-- Overview KPI blocks -->
              <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom: 8px;">
                <tr>
                  <td width="25%" style="padding-right: 8px;">
                    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 5px; text-align: center;">
                      <div style="font-size: 6px; color: #64748b; text-transform: uppercase; margin-bottom: 2px;">Vehicle Mode</div>
                      <div style="font-size: 6px; font-weight: 700; color: #1d4ed8;">{val['mode']}</div>
                    </div>
                  </td>
                  <td width="25%" style="padding-left: 4px; padding-right: 4px;">
                    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 5px; text-align: center;">
                      <div style="font-size: 6px; color: #64748b; text-transform: uppercase; margin-bottom: 2px;">Distance Travelled</div>
                      <div style="font-size: 11px; font-weight: 700; color: #0f172a;">{dist_val}</div>
                    </div>
                  </td>
                  <td width="25%" style="padding-left: 4px; padding-right: 4px;">
                    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 5px; text-align: center;">
                      <div style="font-size: 6px; color: #64748b; text-transform: uppercase; margin-bottom: 2px;">Logged Duration</div>
                      <div style="font-size: 11px; font-weight: 700; color: #0f172a;">{dur_val}</div>
                    </div>
                  </td>
                  <td width="25%" style="padding-left: 8px;">
                    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 5px; text-align: center;">
                      <div style="font-size: 5px; color: #64748b; text-transform: uppercase; margin-bottom: 2px;">Total Issues Logged</div>
                      <div style="font-size: 11px; font-weight: 700; color: {'#16a34a' if status_val == 'healthy' else ('#64748b' if status_val == 'inactive' else ('#ea580c' if status_val == 'mdm_issue' else '#dc2626'))};">{len(val.get('issues', []))}</div>
                    </div>
                  </td>
                </tr>
              </table>

              {extra_kpi_row}
              {versions_html}

              <div style="font-size: 11px; font-weight: 600; color: #475569; margin-bottom: 8px; text-transform: uppercase;">⚠️ System Diagnostics & Activity Status</div>
              {anomalies_section}

              <div style="text-align: right; margin-top: 15px;">
                <a href="#issue-summary" style="font-size: 10px; color: #2563eb; text-decoration: none; font-weight: 600;">&uarr; Back to Customer Vehicles Overview</a>
              </div>
            </div>
            """

            html_out += """
      </td>
    </tr>
"""

    html_out += f"""
    <!-- FOOTER -->
    <tr>
      <td bgcolor="#f8fafc" style="padding: 24px; text-align: center; border-top: 1px solid #e2e8f0; color: #64748b; font-size: 12px;">
        <p style="margin: 0;">This email was generated automatically by Boson Vehicle Dashboard Capture Analysis.</p>
        <p style="margin: 4px 0 0 0;">&copy; 2026 Boson Motor Co. All rights reserved.</p>
      </td>
    </tr>

  </table>

</body>
</html>
"""
    return compress_html(html_out)


def generate_html_report(vehicles: dict, global_duration: str) -> str:
    """Generates and saves the standard email HTML report file."""
    dest_file = os.path.join(DIR_PATH, "vehicle_mission_report_email.html")
    compressed_html = generate_html_report_content(vehicles, global_duration)
    with open(dest_file, "w", encoding="utf-8") as f:
        f.write(compressed_html)
    return dest_file


def prepare_vehicles_for_save(vehicles: dict) -> dict:
    """Validate and clean the issue fields sent by the owner dashboard.

    Customer Feedback is typed by the owner and saved with the other fields."""
    problems = issue_report.validate_vehicles(vehicles)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))
    return issue_report.normalize_vehicles(vehicles)


# ==========================================
# FASTAPI APPLICATION SETUP
# ==========================================

app = FastAPI(title="Boson Motor - Fleet Mission Reports Portal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Schemas
class LoginRequest(BaseModel):
    username: str
    password: str


class SaveStateRequest(BaseModel):
    global_duration: str
    vehicles: dict


class PublishReportRequest(BaseModel):
    global_duration: str
    vehicles: dict
    report_label: Optional[str] = None


# Session Authentication Helpers
def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token and token in ACTIVE_SESSIONS:
        return True
    return False


def require_owner_auth(request: Request):
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in to access Owner features."
        )


# ==========================================
# WEB ROUTE HANDLERS
# ==========================================

# 1. Customer Dashboard (Public, No Auth)
@app.get("/", response_class=HTMLResponse)
@app.get("/customer", response_class=HTMLResponse)
async def customer_dashboard():
    index_file = os.path.join(DIR_PATH, "fleet-mission-reports", "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h2>Boson Motor - Customer Portal</h2><p>index.html not found</p>", status_code=404)


# 2. Owner Login Page
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: Optional[str] = None):
    if is_authenticated(request):
        return RedirectResponse(url=next or "/owner", status_code=303)

    login_file = os.path.join(DIR_PATH, "login.html")
    if os.path.exists(login_file):
        with open(login_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h2>Login Page Not Found</h2>", status_code=404)


# 3. Owner Dashboard (Protected, Auth Required)
@app.get("/owner", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
@app.get("/builder", response_class=HTMLResponse)
async def owner_dashboard(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login?next=/owner", status_code=303)

    owner_file = os.path.join(DIR_PATH, "vehicle_mission_report-4.html")
    if os.path.exists(owner_file):
        with open(owner_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Dynamically inject the full saved state from DB / JSON to guarantee the HTML contains the full 57 vehicles!
        try:
            state = load_previous_vehicles()
            if state and state.get("vehicles"):
                state_json_str = json.dumps(state, indent=2).replace("</", "<\\/")
                start_tag = '<script type="application/json" id="vehicles-json-state">'
                end_tag = '</script>'
                start_idx = content.find(start_tag)
                if start_idx != -1:
                    end_idx = content.find(end_tag, start_idx)
                    if end_idx != -1:
                        content = (
                            content[:start_idx + len(start_tag)] +
                            "\n  " + state_json_str + "\n  " +
                            content[end_idx:]
                        )
        except Exception as e:
            print(f"⚠️ Warning during dynamic state injection: {e}")

        return HTMLResponse(content=content)
    return HTMLResponse(content="<h2>Owner Dashboard File Not Found</h2>", status_code=404)


# 3b. Active Fleet State API
@app.get("/api/fleet_state")
async def api_get_fleet_state():
    if uses_postgres():
        init_db()
    state = load_previous_vehicles()
    return JSONResponse(content=state)


# 4. Login API Endpoint
@app.post("/api/login")
async def api_login(req: LoginRequest, response: Response):
    # Verify owner credentials
    if req.username == OWNER_USERNAME and req.password == OWNER_PASSWORD:
        token = secrets.token_hex(32)
        ACTIVE_SESSIONS.add(token)

        response = JSONResponse(
            content={"status": "success", "message": "Authenticated successfully"})
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=86400 * 30  # 30 days
        )
        return response
    else:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"status": "error",
                     "message": "Invalid username or password"}
        )


# 5. Logout Endpoint
@app.get("/logout")
@app.post("/api/logout")
async def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token in ACTIVE_SESSIONS:
        ACTIVE_SESSIONS.remove(token)

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# 6. Customer Reports List API (Public)
@app.get("/api/reports")
async def api_get_reports():
    reports = get_all_reports()
    return JSONResponse(content=reports)


# 7. Publish / Upload Mission Report API (Owner Authenticated)
@app.post("/api/publish_report")
async def api_publish_report(req: PublishReportRequest, request: Request):
    require_owner_auth(request)
    if uses_postgres():
        init_db()

    vehicles = prepare_vehicles_for_save(req.vehicles)
    global_duration = req.global_duration.strip()

    if not vehicles:
        raise HTTPException(
            status_code=400, detail="Vehicle fleet is empty. Please add vehicles before publishing.")

    if not global_duration:
        raise HTTPException(
            status_code=400, detail="Global report duration is required.")

    # 1. Derive date info and filenames
    sort_date = parse_sort_date(global_duration)
    derived_label = req.report_label or derive_month_label(global_duration)

    # Sanitize date string for filename
    clean_date_str = re.sub(r'[^a-zA-Z0-9_-]', '_',
                            global_duration.replace(' to ', '_'))
    filename = f"report_{clean_date_str}.html"

    # Destination file paths
    report_rel_path = f"reports/{filename}"
    report_abs_path = os.path.join(REPORTS_DIR, filename)
    fleet_report_abs_path = os.path.join(FLEET_REPORTS_DIR, filename)

    # 2. Run existing Python report generation process
    report_html = generate_html_report_content(vehicles, global_duration)

    # Vercel's function filesystem is not persistent; store report HTML in Postgres.
    if not uses_postgres():
        with open(report_abs_path, "w", encoding="utf-8") as f:
            f.write(report_html)
        with open(fleet_report_abs_path, "w", encoding="utf-8") as f:
            f.write(report_html)
        with open(os.path.join(DIR_PATH, "vehicle_mission_report_email.html"), "w", encoding="utf-8") as f:
            f.write(report_html)

    # 4. Save state to builder and JSON/DB
    save_state_to_builder(vehicles, global_duration)

    # 5. Format metadata and store report record
    timestamp_str = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " PDT"
    v_count = len(vehicles)
    v_label = f"Customer Fleet ({v_count} Vehicles)" if v_count > 1 else f"{list(vehicles.values())[0].get('nickname', 'Vehicle')}"

    report_id = f"rpt_{int(time.time())}_{clean_date_str}"
    report_record = {
        "id": report_id,
        "label": derived_label,
        "range": global_duration,
        "sort_date": sort_date,
        "timestamp": timestamp_str,
        "vehicles_count": v_count,
        "vehicles_label": v_label,
        "file": report_rel_path
    }

    # Store in database and reports.json
    save_report_entry(report_record, vehicles=vehicles, report_html=report_html)

    return JSONResponse(content={
        "status": "success",
        "message": "Report generated and published successfully to Customer Dashboard!",
        "report": report_record
    })


# 7b. Delete Report API (Owner Authenticated)
class DeleteReportRequest(BaseModel):
    report_id: Optional[str] = None
    range: Optional[str] = None


@app.post("/api/delete_report")
async def api_delete_report(req: DeleteReportRequest, request: Request):
    require_owner_auth(request)
    identifier = req.report_id or req.range
    if not identifier:
        raise HTTPException(
            status_code=400, detail="Missing report_id or range to delete.")
    delete_report_entry(identifier)
    return JSONResponse(content={"status": "success", "message": f"Report '{identifier}' deleted successfully."})


@app.delete("/api/reports/{report_id}")
async def api_delete_report_by_id(report_id: str, request: Request):
    require_owner_auth(request)
    delete_report_entry(report_id)
    return JSONResponse(content={"status": "success", "message": f"Report '{report_id}' deleted successfully."})


# 8. Save State API (Owner Authenticated)
@app.post("/api/save")
async def api_save_state(req: SaveStateRequest, request: Request):
    require_owner_auth(request)
    try:
        if uses_postgres():
            init_db()
        vehicles = prepare_vehicles_for_save(req.vehicles)
        global_duration = req.global_duration

        save_state_to_builder(vehicles, global_duration)
        if not uses_postgres():
            generate_html_report(vehicles, global_duration)

        return JSONResponse(content={"status": "success", "message": "State saved successfully"})
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# 9. Database & System Status API (Public / Owner)
@app.get("/api/status")
async def api_status():
    db_connected = False
    db_error = None
    db_type = "PostgreSQL" if uses_postgres() else "SQLite"
    try:
        conn = get_db_connection()
        conn.close()
        db_connected = True
    except Exception as e:
        db_error = str(e)

    return JSONResponse(content={
        "status": "healthy",
        "database": {
            "connected": db_connected,
            "error": db_error,
            "type": db_type
        }
    })


# 10. Health Check Endpoint
@app.get("/health")
async def health_check():
    return JSONResponse(content={"status": "healthy"})


# 11. Serve static HTML report files
NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/reports/{filename}")
async def serve_report(filename: str):
    if filename == "Boson_logo.png":
        return await serve_logo()

    safe_name = os.path.basename(filename)
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = "%s" if uses_postgres() else "?"
        cursor.execute(
            f"SELECT report_html FROM reports WHERE file_path = {placeholder}",
            (f"reports/{safe_name}",))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return HTMLResponse(content=row[0], headers=NO_CACHE)
    except Exception as e:
        print(f"⚠️ Warning: Could not load report from database: {e}")
        if uses_postgres():
            raise HTTPException(
                status_code=500, detail="Could not load report from database.") from e

    file_path = os.path.join(REPORTS_DIR, safe_name)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="text/html", headers=NO_CACHE)
    fleet_path = os.path.join(FLEET_REPORTS_DIR, safe_name)
    if os.path.exists(fleet_path):
        return FileResponse(fleet_path, media_type="text/html", headers=NO_CACHE)
    raise HTTPException(status_code=404, detail="Report file not found")


# 11b. Owner-only: CSV export of every logged issue
@app.get("/api/export_csv")
async def api_export_csv(request: Request):
    require_owner_auth(request)
    vehicles = load_previous_vehicles().get("vehicles", {})
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(issue_report.CSV_COLUMNS)
    writer.writerows(issue_report.build_csv_rows(vehicles))
    stamp = datetime.date.today().isoformat()
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="vehicle_issues_{stamp}.csv"'})


# 12. Serve Boson Logo
@app.get("/Boson_logo.png")
@app.get("/static/Boson_logo.png")
@app.get("/static/images/Boson_logo.png")
@app.get("/fleet-mission-reports/Boson_logo.png")
@app.get("/reports/Boson_logo.png")
async def serve_logo():
    logo_path = os.path.join(DIR_PATH, "Boson_logo.png")
    if os.path.exists(logo_path):
        return FileResponse(
            logo_path,
            media_type="image/png",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    raise HTTPException(status_code=404, detail="Logo not found")


# Mount static assets if needed
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ==========================================
# MAIN RUNNER
# ==========================================

def startup_init():
    """Initializes DB, restores latest state, and ensures clean environment."""
    print("==========================================================")
    print("    BOSON MOTOR - FLEET MISSION REPORTS WEB APPLICATION   ")
    print("==========================================================")

    init_db()

    try:
        startup_state = load_previous_vehicles()
        if startup_state and startup_state.get("vehicles"):
            save_state_to_builder(startup_state.get(
                "vehicles", {}), startup_state.get("global_duration", ""))
            print(
                f"✅ Loaded active fleet state ({len(startup_state.get('vehicles', {}))} vehicles).")
    except Exception as e:
        print(f"⚠️ Warning during state restoration: {e}")

    reps = get_all_reports()
    print(f"✅ Loaded {len(reps)} published reports in Customer Library.")


def main():
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")

    startup_init()

    print(f"\n🚀 Customer Portal (Public):   http://localhost:{port}/")
    print(f"🔒 Owner Portal (Protected):  http://localhost:{port}/owner")
    print(
        f"🔑 Default Credentials:       Username: {OWNER_USERNAME} | Password: {OWNER_PASSWORD}\n")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
