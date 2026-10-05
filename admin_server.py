"""
InvoicePro Admin Server — Port 8766
------------------------------------
Run:  python admin_server.py
Stop: Ctrl+C in this window

Features:
  • Receives bug reports from user InvoicePro instances (auto-queued, sent when online)
  • Customer management (add, edit, delete, support plan renewals)
  • Full reports/ticket system with reply
  • Revenue tracking
  • SQLite database — data in admin_data/admin.db
  • Serves AdminPanel.html at http://localhost:8766
"""

import base64
import hashlib
import hmac
import html
import http.server
import json
import os
import random
import re
import smtplib
import ssl
import sqlite3
import threading
import time
import traceback
import uuid
import webbrowser
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid
from datetime import datetime, timezone, timedelta, date
from urllib.parse import urlparse, parse_qs, quote

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "admin_data")
DB_PATH   = os.path.join(DATA_DIR, "admin.db")
HR_SMTP_PROFILE_PATH = os.path.join(DATA_DIR, "hr_smtp_profile.json")
HTML_PATH = os.path.join(BASE_DIR, "AdminPanel.html")
PORT      = int(os.environ.get("PORT", 8766))

os.makedirs(DATA_DIR, exist_ok=True)

_db_lock = threading.RLock()


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip() or os.environ.get("POSTGRES_URL", "").strip() or "postgresql://postgres:abiXJrwSDcLZzVWvWRTgAMSGIBVOoyoP@yamanote.proxy.rlwy.net:52510/railway"

class IndexableRow(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._values = list(self.values())
    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)

class PGCursorWrapper:
    def __init__(self, cur, conn):
        self._cur = cur
        self._conn = conn
    def fetchone(self):
        r = self._cur.fetchone()
        return IndexableRow(r) if r is not None else None
    def fetchall(self):
        rows = self._cur.fetchall()
        return [IndexableRow(r) for r in rows]
    @property
    def rowcount(self):
        return self._cur.rowcount
    @property
    def description(self):
        return self._cur.description
    def close(self):
        try: self._cur.close()
        except Exception: pass

class PGDatabaseWrapper:
    def __init__(self, pg_conn):
        self.conn = pg_conn
    def execute(self, sql, params=None):
        if sql.strip().upper().startswith("PRAGMA"):
            cur = self.conn.cursor()
            cur.execute("SELECT 1")
            return PGCursorWrapper(cur, self.conn)
        sql_trans = self._transform(sql)
        import psycopg2.extras
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if params is not None:
            cur.execute(sql_trans, params)
        else:
            cur.execute(sql_trans)
        return PGCursorWrapper(cur, self.conn)
    def executemany(self, sql, params_list):
        if sql.strip().upper().startswith("PRAGMA"):
            cur = self.conn.cursor()
            cur.execute("SELECT 1")
            return PGCursorWrapper(cur, self.conn)
        sql_trans = self._transform(sql)
        import psycopg2.extras
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.executemany(sql_trans, params_list)
        return PGCursorWrapper(cur, self.conn)
    def executescript(self, sql_script):
        cur = self.conn.cursor()
        for statement in sql_script.split(';'):
            s = statement.strip()
            if s:
                try:
                    cur.execute(self._transform(s))
                except Exception:
                    try: self.conn.rollback()
                    except Exception: pass
        try: self.conn.commit()
        except Exception: pass
        try: cur.close()
        except Exception: pass
    def commit(self):
        try: self.conn.commit()
        except Exception: pass
    def rollback(self):
        try: self.conn.rollback()
        except Exception: pass
    def close(self):
        try: self.conn.close()
        except Exception: pass
    def _transform(self, sql):
        if sql.strip().upper().startswith("PRAGMA"):
            return "SELECT 1"
        # Remove SQLite-specific collation that causes syntax errors in PostgreSQL
        sql = re.sub(r'\s+COLLATE\s+BINARY\b', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\s+COLLATE\s+NOCASE\b', '', sql, flags=re.IGNORECASE)
        # Transform INSERT OR IGNORE INTO to INSERT INTO ... ON CONFLICT DO NOTHING
        if re.search(r'INSERT\s+OR\s+IGNORE\s+INTO', sql, re.IGNORECASE):
            sql = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO\s+', 'INSERT INTO ', sql, flags=re.IGNORECASE)
            sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
        # Transform INSERT OR REPLACE INTO to INSERT INTO ... ON CONFLICT (pk) DO UPDATE SET ...
        m = re.search(r'INSERT\s+OR\s+REPLACE\s+INTO\s+([a-zA-Z0-9_]+)\s*\(([^)]+)\)\s*VALUES\s*(?:\([^)]+\)|%s|\?)', sql, re.IGNORECASE | re.DOTALL)
        if m:
            tbl = m.group(1)
            cols_raw = m.group(2)
            cols = [c.strip() for c in cols_raw.split(',') if c.strip()]
            pk = cols[0]
            update_clauses = [f'{c}=EXCLUDED.{c}' for c in cols if c != pk]
            update_str = ', '.join(update_clauses) if update_clauses else f'{pk}=EXCLUDED.{pk}'
            sql = re.sub(r'INSERT\s+OR\s+REPLACE\s+INTO\s+', 'INSERT INTO ', sql, flags=re.IGNORECASE)
            sql = sql.rstrip().rstrip(';') + f' ON CONFLICT ({pk}) DO UPDATE SET {update_str}'
        return sql.replace('?', '%s')


class SQLiteDatabaseWrapper:
    def __init__(self, conn):
        self.conn = conn
    def execute(self, sql, params=None):
        if params is not None:
            return self.conn.execute(sql, params)
        return self.conn.execute(sql)
    def executemany(self, sql, params_list):
        return self.conn.executemany(sql, params_list)
    def executescript(self, sql):
        return self.conn.executescript(sql)
    def cursor(self):
        return self.conn.cursor()
    def commit(self):
        try:
            self.conn.commit()
        except Exception:
            pass
    def rollback(self):
        try:
            self.conn.rollback()
        except Exception:
            pass
    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
    @property
    def row_factory(self):
        return self.conn.row_factory
    @row_factory.setter
    def row_factory(self, val):
        self.conn.row_factory = val
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# ── Database ──────────────────────────────────────────────────────────────────
def get_db():
    if DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")):
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = True
            return PGDatabaseWrapper(conn)
        except Exception as e:
            print(f"  [DB] PostgreSQL connect failed ({e}), falling back to SQLite.")

    conn = sqlite3.connect(DB_PATH, timeout=60.0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA wal_autocheckpoint=100")
    except Exception:
        pass
    return SQLiteDatabaseWrapper(conn)


def init_db():
    with _db_lock:
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
                id                   TEXT PRIMARY KEY,
                name                 TEXT NOT NULL DEFAULT '',
                owner                TEXT DEFAULT '',
                city                 TEXT DEFAULT '',
                currency             TEXT DEFAULT 'INR',
                email                TEXT DEFAULT '',
                phone                TEXT DEFAULT '',
                license_key          TEXT DEFAULT '',
                purchase_date        TEXT DEFAULT '',
                purchase_amount      REAL DEFAULT 1499,
                support_purchased    INTEGER DEFAULT 0,
                support_purchase_date TEXT DEFAULT '',
                support_amount       REAL DEFAULT 499,
                notes                TEXT DEFAULT '',
                plan_end_date        TEXT DEFAULT '',
                trial_end_date       TEXT DEFAULT '',
                created_at           TEXT DEFAULT '',
                updated_at           TEXT DEFAULT ''
            );
                        CREATE TABLE IF NOT EXISTS recurring_issues (
                id                   TEXT PRIMARY KEY,
                issue                TEXT NOT NULL,
                category             TEXT NOT NULL,
                severity             TEXT NOT NULL DEFAULT 'High',
                impacted_count       INTEGER NOT NULL DEFAULT 1,
                workaround           TEXT NOT NULL,
                root_cause           TEXT DEFAULT '',
                status               TEXT NOT NULL DEFAULT 'Open',
                dev_bug_id           TEXT DEFAULT '',
                created_by_id        TEXT DEFAULT '',
                created_by_name      TEXT DEFAULT '',
                created_at           TEXT NOT NULL,
                updated_at           TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS support_renewals (
                id          TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                date        TEXT NOT NULL,
                amount      REAL DEFAULT 499,
                added_at    TEXT DEFAULT '',
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS employees (
                id          TEXT PRIMARY KEY,
                emp_id      TEXT UNIQUE NOT NULL,
                name        TEXT NOT NULL DEFAULT '',
                mobile      TEXT DEFAULT '',
                email       TEXT DEFAULT '',
                designation TEXT DEFAULT '',
                department  TEXT DEFAULT '',
                join_date   TEXT DEFAULT '',
                notes       TEXT DEFAULT '',
                extra_data  TEXT DEFAULT '{}',
                created_at  TEXT DEFAULT '',
                updated_at  TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS employee_sales (
                id            TEXT PRIMARY KEY,
                employee_id   TEXT NOT NULL,
                customer_name TEXT DEFAULT '',
                date          TEXT DEFAULT '',
                amount        REAL DEFAULT 499,
                commission    REAL DEFAULT 100,
                note          TEXT DEFAULT '',
                created_at    TEXT DEFAULT '',
                FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS employee_payments (
                id          TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL,
                date        TEXT DEFAULT '',
                amount      REAL DEFAULT 0,
                note        TEXT DEFAULT '',
                created_at  TEXT DEFAULT '',
                FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reports (
                id            TEXT PRIMARY KEY,
                customer_id   TEXT DEFAULT '',
                license_key   TEXT DEFAULT '',
                category      TEXT DEFAULT 'General',
                message       TEXT NOT NULL DEFAULT '',
                contact_email TEXT DEFAULT '',
                app_version   TEXT DEFAULT '',
                os_info       TEXT DEFAULT '',
                status        TEXT DEFAULT 'open',
                reply         TEXT DEFAULT '',
                replied_at    TEXT DEFAULT '',
                created_at    TEXT DEFAULT '',
                source        TEXT DEFAULT 'api'
            );
            CREATE TABLE IF NOT EXISTS enquiries (
                id          TEXT PRIMARY KEY,
                customer_id TEXT DEFAULT '',
                date        TEXT DEFAULT '',
                message     TEXT DEFAULT '',
                reply       TEXT DEFAULT '',
                status      TEXT DEFAULT 'open',
                created_at  TEXT DEFAULT '',
                resolved_at TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS staff_users (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL DEFAULT '',
                username    TEXT UNIQUE NOT NULL,
                password    TEXT NOT NULL DEFAULT '',
                role        TEXT NOT NULL DEFAULT 'sales',
                email       TEXT DEFAULT '',
                phone       TEXT DEFAULT '',
                emp_id      TEXT DEFAULT '',
                active      INTEGER DEFAULT 1,
                created_at  TEXT DEFAULT '',
                last_login  TEXT DEFAULT '',
                extra_data  TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS leave_requests (
                id             TEXT PRIMARY KEY,
                employee_id    TEXT DEFAULT '',
                employee_name  TEXT NOT NULL DEFAULT '',
                role           TEXT DEFAULT '',
                leave_type     TEXT DEFAULT 'casual',
                from_date      TEXT NOT NULL DEFAULT '',
                to_date        TEXT NOT NULL DEFAULT '',
                days           REAL DEFAULT 1,
                reason         TEXT DEFAULT '',
                status         TEXT DEFAULT 'pending',
                reviewed_by    TEXT DEFAULT '',
                reviewed_at    TEXT DEFAULT '',
                created_at     TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS hr_candidates (
                id                      TEXT PRIMARY KEY,
                name                    TEXT NOT NULL DEFAULT '',
                email                   TEXT DEFAULT '',
                phone                   TEXT DEFAULT '',
                role_applied            TEXT DEFAULT '',
                experience              TEXT DEFAULT '',
                source_type             TEXT DEFAULT 'self_connected',
                referral_code           TEXT DEFAULT '',
                referrer_name           TEXT DEFAULT '',
                referrer_phone          TEXT DEFAULT '',
                referrer_emp_id         TEXT DEFAULT '',
                hr_round_status         TEXT DEFAULT 'pending',
                hr_notes                TEXT DEFAULT '',
                interview_scheduled_at  TEXT DEFAULT '',
                interview_interviewer   TEXT DEFAULT '',
                interview_meet_link     TEXT DEFAULT '',
                manager_round_status    TEXT DEFAULT 'pending',
                manager_notes           TEXT DEFAULT '',
                onboarding_status       TEXT DEFAULT 'pending',
                offer_response_status   TEXT DEFAULT '',
                decline_reason          TEXT DEFAULT '',
                offered_designation     TEXT DEFAULT '',
                offered_ctc             TEXT DEFAULT '',
                joining_date            TEXT DEFAULT '',
                resume_filename         TEXT DEFAULT '',
                resume_data             TEXT DEFAULT '',
                resume_size             TEXT DEFAULT '',
                resume_text             TEXT DEFAULT '',
                created_at              TEXT DEFAULT '',
                updated_at              TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS hr_jobs (
                id                   TEXT PRIMARY KEY,
                title                TEXT NOT NULL DEFAULT '',
                department           TEXT DEFAULT 'Sales',
                vacancies            INTEGER DEFAULT 1,
                job_type             TEXT DEFAULT 'Full-Time',
                experience_required  TEXT DEFAULT '1-3 Years',
                status               TEXT DEFAULT 'open',
                created_at           TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS hr_grievances (
                id               TEXT PRIMARY KEY,
                title            TEXT NOT NULL DEFAULT '',
                employee_name    TEXT NOT NULL DEFAULT '',
                employee_id      TEXT DEFAULT '',
                department       TEXT DEFAULT '',
                category         TEXT DEFAULT 'General',
                description      TEXT DEFAULT '',
                status           TEXT DEFAULT 'open',
                resolution_notes TEXT DEFAULT '',
                created_at       TEXT DEFAULT '',
                updated_at       TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS hr_training (
                id              TEXT PRIMARY KEY,
                title           TEXT NOT NULL DEFAULT '',
                trainer         TEXT DEFAULT '',
                schedule_date   TEXT DEFAULT '',
                duration        TEXT DEFAULT '1 Hour',
                enrolled_count  INTEGER DEFAULT 0,
                topics          TEXT DEFAULT '',
                status          TEXT DEFAULT 'upcoming',
                created_at      TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS hr_goals (
                id               TEXT PRIMARY KEY,
                employee_id      TEXT DEFAULT '',
                employee_name    TEXT NOT NULL DEFAULT '',
                goal_title       TEXT NOT NULL DEFAULT '',
                target_metric    TEXT DEFAULT '',
                progress_percent INTEGER DEFAULT 0,
                appraisal_score  REAL DEFAULT 0,
                reviewer_notes   TEXT DEFAULT '',
                quarter          TEXT DEFAULT 'Q1',
                status           TEXT DEFAULT 'in_progress',
                created_at       TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS teams (
                id               TEXT PRIMARY KEY,
                dept_id          TEXT DEFAULT '',
                name             TEXT NOT NULL DEFAULT '',
                code             TEXT DEFAULT '',
                lead_name        TEXT DEFAULT '',
                lead_phone       TEXT DEFAULT '',
                lead_email       TEXT DEFAULT '',
                members          TEXT DEFAULT '[]',
                headcount        INTEGER DEFAULT 0,
                targetMonthly    REAL DEFAULT 0,
                progress         REAL DEFAULT 0,
                focus_area       TEXT DEFAULT '',
                created_at       TEXT DEFAULT '',
                updated_at       TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS checkout_orders (
                id                      TEXT PRIMARY KEY,
                order_id                TEXT UNIQUE NOT NULL,
                customer_id             TEXT DEFAULT '',
                customer_name           TEXT NOT NULL DEFAULT '',
                customer_email          TEXT DEFAULT '',
                customer_phone          TEXT DEFAULT '',
                city                    TEXT DEFAULT '',
                plan_name               TEXT NOT NULL DEFAULT 'Standard License',
                plan_duration_years     INTEGER DEFAULT 1,
                amount                  REAL NOT NULL DEFAULT 1499,
                currency                TEXT DEFAULT 'INR',
                payment_status          TEXT NOT NULL DEFAULT 'completed',
                payment_method          TEXT DEFAULT 'Razorpay / Sylivion Checkout',
                transaction_id          TEXT DEFAULT '',
                emp_id                  TEXT DEFAULT '',
                emp_name                TEXT DEFAULT '',
                commission_calculated   REAL DEFAULT 0,
                license_key_generated   TEXT DEFAULT '',
                checkout_source         TEXT DEFAULT 'Sylivion Checkout',
                raw_payload             TEXT DEFAULT '{}',
                created_at              TEXT NOT NULL,
                updated_at              TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dev_tasks (
                id             TEXT PRIMARY KEY,
                title          TEXT NOT NULL DEFAULT '',
                description    TEXT DEFAULT '',
                category       TEXT DEFAULT 'Bug',
                priority       TEXT DEFAULT 'High',
                status         TEXT DEFAULT 'todo',
                assignee_id    TEXT DEFAULT '',
                assignee_name  TEXT DEFAULT '',
                dev_notes      TEXT DEFAULT '',
                branch_name    TEXT DEFAULT '',
                pr_link        TEXT DEFAULT '',
                due_date       TEXT DEFAULT '',
                created_by_id  TEXT DEFAULT '',
                created_by_name TEXT DEFAULT '',
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dev_releases (
                id             TEXT PRIMARY KEY,
                version        TEXT NOT NULL UNIQUE,
                title          TEXT NOT NULL DEFAULT '',
                release_date   TEXT DEFAULT '',
                status         TEXT DEFAULT 'draft',
                features_json  TEXT DEFAULT '[]',
                fixes_json     TEXT DEFAULT '[]',
                notes          TEXT DEFAULT '',
                download_url   TEXT DEFAULT '',
                created_by     TEXT DEFAULT '',
                created_at     TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id             TEXT PRIMARY KEY,
                user_id        TEXT DEFAULT '',
                user_name      TEXT DEFAULT '',
                role           TEXT DEFAULT '',
                action         TEXT NOT NULL,
                module         TEXT DEFAULT 'General',
                details        TEXT DEFAULT '',
                ip_address     TEXT DEFAULT '',
                timestamp      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity_logs (
                id             TEXT PRIMARY KEY,
                employee_id    TEXT DEFAULT '',
                employee_name  TEXT DEFAULT '',
                activity_type  TEXT DEFAULT 'call',
                target_contact TEXT DEFAULT '',
                details        TEXT DEFAULT '',
                extra_data     TEXT DEFAULT '{}',
                created_at     TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS license_keys (
                id             TEXT PRIMARY KEY,
                license_key    TEXT UNIQUE NOT NULL,
                customer_id    TEXT DEFAULT '',
                customer_name  TEXT DEFAULT '',
                plan_name      TEXT DEFAULT 'Standard Plan',
                duration_years INTEGER DEFAULT 1,
                status         TEXT DEFAULT 'active',
                generated_by   TEXT DEFAULT 'system',
                expiry_date    TEXT DEFAULT '',
                created_at     TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS system_settings (
                key            TEXT PRIMARY KEY,
                value          TEXT NOT NULL DEFAULT '',
                category       TEXT DEFAULT 'general',
                updated_at     TEXT DEFAULT ''
            );

        """)
        # Ensure customer table columns for sales attribution, checkout tracking, GSTIN & commission
        for col in ["sold_by_emp_id", "sold_by_emp_name", "sales_person", "added_by", "plan_label", "payment_method", "transaction_id", "checkout_source", "status", "order_id", "gstin"]:
            try:
                db.execute(f"ALTER TABLE customers ADD COLUMN {col} TEXT DEFAULT ''")
            except Exception:
                pass

        # Ensure employee_sales table columns for comprehensive employee attribution
        for col in ["emp_id", "customer_id", "plan_name", "status", "target_month"]:
            try:
                db.execute(f"ALTER TABLE employee_sales ADD COLUMN {col} TEXT DEFAULT ''")
            except Exception:
                pass

        # Ensure activity_logs and audit_logs columns
        for col in ["extra_data"]:
            try:
                db.execute(f"ALTER TABLE activity_logs ADD COLUMN {col} TEXT DEFAULT '{{}}'")
            except Exception:
                pass
            try:
                db.execute(f"ALTER TABLE audit_logs ADD COLUMN {col} TEXT DEFAULT '{{}}'")
            except Exception:
                pass

        # Ensure enquiries table columns for support leader claiming, assignment, and resolution audit
        for col in [
            "subject", "priority", "channel", "customer_name", "customer_phone",
            "claimed_by_leader_id", "claimed_by_leader_name", "claimed_team_id", "claimed_team_name", "claimed_at",
            "assigned_member_id", "assigned_member_name", "assigned_at",
            "resolved_by_member_name", "resolved_by_leader_name", "resolved_by_team"
        ]:
            try:
                db.execute(f"ALTER TABLE enquiries ADD COLUMN {col} TEXT DEFAULT ''")
            except Exception:
                pass
        db.commit()

        # Backfill customer sales attribution from notes if empty & ensure 10% employee_sales
        try:
            cust_rows = db.execute("SELECT id, name, purchase_amount, purchase_date, notes, sold_by_emp_id, sold_by_emp_name, sales_person FROM customers").fetchall()
            for crow in cust_rows:
                cid, cname, camt, cdate, cnotes, csold_id, csold_name, csales_person = crow
                csold_id = (csold_id or '').strip()
                csold_name = (csold_name or '').strip()
                csales_person = (csales_person or '').strip()
                if not csold_id or not csold_name:
                    m = re.search(r'EMP:\s*([A-Za-z0-9\-]+)(?:\s*\(([^)]+)\))?', cnotes or '')
                    if m:
                        emp_code = m.group(1).strip()
                        emp_n = m.group(2).strip() if m.group(2) else ''
                        emp_row = db.execute("SELECT id, name, emp_id FROM employees WHERE emp_id=? OR id=? OR name=?", (emp_code, emp_code, emp_n or emp_code)).fetchone()
                        if emp_row:
                            csold_id = emp_row["emp_id"]
                            csold_name = emp_row["name"]
                            csales_person = emp_row["name"]
                            db.execute("UPDATE customers SET sold_by_emp_id=?, sold_by_emp_name=?, sales_person=? WHERE id=?",
                                       (csold_id, csold_name, csales_person, cid))
                
                # If assigned to an employee, ensure employee_sales row exists
                if csold_id or csold_name or csales_person:
                    emp_row = None
                    if csold_id:
                        emp_row = db.execute("SELECT id, name, emp_id FROM employees WHERE emp_id=? OR id=?", (csold_id, csold_id)).fetchone()
                    if not emp_row and csold_name:
                        emp_row = db.execute("SELECT id, name, emp_id FROM employees WHERE name=?", (csold_name,)).fetchone()
                    if not emp_row and csales_person:
                        emp_row = db.execute("SELECT id, name, emp_id FROM employees WHERE name=? OR emp_id=?", (csales_person, csales_person)).fetchone()
                    
                    if emp_row:
                        emp_db_id = emp_row["id"]
                        amt = float(camt or 1499.0)
                        if amt <= 0: amt = 1499.0
                        existing_sale = db.execute("SELECT id FROM employee_sales WHERE employee_id=? AND (LOWER(TRIM(customer_name))=? OR note LIKE ?)", 
                                                   (emp_db_id, cname.strip().lower(), f"%{cid}%")).fetchone()
                        if not existing_sale:
                            sale_id = new_id()
                            comm = calculate_plan_commission('', amt, cnotes)
                            sdate = (cdate or now_iso()[:10])[:10]
                            db.execute("INSERT INTO employee_sales (id, employee_id, date, customer_name, amount, commission, note, created_at) VALUES (?,?,?,?,?,?,?,?)",
                                       (sale_id, emp_db_id, sdate, cname, amt, comm, f"Customer Account: {cname} ({cid})", now_iso()))
            # Clean up duplicate sales in employee_sales so each employee has at most 1 sale entry per customer
            sales_all = db.execute("SELECT id, employee_id, customer_name, note, date, created_at FROM employee_sales ORDER BY created_at DESC, id DESC").fetchall()
            seen_emp_cust = set()
            for s in sales_all:
                cname_clean = (s["customer_name"] or "").strip().lower()
                emp_key = (s["employee_id"], cname_clean)
                if cname_clean and emp_key in seen_emp_cust:
                    db.execute("DELETE FROM employee_sales WHERE id=?", (s["id"],))
                else:
                    if cname_clean:
                        seen_emp_cust.add(emp_key)
            db.commit()
        except Exception:
            pass

        # Seed default Admin and initial role users if staff_users table is empty
        try:
            count = db.execute("SELECT COUNT(*) FROM staff_users").fetchone()[0]
            now_str = datetime.now().isoformat()
            default_users = [
                ("usr-admin-001", "Master Administrator", "admin", "admin123", "admin", "admin@invoicepro.local", "9322731612", "", 1, now_str),
                ("usr-mgr-001", "Operations Manager", "manager", "manager123", "manager", "manager@invoicepro.local", "", "", 1, now_str),
                ("usr-slead-001", "Sales Team Leader", "sales_lead", "sales123", "sales_leader", "saleslead@invoicepro.local", "", "", 1, now_str),
                ("usr-sales-001", "Senior Sales Executive", "sales", "sales123", "sales_member", "sales@invoicepro.local", "", "", 1, now_str),
                ("usr-suplead-001", "Support Team Leader", "support_lead", "support123", "support_leader", "supportlead@invoicepro.local", "", "", 1, now_str),
                ("usr-sup-alias", "Support Specialist", "support", "support123", "support_leader", "support@invoicepro.local", "", "", 1, now_str),
                ("usr-supmem-001", "Technical Support Specialist", "support_mem", "support123", "support_member", "supportmem@invoicepro.local", "", "", 1, now_str),
                ("usr-devlead-001", "Development Team Leader", "dev_lead", "dev123", "dev_leader", "devlead@invoicepro.local", "", "", 1, now_str),
                ("usr-dev-001", "Senior Frontend Engineer", "dev_front", "dev123", "dev_member", "devfront@invoicepro.local", "", "", 1, now_str),
            ]
            db.executemany("""
                INSERT OR IGNORE INTO staff_users (id, name, username, password, role, email, phone, emp_id, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, default_users)
            db.commit()

            # Ensure support, sales, dev roles are correctly normalized and not mapped to sales
            db.execute("UPDATE staff_users SET role='support_leader', department='Support', designation='Support Team Leader' WHERE username IN ('support_lead', 'support')")
            db.execute("UPDATE staff_users SET role='support_member', department='Support', designation='Technical Support Specialist' WHERE username IN ('support_mem', 'support_priya', 'support_rahul', 'sarah_support')")
            db.execute("UPDATE staff_users SET role='sales_leader', department='Sales', designation='Sales Team Leader' WHERE username IN ('sales_lead')")
            db.execute("UPDATE staff_users SET role='sales_member', department='Sales', designation='Senior Sales Executive' WHERE username IN ('sales', 'sales2')")
            db.execute("UPDATE staff_users SET role='dev_leader', department='Development', designation='Development Team Leader' WHERE username IN ('dev_lead', 'dev')")
            db.execute("UPDATE staff_users SET role='dev_member', department='Development', designation='Senior Frontend Engineer' WHERE username IN ('dev_front', 'dev_back', 'dev_flutter', 'dev_qa')")
            
            # Clean up legacy default HR user if present so only manager-created HR employees exist
            db.execute("DELETE FROM staff_users WHERE id='usr-hr-001' OR (username='hr' AND (name='HR Manager' OR name='Pooja Deshmukh'))")
            db.commit()
        except Exception as seed_err:
            print(f"  [Seed Notice] {seed_err}")
        
        
        # Seed initial HR demo data if hr_candidates is empty
        try:
            cand_count = db.execute("SELECT COUNT(*) FROM hr_candidates").fetchone()[0]
            if cand_count == 0:
                now_str = now_iso()
                sample_candidates = [
                    ("can-101", "Aarav Mehta", "aarav.m@example.com", "9876543210", "Senior Sales Executive", "3 Years in B2B SaaS", "self_connected", "", "", "", "", "passed", "Clear communication, verified background, salary expectation aligned.", "2026-09-05 11:00 AM", "Operations Manager", "Google Meet (meet.google.com/inv-meet)", "pending", "", "pending", "Senior Sales Executive", "₹4,80,000 / annum", "2026-09-15", now_str, now_str),
                    ("can-102", "Pooja Verma", "pooja.v@example.com", "9823112233", "Customer Support Specialist", "2 Years Call & Chat Support", "referral_known", "REF-KP-8492", "Ramesh Verma (Partner)", "9811223344", "", "passed", "Excellent empathy, clear voice, positive attitude.", "2026-09-06 02:30 PM", "Support Lead", "Office Room 2", "passed", "Strong customer focus, passed technical test.", "joining_sent", "Customer Support Specialist", "₹3,60,000 / annum", "2026-09-12", now_str, now_str),
                    ("can-103", "Karan Sharma", "karan.s@example.com", "9845001122", "Field Sales Consultant", "1 Year Retail POS Sales", "referral_employee", "", "Amit Roy", "", "EMP-001", "pending", "Resume under screening.", "", "", "", "pending", "", "pending", "", "", "", now_str, now_str),
                ]
                db.executemany("""
                    INSERT OR IGNORE INTO hr_candidates (
                        id, name, email, phone, role_applied, experience, source_type, referral_code, referrer_name, referrer_phone, referrer_emp_id,
                        hr_round_status, hr_notes, interview_scheduled_at, interview_interviewer, interview_meet_link,
                        manager_round_status, manager_notes, onboarding_status, offered_designation, offered_ctc, joining_date, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, sample_candidates)

                sample_jobs = [
                    ("job-101", "Sales Executive", "Sales", 3, "Full-Time", "1-3 Years in Direct Sales", "open", now_str),
                    ("job-102", "Customer Support Specialist", "Support", 2, "Full-Time", "1+ Year in Technical Support", "open", now_str),
                    ("job-103", "Operations Assistant", "Operations", 1, "Full-Time", "2+ Years Admin / Operations", "open", now_str),
                ]
                db.executemany("""
                    INSERT OR IGNORE INTO hr_jobs (id, title, department, vacancies, job_type, experience_required, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, sample_jobs)

                sample_grievances = [
                    ("grv-101", "Workstation Display Glitch", "Amit Roy", "EMP-001", "Sales", "Equipment / Facilities", "Primary workstation monitor flickering during client calls.", "resolved", "Replaced monitor HDMI cable and display adapter. Issue resolved.", now_str, now_str),
                    ("grv-102", "Shift Handover Scheduling", "Pooja Verma", "EMP-002", "Support", "Work Environment", "Requested 15-minute overlap period during afternoon shift change.", "under_review", "HR reviewing with Operations Manager to adjust roster.", now_str, now_str)
                ]
                db.executemany("""
                    INSERT OR IGNORE INTO hr_grievances (id, title, employee_name, employee_id, department, category, description, status, resolution_notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, sample_grievances)

                sample_training = [
                    ("trn-101", "InvoicePro Enterprise Product Mastery", "Product Manager", "2026-09-10 10:30 AM", "2 Hours", 5, "Keygen flows, invoice templates, offline database sync, and client FAQs", "upcoming", now_str),
                    ("trn-102", "POSH & Anti-Harassment Compliance", "HR Director", "2026-09-18 03:00 PM", "1.5 Hours", 12, "Workplace ethics, POSH regulations, respectful communication, and reporting channels", "upcoming", now_str)
                ]
                db.executemany("""
                    INSERT OR IGNORE INTO hr_training (id, title, trainer, schedule_date, duration, enrolled_count, topics, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, sample_training)

                sample_goals = [
                    ("gol-101", "EMP-001", "Amit Roy", "Achieve Monthly Sales Target", "Close 15 new InvoicePro annual licenses", 75, 4.5, "Strong client conversion rate. On track for quarterly incentive.", "Q3", "in_progress", now_str),
                    ("gol-102", "EMP-002", "Pooja Verma", "First-Contact Resolution", "Maintain >95% first contact ticket resolution", 92, 4.8, "Exceptional response times and positive client reviews.", "Q3", "in_progress", now_str)
                ]
                db.executemany("""
                    INSERT OR IGNORE INTO hr_goals (id, employee_id, employee_name, goal_title, target_metric, progress_percent, appraisal_score, reviewer_notes, quarter, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, sample_goals)
                db.commit()
        except Exception as hr_seed_err:
            print(f"  [HR Seed Notice] {hr_seed_err}")

        # Migration: add columns if they don't exist yet (for older databases)
        # Customers table columns
        cust_cols = {
            "owner": "TEXT DEFAULT ''",
            "city": "TEXT DEFAULT ''",
            "currency": "TEXT DEFAULT 'INR'",
            "email": "TEXT DEFAULT ''",
            "phone": "TEXT DEFAULT ''",
            "license_key": "TEXT DEFAULT ''",
            "purchase_date": "TEXT DEFAULT ''",
            "purchase_amount": "REAL DEFAULT 1499",
            "support_purchased": "INTEGER DEFAULT 0",
            "support_purchase_date": "TEXT DEFAULT ''",
            "support_amount": "REAL DEFAULT 499",
            "notes": "TEXT DEFAULT ''",
            "plan_end_date": "TEXT DEFAULT ''",
            "trial_end_date": "TEXT DEFAULT ''",
            "created_at": "TEXT DEFAULT ''",
            "updated_at": "TEXT DEFAULT ''"
        }
        for col, col_def in cust_cols.items():
            try:
                db.execute(f"ALTER TABLE customers ADD COLUMN {col} {col_def}")
                db.commit()
            except Exception:
                pass
                
        # Support renewals columns
        try:
            db.execute("ALTER TABLE support_renewals ADD COLUMN added_at TEXT DEFAULT ''")
            db.commit()
        except Exception:
            pass
            
        # Employees columns
        emp_cols = {
            "mobile": "TEXT DEFAULT ''",
            "email": "TEXT DEFAULT ''",
            "designation": "TEXT DEFAULT ''",
            "department": "TEXT DEFAULT ''",
            "join_date": "TEXT DEFAULT ''",
            "notes": "TEXT DEFAULT ''",
            "extra_data": "TEXT DEFAULT '{}'",
            "created_at": "TEXT DEFAULT ''",
            "updated_at": "TEXT DEFAULT ''"
        }
        for col, col_def in emp_cols.items():
            try:
                db.execute(f"ALTER TABLE employees ADD COLUMN {col} {col_def}")
                db.commit()
            except Exception:
                pass

        # Staff users table columns
        staff_cols = {
            "name": "TEXT DEFAULT ''",
            "username": "TEXT DEFAULT ''",
            "password": "TEXT DEFAULT ''",
            "role": "TEXT DEFAULT 'sales'",
            "department": "TEXT DEFAULT 'Sales'",
            "designation": "TEXT DEFAULT 'Sales Executive'",
            "email": "TEXT DEFAULT ''",
            "phone": "TEXT DEFAULT ''",
            "emp_id": "TEXT DEFAULT ''",
            "upi_id": "TEXT DEFAULT ''",
            "upi_qr_image": "TEXT DEFAULT ''",
            "active": "INTEGER DEFAULT 1",
            "created_at": "TEXT DEFAULT ''",
            "last_login": "TEXT DEFAULT ''",
            "extra_data": "TEXT DEFAULT '{}'"
        }
        for col, col_def in staff_cols.items():
            try:
                db.execute(f"ALTER TABLE staff_users ADD COLUMN {col} {col_def}")
                db.commit()
            except Exception:
                pass

        # HR Candidates columns
        cand_cols = {
            "offer_response_status": "TEXT DEFAULT ''",
            "decline_reason": "TEXT DEFAULT ''",
            "resume_filename": "TEXT DEFAULT ''",
            "resume_data": "TEXT DEFAULT ''",
            "resume_size": "TEXT DEFAULT ''",
            "resume_text": "TEXT DEFAULT ''"
        }
        for col, col_def in cand_cols.items():
            try:
                db.execute(f"ALTER TABLE hr_candidates ADD COLUMN {col} {col_def}")
                db.commit()
            except Exception:
                pass
                
        db.close()


# Fields that have their own DB columns — everything else goes into extra_data JSON
_BASIC_EMP_FIELDS = {
    'id', 'empId', 'emp_id', 'name', 'mobile', 'email',
    'designation', 'department', 'joinDate', 'join_date',
    'notes', 'created_at', 'updated_at', 'createdAt', 'updatedAt',
    'sales', 'payments', 'extra_data', '_showSalary',
}


def emp_extra_data(data):
    """Extract extra employee fields (not in DB columns) as a JSON string."""
    extra = {k: v for k, v in data.items() if k not in _BASIC_EMP_FIELDS}
    return json.dumps(extra, ensure_ascii=False)


def parse_emp_extra(emp):
    """Parse extra_data JSON and merge fields into the employee dict (in-place)."""
    raw = emp.get('extra_data') or '{}'
    try:
        extra = json.loads(raw) if isinstance(raw, str) else raw
        for k, v in extra.items():
            if k not in emp:
                emp[k] = v
    except Exception:
        pass


def new_id():
    return str(uuid.uuid4())


def now_iso():
    return datetime.now().isoformat()


def rows_to_list(rows):
    return [dict(r) for r in rows]

def is_valid_email(email, required=False):
    """Validate email/gmail address format (RFC 5322 pattern with strict domain checks)."""
    if not email or not str(email).strip():
        return not required
    s = str(email).strip().lower()
    if " " in s or ".." in s or "@" not in s:
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, s):
        return False
    parts = s.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return False
    domain = parts[1]
    if domain.startswith(".") or domain.endswith(".") or domain.startswith("-") or domain.endswith("-"):
        return False
    return True


def clean_phone_number(phone):
    """Extract standard clean digits from phone number string."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits


def is_valid_phone(phone, required=False):
    """Validate strict 10-digit mobile number (starts with 6, 7, 8, 9; rejects dummy/repetitive numbers)."""
    if not phone or not str(phone).strip():
        return not required
    digits = clean_phone_number(phone)
    if len(digits) != 10:
        return False
    if digits[0] not in ("6", "7", "8", "9"):
        return False
    if len(set(digits)) <= 1:
        return False
    if digits in ("1234567890", "0123456789"):
        return False
    return True


def calculate_plan_commission(plan_label="", amount=0, notes=""):
    """
    Commission rules for salesperson after target completed:
    - 1 Year plan (Rs 1499) -> Rs 499 commission
    - 3 Year plan (Rs 3999) -> Rs 999 commission
    - 5 Year plan (Rs 6499) -> Rs 1499 commission
    - VIP Lifetime (Rs 18499) -> Rs 1999 commission
    """
    text = f"{plan_label or ''} {notes or ''}".lower()
    if any(k in text for k in ["vip", "lifetime", "life time", "permanent"]):
        return 1999.0
    if any(k in text for k in ["5 year", "5-year", "5y", "5_year", "five year", "60 month"]):
        return 1499.0
    if any(k in text for k in ["3 year", "3-year", "3y", "3_year", "three year", "36 month"]):
        return 999.0
    if any(k in text for k in ["1 year", "1-year", "1y", "1_year", "one year", "annual", "yearly", "12 month"]):
        return 499.0
    
    try:
        amt = float(amount or 0)
    except Exception:
        amt = 0.0

    if amt >= 12000:
        return 1999.0
    elif amt >= 5000:
        return 1499.0
    elif amt >= 2500:
        return 999.0
    elif amt >= 1000:
        return 499.0
    elif amt >= 300:
        return 100.0
    elif amt > 0:
        return 50.0
    return 499.0


def find_employee_by_identifier(db, raw_ident):
    """
    Look up an employee across employees and staff_users tables by:
    - emp_id (e.g. EMP-101, EMP-VU1612-116, EMP101)
    - id (UUID)
    - name
    - email
    - mobile
    - staff_users username
    """
    if not raw_ident:
        return None
    ident = str(raw_ident).strip()
    if not ident:
        return None
    ident_low = ident.lower()
    ident_clean = re.sub(r'[^a-zA-Z0-9]', '', ident_low)
    
    # 1. Direct query on employees table
    try:
        emp = db.execute(
            "SELECT id, emp_id, name, department, designation, email, mobile FROM employees WHERE LOWER(TRIM(emp_id))=? OR LOWER(TRIM(id))=? OR LOWER(TRIM(name))=? OR LOWER(TRIM(email))=? OR TRIM(mobile)=?",
            (ident_low, ident_low, ident_low, ident_low, ident)
        ).fetchone()
        if emp:
            return dict(emp)
    except Exception:
        pass

    # 2. Normalized alphanumeric match in employees
    all_emps = []
    try:
        all_emps = rows_to_list(db.execute("SELECT id, emp_id, name, department, designation, email, mobile FROM employees").fetchall())
        if ident_clean:
            for e in all_emps:
                e_clean_code = re.sub(r'[^a-zA-Z0-9]', '', str(e.get('emp_id') or '')).lower()
                e_clean_id = re.sub(r'[^a-zA-Z0-9]', '', str(e.get('id') or '')).lower()
                e_clean_name = re.sub(r'[^a-zA-Z0-9]', '', str(e.get('name') or '')).lower()
                if ident_clean in (e_clean_code, e_clean_id, e_clean_name) or (len(ident_clean) >= 3 and (ident_clean == e_clean_code or e_clean_code == ident_clean)):
                    return e
    except Exception:
        all_emps = []

    # 3. Match in staff_users table
    try:
        staff = db.execute(
            "SELECT id, name, username, emp_id, role, email, phone FROM staff_users WHERE LOWER(TRIM(username))=? OR LOWER(TRIM(emp_id))=? OR LOWER(TRIM(name))=? OR LOWER(TRIM(email))=?",
            (ident_low, ident_low, ident_low, ident_low)
        ).fetchone()
        if staff:
            s_dict = dict(staff)
            s_emp_code = s_dict.get("emp_id") or f"EMP-{s_dict.get('username','').upper()}"
            # See if employees table already has this person
            for e in all_emps:
                if str(e.get("name","")).lower().strip() == str(s_dict.get("name","")).lower().strip() or str(e.get("emp_id","")).lower().strip() == s_emp_code.lower().strip():
                    return e
            # Auto-create employee record so sales and commissions are attributed
            new_eid = new_id()
            today_date = datetime.now().strftime("%Y-%m-%d")
            db.execute("""INSERT INTO employees (id, emp_id, name, mobile, email, designation, department, join_date, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (new_eid, s_emp_code, s_dict.get("name", s_dict.get("username")), s_dict.get("phone",""), s_dict.get("email",""), s_dict.get("role","Sales").capitalize(), "Sales" if "sales" in str(s_dict.get("role","")).lower() else "Operations", today_date, "Auto-linked from staff user", now_iso(), now_iso()))
            return {"id": new_eid, "emp_id": s_emp_code, "name": s_dict.get("name", s_dict.get("username")), "department": "Sales", "designation": s_dict.get("role","Sales")}
    except Exception:
        pass

    return None


def record_employee_sale_db(db, matched_emp, cid, c_name, plan_name, amount, order_num="", source="Online Checkout", custom_note=""):
    """
    Record or update an employee sale in employee_sales and compute commission.
    """
    if not matched_emp:
        return 0.0, None
    emp_db_id = matched_emp["id"]
    emp_code = matched_emp.get("emp_id") or ""
    emp_real_name = matched_emp.get("name") or ""
    today_str = datetime.now().strftime("%Y-%m-%d")
    cur_month = today_str[:7]
    commission = calculate_plan_commission(plan_name, amount, f"EMP: {emp_code} ({emp_real_name}) {custom_note}")
    
    sale_note = custom_note or f"{source} ({order_num}) - {plan_name}" if order_num else f"{source} - {plan_name}"
    
    existing_sale = None
    try:
        if order_num:
            existing_sale = db.execute("SELECT id FROM employee_sales WHERE note LIKE ?", (f"%{order_num}%",)).fetchone()
        if not existing_sale and cid:
            existing_sale = db.execute("SELECT id FROM employee_sales WHERE employee_id=? AND (customer_id=? OR note LIKE ?)", (emp_db_id, cid, f"%{cid}%")).fetchone()
        if not existing_sale and c_name:
            existing_sale = db.execute("SELECT id FROM employee_sales WHERE employee_id=? AND LOWER(TRIM(customer_name))=?", (emp_db_id, c_name.lower().strip())).fetchone()
    except Exception:
        pass

    if existing_sale:
        sale_id = existing_sale["id"]
        try:
            db.execute("""UPDATE employee_sales SET 
                customer_id=?, customer_name=?, plan_name=?, amount=?, commission=?, date=?, note=?, status=?, target_month=?
                WHERE id=?""",
                (cid, c_name, plan_name, amount, commission, today_str, sale_note, "approved", cur_month, sale_id))
        except Exception:
            db.execute("""UPDATE employee_sales SET 
                customer_name=?, amount=?, commission=?, date=?, note=?
                WHERE id=?""",
                (c_name, amount, commission, today_str, sale_note, sale_id))
    else:
        sale_id = new_id()
        try:
            db.execute("""INSERT INTO employee_sales 
                (id, employee_id, emp_id, customer_id, customer_name, plan_name, amount, commission, date, note, status, target_month, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sale_id, emp_db_id, emp_code, cid, c_name, plan_name, amount, commission,
                 today_str, sale_note, "approved", cur_month, now_iso()))
        except Exception:
            db.execute("""INSERT INTO employee_sales 
                (id, employee_id, customer_name, date, amount, commission, note, created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (sale_id, emp_db_id, c_name, today_str, amount, commission, sale_note, now_iso()))
                 
    return commission, sale_id


# ── SMTP helpers ──────────────────────────────────────────────────────────────
SMTP_CONFIG_PATH = os.path.join(DATA_DIR, "smtp_config.json")


def load_smtp_config():
    if os.path.exists(SMTP_CONFIG_PATH):
        try:
            with open(SMTP_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def is_dummy_password(pw):
    if not pw:
        return True
    s = str(pw)
    return "•" in s or "\u2022" in s or s.startswith("••••")


def save_smtp_config(cfg):
    existing = load_smtp_config()
    # If password is blank/masked or dummy dots, keep the existing one
    if is_dummy_password(cfg.get("password")) and existing.get("password"):
        cfg["password"] = existing["password"]
    with open(SMTP_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def build_html_email(subject, body, from_name="Sylivion Tech Powered By Workmate4U Pvt. Ltd.", action_buttons=None):
    """Convert email text into clean, simple, light corporate HTML email compatible with all clients."""
    lines = body.split("\n")
    html_elements = []
    in_list = False

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            if in_list:
                html_elements.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("•") or stripped.startswith("*") or (stripped.startswith("-") and not stripped.startswith("---")):
            if not in_list:
                html_elements.append('<ul style="margin: 8px 0 16px 0; padding-left: 20px; list-style-type: disc; color: #334155;">')
                in_list = True
            item_text = stripped.lstrip("•*- ").strip()
            escaped_item = html.escape(item_text)
            if ":" in escaped_item:
                parts = escaped_item.split(":", 1)
                escaped_item = f'<strong style="color: #0f172a;">{parts[0]}:</strong>{parts[1]}'
            html_elements.append(f'<li style="margin-bottom: 6px; line-height: 1.5; color: #334155;">{escaped_item}</li>')
        else:
            if in_list:
                html_elements.append("</ul>")
                in_list = False

            escaped_line = html.escape(stripped)
            if escaped_line.startswith("Dear ") or escaped_line.startswith("Hello,") or escaped_line.startswith("Hello "):
                html_elements.append(f'<p style="margin: 0 0 14px 0; font-size: 15px; font-weight: 600; line-height: 1.5; color: #0f172a;">{escaped_line}</p>')
            elif escaped_line.endswith(":") or escaped_line.startswith("Interview Schedule") or escaped_line.startswith("Key Details") or escaped_line.startswith("Documents required") or escaped_line.startswith("Interview Details"):
                html_elements.append(f'<p style="margin: 16px 0 8px 0; font-size: 14px; font-weight: 700; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px;">{escaped_line}</p>')
            elif escaped_line.startswith("Warm regards,") or escaped_line.startswith("Thanks &amp; Regards,") or escaped_line.startswith("Thanks & Regards,") or escaped_line.startswith("Regards,"):
                html_elements.append(f'<p style="margin: 20px 0 6px 0; font-size: 14px; line-height: 1.5; color: #475569;">{escaped_line}</p>')
            else:
                html_elements.append(f'<p style="margin: 0 0 12px 0; font-size: 14px; line-height: 1.6; color: #334155;">{escaped_line}</p>')

    if in_list:
        html_elements.append("</ul>")

    btn_html = ""
    if action_buttons and isinstance(action_buttons, list):
        btn_items = []
        for btn in action_buttons:
            lbl = html.escape(btn.get("label", "Click here"))
            href = btn.get("url", "#")
            color = btn.get("color", "emerald")
            if color == "emerald":
                bg = "#16a34a"
                txt = "#ffffff"
                border = "#15803d"
            else:
                bg = "#64748b"
                txt = "#ffffff"
                border = "#475569"
            btn_items.append(
                f'<a href="{href}" target="_blank" style="display: inline-block; padding: 11px 22px; margin: 6px 6px; background-color: {bg}; color: {txt}; text-decoration: none; font-weight: 600; font-size: 13px; border-radius: 6px; border: 1px solid {border}; text-align: center;">{lbl}</a>'
            )
        btn_html = f"""
        <div style="margin: 24px 0 16px 0; padding: 18px 20px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; text-align: center;">
          <p style="margin: 0 0 12px 0; font-size: 13px; font-weight: 600; color: #334155;">Please confirm your response:</p>
          <div style="text-align: center;">
            {''.join(btn_items)}
          </div>
        </div>
        """

    body_html = "\n".join(html_elements)
    esc_subj = html.escape(subject or "HR Notification")
    esc_brand = html.escape(from_name or "Sylivion Tech Powered By Workmate4U Pvt. Ltd.")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc_subj}</title>
</head>
<body style="margin: 0; padding: 24px 12px; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 580px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
    <!-- Brand Header -->
    <tr>
      <td style="padding: 24px 28px 18px 28px; border-bottom: 2px solid #2563eb;">
        <span style="font-size: 17px; font-weight: 700; color: #0f172a; letter-spacing: -0.2px;">{esc_brand}</span>
      </td>
    </tr>
    <!-- Email Body -->
    <tr>
      <td style="padding: 24px 28px 28px 28px; font-size: 14px; line-height: 1.6; color: #334155;">
        {body_html}
        {btn_html}
      </td>
    </tr>
    <!-- Footer -->
    <tr>
      <td style="padding: 16px 28px; background-color: #f8fafc; border-top: 1px solid #f1f5f9; font-size: 12px; color: #64748b; text-align: center;">
        This email was sent by {esc_brand}.
      </td>
    </tr>
  </table>
</body>
</html>"""


def do_send_smtp(cfg, to_list, subject, body, attachments=None, cc_list=None, from_email_override=None, from_name_override=None, action_buttons=None):
    """Send clean, branded responsive HTML email with plain-text fallback via SMTP, optional attachments, action buttons, and Cc support."""
    host     = cfg.get("host", "").strip()
    port     = int(cfg.get("port", 587))
    username = cfg.get("username", "").strip()
    password = cfg.get("password", "")
    if is_dummy_password(password):
        stored = load_smtp_config()
        password = stored.get("password", "")
    
    from_name  = (from_name_override or cfg.get("from_name", "Sylivion Tech Powered By Workmate4U Pvt. Ltd.")).strip()
    if from_name in ["InvoicePro", "InvoicePro Billing Systems Pvt Ltd", ""]:
        from_name = "Sylivion Tech Powered By Workmate4U Pvt. Ltd."
    from_email = (from_email_override or cfg.get("from_email", username)).strip() or username
    use_tls  = cfg.get("use_tls", True)

    if isinstance(to_list, str):
        to_list = [t.strip() for t in to_list.split(",") if t.strip()]
    if isinstance(cc_list, str):
        cc_list = [c.strip() for c in cc_list.split(",") if c.strip()]
    elif not cc_list:
        cc_list = []

    domain = from_email.split("@")[-1] if "@" in from_email else "localhost"

    html_content = build_html_email(subject, body, from_name, action_buttons=action_buttons)

    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(body, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_content, "html", "utf-8"))

    if attachments:
        msg = MIMEMultipart("mixed")
        msg.attach(alt_part)

        for att in attachments:
            if not isinstance(att, dict):
                continue
            fname = att.get("filename", "Document.pdf")
            b64_data = att.get("data", "")
            if b64_data:
                try:
                    if "," in b64_data:
                        b64_data = b64_data.split(",", 1)[1]
                    file_data = base64.b64decode(b64_data)
                    part = MIMEApplication(file_data, _subtype="pdf")
                    part.add_header("Content-Disposition", "attachment", filename=fname)
                    msg.attach(part)
                except Exception as att_err:
                    print(f"[Attachment Error] Failed to attach {fname}: {att_err}")
    else:
        msg = alt_part

    msg["Date"]         = formatdate(localtime=True)
    msg["Subject"]      = Header(subject, "utf-8")
    msg["From"]         = formataddr((str(Header(from_name, "utf-8")), from_email)) if from_name else from_email
    msg["Reply-To"]     = formataddr((str(Header(from_name, "utf-8")), from_email)) if from_name else from_email
    msg["To"]           = ", ".join(to_list)
    if cc_list:
        msg["Cc"]       = ", ".join(cc_list)
    # Note: We intentionally omit custom Message-ID, Auto-Submitted, and X-Mailer.
    # When sending via Gmail/Outlook SMTP, the SMTP relay automatically inserts authentic,
    # DKIM-signed Message-IDs. Custom bot headers (like Auto-Submitted or X-Mailer) cause
    # Gmail and Outlook to classify messages as automated bulk/spam.

    if port == 465:
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(host, port, context=context, timeout=15)
    else:
        server = smtplib.SMTP(host, port, timeout=15)
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()

    if username and password:
        server.login(username, password)

    all_recipients = list(set(to_list + cc_list))
    server.send_message(msg, from_addr=from_email, to_addrs=all_recipients)
    server.quit()


def row_to_dict(row):
    return dict(row) if row else None


# ── HTTP Handler ──────────────────────────────────────────────────────────────

# ── Robust Enterprise Security & Anti-Bypass Suite ──
SERVER_SECRET = b"invoicepro_secure_master_salt_key_2026_x89f_anti_tamper_sec_v3"
_active_sessions = {}      # token -> {"user": user_dict, "expires_at": float}
_login_rate_limiter = {}  # ip -> list of float timestamps

def generate_session_token(user_dict):
    now = time.time()
    exp = now + 86400 * 3  # 3 days validity
    payload = {
        "uid": str(user_dict.get("id", "")),
        "username": str(user_dict.get("username", "")),
        "role": str(user_dict.get("role", "")),
        "name": str(user_dict.get("name", "")),
        "department": str(user_dict.get("department", "")),
        "exp": exp,
        "nonce": os.urandom(8).hex()
    }
    payload_json = json.dumps(payload, sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('ascii').rstrip('=')
    sig = hmac.new(SERVER_SECRET, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
    token = f"ipsec_{payload_b64}.{sig}"
    with _db_lock:
        _active_sessions[token] = {"user": user_dict, "expires_at": exp}
    return token

def verify_session_token(token):
    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    if token.startswith("Bearer "):
        token = token[7:].strip()
    if not token.startswith("ipsec_") or "." not in token:
        return None
    try:
        raw = token[6:]
        payload_b64, sig = raw.split(".", 1)
        expected_sig = hmac.new(SERVER_SECRET, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        padded = payload_b64 + '=' * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8'))
        if time.time() > payload.get("exp", 0):
            return None
        return payload
    except Exception:
        return None

def check_login_rate_limit(client_ip):
    now = time.time()
    with _db_lock:
        attempts = [t for t in _login_rate_limiter.get(client_ip, []) if now - t < 300]
        _login_rate_limiter[client_ip] = attempts
        if len(attempts) >= 8:
            return False, int(300 - (now - attempts[0]))
        return True, 0

def record_failed_login(client_ip):
    now = time.time()
    with _db_lock:
        if client_ip not in _login_rate_limiter:
            _login_rate_limiter[client_ip] = []
        _login_rate_limiter[client_ip].append(now)

def clear_login_attempts(client_ip):
    with _db_lock:
        _login_rate_limiter.pop(client_ip, None)

# ── Anti-Data-Duplication Normalizers & Validators ──
def normalize_phone_clean(p):
    if not p:
        return ""
    digits = re.sub(r'\D', '', str(p))
    if len(digits) >= 10:
        return digits[-10:]
    return digits

def normalize_email_clean(e):
    if not e:
        return ""
    return str(e).strip().lower()

class AdminHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # suppress per-request noise

    def log_error(self, fmt, *args):
        import sys
        print(f"  [Error] {fmt % args}", file=sys.stderr)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Session-Token, ngrok-skip-browser-warning")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
        self.wfile.write(body)

    def send_ok(self, msg="ok"):
        self.send_json({"ok": True, "msg": msg})

    def send_err(self, msg, status=400):
        self.send_json({"ok": False, "error": str(msg)}, status)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Session-Token, ngrok-skip-browser-warning")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/", "/AdminPanel.html"):
                with open(HTML_PATH, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            # ── PWA & Static Asset Routes ─────────────────────────────────────────
            if path in ("/manifest.json", "/manifest.webmanifest"):
                manifest_path = os.path.join(BASE_DIR, "manifest.json")
                if not os.path.exists(manifest_path):
                    manifest_path = os.path.join(os.path.dirname(BASE_DIR), "manifest.json")
                if os.path.exists(manifest_path):
                    with open(manifest_path, "rb") as f:
                        body = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

            if path in ("/sw.js", "/service-worker.js"):
                sw_path = os.path.join(BASE_DIR, "sw.js")
                if not os.path.exists(sw_path):
                    sw_path = os.path.join(os.path.dirname(BASE_DIR), "sw.js")
                if os.path.exists(sw_path):
                    with open(sw_path, "rb") as f:
                        body = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript; charset=utf-8")
                    self.send_header("Service-Worker-Allowed", "/")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

            if path == "/offline.html":
                offline_path = os.path.join(BASE_DIR, "offline.html")
                if not os.path.exists(offline_path):
                    offline_path = os.path.join(os.path.dirname(BASE_DIR), "offline.html")
                if os.path.exists(offline_path):
                    with open(offline_path, "rb") as f:
                        body = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

            if path.startswith("/icons/") or path in ("/favicon.ico", "/apple-touch-icon.png"):
                rel = path.lstrip("/")
                if rel in ("favicon.ico", "apple-touch-icon.png"):
                    rel = f"icons/{rel if rel != 'favicon.ico' else 'favicon-32.png'}"
                icon_path = os.path.join(BASE_DIR, rel.replace("/", os.sep))
                if not os.path.exists(icon_path):
                    icon_path = os.path.join(os.path.dirname(BASE_DIR), rel.replace("/", os.sep))
                if os.path.exists(icon_path):
                    with open(icon_path, "rb") as f:
                        body = f.read()
                    ctype = "image/png"
                    if icon_path.endswith(".svg"):
                        ctype = "image/svg+xml"
                    elif icon_path.endswith(".ico"):
                        ctype = "image/x-icon"
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

            if path in ("/api/ping", "/api/health", "/health"):
                self.send_json({"ok": True, "status": "healthy", "service": "InvoicePro Admin", "port": PORT})
                return

            if path == "/api/smtp-config":
                cfg = load_smtp_config()
                safe = {k: v for k, v in cfg.items() if k != "password"}
                safe["hasPassword"] = bool(cfg.get("password"))
                self.send_json(safe)
                return

            if path == "/api/stats":
                with _db_lock:
                    db = get_db()
                    total    = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
                    licensed = db.execute("SELECT COUNT(*) FROM customers WHERE license_key != ''").fetchone()[0]
                    open_rep = db.execute("SELECT COUNT(*) FROM reports WHERE status='open'").fetchone()[0]
                    open_enq = db.execute("SELECT COUNT(*) FROM enquiries WHERE status='open'").fetchone()[0]
                    lic_rev  = db.execute("SELECT COALESCE(SUM(purchase_amount),0) FROM customers").fetchone()[0]
                    db.close()
                self.send_json({
                    "total": total, "licensed": licensed,
                    "openReports": open_rep, "openEnquiries": open_enq,
                    "licenseRevenue": lic_rev, "supportRevenue": 0,
                    "totalRevenue": lic_rev,
                })
                return

            if path == "/api/customers":
                with _db_lock:
                    db = get_db()
                    customers = rows_to_list(db.execute("SELECT * FROM customers ORDER BY created_at DESC").fetchall())
                    for c in customers:
                        c["support_renewals"] = []
                        c["support_purchased"] = False
                    db.close()
                self.send_json(customers)
                return

            if path in ("/api/checkout/orders", "/api/orders"):
                with _db_lock:
                    db = get_db()
                    orders = rows_to_list(db.execute("SELECT * FROM checkout_orders ORDER BY created_at DESC LIMIT 200").fetchall())
                    db.close()
                self.send_json({"ok": True, "orders": orders})
                return

            if path == "/api/reports":
                with _db_lock:
                    db = get_db()
                    reports = rows_to_list(db.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall())
                    db.close()
                self.send_json(reports)
                return

            if path in ("/api/support/recurring-issues", "/api/support/recurring"):
                with _db_lock:
                    db = get_db()
                    recs = rows_to_list(db.execute("SELECT * FROM recurring_issues ORDER BY CASE status WHEN 'Open' THEN 1 WHEN 'Investigating' THEN 2 WHEN 'In Dev Fix' THEN 3 WHEN 'Resolved' THEN 4 ELSE 5 END, impacted_count DESC, created_at DESC").fetchall())
                    db.close()
                self.send_json({"ok": True, "recurring_issues": recs})
                return

            if path == "/api/enquiries":
                with _db_lock:
                    db = get_db()
                    enq = rows_to_list(db.execute("SELECT * FROM enquiries ORDER BY created_at DESC").fetchall())
                    db.close()
                self.send_json(enq)
                return

            if path == "/api/teams":
                with _db_lock:
                    db = get_db()
                    teams = rows_to_list(db.execute("SELECT * FROM teams ORDER BY dept_id ASC, name ASC").fetchall())
                    for t in teams:
                        if isinstance(t.get("members"), str):
                            try:
                                t["members"] = json.loads(t["members"])
                            except Exception:
                                t["members"] = [t["members"]] if t["members"] else []
                        if "targetMonthly" not in t and "targetmonthly" in t:
                            t["targetMonthly"] = t["targetmonthly"]
                        if "targetMonthly" not in t:
                            t["targetMonthly"] = 0
                self.send_json({"ok": True, "teams": teams})
                return

            if path == "/api/employees":
                with _db_lock:
                    db = get_db()
                    emps = rows_to_list(db.execute("SELECT * FROM employees ORDER BY created_at DESC").fetchall())
                    for emp in emps:
                        emp["sales"]    = rows_to_list(db.execute("SELECT * FROM employee_sales WHERE employee_id=? ORDER BY date", (emp["id"],)).fetchall())
                        emp["payments"] = rows_to_list(db.execute("SELECT * FROM employee_payments WHERE employee_id=? ORDER BY date", (emp["id"],)).fetchall())
                        parse_emp_extra(emp)
                    db.close()
                self.send_json(emps)
                return

            if path == "/api/staff-users":
                with _db_lock:
                    db = get_db()
                    users = rows_to_list(db.execute("SELECT id, name, username, password, role, department, designation, email, phone, emp_id, active, created_at, last_login, extra_data FROM staff_users ORDER BY created_at ASC").fetchall())
                    db.close()
                for u in users:
                    role = (u.get("role") or "sales_member").lower()
                    u_name = (u.get("username") or "").lower()
                    if u_name in ("support_lead", "support"):
                        role = "support_leader"
                        u["role"] = role
                    elif u_name in ("support_mem", "support_priya", "support_rahul"):
                        role = "support_member"
                        u["role"] = role
                    elif u_name in ("sales_lead",):
                        role = "sales_leader"
                        u["role"] = role
                    elif u_name in ("dev_lead", "dev"):
                        role = "dev_leader"
                        u["role"] = role

                    if not u.get("department"):
                        u["department"] = (
                            "" if role in ("admin", "manager", "hr")
                            else "Support" if role in ("support", "support_leader", "support_member")
                            else "Development" if role in ("dev_leader", "dev_member", "dev", "development")
                            else "Sales"
                        )
                    if not u.get("designation"):
                        u["designation"] = (
                            "Master Administrator" if role == "admin"
                            else "Operations Manager" if role == "manager"
                            else "HR Specialist" if role == "hr"
                            else "Support Team Leader" if role in ("support_leader", "support_lead")
                            else "Technical Support Specialist" if role in ("support_member", "support_mem", "support")
                            else "Development Team Leader" if role in ("dev_leader", "dev_lead")
                            else "Senior Software Engineer" if role in ("dev_member", "dev_front", "dev_back", "dev_flutter", "dev_qa")
                            else "Sales Team Leader" if role in ("sales_leader", "sales_lead")
                            else "Senior Sales Executive"
                        )
                self.send_json(users)
                return

            if path in ("/api/activity-logs", "/api/audit-logs", "/api/activities", "/api/logs"):
                with _db_lock:
                    db = get_db()
                    audit_rows = rows_to_list(db.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 1000").fetchall())
                    act_rows = rows_to_list(db.execute("SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT 1000").fetchall())
                    db.close()
                self.send_json({"ok": True, "logs": audit_rows, "audit_logs": audit_rows, "activity_logs": act_rows})
                return
            
            if path == "/api/hr/candidates":
                with _db_lock:
                    db = get_db()
                    candidates = rows_to_list(db.execute("SELECT * FROM hr_candidates ORDER BY created_at DESC").fetchall())
                    db.close()
                self.send_json(candidates)
                return

            if path == "/api/hr/jobs":
                with _db_lock:
                    db = get_db()
                    jobs = rows_to_list(db.execute("SELECT * FROM hr_jobs ORDER BY created_at DESC").fetchall())
                    db.close()
                self.send_json(jobs)
                return

            if path == "/api/hr/grievances":
                with _db_lock:
                    db = get_db()
                    grievances = rows_to_list(db.execute("SELECT * FROM hr_grievances ORDER BY created_at DESC").fetchall())
                    db.close()
                self.send_json(grievances)
                return

            if path == "/api/hr/training":
                with _db_lock:
                    db = get_db()
                    trainings = rows_to_list(db.execute("SELECT * FROM hr_training ORDER BY schedule_date ASC").fetchall())
                    db.close()
                self.send_json(trainings)
                return

            if path == "/api/hr/goals":
                with _db_lock:
                    db = get_db()
                    goals = rows_to_list(db.execute("SELECT * FROM hr_goals ORDER BY created_at DESC").fetchall())
                    db.close()
                self.send_json(goals)
                return

            if path == "/api/hr/get-smtp-profile":
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                uid = qs.get("user_id", [""])[0] or qs.get("emp_id", [""])[0] or "default_hr"
                profile = {}
                with _db_lock:
                    db = get_db()
                    emp_row = db.execute("SELECT * FROM employees WHERE id=? OR emp_id=?", (uid, uid)).fetchone()
                    if emp_row:
                        try:
                            extra = json.loads(emp_row["extra_data"] or "{}")
                            profile = extra.get("hr_smtp_config") or {}
                        except Exception:
                            pass
                    db.close()
                if (not profile or not profile.get("from_email")) and os.path.exists(HR_SMTP_PROFILE_PATH):
                    try:
                        with open(HR_SMTP_PROFILE_PATH, "r", encoding="utf-8") as f:
                            profile = json.load(f)
                    except Exception:
                        pass
                self.send_json({"ok": True, "smtp_profile": profile})
                return

            if path == "/api/sales/targets/config":
                target_file = os.path.join(DATA_DIR, "sales_target_config.json")
                default_config = {
                    "fixed_salary": 15000,
                    "plans": [
                        {"id": "1y", "name": "1 Year Plan", "price": 1499, "target": 15, "commission": 499, "icon": "fa-calendar-days", "color": "indigo"},
                        {"id": "3y", "name": "3 Year Plan", "price": 3999, "target": 10, "commission": 999, "icon": "fa-calendar-check", "color": "purple"},
                        {"id": "5y", "name": "5 Year Plan", "price": 6499, "target": 5, "commission": 1499, "icon": "fa-gem", "color": "emerald"},
                        {"id": "vip", "name": "VIP Lifetime Plan", "price": 18499, "target": 3, "commission": 1999, "icon": "fa-crown", "color": "amber"}
                    ]
                }
                config = default_config
                if os.path.exists(target_file):
                    try:
                        with open(target_file, "r", encoding="utf-8") as f:
                            config = json.load(f)
                    except Exception:
                        pass
                self.send_json({"ok": True, "config": config})
                return

            if path == "/api/sales/rep-quotas":
                target_file = os.path.join(DATA_DIR, "sales_target_config.json")
                default_config = {
                    "fixed_salary": 15000,
                    "plans": [
                        {"id": "1y", "name": "1 Year Plan", "price": 1499, "target": 15, "commission": 499, "icon": "fa-calendar-days", "color": "indigo"},
                        {"id": "3y", "name": "3 Year Plan", "price": 3999, "target": 10, "commission": 999, "icon": "fa-calendar-check", "color": "purple"},
                        {"id": "5y", "name": "5 Year Plan", "price": 6499, "target": 5, "commission": 1499, "icon": "fa-gem", "color": "emerald"},
                        {"id": "vip", "name": "VIP Lifetime Plan", "price": 18499, "target": 3, "commission": 1999, "icon": "fa-crown", "color": "amber"}
                    ]
                }
                config = default_config
                if os.path.exists(target_file):
                    try:
                        with open(target_file, "r", encoding="utf-8") as f:
                            config = json.load(f)
                    except Exception:
                        pass
                
                with _db_lock:
                    db = get_db()
                    staff_rows = rows_to_list(db.execute("SELECT * FROM staff_users WHERE LOWER(role) IN ('sales', 'sales_member', 'sales_leader') OR LOWER(department) LIKE '%sales%'").fetchall())
                    employees_rows = rows_to_list(db.execute("SELECT * FROM employees WHERE LOWER(department) LIKE '%sales%' OR LOWER(designation) LIKE '%sales%' OR LOWER(designation) LIKE '%bde%'").fetchall())
                    sales_rows = rows_to_list(db.execute("SELECT * FROM employee_sales").fetchall())
                    customers_rows = rows_to_list(db.execute("SELECT * FROM customers WHERE sold_by_emp_id != '' OR sold_by_emp_name != ''").fetchall())
                    db.close()

                # Build summary per rep
                reps = []
                seen_ids = set()
                
                # Combine employees and staff
                all_reps = []
                for s in staff_rows:
                    all_reps.append({
                        "id": s.get("id"),
                        "username": s.get("username"),
                        "name": s.get("display_name") or s.get("username"),
                        "department": s.get("department", "Sales"),
                        "role": s.get("role", "sales_member")
                    })
                for e in employees_rows:
                    if not any(r["username"] == e.get("emp_id") or r["id"] == e.get("id") for r in all_reps):
                        all_reps.append({
                            "id": e.get("id"),
                            "username": e.get("emp_id") or e.get("name"),
                            "name": e.get("name"),
                            "department": e.get("department", "Sales"),
                            "role": "sales_member"
                        })

                for rep in all_reps:
                    rid = rep["id"]
                    runame = rep["username"]
                    rname = rep["name"]
                    
                    rep_sales = [s for s in sales_rows if s.get("employee_id") == rid or s.get("employee_id") == runame]
                    rep_cust = [c for c in customers_rows if c.get("sold_by_emp_id") == runame or c.get("sold_by_emp_id") == rid or c.get("sold_by_emp_name") == rname]
                    
                    all_deals = list(rep_sales) + list(rep_cust)
                    
                    counts = {"1y": 0, "3y": 0, "5y": 0, "vip": 0}
                    for s in all_deals:
                        pl = (s.get("note") or s.get("notes") or s.get("plan_label") or s.get("plan") or "").lower()
                        amt = float(s.get("amount") or s.get("purchase_amount") or 0)
                        if "vip" in pl or "lifetime" in pl or amt >= 12000:
                            counts["vip"] += 1
                        elif "5 year" in pl or "5y" in pl or amt >= 5000:
                            counts["5y"] += 1
                        elif "3 year" in pl or "3y" in pl or amt >= 2500:
                            counts["3y"] += 1
                        else:
                            counts["1y"] += 1

                    plan_progress = []
                    tot_comm = 0
                    mandatory_met = False
                    for pl in config["plans"]:
                        cnt = counts[pl["id"]]
                        tgt = pl["target"]
                        comm_rate = pl["commission"]
                        unlocked = cnt >= tgt
                        if unlocked:
                            mandatory_met = True
                        bonus_cnt = max(0, cnt - tgt)
                        earned = bonus_cnt * comm_rate
                        tot_comm += earned
                        plan_progress.append({
                            "id": pl["id"],
                            "name": pl["name"],
                            "price": pl["price"],
                            "target": tgt,
                            "count": cnt,
                            "is_unlocked": unlocked,
                            "bonus_sales": bonus_cnt,
                            "commission_earned": earned,
                            "commission_rate": comm_rate
                        })

                    reps.append({
                        "id": rid,
                        "username": runame,
                        "name": rname,
                        "department": rep.get("department", "Sales"),
                        "role": rep.get("role", "sales_member"),
                        "fixed_salary": config["fixed_salary"],
                        "total_sales": len(all_deals),
                        "is_mandatory_target_met": mandatory_met,
                        "commission_earned": tot_comm if mandatory_met else 0,
                        "total_payout": config["fixed_salary"] + (tot_comm if mandatory_met else 0),
                        "plan_progress": plan_progress
                    })

                self.send_json({"ok": True, "config": config, "reps": reps})
                return


            if path == "/api/candidate/offer-response":
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                cid = qs.get("cid", [""])[0]
                action = qs.get("action", [""])[0].strip().lower()
                now_str = now_iso()
                now_display = datetime.now().strftime("%d %b %Y, %I:%M %p")

                if not cid or action not in ("accept", "decline"):
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<!DOCTYPE html><html><body style='background:#0f172a;color:#f8fafc;font-family:sans-serif;padding:40px;text-align:center;'><h2>Invalid Offer Action Link</h2><p>Please check your email link or contact HR.</p></body></html>")
                    return

                with _db_lock:
                    db = get_db()
                    cand = db.execute("SELECT * FROM hr_candidates WHERE id=?", (cid,)).fetchone()
                    if cand:
                        new_status = "offer_accepted" if action == "accept" else "declined"
                        offer_resp = "accepted" if action == "accept" else "declined"
                        decline_r = "" if action == "accept" else "Candidate declined offer via email confirmation link"
                        db.execute("UPDATE hr_candidates SET onboarding_status=?, offer_response_status=?, decline_reason=?, updated_at=? WHERE id=?", (new_status, offer_resp, decline_r, now_str, cid))
                        db.commit()
                    db.close()

                if not cand:
                    self.send_response(404)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<!DOCTYPE html><html><body style='background:#0f172a;color:#f8fafc;font-family:sans-serif;padding:40px;text-align:center;'><h2>Candidate Record Not Found</h2><p>This candidate offer link is invalid or has already been removed.</p></body></html>")
                    return

                cand_name = cand["name"]
                role_name = cand["offered_designation"] or cand["role_applied"] or "Designation"
                cand_email = cand["email"] or ""
                cand_phone = cand["phone"] or ""
                joining_date = cand["joining_date"] or "As scheduled"

                # Send real-time notification email to HR & CC info@sylivion.com in background thread
                def _async_notify():
                    try:
                        smtp_cfg = load_smtp_config()
                        if smtp_cfg and smtp_cfg.get("host"):
                            decision_label = "ACCEPTED" if action == "accept" else "DECLINED"
                            hr_subj = f"[Candidate Response: {decision_label}] {cand_name} — {role_name}"
                            hr_body = (
                                f"Hello HR Team,\n\n"
                                f"Candidate {cand_name} has submitted their response via the email offer link:\n\n"
                                f"• Candidate Decision: {'ACCEPTED — Ready to Join' if action == 'accept' else 'DECLINED / Not Interested'}\n"
                                f"• Candidate Name: {cand_name}\n"
                                f"• Designation: {role_name}\n"
                                f"• Candidate Email: {cand_email}\n"
                                f"• Candidate Phone: {cand_phone}\n"
                                f"• Scheduled Joining Date: {joining_date}\n"
                                f"• Response Timestamp: {now_display}\n\n"
                                f"The candidate's status in the InvoicePro HR Dashboard has been updated to: {'Offer Accepted (Ready to Onboard)' if action == 'accept' else 'Candidate Declined'}.\n\n"
                                f"Regards,\nInvoicePro HR System"
                            )
                            do_send_smtp(
                                smtp_cfg,
                                smtp_cfg.get("from_email") or "info@sylivion.com",
                                hr_subj,
                                hr_body,
                                cc_list=["info@sylivion.com"]
                            )
                            print(f"  [Offer Response Notification Sent] {cand_name} -> {decision_label} (CC: info@sylivion.com)")
                    except Exception as notif_err:
                        print(f"  [Offer Response Email Alert Err] {notif_err}")

                threading.Thread(target=_async_notify, daemon=True).start()


                # Render responsive HTML confirmation page to the candidate
                is_accept = (action == "accept")
                accent_color = "#10b981" if is_accept else "#ef4444"
                icon_html = '<div style="width:64px;height:64px;margin:0 auto 20px;border-radius:50%;background:#064e3b;color:#34d399;display:flex;align-items:center;justify-content:center;font-size:32px;border:2px solid #059669;">✓</div>' if is_accept else '<div style="width:64px;height:64px;margin:0 auto 20px;border-radius:50%;background:#450a0a;color:#f87171;display:flex;align-items:center;justify-content:center;font-size:28px;border:2px solid #dc2626;">✕</div>'
                heading = f"🎉 Offer Accepted!" if is_accept else "Response Recorded"
                msg_body = f"<p style='color:#e2e8f0;font-size:16px;line-height:1.6;margin-bottom:18px;'>Thank you, <strong style='color:#f8fafc;'>{html.escape(cand_name)}</strong>! Your acceptance for the position of <strong style='color:#a5b4fc;'>{html.escape(role_name)}</strong> has been confirmed.</p><p style='color:#94a3b8;font-size:14px;line-height:1.6;'>Our HR department has been notified. Please make sure to report on your scheduled joining date: <strong style='color:#f8fafc;'>{html.escape(joining_date)}</strong> with the requested documents.</p>" if is_accept else f"<p style='color:#e2e8f0;font-size:16px;line-height:1.6;margin-bottom:18px;'>Thank you for letting us know, <strong style='color:#f8fafc;'>{html.escape(cand_name)}</strong>.</p><p style='color:#94a3b8;font-size:14px;line-height:1.6;'>Your response has been recorded in our HR system and the team has been notified. We wish you all the very best in your future career endeavors.</p>"

                resp_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{heading} — InvoicePro</title>
</head>
<body style="margin:0;padding:30px 16px;background-color:#0b0f19;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#f8fafc;display:flex;align-items:center;justify-content:center;min-height:90vh;">
  <div style="max-width:480px;width:100%;background-color:#131b2e;border:1px solid #1e293b;border-radius:20px;padding:36px 28px;text-align:center;box-shadow:0 20px 40px rgba(0,0,0,0.5);">
    {icon_html}
    <h1 style="font-size:24px;font-weight:700;margin:0 0 12px 0;color:#ffffff;">{heading}</h1>
    {msg_body}
    <div style="margin-top:28px;padding-top:20px;border-top:1px solid #1e293b;font-size:12px;color:#64748b;">
      InvoicePro HR Desk • Automated Confirmation
    </div>
  </div>
</body>
</html>"""

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(resp_html.encode("utf-8"))))
                self.end_headers()
                self.wfile.write(resp_html.encode("utf-8"))
                return


            if path == "/api/leaves":
                with _db_lock:
                    db = get_db()
                    leaves = rows_to_list(db.execute("SELECT * FROM leave_requests ORDER BY created_at DESC").fetchall())
                    db.close()
                self.send_json(leaves)
                return

            if path == "/api/manager/overview":
                with _db_lock:
                    db = get_db()
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    total_emps = db.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
                    sales_today = db.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM employee_sales WHERE date LIKE ?", (f"{today_str}%",)).fetchone()
                    keys_today = db.execute("SELECT COUNT(*) FROM customers WHERE purchase_date LIKE ?", (f"{today_str}%",)).fetchone()[0]
                    open_enquiries = db.execute("SELECT COUNT(*) FROM enquiries WHERE status='open'").fetchone()[0]
                    pending_leaves = db.execute("SELECT COUNT(*) FROM leave_requests WHERE status='pending'").fetchone()[0]
                    recent_leaves = rows_to_list(db.execute("SELECT * FROM leave_requests ORDER BY created_at DESC LIMIT 5").fetchall())
                    recent_enquiries = rows_to_list(db.execute("SELECT * FROM enquiries ORDER BY created_at DESC LIMIT 5").fetchall())
                    db.close()
                self.send_json({
                    "totalEmployees": total_emps,
                    "salesTodayCount": sales_today[0] or 0,
                    "salesTodayAmount": sales_today[1] or 0,
                    "keysGeneratedToday": keys_today or 0,
                    "openEnquiries": open_enquiries or 0,
                    "pendingLeaves": pending_leaves or 0,
                    "recentLeaves": recent_leaves,
                    "recentEnquiries": recent_enquiries
                })
                return

            if path in ("/api/system/settings", "/api/system-settings"):
                with _db_lock:
                    db = get_db()
                    rows = rows_to_list(db.execute("SELECT * FROM system_settings").fetchall())
                    db.close()
                settings = {}
                for r in rows:
                    k = r.get("key")
                    v = r.get("value")
                    try:
                        settings[k] = json.loads(v)
                    except Exception:
                        settings[k] = v
                self.send_json({"ok": True, "settings": settings})
                return

            if path in ("/api/dev/data", "/api/dev/tasks"):
                with _db_lock:
                    db = get_db()
                    tasks = rows_to_list(db.execute("SELECT * FROM dev_tasks ORDER BY created_at DESC").fetchall())
                    releases = rows_to_list(db.execute("SELECT * FROM dev_releases ORDER BY release_date DESC").fetchall())
                    meta_row = db.execute("SELECT value FROM system_settings WHERE key='dev_metadata'").fetchone()
                    db.close()
                meta = {}
                if meta_row:
                    try: meta = json.loads(meta_row[0] or "{}")
                    except Exception: pass
                self.send_json({
                    "ok": True,
                    "tasks": tasks,
                    "releases": releases,
                    "sprints": meta.get("sprints", []),
                    "prs": meta.get("prs", []),
                    "escalations": meta.get("escalations", []),
                    "docs": meta.get("docs", [])
                })
                return

            if path == "/api/sales/data":
                with _db_lock:
                    db = get_db()
                    meta_row = db.execute("SELECT value FROM system_settings WHERE key='sales_metadata'").fetchone()
                    acts = rows_to_list(db.execute("SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT 500").fetchall())
                    db.close()
                meta = {}
                if meta_row:
                    try: meta = json.loads(meta_row[0] or "{}")
                    except Exception: pass
                self.send_json({
                    "ok": True,
                    "leads": meta.get("leads", []),
                    "targets": meta.get("targets", []),
                    "escalations": meta.get("escalations", []),
                    "activities": acts
                })
                return

            if path == "/api/support/data":
                with _db_lock:
                    db = get_db()
                    meta_row = db.execute("SELECT value FROM system_settings WHERE key='support_metadata'").fetchone()
                    recs = rows_to_list(db.execute("SELECT * FROM recurring_issues ORDER BY impacted_count DESC").fetchall())
                    enqs = rows_to_list(db.execute("SELECT * FROM enquiries ORDER BY created_at DESC").fetchall())
                    db.close()
                meta = {}
                if meta_row:
                    try: meta = json.loads(meta_row[0] or "{}")
                    except Exception: pass
                
                raw_tickets = meta.get("tickets", [])
                if not raw_tickets:
                    raw_tickets = []
                    for e in enqs:
                        tid = e.get("id") or ("ST-" + str(random.randint(100, 999)))
                        raw_tickets.append({
                            "id": tid,
                            "ticketNo": tid,
                            "ticket_no": tid,
                            "customerName": e.get("customer_name") or e.get("name") or "Customer",
                            "customer_name": e.get("customer_name") or e.get("name") or "Customer",
                            "phone": e.get("phone") or "",
                            "mobile": e.get("phone") or "",
                            "subject": e.get("subject") or e.get("message") or "Support Request",
                            "category": e.get("category") or "GST & Invoicing",
                            "channel": e.get("channel") or "Phone Call",
                            "priority": (e.get("priority") or "Medium").capitalize(),
                            "status": e.get("status") or "open",
                            "assignedTo": e.get("assigned_to") or "",
                            "assigned_to": e.get("assigned_to") or "",
                            "assignedToName": e.get("assigned_to_name") or "Unassigned",
                            "createdAt": e.get("created_at") or "",
                            "created_at": e.get("created_at") or ""
                        })

                self.send_json({
                    "ok": True,
                    "tickets": raw_tickets,
                    "calls": meta.get("calls", []),
                    "kb": meta.get("kb", []),
                    "recurring_issues": recs
                })
                return

            if path == "/api/license-keys":
                with _db_lock:
                    db = get_db()
                    keys = rows_to_list(db.execute("SELECT * FROM license_keys ORDER BY created_at DESC").fetchall())
                    db.close()
                self.send_json({"ok": True, "license_keys": keys})
                return

            if path == "/api/export":
                with _db_lock:
                    db = get_db()
                    customers = rows_to_list(db.execute("SELECT * FROM customers").fetchall())
                    for c in customers:
                        c["support_renewals"] = rows_to_list(db.execute(
                            "SELECT * FROM support_renewals WHERE customer_id=?", (c["id"],)).fetchall())
                    reports  = rows_to_list(db.execute("SELECT * FROM reports").fetchall())
                    enquiries = rows_to_list(db.execute("SELECT * FROM enquiries").fetchall())
                    db.close()
                data = {"customers": customers, "reports": reports, "enquiries": enquiries,
                        "exportedAt": now_iso(), "version": "1.0"}
                body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Disposition", "attachment; filename=\"invoicepro-admin-backup.json\"")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/favicon.ico":
                # 1x1 transparent ICO — stops browser 404 noise
                ico = bytes([
                    0,0,1,0,1,0,1,1,0,0,1,0,24,0,40,0,0,0,22,0,0,0,40,0,0,0,
                    1,0,0,0,2,0,0,0,1,0,24,0,0,0,0,0,4,0,0,0,0,0,0,0,0,0,0,0,
                    0,0,0,0,0,0,0,0,0,0,255,255,255,0,0,0,255,255
                ])
                self.send_response(200)
                self.send_header("Content-Type", "image/x-icon")
                self.send_header("Content-Length", str(len(ico)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(ico)
                return
            self.send_err("Not found", 404)

        except Exception:
            traceback.print_exc()
            self.send_err(traceback.format_exc(), 500)

    # ── POST ──────────────────────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.read_json()

            if path == "/api/admin/me/profile":
                username = (data.get("username") or "").strip().lower()
                emp_id = (data.get("employeeId") or data.get("emp_id") or "").strip()
                name = (data.get("name") or "").strip()
                email = (data.get("email") or "").strip()
                phone = (data.get("phone") or data.get("mobile") or "").strip()
                upi_id = (data.get("upi_id") or "").strip()
                upi_qr_image = (data.get("upi_qr_image") or "").strip()

                # Update SQLite employees database
                with _db_lock:
                    db = get_db()
                    target_emp = None
                    if emp_id:
                        target_emp = db.execute("SELECT * FROM employees WHERE id=? OR emp_id=?", (emp_id, emp_id)).fetchone()
                    if not target_emp and (email or username):
                        target_emp = db.execute("SELECT * FROM employees WHERE LOWER(email)=? OR LOWER(name)=? OR LOWER(email) LIKE ?", 
                                                (email.lower(), username, f"%{username}%")).fetchone()
                    
                    if target_emp:
                        emp_dict = dict(target_emp)
                        parse_emp_extra(emp_dict)
                        if upi_id: emp_dict["upi_id"] = upi_id
                        if upi_qr_image: emp_dict["upi_qr_image"] = upi_qr_image
                        if name: emp_dict["name"] = name
                        if email: emp_dict["email"] = email
                        if phone: emp_dict["mobile"] = phone
                        
                        extra_json = emp_extra_data(emp_dict)
                        db.execute("""UPDATE employees 
                                      SET name=?, email=?, mobile=?, extra_data=?, updated_at=?
                                      WHERE id=?""",
                                   (emp_dict.get("name"), emp_dict.get("email"), emp_dict.get("mobile"), extra_json, now_iso(), emp_dict["id"]))
                        db.commit()
                    db.close()

                # Also update admin_data/employees.json if it exists
                emp_file = os.path.join(DATA_DIR, "employees.json")
                if os.path.exists(emp_file):
                    try:
                        with open(emp_file, "r", encoding="utf-8") as f:
                            emps = json.load(f)
                        for e in emps:
                            e_match = False
                            if emp_id and (e.get("id") == emp_id or e.get("empId") == emp_id):
                                e_match = True
                            elif email and (e.get("email") or "").lower() == email.lower():
                                e_match = True
                            elif username and ((e.get("email") or "").lower().startswith(username) or (e.get("name") or "").lower() == username):
                                e_match = True
                            if e_match:
                                if upi_id: e["upi_id"] = upi_id
                                if upi_qr_image: e["upi_qr_image"] = upi_qr_image
                                if name: e["name"] = name
                                if email: e["email"] = email
                                if phone: e["mobile"] = phone
                        with open(emp_file, "w", encoding="utf-8") as f:
                            json.dump(emps, f, indent=2)
                    except Exception as ex:
                        print(f"  [Profile] employees.json update error: {ex}")

                # Also update admin_data/users.json if it exists
                users_file = os.path.join(DATA_DIR, "users.json")
                if os.path.exists(users_file):
                    try:
                        with open(users_file, "r", encoding="utf-8") as f:
                            users = json.load(f)
                        for u in users:
                            if (u.get("username") or "").lower() == username or (email and (u.get("email") or "").lower() == email.lower()):
                                if upi_id: u["upi_id"] = upi_id
                                if upi_qr_image: u["upi_qr_image"] = upi_qr_image
                                if name: u["name"] = name
                                if email: u["email"] = email
                                if phone: u["phone"] = phone
                        with open(users_file, "w", encoding="utf-8") as f:
                            json.dump(users, f, indent=2)
                    except Exception as ex:
                        print(f"  [Profile] users.json update error: {ex}")

                self.send_json({"success": True, "message": "Profile updated successfully", "upi_id": upi_id})
                return

            if path == "/api/sales/targets/config":
                target_file = os.path.join(DATA_DIR, "sales_target_config.json")
                config = {
                    "fixed_salary": int(data.get("fixed_salary") or 15000),
                    "plans": data.get("plans") or [
                        {"id": "1y", "name": "1 Year Plan", "price": 1499, "target": 15, "commission": 499, "icon": "fa-calendar-days", "color": "indigo"},
                        {"id": "3y", "name": "3 Year Plan", "price": 3999, "target": 10, "commission": 999, "icon": "fa-calendar-check", "color": "purple"},
                        {"id": "5y", "name": "5 Year Plan", "price": 6499, "target": 5, "commission": 1499, "icon": "fa-gem", "color": "emerald"},
                        {"id": "vip", "name": "VIP Lifetime Plan", "price": 18499, "target": 3, "commission": 1999, "icon": "fa-crown", "color": "amber"}
                    ]
                }
                with open(target_file, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
                self.send_json({"ok": True, "config": config})
                return

            # ── Receive incoming report from user InvoicePro instance ─────────
            if path == "/api/incoming-report":
                license_key = (data.get("licenseKey") or "").strip()
                with _db_lock:
                    db = get_db()
                    cust = row_to_dict(db.execute(
                        "SELECT id FROM customers WHERE license_key=?", (license_key,)).fetchone())
                    cid = cust["id"] if cust else ""
                    rid = new_id()
                    db.execute("""INSERT INTO reports
                        (id,customer_id,license_key,category,message,contact_email,app_version,os_info,status,created_at,source)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (rid, cid, license_key,
                         data.get("category", "General"),
                         (data.get("message") or "").strip(),
                         data.get("contactEmail", ""),
                         data.get("appVersion", ""),
                         data.get("osInfo", ""),
                         "open", now_iso(), "api"))
                    db.commit()
                    db.close()
                print(f"  [Report IN] [{data.get('category','?')}] {(data.get('message') or '')[:60]}")
            # ── Sylivion Checkout & Keygen Integration ───────────────────────
            if path in ("/api/checkout/order", "/api/checkout/webhook", "/api/checkout", "/api/orders/create", "/api/v1/checkout/order", "/api/license-keys/generate", "/api/customers/keygen"):
                c_company = (data.get("company") or data.get("customer_name") or data.get("customerName") or data.get("name") or data.get("business_name") or data.get("client_name") or "").strip()
                c_owner = (data.get("owner") or data.get("owner_name") or data.get("contact_person") or c_company).strip()
                c_name = c_company if c_company else c_owner
                if not c_name:
                    c_name = "InvoicePro Customer"
                
                c_email = (data.get("customer_email") or data.get("email") or data.get("customerEmail") or "").strip()
                c_phone = (data.get("customer_phone") or data.get("phone") or data.get("mobile") or data.get("customerPhone") or "").strip()
                c_city = (data.get("city") or data.get("customer_city") or "").strip()
                c_gstin = (data.get("gstin") or data.get("gst_number") or data.get("tax_id") or "").strip()
                plan_name = (data.get("plan_name") or data.get("plan") or data.get("planLabel") or data.get("plan_label") or data.get("package") or "1 Year Plan").strip()
                try:
                    amount = float(data.get("amount") or data.get("price") or data.get("total_amount") or data.get("totalAmount") or 1499.0)
                except Exception:
                    amount = 1499.0
                currency = (data.get("currency") or "INR").strip().upper()
                tx_id = (data.get("transaction_id") or data.get("transactionId") or data.get("payment_id") or data.get("paymentId") or data.get("utr") or data.get("txId") or f"TXN-{os.urandom(4).hex().upper()}").strip()
                is_upi = bool(data.get("is_manual_upi") or "upi" in (data.get("payment_method") or "").lower())
                pay_method = (data.get("payment_method") or data.get("paymentMethod") or ("Direct UPI QR Code" if is_upi else "Razorpay Gateway")).strip()
                order_num = (data.get("order_id") or data.get("orderId") or data.get("orderNumber") or f"ORD-{int(time.time())}-{os.urandom(2).hex().upper()}").strip()
                raw_emp_id = (data.get("emp_id") or data.get("empId") or data.get("employee_id") or data.get("employeeId") or data.get("referral_code") or data.get("referralCode") or data.get("employee_code") or data.get("sales_person") or data.get("salesPerson") or "").strip()
                c_status = "pending_verification" if is_upi else "active"
                order_status = "pending_verification" if is_upi else "completed"
                
                # License Key Generation
                lic_key = (data.get("license_key") or data.get("licenseKey") or "").strip()
                if not lic_key and not is_upi:
                    lic_key = f"INV-{os.urandom(2).hex().upper()}-{os.urandom(2).hex().upper()}-{os.urandom(2).hex().upper()}"
                
                # Plan duration calculation
                plan_years = 1
                low_p = plan_name.lower()
                if "3" in low_p or "3y" in low_p: plan_years = 3
                elif "5" in low_p or "5y" in low_p: plan_years = 5
                elif any(k in low_p for k in ["lifetime", "vip", "life"]): plan_years = 99
                elif "1m" in low_p or "1 month" in low_p: plan_years = 0.1
                
                today_str = datetime.now().strftime("%Y-%m-%d")
                try:
                    if plan_years == 0.1:
                        plan_end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                    else:
                        exp_year = datetime.now().year + (int(plan_years) if plan_years < 50 else 50)
                        plan_end_date = datetime.now().replace(year=exp_year).strftime("%Y-%m-%d")
                except Exception:
                    plan_end_date = f"{datetime.now().year + 1}-12-31"

                with _db_lock:
                    db = get_db()
                    # 1. Match Employee attribution
                    matched_emp = find_employee_by_identifier(db, raw_emp_id)
                    emp_code = matched_emp["emp_id"] if matched_emp else raw_emp_id
                    emp_real_name = matched_emp["name"] if matched_emp else ""
                    sales_rep_name = emp_real_name or (f"EMP: {emp_code}" if emp_code else "Sylivion Checkout")

                    # 2. Check or Create/Update Customer
                    cust_row = None
                    if data.get("id"):
                        cust_row = db.execute("SELECT id, name, email, phone, notes FROM customers WHERE id=?", (data["id"],)).fetchone()
                    if not cust_row and c_email:
                        cust_row = db.execute("SELECT id, name, email, phone, notes FROM customers WHERE LOWER(TRIM(email))=?", (c_email.lower(),)).fetchone()
                    if not cust_row and c_phone:
                        clean_p = re.sub(r'\D', '', c_phone)[-10:]
                        if clean_p:
                            cust_row = db.execute("SELECT id, name, email, phone, notes FROM customers WHERE phone LIKE ? OR phone=?", (f"%{clean_p}", c_phone)).fetchone()
                    if not cust_row and c_name:
                        cust_row = db.execute("SELECT id, name, email, phone, notes FROM customers WHERE LOWER(TRIM(name))=?", (c_name.lower(),)).fetchone()
                    
                    notes_str = f"Purchased via Sylivion Checkout. Plan: {plan_name}" + (f" · EMP: {emp_code} ({emp_real_name})" if emp_code else "")

                    if cust_row:
                        cid = cust_row["id"]
                        old_notes = str(cust_row["notes"] or "")
                        combined_notes = (old_notes + "\n" + notes_str).strip() if old_notes and notes_str not in old_notes else (old_notes or notes_str)
                        db.execute("""UPDATE customers SET 
                            name=?, owner=?, city=?, currency=?, gstin=?, email=?, phone=?, license_key=?, purchase_date=?, purchase_amount=?, 
                            plan_end_date=?, plan_label=?, sold_by_emp_id=?, sold_by_emp_name=?, 
                            sales_person=?, payment_method=?, transaction_id=?, checkout_source=?, 
                            status=?, order_id=?, notes=?, updated_at=?
                            WHERE id=?""",
                            (c_name, c_owner, c_city, currency, c_gstin,
                             c_email or cust_row["email"], c_phone or cust_row["phone"],
                             lic_key, today_str, amount, plan_end_date, plan_name,
                             emp_code, emp_real_name, sales_rep_name, pay_method, tx_id,
                             "Sylivion Checkout", c_status, order_num, combined_notes, now_iso(), cid))
                    else:
                        cid = data.get("id") or new_id()
                        db.execute("""INSERT INTO customers 
                            (id, name, owner, city, currency, email, phone, gstin, license_key, purchase_date,
                             purchase_amount, support_purchased, support_amount, notes, plan_end_date,
                             sold_by_emp_id, sold_by_emp_name, sales_person, added_by, plan_label,
                             payment_method, transaction_id, checkout_source, status, order_id, created_at, updated_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (cid, c_name, c_owner, c_city, currency, c_email, c_phone, c_gstin, lic_key, today_str,
                             amount, 1, 0, notes_str, plan_end_date, emp_code, emp_real_name, sales_rep_name, "Sylivion Checkout",
                             plan_name, pay_method, tx_id, "Sylivion Checkout", c_status, order_num, now_iso(), now_iso()))

                    # 3. Record in employee_sales if employee attributed
                    commission, sale_id = record_employee_sale_db(db, matched_emp, cid, c_name, plan_name, amount, order_num, "Sylivion Checkout")

                    # 4. Insert into checkout_orders
                    chk_id = new_id()
                    db.execute("""INSERT OR REPLACE INTO checkout_orders
                        (id, order_id, customer_id, customer_name, customer_email, customer_phone, city,
                         plan_name, plan_duration_years, amount, currency, payment_status, payment_method,
                         transaction_id, emp_id, emp_name, commission_calculated, license_key_generated,
                         checkout_source, raw_payload, created_at, updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (chk_id, order_num, cid, c_name, c_email, c_phone, c_city,
                         plan_name, int(plan_years) if plan_years >= 1 else 1, amount, currency, order_status, pay_method,
                         tx_id, emp_code, emp_real_name, commission, lic_key,
                         "Sylivion Checkout", json.dumps(data), now_iso(), now_iso()))

                    # 5. Insert license key record
                    if lic_key:
                        db.execute("""INSERT OR REPLACE INTO license_keys 
                            (id, license_key, customer_id, customer_name, plan_name, duration_years, status, generated_by, expiry_date, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (new_id(), lic_key, cid, c_name, plan_name, int(plan_years) if plan_years >= 1 else 1, "active", f"checkout ({emp_code or 'direct'})", plan_end_date, now_iso()))

                    # 6. Audit Log
                    db.execute("""INSERT INTO audit_logs 
                        (id, user_id, user_name, role, action, module, details, timestamp)
                        VALUES (?,?,?,?,?,?,?,?)""",
                        (new_id(), emp_code or "checkout-system", emp_real_name or "Sylivion Checkout", "sales" if emp_code else "system",
                         f"Processed checkout order {order_num} for {c_name} (Plan: {plan_name}, EMP: {emp_code or 'None'})",
                         "Checkout", f"Amount: {currency} {amount}, License: {lic_key}, Commission: Rs {commission}", now_iso()))

                    db.commit()
                    db.close()

                self.send_json({
                    "ok": True,
                    "order_id": order_num,
                    "customer_id": cid,
                    "customer_name": c_name,
                    "license_key": lic_key,
                    "plan_name": plan_name,
                    "plan_end_date": plan_end_date,
                    "amount": amount,
                    "currency": currency,
                    "employee_attributed": {
                        "matched": bool(matched_emp),
                        "emp_id": emp_code,
                        "name": emp_real_name,
                        "commission": commission
                    } if emp_code else None
                })
                return

            # ── Customers ─────────────────────────────────────────────────────
            if path == "/api/customers/add":
                with _db_lock:
                    db = get_db()
                    cid = (data.get("id") or "").strip() or new_id()
                    name = (data.get("name") or "").strip()
                    if not name:
                        self.send_err("name is required", 400)
                        return
                    phone = str(data.get("phone", "")).strip()
                    if phone and not is_valid_phone(phone, required=False):
                        self.send_err("Invalid mobile number format (e.g. 9876543210 or +91 9876543210).", 400)
                        return
                    email = str(data.get("email", "")).strip()
                    if email and not is_valid_email(email, required=False):
                        self.send_err("Invalid email address format (e.g. customer@gmail.com).", 400)
                        return
                    
                    def safe_num(key, default):
                        v = data.get(key)
                        if v is None or v == "" or v != v:
                            return default
                        try: return float(v)
                        except (TypeError, ValueError): return default
                    purchase_amount  = safe_num("purchaseAmount", 1499)
                    support_amount   = safe_num("supportAmount", 499)
                    sold_by_emp_id   = str(data.get("soldByEmpId") or data.get("sold_by_emp_id") or "").strip()
                    sold_by_emp_name = str(data.get("soldByEmpName") or data.get("sold_by_emp_name") or "").strip()
                    sales_person     = str(data.get("salesPerson") or data.get("sales_person") or sold_by_emp_name or "").strip()
                    added_by         = str(data.get("addedBy") or data.get("added_by") or "").strip()
                    plan_label       = str(data.get("planLabel") or data.get("plan_label") or "").strip()
                    notes_str        = str(data.get("notes") or "")
                    lic_key          = str(data.get("licenseKey") or data.get("license_key") or "").strip()

                    if not sold_by_emp_id:
                        m = re.search(r'EMP:\s*([A-Za-z0-9\-]+)(?:\s*\(([^)]+)\))?', notes_str)
                        if m:
                            sold_by_emp_id = m.group(1).strip()
                            if not sold_by_emp_name and m.group(2):
                                sold_by_emp_name = m.group(2).strip()
                                if not sales_person: sales_person = sold_by_emp_name

                    matched_emp = find_employee_by_identifier(db, sold_by_emp_id or sold_by_emp_name or sales_person)
                    if matched_emp:
                        sold_by_emp_id = matched_emp.get("emp_id") or sold_by_emp_id
                        sold_by_emp_name = matched_emp.get("name") or sold_by_emp_name
                        if not sales_person: sales_person = sold_by_emp_name

                    # Check if customer already exists by id, email, or phone
                    cust_exist = None
                    if cid:
                        cust_exist = row_to_dict(db.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone())
                    if not cust_exist and email:
                        cust_exist = row_to_dict(db.execute("SELECT * FROM customers WHERE LOWER(TRIM(email))=?", (email.lower(),)).fetchone())
                    if not cust_exist and phone:
                        clean_p = re.sub(r'\D', '', phone)[-10:]
                        if clean_p:
                            cust_exist = row_to_dict(db.execute("SELECT * FROM customers WHERE phone LIKE ? OR phone=?", (f"%{clean_p}", phone)).fetchone())
                    
                    cust_exist = cust_exist or {}
                    final_cid = cust_exist.get("id") or cid

                    db.execute("""INSERT OR REPLACE INTO customers
                        (id,name,owner,city,currency,email,phone,gstin,license_key,purchase_date,purchase_amount,
                         support_purchased,support_purchase_date,support_amount,notes,plan_end_date,trial_end_date,
                         sold_by_emp_id,sold_by_emp_name,sales_person,added_by,plan_label,
                         payment_method,transaction_id,checkout_source,status,order_id,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (final_cid, name,
                         str(data.get("owner") or cust_exist.get("owner", "")),
                         str(data.get("city") or cust_exist.get("city", "")),
                         str(data.get("currency") or cust_exist.get("currency", "INR")),
                         email or cust_exist.get("email", ""),
                         phone or cust_exist.get("phone", ""),
                         str(data.get("gstin") or cust_exist.get("gstin", "")),
                         lic_key or cust_exist.get("license_key", ""),
                         str(data.get("purchaseDate") or cust_exist.get("purchase_date", now_iso()[:10])),
                         purchase_amount,
                         1 if data.get("supportPurchased") else (1 if cust_exist.get("support_purchased") else 0),
                         str(data.get("supportPurchaseDate") or cust_exist.get("support_purchase_date", "")),
                         support_amount,
                         notes_str or cust_exist.get("notes", ""),
                         str(data.get("planEndDate") or cust_exist.get("plan_end_date", "")),
                         str(data.get("trialEndDate") or cust_exist.get("trial_end_date", "")),
                         sold_by_emp_id, sold_by_emp_name, sales_person, added_by, plan_label,
                         str(data.get("payment_method") or cust_exist.get("payment_method", "")),
                         str(data.get("transaction_id") or cust_exist.get("transaction_id", "")),
                         str(data.get("checkout_source") or cust_exist.get("checkout_source", "Admin")),
                         str(data.get("status") or cust_exist.get("status", "active")),
                         str(data.get("order_id") or cust_exist.get("order_id", "")),
                         cust_exist.get("created_at", now_iso()),
                         now_iso()))

                    # Automatically record employee sale and calculate commission if attributed
                    if matched_emp and purchase_amount > 0:
                        record_employee_sale_db(db, matched_emp, final_cid, name, plan_label or "Standard", purchase_amount, "", "Admin Entry/Keygen", notes_str)

                    # Insert license key record if present
                    if lic_key:
                        db.execute("""INSERT OR REPLACE INTO license_keys 
                            (id, license_key, customer_id, customer_name, plan_name, duration_years, status, generated_by, expiry_date, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (new_id(), lic_key, final_cid, name, plan_label or "Standard", 1, "active", f"admin ({sold_by_emp_id or 'direct'})", str(data.get("planEndDate") or ""), now_iso()))

                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": final_cid})
                return

            if path == "/api/customers/update":
                with _db_lock:
                    db = get_db()
                    phone = str(data.get("phone", "")).strip()
                    if phone and not is_valid_phone(phone, required=False):
                        self.send_err("Invalid mobile number format (e.g. 9876543210 or +91 9876543210).", 400)
                        return
                    email = str(data.get("email", "")).strip()
                    if email and not is_valid_email(email, required=False):
                        self.send_err("Invalid email address format (e.g. customer@gmail.com).", 400)
                        return
                    
                    cid = str(data.get("id") or "").strip()
                    existing = None
                    if cid:
                        existing = row_to_dict(db.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone())
                    if not existing and email:
                        existing = row_to_dict(db.execute("SELECT * FROM customers WHERE LOWER(TRIM(email))=?", (email.lower(),)).fetchone())
                    if not existing and phone:
                        clean_p = re.sub(r'\D', '', phone)[-10:]
                        if clean_p:
                            existing = row_to_dict(db.execute("SELECT * FROM customers WHERE phone LIKE ? OR phone=?", (f"%{clean_p}", phone)).fetchone())
                    if not existing and data.get("name"):
                        existing = row_to_dict(db.execute("SELECT * FROM customers WHERE LOWER(TRIM(name))=?", (str(data.get("name")).lower().strip(),)).fetchone())

                    existing = existing or {}
                    final_cid = existing.get("id") or cid or new_id()

                    sold_by_emp_id   = str(data.get("soldByEmpId", existing.get("sold_by_emp_id", "")) or "").strip()
                    sold_by_emp_name = str(data.get("soldByEmpName", existing.get("sold_by_emp_name", "")) or "").strip()
                    sales_person     = str(data.get("salesPerson", existing.get("sales_person", "")) or sold_by_emp_name or "").strip()
                    added_by         = str(data.get("addedBy", existing.get("added_by", "")) or "").strip()
                    plan_label       = str(data.get("planLabel", existing.get("plan_label", "")) or "").strip()
                    notes_str        = str(data.get("notes", existing.get("notes", "")) or "")
                    lic_key          = str(data.get("licenseKey", existing.get("license_key", "")) or "").strip()

                    if not sold_by_emp_id:
                        m = re.search(r'EMP:\s*([A-Za-z0-9\-]+)(?:\s*\(([^)]+)\))?', notes_str)
                        if m:
                            sold_by_emp_id = m.group(1).strip()
                            if not sold_by_emp_name and m.group(2):
                                sold_by_emp_name = m.group(2).strip()
                                if not sales_person: sales_person = sold_by_emp_name

                    matched_emp = find_employee_by_identifier(db, sold_by_emp_id or sold_by_emp_name or sales_person)
                    if matched_emp:
                        sold_by_emp_id = matched_emp.get("emp_id") or sold_by_emp_id
                        sold_by_emp_name = matched_emp.get("name") or sold_by_emp_name
                        if not sales_person: sales_person = sold_by_emp_name

                    purchase_amt     = data.get("purchaseAmount", existing.get("purchase_amount", 1499))
                    try: purchase_amt = float(purchase_amt)
                    except Exception: purchase_amt = 1499.0

                    c_name = str(data.get("name", existing.get("name", ""))).strip() or "Customer"

                    db.execute("""INSERT OR REPLACE INTO customers
                        (id,name,owner,city,currency,email,phone,gstin,license_key,purchase_date,purchase_amount,
                         support_purchased,support_purchase_date,support_amount,notes,plan_end_date,trial_end_date,
                         sold_by_emp_id,sold_by_emp_name,sales_person,added_by,plan_label,
                         payment_method,transaction_id,checkout_source,status,order_id,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (final_cid,
                         c_name,
                         data.get("owner",          existing.get("owner", "")),
                         data.get("city",           existing.get("city", "")),
                         data.get("currency",       existing.get("currency", "INR")),
                         email or existing.get("email", ""),
                         phone or existing.get("phone", ""),
                         data.get("gstin",          existing.get("gstin", "")),
                         lic_key or existing.get("license_key", ""),
                         data.get("purchaseDate",   existing.get("purchase_date", now_iso()[:10])),
                         purchase_amt,
                         1 if data.get("supportPurchased", bool(existing.get("support_purchased"))) else 0,
                         data.get("supportPurchaseDate", existing.get("support_purchase_date", "")),
                         data.get("supportAmount",  existing.get("support_amount", 499)),
                         notes_str,
                         data.get("planEndDate",     existing.get("plan_end_date", "")),
                         data.get("trialEndDate",    existing.get("trial_end_date", "")),
                         sold_by_emp_id, sold_by_emp_name, sales_person, added_by, plan_label,
                         data.get("payment_method", existing.get("payment_method", "")),
                         data.get("transaction_id", existing.get("transaction_id", "")),
                         data.get("checkout_source", existing.get("checkout_source", "Admin")),
                         data.get("status", existing.get("status", "active")),
                         data.get("order_id", existing.get("order_id", "")),
                         existing.get("created_at", now_iso()),
                         now_iso()))

                    # Automatically record employee sale and calculate commission if attributed
                    if matched_emp and purchase_amt > 0:
                        record_employee_sale_db(db, matched_emp, final_cid, c_name, plan_label or "Standard", purchase_amt, "", "Admin Update/Keygen", notes_str)

                    # Insert/update license key record if present
                    if lic_key:
                        db.execute("""INSERT OR REPLACE INTO license_keys 
                            (id, license_key, customer_id, customer_name, plan_name, duration_years, status, generated_by, expiry_date, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (new_id(), lic_key, final_cid, c_name, plan_label or "Standard", 1, "active", f"admin ({sold_by_emp_id or 'direct'})", str(data.get("planEndDate", existing.get("plan_end_date", ""))), now_iso()))

                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": final_cid})
                return

            if path == "/api/customers/delete":
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM customers WHERE id=?", (data["id"],))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            if path == "/api/customers/add-renewal":
                self.send_ok()
                return

            # ── Reports ───────────────────────────────────────────────────────
            if path == "/api/reports/add":
                with _db_lock:
                    db = get_db()
                    rid = new_id()
                    db.execute("""INSERT INTO reports
                        (id,customer_id,license_key,category,message,contact_email,status,created_at,source)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        (rid, data.get("customerId",""), data.get("licenseKey",""),
                         data.get("category","General"), data.get("message",""),
                         data.get("contactEmail",""), "open", now_iso(), "manual"))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": rid})
                return

            if path == "/api/reports/reply":
                with _db_lock:
                    db = get_db()
                    db.execute("UPDATE reports SET reply=?,status='resolved',replied_at=? WHERE id=?",
                        (data["reply"], now_iso(), data["id"]))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            if path == "/api/reports/resolve":
                with _db_lock:
                    db = get_db()
                    db.execute("UPDATE reports SET status='resolved',replied_at=? WHERE id=?",
                        (now_iso(), data["id"]))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            if path == "/api/reports/delete":
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM reports WHERE id=?", (data["id"],))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            # ── Enquiries ─────────────────────────────────────────────────────
                        # --- SUPPORT RECURRING ISSUES REAL-TIME CRUD ---
            if path in ("/api/support/recurring-issues/add", "/api/support/recurring-issues"):
                issue_title = str(data.get("issue", "")).strip()
                if not issue_title:
                    self.send_json({"ok": False, "error": "Issue title is required"})
                    return
                with _db_lock:
                    db = get_db()
                    last_row = db.execute("SELECT id FROM recurring_issues WHERE id LIKE 'REC-%' ORDER BY id DESC LIMIT 1").fetchone()
                    next_num = 1
                    if last_row and last_row[0]:
                        try:
                            next_num = int(last_row[0].replace("REC-", "")) + 1
                        except Exception:
                            next_num = db.execute("SELECT COUNT(*) FROM recurring_issues").fetchone()[0] + 1
                    rid = data.get("id") or f"REC-{str(next_num).zfill(2)}"
                    now = now_iso()
                    db.execute("""
                        INSERT INTO recurring_issues (
                            id, issue, category, severity, impacted_count, workaround, root_cause,
                            status, dev_bug_id, created_by_id, created_by_name, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rid,
                        issue_title,
                        data.get("category") or "GST & Invoicing",
                        data.get("severity") or "High",
                        int(data.get("impactedCount") or data.get("impacted_count") or 1),
                        data.get("workaround") or "",
                        data.get("root_cause") or "",
                        data.get("status") or "Open",
                        data.get("dev_bug_id") or "",
                        data.get("created_by_id") or "",
                        data.get("created_by_name") or "",
                        now,
                        now
                    ))
                    db.commit()
                    all_recs = rows_to_list(db.execute("SELECT * FROM recurring_issues ORDER BY CASE status WHEN 'Open' THEN 1 WHEN 'Investigating' THEN 2 WHEN 'In Dev Fix' THEN 3 WHEN 'Resolved' THEN 4 ELSE 5 END, impacted_count DESC, created_at DESC").fetchall())
                    created_rec = db.execute("SELECT * FROM recurring_issues WHERE id = ?", (rid,)).fetchone()
                    db.close()
                self.send_json({"ok": True, "id": rid, "recurring_issue": dict(created_rec) if created_rec else None, "recurring_issues": all_recs})
                return

            if path == "/api/support/recurring-issues/update":
                rid = str(data.get("id", "")).strip()
                if not rid:
                    self.send_json({"ok": False, "error": "Recurring issue ID is required"})
                    return
                with _db_lock:
                    db = get_db()
                    existing = db.execute("SELECT * FROM recurring_issues WHERE id = ?", (rid,)).fetchone()
                    if not existing:
                        db.close()
                        self.send_json({"ok": False, "error": "Recurring issue not found"})
                        return
                    existing_dict = dict(existing)
                    now = now_iso()
                    db.execute("""
                        UPDATE recurring_issues SET
                            issue = ?,
                            category = ?,
                            severity = ?,
                            impacted_count = ?,
                            workaround = ?,
                            root_cause = ?,
                            status = ?,
                            dev_bug_id = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (
                        str(data.get("issue", existing_dict["issue"])).strip(),
                        str(data.get("category", existing_dict["category"])),
                        str(data.get("severity", existing_dict["severity"])),
                        int(data.get("impactedCount") or data.get("impacted_count") or existing_dict["impacted_count"]),
                        str(data.get("workaround", existing_dict["workaround"])),
                        str(data.get("root_cause", existing_dict["root_cause"])),
                        str(data.get("status", existing_dict["status"])),
                        str(data.get("dev_bug_id", existing_dict["dev_bug_id"])),
                        now,
                        rid
                    ))
                    db.commit()
                    all_recs = rows_to_list(db.execute("SELECT * FROM recurring_issues ORDER BY CASE status WHEN 'Open' THEN 1 WHEN 'Investigating' THEN 2 WHEN 'In Dev Fix' THEN 3 WHEN 'Resolved' THEN 4 ELSE 5 END, impacted_count DESC, created_at DESC").fetchall())
                    updated_rec = db.execute("SELECT * FROM recurring_issues WHERE id = ?", (rid,)).fetchone()
                    db.close()
                self.send_json({"ok": True, "recurring_issue": dict(updated_rec) if updated_rec else None, "recurring_issues": all_recs})
                return

            if path == "/api/support/recurring-issues/increment":
                rid = str(data.get("id", "")).strip()
                if not rid:
                    self.send_json({"ok": False, "error": "Recurring issue ID is required"})
                    return
                with _db_lock:
                    db = get_db()
                    now = now_iso()
                    db.execute("UPDATE recurring_issues SET impacted_count = impacted_count + 1, updated_at = ? WHERE id = ?", (now, rid))
                    db.commit()
                    updated_rec = db.execute("SELECT * FROM recurring_issues WHERE id = ?", (rid,)).fetchone()
                    all_recs = rows_to_list(db.execute("SELECT * FROM recurring_issues ORDER BY CASE status WHEN 'Open' THEN 1 WHEN 'Investigating' THEN 2 WHEN 'In Dev Fix' THEN 3 WHEN 'Resolved' THEN 4 ELSE 5 END, impacted_count DESC, created_at DESC").fetchall())
                    db.close()
                self.send_json({"ok": True, "id": rid, "recurring_issue": dict(updated_rec) if updated_rec else None, "recurring_issues": all_recs})
                return

            if path == "/api/support/recurring-issues/resolve":
                rid = str(data.get("id", "")).strip()
                if not rid:
                    self.send_json({"ok": False, "error": "Recurring issue ID is required"})
                    return
                with _db_lock:
                    db = get_db()
                    now = now_iso()
                    new_status = data.get("status", "Resolved")
                    db.execute("UPDATE recurring_issues SET status = ?, updated_at = ? WHERE id = ?", (new_status, now, rid))
                    db.commit()
                    all_recs = rows_to_list(db.execute("SELECT * FROM recurring_issues ORDER BY CASE status WHEN 'Open' THEN 1 WHEN 'Investigating' THEN 2 WHEN 'In Dev Fix' THEN 3 WHEN 'Resolved' THEN 4 ELSE 5 END, impacted_count DESC, created_at DESC").fetchall())
                    db.close()
                self.send_json({"ok": True, "id": rid, "status": new_status, "recurring_issues": all_recs})
                return

            if path == "/api/support/recurring-issues/delete":
                rid = str(data.get("id", "")).strip()
                if not rid:
                    self.send_json({"ok": False, "error": "Recurring issue ID is required"})
                    return
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM recurring_issues WHERE id = ?", (rid,))
                    db.commit()
                    all_recs = rows_to_list(db.execute("SELECT * FROM recurring_issues ORDER BY CASE status WHEN 'Open' THEN 1 WHEN 'Investigating' THEN 2 WHEN 'In Dev Fix' THEN 3 WHEN 'Resolved' THEN 4 ELSE 5 END, impacted_count DESC, created_at DESC").fetchall())
                    db.close()
                self.send_json({"ok": True, "deleted_id": rid, "recurring_issues": all_recs})
                return

            if path == "/api/enquiries/add":
                with _db_lock:
                    db = get_db()
                    eid = data.get("id") or new_id()
                    db.execute("""INSERT INTO enquiries (
                        id, customer_id, date, subject, priority, channel,
                        customer_name, customer_phone, message, status, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (eid, data.get("customerId") or data.get("customer_id") or "",
                         data.get("date", now_iso()[:10]),
                         data.get("subject", "General Support / Inquiry"),
                         data.get("priority", "Normal"),
                         data.get("channel", "Phone Call"),
                         data.get("customerName") or data.get("customer_name") or "",
                         data.get("phone") or data.get("customer_phone") or "",
                         data.get("message", ""), "open", now_iso()))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": eid})
                return

            if path == "/api/enquiries/claim":
                with _db_lock:
                    db = get_db()
                    eid = data.get("id") or data.get("enquiryId") or data.get("enquiry_id")
                    leader_id = data.get("leaderId") or data.get("leader_id") or data.get("claimed_by_leader_id") or ""
                    leader_name = data.get("leaderName") or data.get("leader_name") or data.get("claimed_by_leader_name") or ""
                    team_id = data.get("teamId") or data.get("team_id") or data.get("claimed_team_id") or ""
                    team_name = data.get("teamName") or data.get("team_name") or data.get("claimed_team_name") or "Support Team"
                    claimed_at = data.get("claimedAt") or data.get("claimed_at") or now_iso()
                    db.execute("""UPDATE enquiries SET 
                        claimed_by_leader_id=?, claimed_by_leader_name=?, 
                        claimed_team_id=?, claimed_team_name=?, 
                        claimed_at=?, status='claimed' 
                        WHERE id=?""",
                        (leader_id, leader_name, team_id, team_name, claimed_at, eid))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            if path == "/api/enquiries/assign":
                with _db_lock:
                    db = get_db()
                    eid = data.get("id") or data.get("enquiryId") or data.get("enquiry_id")
                    member_id = data.get("memberId") or data.get("member_id") or data.get("assigned_member_id") or ""
                    member_name = data.get("memberName") or data.get("member_name") or data.get("assigned_member_name") or ""
                    assigned_at = data.get("assignedAt") or data.get("assigned_at") or now_iso()
                    db.execute("""UPDATE enquiries SET 
                        assigned_member_id=?, assigned_member_name=?, 
                        assigned_at=?, status='in_progress' 
                        WHERE id=?""",
                        (member_id, member_name, assigned_at, eid))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            if path == "/api/enquiries/reply":
                with _db_lock:
                    db = get_db()
                    eid = data.get("id") or data.get("enquiryId") or data.get("enquiry_id")
                    reply_text = data.get("reply") or data.get("solution") or data.get("solutionNotes") or ""
                    member_name = data.get("memberName") or data.get("member_name") or data.get("resolved_by_member_name") or ""
                    leader_name = data.get("leaderName") or data.get("leader_name") or data.get("resolved_by_leader_name") or ""
                    team_name = data.get("teamName") or data.get("team_name") or data.get("resolved_by_team") or ""
                    res_at = data.get("resolvedAt") or data.get("resolved_at") or now_iso()
                    db.execute("""UPDATE enquiries SET 
                        reply=?, status='resolved', resolved_at=?,
                        resolved_by_member_name=CASE WHEN ? != '' THEN ? ELSE resolved_by_member_name END,
                        resolved_by_leader_name=CASE WHEN ? != '' THEN ? ELSE resolved_by_leader_name END,
                        resolved_by_team=CASE WHEN ? != '' THEN ? ELSE resolved_by_team END
                        WHERE id=?""",
                        (reply_text, res_at, member_name, member_name, leader_name, leader_name, team_name, team_name, eid))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            if path == "/api/enquiries/resolve":
                with _db_lock:
                    db = get_db()
                    eid = data.get("id") or data.get("enquiryId") or data.get("enquiry_id")
                    reply_text = data.get("reply") or data.get("solution") or data.get("solutionNotes") or ""
                    member_name = data.get("memberName") or data.get("member_name") or data.get("resolved_by_member_name") or ""
                    leader_name = data.get("leaderName") or data.get("leader_name") or data.get("resolved_by_leader_name") or ""
                    team_name = data.get("teamName") or data.get("team_name") or data.get("resolved_by_team") or ""
                    res_at = data.get("resolvedAt") or data.get("resolved_at") or now_iso()
                    db.execute("""UPDATE enquiries SET 
                        status='resolved', resolved_at=?,
                        reply=CASE WHEN ? != '' THEN ? ELSE reply END,
                        resolved_by_member_name=CASE WHEN ? != '' THEN ? ELSE resolved_by_member_name END,
                        resolved_by_leader_name=CASE WHEN ? != '' THEN ? ELSE resolved_by_leader_name END,
                        resolved_by_team=CASE WHEN ? != '' THEN ? ELSE resolved_by_team END
                        WHERE id=?""",
                        (res_at, reply_text, reply_text, member_name, member_name, leader_name, leader_name, team_name, team_name, eid))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            if path == "/api/enquiries/delete":
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM enquiries WHERE id=?", (data["id"],))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            # ── Employees ─────────────────────────────────────────────────────
            if path == "/api/employees":
                with _db_lock:
                    db = get_db()
                    emps = rows_to_list(db.execute("SELECT * FROM employees ORDER BY created_at DESC").fetchall())
                    for emp in emps:
                        emp["sales"]    = rows_to_list(db.execute("SELECT * FROM employee_sales WHERE employee_id=? ORDER BY date", (emp["id"],)).fetchall())
                        emp["payments"] = rows_to_list(db.execute("SELECT * FROM employee_payments WHERE employee_id=? ORDER BY date", (emp["id"],)).fetchall())
                        parse_emp_extra(emp)
                    db.close()
                self.send_json(emps)
                return

            if path == "/api/teams/save":
                teams_list = data.get("teams", [])
                with _db_lock:
                    db = get_db()
                    for t in teams_list:
                        tid = t.get("id") or ("team-" + str(int(time.time() * 1000)))
                        members_json = json.dumps(t.get("members", [])) if isinstance(t.get("members"), list) else json.dumps([])
                        db.execute('''
                            INSERT OR REPLACE INTO teams (id, dept_id, name, code, lead_name, lead_phone, lead_email, members, headcount, targetMonthly, progress, focus_area, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            tid,
                            t.get("dept_id", ""),
                            t.get("name", ""),
                            t.get("code", ""),
                            t.get("lead_name", ""),
                            t.get("lead_phone", ""),
                            t.get("lead_email", ""),
                            members_json,
                            int(t.get("headcount") or (len(t.get("members", [])) if isinstance(t.get("members"), list) else 1)),
                            t.get("targetMonthly", ""),
                            int(t.get("progress") or 0),
                            t.get("focus_area", ""),
                            t.get("created_at") or datetime.now().isoformat()
                        ))
                    db.commit()
                self.send_json({"ok": True, "message": "Teams saved successfully"})
                return

            if path == "/api/teams/delete":
                tid = data.get("id")
                if tid:
                    with _db_lock:
                        db = get_db()
                        db.execute("DELETE FROM teams WHERE id = ?", (tid,))
                        db.commit()
                self.send_json({"ok": True, "message": "Team deleted successfully"})
                return

            if path == "/api/employees/add":
                with _db_lock:
                    db = get_db()
                    eid = data.get("id") or new_id()
                    emp_id_val = (data.get("empId") or "").strip()
                    name = str(data.get("name", "")).strip()
                    if not name:
                        self.send_err("Employee name is required", 400)
                        return
                    if not emp_id_val:
                        self.send_err("empId is required", 400)
                        return
                    mobile = str(data.get("mobile", "")).strip()
                    if not mobile or not is_valid_phone(mobile, required=True):
                        self.send_err("Valid 10-digit mobile number is required for employee.", 400)
                        return
                    email = str(data.get("email", "")).strip()
                    if email and not is_valid_email(email, required=False):
                        self.send_err("Invalid email address format (e.g. employee@gmail.com).", 400)
                        return
                    # Check for duplicate by id, emp_id, mobile or email — update instead of duplicate insert
                    existing = db.execute("SELECT id FROM employees WHERE id=? OR emp_id=? OR (mobile!='' AND mobile=?) OR (email!='' AND LOWER(email)=LOWER(?))", (eid, emp_id_val, mobile, email)).fetchone()
                    if existing:
                        db.execute("""UPDATE employees SET
                            name=?,mobile=?,email=?,designation=?,department=?,join_date=?,notes=?,extra_data=?,updated_at=?
                            WHERE id=?""",
                            (name, mobile, email,
                             data.get("designation",""), data.get("department",""),
                             data.get("joinDate",""), data.get("notes",""),
                             emp_extra_data(data), now_iso(), existing["id"]))
                        eid = existing["id"]
                    else:
                        db.execute("""INSERT INTO employees
                            (id,emp_id,name,mobile,email,designation,department,join_date,notes,extra_data,created_at,updated_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (eid, emp_id_val, name,
                             mobile, email,
                             data.get("designation",""), data.get("department",""),
                             data.get("joinDate",""), data.get("notes",""),
                             emp_extra_data(data), now_iso(), now_iso()))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": eid})
                return

            if path == "/api/employees/update":
                with _db_lock:
                    db = get_db()
                    mobile = str(data.get("mobile", "")).strip()
                    if mobile and not is_valid_phone(mobile, required=False):
                        self.send_err("Valid 10-digit mobile number is required for employee.", 400)
                        return
                    email = str(data.get("email", "")).strip()
                    if email and not is_valid_email(email, required=False):
                        self.send_err("Invalid email address format (e.g. employee@gmail.com).", 400)
                        return
                    db.execute("""UPDATE employees SET
                        name=?,mobile=?,email=?,designation=?,department=?,join_date=?,notes=?,extra_data=?,updated_at=?
                        WHERE id=?""",
                        (data["name"], mobile, email,
                         data.get("designation",""), data.get("department",""),
                         data.get("joinDate",""), data.get("notes",""),
                         emp_extra_data(data), now_iso(), data["id"]))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            if path == "/api/employees/delete":
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM employee_sales WHERE employee_id=?", (data["id"],))
                    db.execute("DELETE FROM employee_payments WHERE employee_id=?", (data["id"],))
                    db.execute("DELETE FROM employees WHERE id=?", (data["id"],))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            if path == "/api/employees/add-sale":
                with _db_lock:
                    db = get_db()
                    sid = data.get("id") or new_id()
                    raw_emp_ident = data.get("employeeId") or data.get("employee_id") or data.get("empId") or data.get("emp_id") or ""
                    matched_emp = find_employee_by_identifier(db, raw_emp_ident)
                    emp_id = matched_emp["id"] if matched_emp else str(raw_emp_ident)
                    emp_code = matched_emp["emp_id"] if matched_emp else ""
                    emp_name = matched_emp["name"] if matched_emp else ""
                    
                    cname = (data.get("customerName") or data.get("customer_name") or "").strip()
                    cid = data.get("customerId") or data.get("customer_id") or ""
                    sale_amount = data.get("amount", 1499)
                    try: sale_amount = float(sale_amount)
                    except Exception: sale_amount = 1499.0
                    plan_label = data.get("planLabel") or data.get("plan_label") or data.get("plan") or "Standard"
                    comm_val = data.get("commission")
                    if comm_val is None or comm_val == "":
                        comm_val = calculate_plan_commission(plan_label, sale_amount, data.get("note", ""))
                    else:
                        try: comm_val = float(comm_val)
                        except Exception: comm_val = calculate_plan_commission(plan_label, sale_amount, data.get("note", ""))
                    
                    sdate = data.get("date", now_iso()[:10])
                    snote = data.get("note", "") or f"Keygen/Manual Sale: {cname} ({plan_label})"
                    cur_month = sdate[:7]
                    
                    # Deduplicate: if sale with this id or (employeeId, customerName/customerId) already exists, update in-place
                    existing = None
                    if data.get("id"):
                        existing = db.execute("SELECT id FROM employee_sales WHERE id=?", (data["id"],)).fetchone()
                    if not existing and cid:
                        existing = db.execute("SELECT id FROM employee_sales WHERE employee_id=? AND (customer_id=? OR note LIKE ?)", (emp_id, cid, f"%{cid}%")).fetchone()
                    if not existing and cname:
                        existing = db.execute("SELECT id FROM employee_sales WHERE employee_id=? AND LOWER(TRIM(customer_name))=?", (emp_id, cname.lower())).fetchone()
                    
                    if existing:
                        db.execute("""UPDATE employee_sales
                            SET customer_name=?, customer_id=?, plan_name=?, date=?, amount=?, commission=?, note=?, target_month=?
                            WHERE id=?""",
                            (cname, cid, plan_label, sdate, sale_amount, comm_val, snote, cur_month, existing["id"]))
                        sid = existing["id"]
                    else:
                        try:
                            db.execute("""INSERT INTO employee_sales
                                (id,employee_id,emp_id,customer_id,customer_name,plan_name,date,amount,commission,note,status,target_month,created_at)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (sid, emp_id, emp_code, cid, cname, plan_label, sdate, sale_amount, comm_val, snote, "approved", cur_month, now_iso()))
                        except Exception:
                            db.execute("""INSERT INTO employee_sales
                                (id,employee_id,customer_name,date,amount,commission,note,created_at)
                                VALUES (?,?,?,?,?,?,?,?)""",
                                (sid, emp_id, cname, sdate, sale_amount, comm_val, snote, now_iso()))
                    
                    # Sync customer soldByEmpId/soldByEmpName if customer exists
                    if cid or cname:
                        try:
                            if cid:
                                db.execute("UPDATE customers SET sold_by_emp_id=?, sold_by_emp_name=?, sales_person=? WHERE id=?", (emp_code, emp_name, emp_name, cid))
                            elif cname:
                                db.execute("UPDATE customers SET sold_by_emp_id=?, sold_by_emp_name=?, sales_person=? WHERE LOWER(TRIM(name))=?", (emp_code, emp_name, emp_name, cname.lower()))
                        except Exception:
                            pass

                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": sid, "commission": comm_val})
                return

            if path == "/api/employees/delete-sale":
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM employee_sales WHERE id=?", (data["id"],))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            if path == "/api/employees/add-payment":
                with _db_lock:
                    db = get_db()
                    pid = data.get("id") or new_id()
                    db.execute("""INSERT INTO employee_payments
                        (id,employee_id,date,amount,note,created_at)
                        VALUES (?,?,?,?,?,?)""",
                        (pid, data["employeeId"], data.get("date", now_iso()[:10]),
                         data.get("amount", 0), data.get("note",""), now_iso()))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": pid})
                return

            if path == "/api/employees/delete-payment":
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM employee_payments WHERE id=?", (data["id"],))
                    db.commit()
                    db.close()
                self.send_ok()
                return

            # ── Import backup ─────────────────────────────────────────────────────
            if path == "/api/import":
                imported = {"customers": 0, "reports": 0, "enquiries": 0}
                with _db_lock:
                    db = get_db()
                    for c in data.get("customers", []):
                        exists = db.execute("SELECT id FROM customers WHERE id=?", (c.get("id",""),)).fetchone()
                        if not exists:
                            db.execute("""INSERT OR IGNORE INTO customers
                                (id,name,email,phone,license_key,purchase_date,purchase_amount,
                                 support_purchased,support_purchase_date,support_amount,notes,created_at,updated_at)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (c.get("id", new_id()),
                                 c.get("name",""), c.get("email",""), c.get("phone",""),
                                 c.get("license_key","") or c.get("licenseKey",""),
                                 c.get("purchase_date","") or c.get("purchaseDate",""),
                                 c.get("purchase_amount",1499) or c.get("purchaseAmount",1499),
                                 1 if (c.get("support_purchased") or c.get("supportPurchased")) else 0,
                                 c.get("support_purchase_date","") or c.get("supportPurchaseDate",""),
                                 c.get("support_amount",499) or c.get("supportAmount",499),
                                 c.get("notes",""),
                                 c.get("created_at","") or c.get("createdAt", now_iso()),
                                 now_iso()))
                            imported["customers"] += 1
                    for r in data.get("reports", []):
                        db.execute("""INSERT OR IGNORE INTO reports
                            (id,customer_id,license_key,category,message,contact_email,status,reply,created_at,source)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (r.get("id", new_id()),
                             r.get("customer_id","") or r.get("customerId",""),
                             r.get("license_key","") or r.get("licenseKey",""),
                             r.get("category","General"), r.get("message",""),
                             r.get("contact_email","") or r.get("contactEmail",""),
                             r.get("status","open"), r.get("reply",""),
                             r.get("created_at","") or r.get("createdAt", now_iso()),
                             r.get("source","import")))
                        imported["reports"] += 1
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "imported": imported})
                return

            # ── SMTP config ───────────────────────────────────────────────────
            if path == "/api/smtp-config":
                save_smtp_config(data)
                self.send_ok("SMTP settings saved.")
                return

            # ── Send single email ─────────────────────────────────────────────
            if path == "/api/send-email":
                cfg = load_smtp_config()
                stored_pw = cfg.get("password", "")
                if data.get("cfg") and isinstance(data["cfg"], dict):
                    client_cfg = data["cfg"]
                    for k, v in client_cfg.items():
                        if k == "password" and is_dummy_password(v):
                            continue
                        if v or k not in cfg:
                            cfg[k] = v
                if is_dummy_password(cfg.get("password")) and stored_pw:
                    cfg["password"] = stored_pw

                if not cfg.get("host"):
                    self.send_json({"ok": False, "error": "SMTP not configured. Open Email Settings to set up."})
                    return
                to          = data.get("to", "").strip()
                subject     = data.get("subject", "").strip()
                body        = data.get("body", "").strip()
                attachments = data.get("attachments") or ([] if not data.get("attachment") else [data.get("attachment")])
                cc_list     = data.get("cc", []) or data.get("cc_list", [])
                from_email_override = data.get("from_email") or data.get("fromEmail")
                from_name_override = data.get("from_name") or data.get("fromName")
                if not to:
                    self.send_json({"ok": False, "error": "Recipient email address is required."})
                    return
                try:
                    do_send_smtp(cfg, to, subject, body, attachments=attachments, cc_list=cc_list, from_email_override=from_email_override, from_name_override=from_name_override)
                    self.send_json({"ok": True, "msg": f"Email sent to {to}"})
                except smtplib.SMTPAuthenticationError:
                    if stored_pw and cfg.get("password") != stored_pw:
                        try:
                            cfg["password"] = stored_pw
                            do_send_smtp(cfg, to, subject, body, attachments=attachments, cc_list=cc_list, from_email_override=from_email_override, from_name_override=from_name_override)
                            self.send_json({"ok": True, "msg": f"Email sent to {to}"})
                            return
                        except Exception as retry_err:
                            self.send_json({"ok": False, "error": f"SMTP authentication failed: {retry_err}"})
                            return
                    self.send_json({"ok": False, "error": "SMTP authentication failed. Please check username and password."})
                except Exception as e:
                    self.send_json({"ok": False, "error": f"Failed to send email: {str(e)}"})
                return

            # ── Send broadcast emails ─────────────────────────────────────────
            if path == "/api/send-broadcast":
                cfg = load_smtp_config()
                stored_pw = cfg.get("password", "")
                if data.get("cfg") and isinstance(data["cfg"], dict):
                    client_cfg = data["cfg"]
                    for k, v in client_cfg.items():
                        if k == "password" and is_dummy_password(v):
                            continue
                        if v or k not in cfg:
                            cfg[k] = v
                if is_dummy_password(cfg.get("password")) and stored_pw:
                    cfg["password"] = stored_pw

                if not cfg.get("host"):
                    self.send_json({"ok": False, "error": "SMTP not configured. Open Email Settings to set up."})
                    return
                to_list     = data.get("to") or []
                if isinstance(to_list, str):
                    to_list = [t.strip() for t in to_list.split(",") if t.strip()]
                subject     = data.get("subject", "").strip()
                body        = data.get("body", "").strip()
                attachments = data.get("attachments") or ([] if not data.get("attachment") else [data.get("attachment")])
                
                sent_count = 0
                errors = []
                for recipient in to_list:
                    r_clean = (recipient or "").strip()
                    if not r_clean:
                        continue
                    try:
                        do_send_smtp(cfg, r_clean, subject, body, attachments=attachments)
                        sent_count += 1
                    except Exception as err:
                        errors.append({"to": r_clean, "error": str(err)})
                self.send_json({"ok": True, "sent": sent_count, "errors": errors})
                return

            # ── Sync Fallback ─────────────────────────────────────────────────
            if path == "/api/sync":
                self.send_json({"ok": True, "msg": "Sync batch received successfully"})
                return

            # ── Activity & Audit Logs ─────────────────────────────────────────
            if path in ("/api/activity-logs/add", "/api/audit-logs/add", "/api/log-activity", "/api/sales/activities/add"):
                log_id = data.get("id") or ("act-" + str(int(time.time() * 1000)) + "-" + uuid.uuid4().hex[:5])
                user_id = data.get("user_id") or data.get("user_emp_id") or data.get("employee_id") or ""
                user_name = data.get("user_name") or data.get("rep_name") or data.get("employee_name") or "Staff"
                role = data.get("user_role") or data.get("role") or ""
                action = data.get("description") or data.get("action") or data.get("summary") or "Action logged"
                module = data.get("type") or data.get("category") or data.get("module") or "General"
                details = data.get("details") or data.get("summary") or action
                client_ip = self.client_address[0] if self.client_address else "127.0.0.1"
                ts = data.get("timestamp") or data.get("ts") or data.get("created_at") or now_iso()
                extra_json = json.dumps(data)

                with _db_lock:
                    db = get_db()
                    # Record in audit_logs
                    db.execute("""
                        INSERT OR REPLACE INTO audit_logs (id, user_id, user_name, role, action, module, details, ip_address, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (log_id, user_id, user_name, role, action, module, details, client_ip, ts))
                    
                    # Also record in activity_logs
                    act_type = data.get("type") or data.get("activity_type") or "call"
                    target = data.get("lead_name") or data.get("customer_name") or data.get("target_contact") or ""
                    db.execute("""
                        INSERT OR REPLACE INTO activity_logs (id, employee_id, employee_name, activity_type, target_contact, details, extra_data, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (log_id, user_id, user_name, act_type, target, details, extra_json, ts))
                    
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": log_id})
                return

            if path in ("/api/activity-logs/clear", "/api/audit-logs/clear"):
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM audit_logs")
                    db.execute("DELETE FROM activity_logs")
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "message": "Logs cleared successfully"})
                return

            if path in ("/api/system/settings/save", "/api/system/settings", "/api/system-settings/save"):
                settings_map = data.get("settings") if isinstance(data.get("settings"), dict) else data
                now_str = now_iso()
                with _db_lock:
                    db = get_db()
                    for k, v in settings_map.items():
                        v_str = json.dumps(v) if not isinstance(v, str) else v
                        cat = "company" if "company" in k else "security" if "pin" in k or "sec" in k else "general"
                        db.execute("""
                            INSERT OR REPLACE INTO system_settings (key, value, category, updated_at)
                            VALUES (?, ?, ?, ?)
                        """, (k, v_str, cat, now_str))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "message": "Settings saved successfully"})
                return

            if path in ("/api/dev/data/save", "/api/dev/tasks/save"):
                now_str = now_iso()
                with _db_lock:
                    db = get_db()
                    tasks = data.get("tasks") or []
                    for t in tasks:
                        tid = t.get("id") or ("TASK-" + str(int(time.time() * 1000)))
                        db.execute("""
                            INSERT OR REPLACE INTO dev_tasks (id, title, description, category, priority, status, assignee_id, assignee_name, dev_notes, branch_name, pr_link, due_date, created_by_id, created_by_name, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            tid,
                            t.get("title", ""),
                            t.get("description", "") or t.get("dev_notes", ""),
                            t.get("category", "Bug"),
                            t.get("priority", "High"),
                            t.get("status", "todo"),
                            t.get("assignee_id", "") or t.get("assignee", ""),
                            t.get("assignee_name", "") or t.get("assigneeName", ""),
                            t.get("dev_notes", ""),
                            t.get("branch", "") or t.get("branch_name", ""),
                            t.get("pr_link", "") or t.get("prLink", ""),
                            t.get("due_date", ""),
                            t.get("created_by_id", ""),
                            t.get("created_by_name", ""),
                            t.get("created_at") or now_str,
                            t.get("updated_at") or now_str
                        ))
                    
                    meta = {
                        "sprints": data.get("sprints", []),
                        "prs": data.get("prs", []),
                        "escalations": data.get("escalations", []),
                        "docs": data.get("docs", [])
                    }
                    db.execute("""
                        INSERT OR REPLACE INTO system_settings (key, value, category, updated_at)
                        VALUES ('dev_metadata', ?, 'development', ?)
                    """, (json.dumps(meta), now_str))
                    
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "message": "Dev data synchronized successfully"})
                return

            if path == "/api/sales/data/save":
                now_str = now_iso()
                meta = {
                    "leads": data.get("leads", []),
                    "targets": data.get("targets", []),
                    "escalations": data.get("escalations", [])
                }
                with _db_lock:
                    db = get_db()
                    db.execute("""
                        INSERT OR REPLACE INTO system_settings (key, value, category, updated_at)
                        VALUES ('sales_metadata', ?, 'sales', ?)
                    """, (json.dumps(meta), now_str))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "message": "Sales data synchronized successfully"})
                return

            if path == "/api/support/data/save":
                now_str = now_iso()
                meta = {
                    "tickets": data.get("tickets", []),
                    "calls": data.get("calls", []),
                    "kb": data.get("kb", [])
                }
                with _db_lock:
                    db = get_db()
                    db.execute("""
                        INSERT OR REPLACE INTO system_settings (key, value, category, updated_at)
                        VALUES ('support_metadata', ?, 'support', ?)
                    """, (json.dumps(meta), now_str))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "message": "Support data synchronized successfully"})
                return

            if path == "/api/test-email":
                cfg = load_smtp_config()
                stored_pw = cfg.get("password", "")
                if data.get("cfg") and isinstance(data["cfg"], dict):
                    client_cfg = data["cfg"]
                    for k, v in client_cfg.items():
                        if k == "password" and is_dummy_password(v):
                            continue
                        if v or k not in cfg:
                            cfg[k] = v
                if is_dummy_password(cfg.get("password")) and stored_pw:
                    cfg["password"] = stored_pw

                if not cfg.get("host"):
                    self.send_json({"ok": False, "error": "SMTP not configured in Email Settings."})
                    return
                test_addr = cfg.get("from_email") or cfg.get("username", "")
                try:
                    do_send_smtp(cfg, test_addr, "InvoicePro — SMTP Test",
                                 "This is a test email from your InvoicePro Admin Panel.\n\nSMTP is working correctly!")
                    self.send_json({"ok": True, "msg": f"Test email sent to {test_addr}"})
                except smtplib.SMTPAuthenticationError:
                    if stored_pw and cfg.get("password") != stored_pw:
                        try:
                            cfg["password"] = stored_pw
                            do_send_smtp(cfg, test_addr, "InvoicePro — SMTP Test", "SMTP working!")
                            self.send_json({"ok": True, "msg": f"Test email sent to {test_addr}"})
                            return
                        except Exception:
                            pass
                    self.send_json({"ok": False, "error": "SMTP Authentication failed. Please check username/password in Email Settings."})
                except Exception as e:
                    self.send_json({"ok": False, "error": f"Test failed: {e}"})
                return

            # ── Auth & RBAC Staff Management ──────────────────────────────────
            if path == "/api/auth/login":
                client_ip = self.client_address[0] if self.client_address else "127.0.0.1"
                allowed, retry_after = check_login_rate_limit(client_ip)
                if not allowed:
                    self.send_json({"ok": False, "error": f"Too many failed login attempts. Security lock active. Please retry in {retry_after} seconds.", "locked": True}, 429)
                    return
                username = str(data.get("username", "")).strip()
                password = str(data.get("password", "")).strip()
                if not username:
                    self.send_json({"ok": False, "error": "Please enter your username or user ID."})
                    return
                if not password:
                    self.send_json({"ok": False, "error": "Please enter your password."})
                    return
                with _db_lock:
                    db = get_db()
                    # Strict match for username, employee ID, or email with matching password
                    user_row = db.execute("SELECT * FROM staff_users WHERE (username = ? OR emp_id = ? OR email = ?)", (username, username, username)).fetchone()
                    user = None
                    if user_row:
                        user_dict = dict(user_row)
                        if user_dict.get("password") == password:
                            user = user_row

                    # If still not found in staff_users, check employees table
                    if not user:
                        emps = rows_to_list(db.execute("SELECT * FROM employees").fetchall())
                        matched_emp = None
                        for e in emps:
                            parse_emp_extra(e)
                            emp_user = (e.get("staffUsername") or (e.get("name", "").split()[0] + "_" + (e.get("role") or "sales"))).strip()
                            emp_pass = e.get("staffPassword") or "emp123"
                            emp_id_val = (e.get("emp_id") or "").strip()
                            emp_email = (e.get("email") or "").strip()
                            if (emp_user == username or (emp_id_val and emp_id_val.lower() == username.lower()) or (emp_email and emp_email.lower() == username.lower())) and password == emp_pass:
                                matched_emp = e
                                break
                        if matched_emp:
                            r_raw = (matched_emp.get("role") or "").lower()
                            d_raw = (matched_emp.get("department") or "").lower()
                            t_raw = (matched_emp.get("designation") or "").lower()
                            if r_raw in ("admin", "manager", "hr", "sales_leader", "sales_member", "support_leader", "support_member", "dev_leader", "dev_member"):
                                role = r_raw
                            elif "admin" in d_raw or "admin" in t_raw:
                                role = "admin"
                            elif "oper" in d_raw or "manage" in d_raw:
                                role = "manager"
                            elif "hr" in d_raw or "human" in d_raw:
                                role = "hr"
                            elif "supp" in d_raw or "helpdesk" in d_raw:
                                role = "support_leader" if ("lead" in t_raw or "head" in t_raw) else "support_member"
                            elif "dev" in d_raw or "software" in d_raw:
                                role = "dev_leader" if ("lead" in t_raw or "head" in t_raw) else "dev_member"
                            elif "sale" in d_raw:
                                role = "sales_leader" if ("lead" in t_raw or "head" in t_raw) else "sales_member"
                            else:
                                role = "sales_member"

                            uid = "usr-" + str(matched_emp.get("id"))
                            now_str = now_iso()
                            db.execute("""
                                INSERT OR REPLACE INTO staff_users (id, name, username, password, role, department, designation, email, phone, emp_id, active, created_at, last_login)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                            """, (uid, matched_emp.get("name"), username, password, role, matched_emp.get("department", "Sales"), matched_emp.get("designation", "Sales Executive"), matched_emp.get("email", ""), matched_emp.get("mobile", ""), matched_emp.get("emp_id", ""), now_str, now_str))
                            db.commit()
                            user_dict = {
                                "id": uid,
                                "name": matched_emp.get("name"),
                                "username": username,
                                "role": role,
                                "department": matched_emp.get("department", "Sales"),
                                "designation": matched_emp.get("designation", "Sales Executive"),
                                "email": matched_emp.get("email", ""),
                                "phone": matched_emp.get("mobile", ""),
                                "emp_id": matched_emp.get("emp_id", ""),
                                "active": 1,
                                "last_login": now_str
                            }
                            db.close()
                            clear_login_attempts(client_ip)
                            token = generate_session_token(user_dict)
                            self.send_json({"ok": True, "user": user_dict, "token": token})
                            return

                    if not user:
                        db.close()
                        record_failed_login(client_ip)
                        self.send_json({"ok": False, "error": "Invalid username or password."})
                        return
                    user_dict = dict(user)
                    if not user_dict.get("active", 1):
                        db.close()
                        self.send_json({"ok": False, "error": "This account is inactive/suspended. Please contact the administrator."})
                        return
                    # Update last login safely
                    now_str = now_iso()
                    try:
                        db.execute("UPDATE staff_users SET last_login = ? WHERE id = ?", (now_str, user_dict["id"]))
                        db.commit()
                    except Exception as db_err:
                        print(f"  [AUTH] Warning: Failed to update last_login timestamp: {db_err}")
                    finally:
                        try:
                            db.close()
                        except Exception:
                            pass

                # Normalize username-to-role mappings
                un_lower = (user_dict.get("username") or "").lower()
                if un_lower in ("support_lead", "support"):
                    user_dict["role"] = "support_leader"
                elif un_lower in ("support_mem", "support_priya", "support_rahul", "sarah_support"):
                    user_dict["role"] = "support_member"
                elif un_lower in ("sales_lead",):
                    user_dict["role"] = "sales_leader"
                elif un_lower in ("dev_lead", "dev"):
                    user_dict["role"] = "dev_leader"
                elif un_lower in ("dev_front", "dev_back", "dev_flutter", "dev_qa"):
                    user_dict["role"] = "dev_member"

                # Return safe user profile
                user_dict["last_login"] = now_str
                user_dict.pop("password", None)
                role = (user_dict.get("role") or "sales_member").lower()
                if not user_dict.get("department"):
                    user_dict["department"] = (
                        "" if role in ("admin", "manager", "hr")
                        else "Support" if role in ("support", "support_leader", "support_member")
                        else "Development" if role in ("dev_leader", "dev_member", "dev", "development")
                        else "Sales"
                    )
                if not user_dict.get("designation"):
                    user_dict["designation"] = (
                        "Master Administrator" if role == "admin"
                        else "Operations Manager" if role == "manager"
                        else "HR Specialist" if role == "hr"
                        else "Support Team Leader" if role in ("support_leader", "support_lead")
                        else "Technical Support Specialist" if role in ("support_member", "support_mem", "support")
                        else "Development Team Leader" if role in ("dev_leader", "dev_lead")
                        else "Senior Software Engineer" if role in ("dev_member", "dev_front", "dev_back", "dev_flutter", "dev_qa")
                        else "Sales Team Leader" if role in ("sales_leader", "sales_lead")
                        else "Senior Sales Executive"
                    )
                clear_login_attempts(client_ip)
                token = generate_session_token(user_dict)
                self.send_json({"ok": True, "user": user_dict, "token": token})
                return

            if path == "/api/staff-users/add":
                with _db_lock:
                    db = get_db()
                    username = str(data.get("username", "")).strip()
                    if not username:
                        self.send_err("Username is required", 400)
                        return
                    dup_u = db.execute("SELECT id, name FROM staff_users WHERE LOWER(username) = ?", (username.lower(),)).fetchone()
                    if dup_u:
                        self.send_err(f"DUPLICATE USERNAME: Username '{username}' is already taken. Please choose another username.", 409)
                        return
                uid = data.get("id") or ("usr-" + str(uuid.uuid4())[:8])
                name = str(data.get("name", "")).strip()
                username = str(data.get("username", "")).strip()
                password = str(data.get("password", "")).strip() or "staff123"
                role = str(data.get("role", "sales_member")).strip().lower()
                VALID_STAFF_ROLES = (
                    "admin", "manager", "hr",
                    "sales", "sales_leader", "sales_member",
                    "support", "support_leader", "support_member",
                    "dev", "dev_leader", "dev_member", "development"
                )
                if role not in VALID_STAFF_ROLES:
                    role = "sales_member"

                department = str(data.get("department", "")).strip() or (
                    "" if role in ("admin", "manager", "hr")
                    else "Support" if role in ("support", "support_leader", "support_member")
                    else "Development" if role in ("dev_leader", "dev_member", "dev", "development")
                    else "Sales"
                )
                designation = str(data.get("designation", "")).strip() or (
                    "Master Administrator" if role == "admin"
                    else "Operations Manager" if role == "manager"
                    else "HR Specialist" if role == "hr"
                    else "Support Team Leader" if role in ("support_leader", "support_lead")
                    else "Technical Support Specialist" if role in ("support_member", "support_mem", "support")
                    else "Development Team Leader" if role in ("dev_leader", "dev_lead")
                    else "Senior Software Engineer" if role in ("dev_member", "dev_front", "dev_back", "dev_flutter", "dev_qa")
                    else "Sales Team Leader" if role in ("sales_leader", "sales_lead")
                    else "Senior Sales Executive"
                )
                email = str(data.get("email", "")).strip()
                phone = str(data.get("phone", "")).strip()
                emp_id = str(data.get("emp_id", "")).strip()
                active = 1 if data.get("active", True) else 0

                if not username or not name:
                    self.send_json({"ok": False, "error": "Name and Username are required."})
                    return
                if email and not is_valid_email(email, required=False):
                    self.send_json({"ok": False, "error": "Please enter a valid email address (e.g. user@gmail.com)."})
                    return
                if phone and not is_valid_phone(phone, required=False):
                    self.send_json({"ok": False, "error": "Please enter a valid 10-digit mobile number."})
                    return

                with _db_lock:
                    db = get_db()
                    existing = db.execute("SELECT id FROM staff_users WHERE LOWER(username) = LOWER(?)", (username,)).fetchone()
                    if existing:
                        db.close()
                        self.send_json({"ok": False, "error": f"Username '{username}' already exists. Choose a different one."})
                        return
                    now_str = now_iso()
                    db.execute("""
                        INSERT INTO staff_users (id, name, username, password, role, department, designation, email, phone, emp_id, active, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (uid, name, username, password, role, department, designation, email, phone, emp_id, active, now_str))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": uid, "msg": f"Staff profile created for {name} ({role.upper()})."})
                return

            if path == "/api/staff-users/update":
                uid = data.get("id")
                if not uid:
                    self.send_json({"ok": False, "error": "Staff User ID is required."})
                    return
                with _db_lock:
                    db = get_db()
                    existing_user = db.execute("SELECT * FROM staff_users WHERE id=?", (uid,)).fetchone()
                    if not existing_user:
                        db.close()
                        self.send_json({"ok": False, "error": "Staff user not found."})
                        return

                    name = str(data.get("name", existing_user["name"] or "")).strip()
                    role = str(data.get("role", existing_user["role"] or "sales_member")).strip().lower()
                    VALID_STAFF_ROLES = (
                        "admin", "manager", "hr",
                        "sales", "sales_leader", "sales_member",
                        "support", "support_leader", "support_member",
                        "dev", "dev_leader", "dev_member", "development"
                    )
                    if role not in VALID_STAFF_ROLES:
                        role = existing_user["role"] or "sales_member"

                    department = str(data.get("department", existing_user["department"] or "")).strip() or (
                        "" if role in ("admin", "manager", "hr")
                        else "Support" if role in ("support", "support_leader", "support_member")
                        else "Development" if role in ("dev_leader", "dev_member", "dev", "development")
                        else "Sales"
                    )
                    designation = str(data.get("designation", existing_user["designation"] or "")).strip() or (
                        "Master Administrator" if role == "admin"
                        else "Operations Manager" if role == "manager"
                        else "HR Specialist" if role == "hr"
                        else "Support Team Leader" if role in ("support_leader", "support_lead")
                        else "Technical Support Specialist" if role in ("support_member", "support_mem", "support")
                        else "Development Team Leader" if role in ("dev_leader", "dev_lead")
                        else "Senior Software Engineer" if role in ("dev_member", "dev_front", "dev_back", "dev_flutter", "dev_qa")
                        else "Sales Team Leader" if role in ("sales_leader", "sales_lead")
                        else "Senior Sales Executive"
                    )
                    email = str(data.get("email", "")).strip()
                    phone = str(data.get("phone", "")).strip()
                    emp_id = str(data.get("emp_id", existing_user["emp_id"] or "")).strip()
                    active = 1 if data.get("active", True) else 0
                    password = str(data.get("password", "")).strip()

                    if email and not is_valid_email(email, required=False):
                        db.close()
                        self.send_json({"ok": False, "error": "Please enter a valid email address (e.g. user@gmail.com)."})
                        return
                    if phone and not is_valid_phone(phone, required=False):
                        db.close()
                        self.send_json({"ok": False, "error": "Please enter a valid 10-digit mobile number."})
                        return

                    if password:
                        db.execute("""
                            UPDATE staff_users SET name=?, role=?, department=?, designation=?, email=?, phone=?, emp_id=?, active=?, password=?
                            WHERE id=?
                        """, (name, role, department, designation, email, phone, emp_id, active, password, uid))
                    else:
                        db.execute("""
                            UPDATE staff_users SET name=?, role=?, department=?, designation=?, email=?, phone=?, emp_id=?, active=?
                            WHERE id=?
                        """, (name, role, department, designation, email, phone, emp_id, active, uid))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "Staff profile updated successfully."})
                return

            if path == "/api/staff-users/delete":
                uid = data.get("id")
                if not uid:
                    self.send_json({"ok": False, "error": "Staff User ID is required."})
                    return
                with _db_lock:
                    db = get_db()
                    # Check if last admin
                    user = db.execute("SELECT role FROM staff_users WHERE id=?", (uid,)).fetchone()
                    if user and user[0] == "admin":
                        admin_count = db.execute("SELECT COUNT(*) FROM staff_users WHERE role='admin'").fetchone()[0]
                        if admin_count <= 1:
                            db.close()
                            self.send_json({"ok": False, "error": "Cannot delete the last remaining Master Admin account."})
                            return
                    db.execute("DELETE FROM staff_users WHERE id=?", (uid,))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "Staff profile removed."})
                return

            if path == "/api/admin/me/profile":
                username = str(data.get("username", "")).strip()
                emp_id_val = str(data.get("employeeId") or data.get("emp_id") or "").strip()
                name = str(data.get("name", "")).strip()
                email = str(data.get("email", "")).strip()
                phone = str(data.get("phone", "")).strip()
                upi_id = str(data.get("upi_id") or data.get("upiId") or "").strip()
                upi_qr_image = str(data.get("upi_qr_image") or data.get("upiQrImage") or "").strip()

                with _db_lock:
                    db = get_db()
                    if username:
                        db.execute("""
                            UPDATE staff_users 
                            SET name=COALESCE(NULLIF(?, ''), name),
                                email=COALESCE(NULLIF(?, ''), email),
                                phone=COALESCE(NULLIF(?, ''), phone),
                                upi_id=?,
                                upi_qr_image=?
                            WHERE LOWER(username)=LOWER(?)
                        """, (name, email, phone, upi_id, upi_qr_image, username))
                    if emp_id_val or username or email or name:
                        # Find matching employee and update their extra_data and columns
                        emp = db.execute("""
                            SELECT * FROM employees 
                            WHERE id=? OR emp_id=? OR (email!='' AND LOWER(email)=LOWER(?)) OR (name!='' AND LOWER(name)=LOWER(?))
                        """, (emp_id_val, emp_id_val, email, name)).fetchone()
                        if emp:
                            emp_dict = dict(emp)
                            parse_emp_extra(emp_dict)
                            emp_dict["upiId"] = upi_id
                            emp_dict["upi_id"] = upi_id
                            emp_dict["upi_qr_image"] = upi_qr_image
                            emp_dict["upiQrImage"] = upi_qr_image
                            extra_json = emp_extra_data(emp_dict)
                            db.execute("""
                                UPDATE employees 
                                SET name=COALESCE(NULLIF(?, ''), name),
                                    email=COALESCE(NULLIF(?, ''), email),
                                    mobile=COALESCE(NULLIF(?, ''), mobile),
                                    extra_data=?,
                                    updated_at=?
                                WHERE id=?
                            """, (name, email, phone, extra_json, now_iso(), emp_dict["id"]))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "Profile & payout UPI details saved."})
                return

            if path == "/api/staff-users/reset-password":
                uid = data.get("id")
                new_pw = str(data.get("password") or data.get("new_password") or "").strip()
                if not uid or not new_pw:
                    self.send_json({"ok": False, "error": "User ID and new password are required."})
                    return
                with _db_lock:
                    db = get_db()
                    db.execute("UPDATE staff_users SET password=? WHERE id=?", (new_pw, uid))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "Password updated successfully."})
                return

            # ── Leave Management ──────────────────────────────────────────────
            
            # ── HR Portal Endpoints ───────────────────────────────────────────
            if path == "/api/hr/candidates/add":
                with _db_lock:
                    db = get_db()
                    cid = data.get("id") or ("can-" + str(uuid.uuid4())[:8])
                    name = str(data.get("name", "")).strip()
                    email = str(data.get("email", "")).strip()
                    phone = str(data.get("phone", "")).strip()

                    # ── Candidate Deduplication ──
                    norm_phone = normalize_phone_clean(phone)
                    if norm_phone:
                        dup_can = db.execute("""
                            SELECT id, name, phone FROM hr_candidates 
                            WHERE REPLACE(REPLACE(REPLACE(REPLACE(phone, ' ', ''), '-', ''), '+91', ''), '+', '') LIKE ? OR phone = ?
                        """, (f"%{norm_phone}", phone)).fetchone()
                        if dup_can:
                            dup = dict(dup_can)
                            self.send_err(f"DUPLICATE CANDIDATE: A candidate with mobile number '{phone}' already exists: '{dup.get('name')}' (ID: {dup.get('id')}).", 409)
                            return

                    norm_email = normalize_email_clean(email)
                    if norm_email:
                        dup_can_e = db.execute("SELECT id, name, email FROM hr_candidates WHERE LOWER(TRIM(email)) = ? AND email != ''", (norm_email,)).fetchone()
                        if dup_can_e:
                            dup = dict(dup_can_e)
                            self.send_err(f"DUPLICATE CANDIDATE: A candidate with email '{email}' already exists: '{dup.get('name')}' (ID: {dup.get('id')}).", 409)
                            return
                    role_applied = str(data.get("role_applied", "")).strip()
                experience = str(data.get("experience", "")).strip()
                source_type = str(data.get("source_type", "self_connected")).strip()
                referral_code = str(data.get("referral_code", "")).strip()
                referrer_name = str(data.get("referrer_name", "")).strip()
                referrer_phone = str(data.get("referrer_phone", "")).strip()
                referrer_emp_id = str(data.get("referrer_emp_id", "")).strip()
                resume_filename = str(data.get("resume_filename", "")).strip()
                resume_data = str(data.get("resume_data", "")).strip()
                resume_size = str(data.get("resume_size", "")).strip()
                resume_text = str(data.get("resume_text", "")).strip()
                hr_notes = str(data.get("hr_notes", "")).strip()
                now_str = now_iso()

                if not name:
                    self.send_json({"ok": False, "error": "Candidate Name is required."})
                    return
                if not phone or not is_valid_phone(phone, required=True):
                    self.send_json({"ok": False, "error": "A valid 10-digit mobile number is required (e.g. 9876543210 or +91 9876543210)."})
                    return
                if email and not is_valid_email(email, required=False):
                    self.send_json({"ok": False, "error": "Please enter a valid email address (e.g. candidate@gmail.com)."})
                    return
                if referrer_phone and not is_valid_phone(referrer_phone, required=False):
                    self.send_json({"ok": False, "error": "Referrer mobile number must be a valid 10-digit number."})
                    return

                # If referral by known person and code is empty, generate one
                if source_type == "referral_known" and not referral_code:
                    clean = re.sub(r'[^A-Za-z0-9]', '', referrer_name).upper()[:3].ljust(3, 'K') if referrer_name else "KP"
                    rand = str(random.randint(1000, 9999))
                    referral_code = f"REF-{clean}-{rand}"

                with _db_lock:
                    db = get_db()
                    clean_phone = re.sub(r'\D', '', phone)
                    dup = None
                    if email:
                        dup = db.execute("SELECT id, name, phone, email, role_applied FROM hr_candidates WHERE LOWER(email)=LOWER(?) AND id!=?", (email, cid)).fetchone()
                    if not dup and clean_phone:
                        all_cands = db.execute("SELECT id, name, phone, email, role_applied FROM hr_candidates WHERE id!=?", (cid,)).fetchall()
                        for c in all_cands:
                            cp = re.sub(r'\D', '', c["phone"] or "")
                            if cp and cp == clean_phone:
                                dup = c
                                break
                    if dup:
                        db.close()
                        dup_role = dup['role_applied'] or 'General'
                        self.send_json({"ok": False, "error": f"Candidate with this phone ({phone}) or email ({email}) is already registered in the recruitment pipeline ({dup['name']} for position '{dup_role}'). Same candidate cannot be added for multiple positions."})
                        return

                    added_by_id = str(data.get("added_by_id", "")).strip()
                    added_by_name = str(data.get("added_by_name", "")).strip()
                    added_by_email = str(data.get("added_by_email", "")).strip()
                    added_by_username = str(data.get("added_by_username", "")).strip()

                    db.execute("""
                        INSERT OR REPLACE INTO hr_candidates (
                            id, name, email, phone, role_applied, experience, source_type, referral_code,
                            referrer_name, referrer_phone, referrer_emp_id, hr_round_status, hr_notes,
                            interview_scheduled_at, interview_interviewer, interview_meet_link,
                            manager_round_status, manager_notes, onboarding_status, offered_designation,
                            offered_ctc, joining_date, resume_filename, resume_data, resume_size, resume_text,
                            added_by_id, added_by_name, added_by_email, added_by_username,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, '', '', '', 'pending', '', 'pending', '', '', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (cid, name, email, phone, role_applied, experience, source_type, referral_code,
                            referrer_name, referrer_phone, referrer_emp_id, hr_notes,
                            resume_filename, resume_data, resume_size, resume_text,
                            added_by_id, added_by_name, added_by_email, added_by_username,
                            now_str, now_str))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": cid, "referral_code": referral_code, "msg": f"Candidate {name} added to recruitment pipeline."})
                return

            if path == "/api/hr/candidates/status":
                cid = data.get("id")
                round_type = str(data.get("round", "hr")).strip().lower() # 'hr', 'manager', 'offer_response', 'onboarding', 'decline'
                status = str(data.get("status", "pending")).strip().lower() # 'passed', 'failed', 'pending', 'declined', 'offer_accepted', 'offer_declined'
                notes = str(data.get("notes", "")).strip()
                decline_reason = str(data.get("decline_reason", notes)).strip()
                now_str = now_iso()

                if not cid:
                    self.send_json({"ok": False, "error": "Candidate ID is required."})
                    return

                with _db_lock:
                    db = get_db()
                    if round_type == "hr":
                        db.execute("UPDATE hr_candidates SET hr_round_status=?, hr_notes=?, updated_at=? WHERE id=?",
                                   (status, notes, now_str, cid))
                    elif round_type == "manager":
                        db.execute("UPDATE hr_candidates SET manager_round_status=?, manager_notes=?, updated_at=? WHERE id=?",
                                   (status, notes, now_str, cid))
                    elif round_type in ("offer_response", "onboarding", "offer", "decline") or status in ("declined", "offer_declined", "offer_accepted", "accepted"):
                        if status in ("declined", "offer_declined"):
                            db.execute("UPDATE hr_candidates SET onboarding_status='declined', offer_response_status='declined', decline_reason=?, updated_at=? WHERE id=?",
                                       (decline_reason or notes or "Candidate declined offer", now_str, cid))
                        elif status in ("offer_accepted", "accepted"):
                            db.execute("UPDATE hr_candidates SET onboarding_status='offer_accepted', offer_response_status='accepted', updated_at=? WHERE id=?",
                                       (now_str, cid))
                        else:
                            db.execute("UPDATE hr_candidates SET onboarding_status=?, offer_response_status=?, decline_reason=?, updated_at=? WHERE id=?",
                                       (status, status, decline_reason or notes, now_str, cid))
                    else:
                        db.execute("UPDATE hr_candidates SET manager_round_status=?, manager_notes=?, updated_at=? WHERE id=?",
                                   (status, notes, now_str, cid))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "Candidate status updated successfully."})
                return

            if path == "/api/hr/candidates/schedule-interview":
                cid = data.get("id")
                sched_at = str(data.get("scheduled_at", "")).strip()
                interviewer = str(data.get("interviewer", "Operations Manager")).strip()
                meet_link = str(data.get("meet_link", "")).strip()
                mode = str(data.get("mode", "video")).strip()
                candidate_email = (data.get("candidate_email") or "").strip()
                send_email = bool(data.get("send_email", True))
                from_email = (data.get("from_email") or "").strip()
                company_name = (data.get("company_name") or "Sylivion Tech Powered By Workmate4U Pvt. Ltd.").strip()
                if company_name in ["InvoicePro", "InvoicePro Billing Systems Pvt Ltd", ""] or not company_name:
                    company_name = "Sylivion Tech Powered By Workmate4U Pvt. Ltd."
                from_name = (data.get("from_name") or company_name).strip()
                if from_name in ["InvoicePro", "InvoicePro Billing Systems Pvt Ltd", "HR Team", ""] or not from_name:
                    from_name = company_name
                from_phone = data.get("from_phone") or ""
                company_city = (data.get("company_city") or "").strip()
                hr_smtp_cfg = data.get("hr_smtp_config")
                now_str = now_iso()

                if not cid or not sched_at:
                    self.send_json({"ok": False, "error": "Candidate ID and Schedule Date/Time are required."})
                    return

                if mode == "video" and not meet_link:
                    self.send_json({"ok": False, "error": "Google Meet link is mandatory for online interviews. Please paste the meeting link manually."})
                    return

                scheduled_by_id = str(data.get("scheduled_by_id", "")).strip()
                scheduled_by_name = str(data.get("scheduled_by_name", "")).strip()
                scheduled_by_email = str(data.get("scheduled_by_email", "")).strip()
                scheduled_by_username = str(data.get("scheduled_by_username", "")).strip()

                with _db_lock:
                    db = get_db()
                    if candidate_email:
                        db.execute("""
                            UPDATE hr_candidates
                            SET interview_scheduled_at=?, interview_interviewer=?, interview_meet_link=?, email=?, updated_at=?,
                                scheduled_by_id=?, scheduled_by_name=?, scheduled_by_email=?, scheduled_by_username=?, interview_status='scheduled'
                            WHERE id=?
                        """, (sched_at, interviewer, meet_link, candidate_email, now_str, scheduled_by_id, scheduled_by_name, scheduled_by_email, scheduled_by_username, cid))
                    else:
                        db.execute("""
                            UPDATE hr_candidates
                            SET interview_scheduled_at=?, interview_interviewer=?, interview_meet_link=?, updated_at=?,
                                scheduled_by_id=?, scheduled_by_name=?, scheduled_by_email=?, scheduled_by_username=?, interview_status='scheduled'
                            WHERE id=?
                        """, (sched_at, interviewer, meet_link, now_str, scheduled_by_id, scheduled_by_name, scheduled_by_email, scheduled_by_username, cid))
                    cand = db.execute("SELECT * FROM hr_candidates WHERE id=?", (cid,)).fetchone()
                    db.commit()
                    db.close()

                email_sent = False
                email_err = None
                if send_email and cand and cand["email"]:
                    # Method 1: Check if HR provided their own SMTP config
                    cfg = None
                    if hr_smtp_cfg and isinstance(hr_smtp_cfg, dict) and hr_smtp_cfg.get("host") and hr_smtp_cfg.get("username") and hr_smtp_cfg.get("password"):
                        cfg = hr_smtp_cfg
                        sender_addr = hr_smtp_cfg.get("from_email") or hr_smtp_cfg.get("username")
                        sender_name = hr_smtp_cfg.get("from_name") or from_name
                    else:
                        cfg = load_smtp_config()
                        sender_addr = from_email or cfg.get("from_email") or cfg.get("username")
                        sender_name = from_name

                    if sender_name in ["InvoicePro", "HR Team", ""] or not sender_name:
                        sender_name = company_name

                    if cfg and cfg.get("host"):
                        subj = f"Interview Invitation — {cand['role_applied'] or 'Position'} at {company_name}"
                        city_suffix = f", {company_city}" if company_city else ""
                        phone_line = f"Phone: {from_phone}\n" if from_phone else ""
                        body = (
                            f"Dear {cand['name']},\n\n"
                            f"Thank you for your interest in joining {company_name}. We are pleased to invite you for the interview round for the {cand['role_applied'] or 'Position'} position.\n\n"
                            f"Interview Details:\n"
                            f"• Date & Time: {sched_at}\n"
                            f"• Interviewer: {interviewer}\n"
                            f"• Meeting Mode / Link: {meet_link or 'Office Conference Room'}\n\n"
                            f"Please ensure you are available 5 minutes prior to the scheduled time with your updated resume.\n\n"
                            f"If you have any questions or need to reschedule, please reply directly to this email.\n\n"
                            f"Warm regards,\n"
                            f"Human Resources Team\n"
                            f"{company_name}{city_suffix}\n"
                            f"{phone_line}"
                        )
                        try:
                            do_send_smtp(cfg, cand["email"], subj, body, cc_list=None, from_email_override=sender_addr, from_name_override=company_name)
                            email_sent = True
                            print(f"  [HR Interview Email] Sent to {cand['email']} using {cfg.get('username')} (Sender: {company_name})")
                        except Exception as em_err:
                            email_err = str(em_err)
                            print(f"  [Schedule Email Err] {em_err}")

                self.send_json({
                    "ok": True,
                    "msg": f"Manager interview scheduled for {sched_at}." + (" (Email invitation sent directly to candidate)" if email_sent else (f" (Email error: {email_err})" if email_err else "")),
                    "email_sent": email_sent,
                    "email_error": email_err
                })
                return

            if path == "/api/hr/candidates/send-joining-kit":
                cid = data.get("id")
                offered_desig = str(data.get("offered_designation", "")).strip()
                offered_ctc = str(data.get("offered_ctc", "")).strip()
                joining_date = str(data.get("joining_date", "")).strip()
                interview_date = str(data.get("interview_date", "17th March 2026")).strip()
                candidate_email = (data.get("candidate_email") or "").strip()
                send_email = bool(data.get("send_email", True))
                from_email = (data.get("from_email") or "").strip()
                company_name = (data.get("company_name") or "Sylivion Tech Powered By Workmate4U Pvt. Ltd.").strip()
                if company_name in ["InvoicePro", "InvoicePro Billing Systems Pvt Ltd", ""] or not company_name:
                    company_name = "Sylivion Tech Powered By Workmate4U Pvt. Ltd."
                from_name = (data.get("from_name") or company_name).strip()
                if from_name in ["InvoicePro", "InvoicePro Billing Systems Pvt Ltd", "HR Team", ""] or not from_name:
                    from_name = company_name
                from_phone = data.get("from_phone") or ""
                company_city = (data.get("company_city") or "").strip()
                hr_smtp_cfg = data.get("hr_smtp_config")
                now_str = now_iso()

                if not cid:
                    self.send_json({"ok": False, "error": "Candidate ID is required."})
                    return

                with _db_lock:
                    db = get_db()
                    if candidate_email:
                        db.execute("""
                            UPDATE hr_candidates
                            SET onboarding_status='joining_sent', offered_designation=?, offered_ctc=?, joining_date=?, email=?, updated_at=?
                            WHERE id=?
                        """, (offered_desig, offered_ctc, joining_date, candidate_email, now_str, cid))
                    else:
                        db.execute("""
                            UPDATE hr_candidates
                            SET onboarding_status='joining_sent', offered_designation=?, offered_ctc=?, joining_date=?, updated_at=?
                            WHERE id=?
                        """, (offered_desig, offered_ctc, joining_date, now_str, cid))
                    cand = db.execute("SELECT * FROM hr_candidates WHERE id=?", (cid,)).fetchone()
                    db.commit()
                    db.close()

                email_sent = False
                email_err = None
                if send_email and cand and cand["email"]:
                    # Method 1: Check if HR provided their own SMTP config
                    cfg = None
                    if hr_smtp_cfg and isinstance(hr_smtp_cfg, dict) and hr_smtp_cfg.get("host") and hr_smtp_cfg.get("username") and hr_smtp_cfg.get("password"):
                        cfg = hr_smtp_cfg
                        sender_addr = hr_smtp_cfg.get("from_email") or hr_smtp_cfg.get("username")
                        sender_name = hr_smtp_cfg.get("from_name") or from_name
                    else:
                        cfg = load_smtp_config()
                        sender_addr = from_email or cfg.get("from_email") or cfg.get("username")
                        sender_name = from_name

                    if sender_name in ["InvoicePro", "HR Team", ""] or not sender_name:
                        sender_name = company_name

                    if cfg and cfg.get("host"):
                        role_name = offered_desig or cand['role_applied'] or 'Role'
                        subj = f"Selection Confirmation |  {company_name} - {role_name}"
                        city_suffix = f", {company_city}" if company_city else ""
                        phone_line = f"Phone: {from_phone}\n" if from_phone else ""

                        accept_subject = quote(f"Selection Confirmation Accepted - {cand['name']} ({role_name}) - {company_name}")
                        accept_body = quote(
                            f"Dear Human Resources,\n\n"
                            f"I am pleased to accept the job offer for the position of {role_name} at {company_name}.\n"
                            f"I confirm that I will join on {joining_date} and carry all required documents.\n\n"
                            f"Candidate Details:\n"
                            f"• Name: {cand['name']}\n"
                            f"• Contact: {cand['phone']}\n"
                            f"• Designation: {role_name}\n\n"
                            f"Regards,\n"
                            f"{cand['name']}"
                        )
                        accept_url = f"mailto:{sender_addr}?subject={accept_subject}&body={accept_body}"

                        decline_subject = quote(f"Selection Confirmation Declined - {cand['name']} ({role_name}) - {company_name}")
                        decline_body = quote(
                            f"Dear Human Resources,\n\n"
                            f"Thank you for considering me for the position of {role_name} at {company_name}.\n"
                            f"I regret to inform you that I will not be able to accept the offer at this time.\n\n"
                            f"Candidate Details:\n"
                            f"• Name: {cand['name']}\n"
                            f"• Designation: {role_name}\n\n"
                            f"Regards,\n"
                            f"{cand['name']}"
                        )
                        decline_url = f"mailto:{sender_addr}?subject={decline_subject}&body={decline_body}"

                        action_buttons = [
                            {"label": "Accept Offer & Confirm Joining", "url": accept_url, "color": "emerald"},
                            {"label": "Decline Offer", "url": decline_url, "color": "slate"}
                        ]

                        body = (
                            f"Dear {cand['name']},\n\n"
                            f"Following your interview and HR discussions, we are delighted to offer you the position of {role_name} at {company_name}.\n"
                            f"Congratulations on your selection!\n\n"
                            f"Key Details:\n"
                            f"• Designation: {role_name}\n"
                            f"• Joining Date: {joining_date}\n\n"
                            f"Your detailed Appointment & Offer Letter containing compensation structure and company policies will be issued on your date of joining.\n\n"
                            f"Documents required on the day of joining:\n"
                            f"• Aadhaar Card (Copy)\n"
                            f"• PAN Card (Copy)\n"
                            f"• Educational Certificates (Copies)\n"
                            f"• 2 Passport-size Photographs\n"
                            f"• Current Residential Address Proof\n"
                            f"• 2 Copies of Updated Resume\n\n"
                            f"Please confirm your acceptance by clicking below or replying directly to {sender_addr}.\n\n"
                            f"We look forward to welcoming you to our team!\n\n"
                            f"Warm regards,\n"
                            f"Human Resources Team\n"
                            f"{company_name}{city_suffix}\n"
                            f"{phone_line}"
                        )

                        try:
                            do_send_smtp(
                                cfg,
                                cand["email"],
                                subj,
                                body,
                                cc_list=["info@sylivion.com"],
                                from_email_override=sender_addr,
                                from_name_override=company_name,
                                action_buttons=action_buttons
                            )
                            email_sent = True
                            print(f"  [HR Joining Email with Action Buttons] Sent to {cand['email']} (Sender: {company_name})")
                        except Exception as em_err:
                            email_err = str(em_err)
                            print(f"  [Joining Kit Email Err] {em_err}")


                self.send_json({
                    "ok": True,
                    "msg": "Selection & joining email processed!" + (" (Email sent directly to candidate)" if email_sent else (f" (Email error: {email_err})" if email_err else "")),
                    "email_sent": email_sent,
                    "email_error": email_err
                })
                return

            if path == "/api/hr/test-email":
                hr_smtp_cfg = data.get("hr_smtp_config") or {}
                to_addr = (data.get("to_email") or hr_smtp_cfg.get("from_email") or hr_smtp_cfg.get("username") or "").strip()
                company_name = "Sylivion Tech Powered By Workmate4U Pvt. Ltd."
                if not to_addr:
                    self.send_json({"ok": False, "error": "Recipient / Test email is required."})
                    return
                if not hr_smtp_cfg.get("username") and hr_smtp_cfg.get("from_email"):
                    hr_smtp_cfg["username"] = str(hr_smtp_cfg.get("from_email")).strip()
                if not hr_smtp_cfg.get("host") or not hr_smtp_cfg.get("username") or not hr_smtp_cfg.get("password"):
                    self.send_json({"ok": False, "error": "Incomplete HR SMTP credentials. Host, Email/Username, and App Password are required."})
                    return
                
                try:
                    do_send_smtp(
                        hr_smtp_cfg,
                        to_addr,
                        f"HR Outgoing Email Verification — {company_name}",
                        f"Hello,\n\nThis is a verification email confirming that your HR outgoing email configuration is active and connected for {company_name}.\n\nAll candidate interview invitations and offer letters dispatched by you will be sent directly from this address in the background.\n\nWarm regards,\nHR Team | {company_name}",
                        from_email_override=hr_smtp_cfg.get("from_email") or hr_smtp_cfg.get("username"),
                        from_name_override=company_name
                    )
                    self.send_json({"ok": True, "msg": f"Test email sent successfully to {to_addr}!"})
                except Exception as ex:
                    err_msg = str(ex)
                    if "535" in err_msg or "BadCredentials" in err_msg or "Username and Password not accepted" in err_msg:
                        err_msg += " (Authentication failed: For Gmail, please make sure 2-Step Verification is active and use a generated 16-character App Password, not your account login password)."
                    self.send_json({"ok": False, "error": f"SMTP Connection Failed: {err_msg}"})
                return


            if path == "/api/hr/save-smtp-profile":
                uid = data.get("user_id") or data.get("emp_id") or "default_hr"
                smtp_profile = data.get("smtp_profile") or {}
                now_str = now_iso()
                # Persist to disk
                try:
                    with open(HR_SMTP_PROFILE_PATH, "w", encoding="utf-8") as f:
                        json.dump(smtp_profile, f, indent=2)
                except Exception as save_err:
                    print(f"  [HR SMTP File Save Err] {save_err}")

                with _db_lock:
                    db = get_db()
                    row = db.execute("SELECT * FROM staff_users WHERE id=? OR username=? OR emp_id=?", (uid, uid, uid)).fetchone()
                    if row:
                        db.execute("UPDATE staff_users SET email=? WHERE id=?", (smtp_profile.get("from_email") or smtp_profile.get("username", ""), row["id"]))
                    emp_row = db.execute("SELECT * FROM employees WHERE id=? OR emp_id=?", (uid, uid)).fetchone()
                    if emp_row:
                        try:
                            extra = json.loads(emp_row["extra_data"] or "{}")
                        except Exception:
                            extra = {}
                        extra["hr_smtp_config"] = smtp_profile
                        db.execute("UPDATE employees SET extra_data=?, email=?, updated_at=? WHERE id=?", (json.dumps(extra), smtp_profile.get("from_email") or smtp_profile.get("username", ""), now_str, emp_row["id"]))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "HR email configuration profile saved successfully!"})
                return

            if path == "/api/hr/get-smtp-profile":
                uid = data.get("user_id") or data.get("emp_id") or "default_hr"
                profile = {}
                with _db_lock:
                    db = get_db()
                    emp_row = db.execute("SELECT * FROM employees WHERE id=? OR emp_id=?", (uid, uid)).fetchone()
                    if emp_row:
                        try:
                            extra = json.loads(emp_row["extra_data"] or "{}")
                            profile = extra.get("hr_smtp_config") or {}
                        except Exception:
                            pass
                    db.close()
                if (not profile or not profile.get("from_email")) and os.path.exists(HR_SMTP_PROFILE_PATH):
                    try:
                        with open(HR_SMTP_PROFILE_PATH, "r", encoding="utf-8") as f:
                            profile = json.load(f)
                    except Exception:
                        pass
                self.send_json({"ok": True, "smtp_profile": profile})
                return


            if path in ("/api/hr/candidates/onboard", "/api/hr/candidates/onboard-candidate"):
                cid = data.get("id") or data.get("candidate_id") or data.get("candidateId")
                if not cid:
                    self.send_json({"ok": False, "error": "Candidate ID is required."})
                    return

                with _db_lock:
                    db = get_db()
                    cand = db.execute("SELECT * FROM hr_candidates WHERE id=?", (cid,)).fetchone()
                    if not cand:
                        db.close()
                        self.send_json({"ok": False, "error": "Candidate not found."})
                        return

                    cand_dict = dict(cand)
                    emp_obj = data.get("employee") if isinstance(data.get("employee"), dict) else {}
                    
                    # Check if already onboarded or custom empId provided
                    new_emp_id = str(data.get("empId") or data.get("emp_id") or emp_obj.get("empId") or cand_dict.get("empId") or cand_dict.get("id", "").replace("can-", "EMP-") or ("EMP-" + str(uuid.uuid4())[:6].upper())).strip()
                    
                    # Extract designation, department and role
                    desig = str(
                        data.get("designation") 
                        or emp_obj.get("designation") 
                        or cand_dict.get("offered_designation") 
                        or cand_dict.get("role_applied") 
                        or "Software Engineer"
                    ).strip()

                    explicit_dept = str(data.get("department") or emp_obj.get("department") or "").strip()
                    explicit_role = str(data.get("role") or emp_obj.get("role") or "").strip().lower()

                    desig_lower = desig.lower()
                    role_applied_lower = str(cand_dict.get("role_applied") or "").lower()
                    combined_text = f"{desig_lower} {role_applied_lower}"

                    # Canonical Department Resolution
                    if explicit_dept in ("Development", "Engineering", "Software", "Tech", "IT"):
                        dept = "Development"
                    elif explicit_dept in ("Support", "Customer Support", "Helpdesk"):
                        dept = "Support"
                    elif explicit_dept in ("Human Resources", "HR"):
                        dept = "Human Resources"
                    elif explicit_dept in ("Operations", "Management", "Admin"):
                        dept = "Operations"
                    elif explicit_dept in ("Sales", "Marketing", "Business Development"):
                        dept = "Sales"
                    elif any(k in combined_text for k in ("support", "helpdesk", "customer service", "troubleshoot", "service desk")):
                        dept = "Support"
                    elif any(k in combined_text for k in ("developer", "backend", "frontend", "fullstack", "software", "flutter", "engineer", "dev", "programmer", "qa", "tester", "architect", "tech lead", "coding")):
                        dept = "Development"
                    elif any(k in combined_text for k in ("hr", "recruiter", "talent", "human resource", "people ops", "payroll")):
                        dept = "Human Resources"
                    elif any(k in combined_text for k in ("operations", "general manager", "operations manager", "branch manager", "ops manager")):
                        dept = "Operations"
                    elif any(k in combined_text for k in ("sales", "bde", "business dev", "account executive", "telecaller")):
                        dept = "Sales"
                    elif any(k in combined_text for k in ("dev", "tech", "eng", "code")):
                        dept = "Development"
                    else:
                        dept = "Sales"

                    # Canonical Role Resolution
                    if explicit_role:
                        if explicit_role in ("dev_member", "dev_leader", "sales_member", "sales_leader", "support_member", "support_leader", "hr", "manager", "admin"):
                            role = explicit_role
                        elif explicit_role in ("developer", "engineer", "tech", "dev", "dev_mem"):
                            role = "dev_member"
                        elif explicit_role in ("dev_lead", "tech_lead", "lead_dev"):
                            role = "dev_leader"
                        elif explicit_role in ("support", "support_agent", "support_exec", "customer_support"):
                            role = "support_member"
                        elif explicit_role in ("support_lead", "support_head"):
                            role = "support_leader"
                        elif explicit_role in ("sales", "sales_exec", "sales_rep"):
                            role = "sales_member"
                        elif explicit_role in ("sales_lead", "sales_head"):
                            role = "sales_leader"
                        elif explicit_role in ("hr_recruiter", "talent_acquisition"):
                            role = "hr"
                        elif explicit_role in ("operations_manager", "ops_manager", "general_manager"):
                            role = "manager"
                        else:
                            role = explicit_role
                    else:
                        is_leader = any(k in combined_text for k in ("lead", "manager", "head", "principal", "sr.", "senior"))
                        if dept == "Development":
                            role = "dev_leader" if (is_leader and not any(k in combined_text for k in ("associate", "junior", "intern"))) else "dev_member"
                        elif dept == "Support":
                            role = "support_leader" if is_leader else "support_member"
                        elif dept == "Human Resources":
                            role = "hr"
                        elif dept == "Operations":
                            role = "manager"
                        else:
                            role = "sales_leader" if is_leader else "sales_member"

                    now_str = now_iso()
                    join_d = cand_dict.get("joining_date") or datetime.now().strftime("%Y-%m-%d")

                    # Check if employee already exists by mobile or email
                    cand_phone = str(cand_dict.get("phone", "")).strip()
                    cand_email = str(cand_dict.get("email", "")).strip()
                    existing_emp = None
                    if cand_phone or cand_email:
                        existing_emp = db.execute("SELECT id, emp_id FROM employees WHERE (mobile!='' AND mobile=?) OR (email!='' AND LOWER(email)=LOWER(?))", (cand_phone, cand_email)).fetchone()
                    
                    if existing_emp:
                        emp_pk_id = existing_emp["id"]
                        new_emp_id = existing_emp["emp_id"]
                        db.execute("""
                            UPDATE employees SET name=?, mobile=?, email=?, designation=?, department=?, join_date=?, notes=?, updated_at=?
                            WHERE id=?
                        """, (cand_dict["name"], cand_phone, cand_email, desig, dept, join_d, f"Onboarded from HR Pipeline (Candidate ID: {cid})", now_str, emp_pk_id))
                    else:
                        emp_pk_id = "emp-" + str(uuid.uuid4())[:8]
                        db.execute("""
                            INSERT OR REPLACE INTO employees (id, emp_id, name, mobile, email, designation, department, join_date, notes, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (emp_pk_id, new_emp_id, cand_dict["name"], cand_phone, cand_email, desig, dept, join_d, f"Onboarded from HR Pipeline (Candidate ID: {cid})", now_str, now_str))

                    # Auto-provision staff login account
                    raw_name = cand_dict.get("name", "staff").lower().split()[0]
                    clean_name = re.sub(r'[^a-z0-9]', '', raw_name) or "staff"
                    staff_user = clean_name + "_" + role
                    staff_id = "usr-" + new_emp_id.lower()
                    db.execute("""
                        INSERT OR REPLACE INTO staff_users (id, name, username, password, role, department, designation, email, phone, emp_id, active, created_at)
                        VALUES (?, ?, ?, 'emp123', ?, ?, ?, ?, ?, ?, 1, ?)
                    """, (staff_id, cand_dict["name"], staff_user, role, dept, desig, cand_dict.get("email", ""), cand_dict.get("phone", ""), new_emp_id, now_str))

                    # Mark candidate as onboarded
                    db.execute("UPDATE hr_candidates SET onboarding_status='onboarded', updated_at=? WHERE id=?", (now_str, cid))
                    db.commit()
                    db.close()

                self.send_json({"ok": True, "emp_id": new_emp_id, "username": staff_user, "role": role, "department": dept, "designation": desig, "msg": f"{cand_dict['name']} successfully onboarded as {desig} in {dept} ({new_emp_id}) and Staff login ({staff_user}) created!"})
                return

            if path == "/api/hr/candidates/delete":
                cid = data.get("id")
                if not cid:
                    self.send_json({"ok": False, "error": "Candidate ID is required."})
                    return
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM hr_candidates WHERE id=?", (cid,))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "Candidate removed from pipeline."})
                return

            if path == "/api/hr/jobs/add":
                jid = data.get("id") or ("job-" + str(uuid.uuid4())[:8])
                title = str(data.get("title", "")).strip()
                department = str(data.get("department", "Sales")).strip()
                vacancies = int(data.get("vacancies", 1))
                job_type = str(data.get("job_type", "Full-Time")).strip()
                experience_required = str(data.get("experience_required", "1-3 Years")).strip()
                status = str(data.get("status", "open")).strip()
                now_str = now_iso()

                if not title:
                    self.send_json({"ok": False, "error": "Job Title is required."})
                    return

                with _db_lock:
                    db = get_db()
                    db.execute("""
                        INSERT OR REPLACE INTO hr_jobs (id, title, department, vacancies, job_type, experience_required, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (jid, title, department, vacancies, job_type, experience_required, status, now_str))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": jid, "msg": f"Job opening '{title}' posted successfully."})
                return

            if path == "/api/hr/jobs/delete":
                jid = data.get("id")
                if not jid:
                    self.send_json({"ok": False, "error": "Job ID is required."})
                    return
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM hr_jobs WHERE id=?", (jid,))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "Job opening removed."})
                return

            if path == "/api/hr/grievances/add":
                gid = data.get("id") or ("grv-" + str(uuid.uuid4())[:8])
                title = str(data.get("title", "")).strip()
                emp_name = str(data.get("employee_name", "")).strip()
                emp_id = str(data.get("employee_id", "")).strip()
                dept = str(data.get("department", "")).strip()
                category = str(data.get("category", "General")).strip()
                desc = str(data.get("description", "")).strip()
                status = str(data.get("status", "open")).strip()
                notes = str(data.get("resolution_notes", "")).strip()
                now_str = now_iso()

                if not title or not emp_name:
                    self.send_json({"ok": False, "error": "Grievance Title and Employee Name are required."})
                    return

                with _db_lock:
                    db = get_db()
                    db.execute("""
                        INSERT OR REPLACE INTO hr_grievances (id, title, employee_name, employee_id, department, category, description, status, resolution_notes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (gid, title, emp_name, emp_id, dept, category, desc, status, notes, now_str, now_str))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": gid, "msg": "Grievance ticket logged successfully."})
                return

            if path == "/api/hr/grievances/status":
                gid = data.get("id")
                status = str(data.get("status", "open")).strip()
                notes = str(data.get("resolution_notes", "")).strip()
                now_str = now_iso()

                if not gid:
                    self.send_json({"ok": False, "error": "Grievance ID is required."})
                    return

                with _db_lock:
                    db = get_db()
                    db.execute("UPDATE hr_grievances SET status=?, resolution_notes=?, updated_at=? WHERE id=?",
                               (status, notes, now_str, gid))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": f"Grievance status updated to {status.upper()}."})
                return

            if path == "/api/hr/grievances/delete":
                gid = data.get("id")
                if not gid:
                    self.send_json({"ok": False, "error": "Grievance ID is required."})
                    return
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM hr_grievances WHERE id=?", (gid,))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "Grievance record removed."})
                return

            if path == "/api/hr/training/add":
                tid = data.get("id") or ("trn-" + str(uuid.uuid4())[:8])
                title = str(data.get("title", "")).strip()
                trainer = str(data.get("trainer", "")).strip()
                schedule_date = str(data.get("schedule_date", "")).strip()
                duration = str(data.get("duration", "1 Hour")).strip()
                enrolled_count = int(data.get("enrolled_count", 0))
                topics = str(data.get("topics", "")).strip()
                status = str(data.get("status", "upcoming")).strip()
                now_str = now_iso()

                if not title:
                    self.send_json({"ok": False, "error": "Training Title is required."})
                    return

                with _db_lock:
                    db = get_db()
                    db.execute("""
                        INSERT OR REPLACE INTO hr_training (id, title, trainer, schedule_date, duration, enrolled_count, topics, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (tid, title, trainer, schedule_date, duration, enrolled_count, topics, status, now_str))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": tid, "msg": f"Training module '{title}' scheduled."})
                return

            if path == "/api/hr/training/delete":
                tid = data.get("id")
                if not tid:
                    self.send_json({"ok": False, "error": "Training ID is required."})
                    return
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM hr_training WHERE id=?", (tid,))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "Training module removed."})
                return

            if path == "/api/hr/goals/add":
                gid = data.get("id") or ("gol-" + str(uuid.uuid4())[:8])
                emp_id = str(data.get("employee_id", "")).strip()
                emp_name = str(data.get("employee_name", "")).strip()
                goal_title = str(data.get("goal_title", "")).strip()
                target_metric = str(data.get("target_metric", "")).strip()
                progress_percent = int(data.get("progress_percent", 0))
                appraisal_score = float(data.get("appraisal_score", 0))
                reviewer_notes = str(data.get("reviewer_notes", "")).strip()
                quarter = str(data.get("quarter", "Q3")).strip()
                status = str(data.get("status", "in_progress")).strip()
                now_str = now_iso()

                if not goal_title or not emp_name:
                    self.send_json({"ok": False, "error": "Goal Title and Employee Name are required."})
                    return

                with _db_lock:
                    db = get_db()
                    db.execute("""
                        INSERT OR REPLACE INTO hr_goals (id, employee_id, employee_name, goal_title, target_metric, progress_percent, appraisal_score, reviewer_notes, quarter, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (gid, emp_id, emp_name, goal_title, target_metric, progress_percent, appraisal_score, reviewer_notes, quarter, status, now_str))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": gid, "msg": "Employee goal & appraisal updated."})
                return

            if path == "/api/hr/goals/delete":
                gid = data.get("id")
                if not gid:
                    self.send_json({"ok": False, "error": "Goal ID is required."})
                    return
                with _db_lock:
                    db = get_db()
                    db.execute("DELETE FROM hr_goals WHERE id=?", (gid,))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": "Goal record removed."})
                return
            if path == "/api/leaves/apply":
                lid = data.get("id") or ("lv-" + str(uuid.uuid4())[:8])
                emp_id = str(data.get("employee_id", "")).strip()
                emp_name = str(data.get("employee_name", "Employee")).strip()
                role = str(data.get("role", "")).strip()
                ltype = str(data.get("leave_type", "casual")).strip()
                from_d = str(data.get("from_date", "")).strip()
                to_d = str(data.get("to_date", "")).strip()
                days = float(data.get("days", 1))
                reason = str(data.get("reason", "")).strip()
                now_str = now_iso()

                if not from_d or not to_d:
                    self.send_json({"ok": False, "error": "From date and To date are required."})
                    return

                with _db_lock:
                    db = get_db()
                    db.execute("""
                        INSERT INTO leave_requests (id, employee_id, employee_name, role, leave_type, from_date, to_date, days, reason, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """, (lid, emp_id, emp_name, role, ltype, from_d, to_d, days, reason, now_str))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "id": lid, "msg": f"Leave application submitted for {days} day(s)."})
                return

            if path == "/api/leaves/status":
                lid = data.get("id")
                status = str(data.get("status", "pending")).strip().lower()
                reviewed_by = str(data.get("reviewed_by", "Manager")).strip()
                reviewer_role = str(data.get("reviewer_role", "")).strip().lower()
                if not lid or status not in ("approved", "rejected", "pending"):
                    self.send_json({"ok": False, "error": "Invalid leave status request."})
                    return
                with _db_lock:
                    db = get_db()
                    cur = db.cursor()
                    cur.execute("SELECT role, employee_name, employee_id FROM leave_requests WHERE id=?", (lid,))
                    row = cur.fetchone()
                    if row:
                        target_role = (row["role"] or "").lower()
                        emp_name = (row["employee_name"] or "").lower()
                        is_mgr = target_role == "manager" or "manager" in emp_name
                        if is_mgr and reviewer_role != "admin" and "admin" not in reviewed_by.lower():
                            db.close()
                            self.send_json({"ok": False, "error": "Operations Manager leave requests can only be approved or rejected by Master Admin."})
                            return
                    now_str = now_iso()
                    db.execute("""
                        UPDATE leave_requests SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?
                    """, (status, reviewed_by, now_str, lid))
                    db.commit()
                    db.close()
                self.send_json({"ok": True, "msg": f"Leave application marked as {status.upper()}."})
                return

            if path == "/favicon.ico":
                # 1x1 transparent ICO — stops browser 404 noise
                ico = bytes([
                    0,0,1,0,1,0,1,1,0,0,1,0,24,0,40,0,0,0,22,0,0,0,40,0,0,0,
                    1,0,0,0,2,0,0,0,1,0,24,0,0,0,0,0,4,0,0,0,0,0,0,0,0,0,0,0,
                    0,0,0,0,0,0,0,0,0,0,255,255,255,0,0,0,255,255
                ])
                self.send_response(200)
                self.send_header("Content-Type", "image/x-icon")
                self.send_header("Content-Length", str(len(ico)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(ico)
                return
            self.send_err("Not found", 404)

        except KeyError as e:
            self.send_err(f"Missing required field: {e}")
        except Exception:
            traceback.print_exc()
            self.send_err(traceback.format_exc(), 500)


# ── Port check ────────────────────────────────────────────────────────────────
def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()

    if not is_port_free(PORT):
        url = f"http://localhost:{PORT}"
        print(f"  Admin server already running — opening {url}")
        webbrowser.open(url)
        return

    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), AdminHandler)
    server.daemon_threads = True
    url = f"http://localhost:{PORT}"

    print("=" * 56)
    print("  InvoicePro Admin Server — v1.0")
    print(f"  URL  : {url}")
    print(f"  DB   : admin_data/admin.db")
    print()
    print("  Share your LAN IP with customers to receive reports:")
    try:
        lan_ip = socket.gethostbyname(socket.gethostname())
        print(f"  LAN  : http://{lan_ip}:{PORT}")
        print(f"  Set in InvoicePro config: adminUrl = http://{lan_ip}:{PORT}")
    except Exception:
        pass
    print()
    def _open_url():
        try:
            if not os.environ.get("RAILWAY_ENVIRONMENT") and not os.environ.get("DYNO") and not os.environ.get("DOCKER"):
                webbrowser.open(url)
        except Exception:
            pass

    threading.Timer(1.0, _open_url).start()

    # Start background scheduler (daily reminders + auto-backup)
    _start_scheduler()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAdmin server stopped.")
        server.server_close()


# ── Background scheduler ──────────────────────────────────────────────────────
_scheduler_stop = threading.Event()

def _scheduler_loop():
    """Run once at startup then every 24 hours."""
    import json as _json
    _auto_backup()
    while not _scheduler_stop.wait(86400):   # sleep 24 h
        _auto_backup()
        _send_scheduled_reminders()


def _start_scheduler():
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()


def _auto_backup():
    """Save a timestamped JSON backup of the full database."""
    try:
        backup_dir = os.path.join(DATA_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        with _db_lock:
            db = get_db()
            customers = rows_to_list(db.execute("SELECT * FROM customers").fetchall())
            for c in customers:
                c["support_renewals"] = []
            employees = rows_to_list(db.execute("SELECT * FROM employees").fetchall())
            for e in employees:
                e["sales"]    = rows_to_list(db.execute("SELECT * FROM employee_sales WHERE employee_id=?", (e["id"],)).fetchall())
                e["payments"] = rows_to_list(db.execute("SELECT * FROM employee_payments WHERE employee_id=?", (e["id"],)).fetchall())
            reports   = rows_to_list(db.execute("SELECT * FROM reports").fetchall())
            enquiries = rows_to_list(db.execute("SELECT * FROM enquiries").fetchall())
            db.close()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"backup_{stamp}.json")
        data = {"customers": customers, "employees": employees,
                "reports": reports, "enquiries": enquiries,
                "exportedAt": now_iso(), "version": "1.0"}
        with open(backup_path, "w", encoding="utf-8") as f:
            import json as _json
            _json.dump(data, f, ensure_ascii=False, indent=2)
        # Keep only the 30 most recent backups
        backups = sorted([
            os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
            if f.startswith("backup_") and f.endswith(".json")
        ])
        for old in backups[:-30]:
            try: os.remove(old)
            except: pass
        print(f"  [Backup] Saved {backup_path}")
    except Exception as e:
        print(f"  [Backup] Failed: {e}")


def _send_scheduled_reminders():
    """Email renewal reminders to customers expiring in exactly 7 days."""
    cfg = load_smtp_config()
    if not cfg.get("host"):
        return  # SMTP not configured
    try:
        today = datetime.now().date()
        target = today + __import__('datetime').timedelta(days=7)
        with _db_lock:
            db = get_db()
            customers = rows_to_list(db.execute("SELECT * FROM customers WHERE email != ''").fetchall())
            db.close()
        sent = 0
        for c in customers:
            # Calculate expiry from support_purchase_date (simple 1-year assumption)
            sp = c.get("support_purchase_date") or c.get("supportPurchaseDate") or ""
            if not sp:
                continue
            try:
                from datetime import date as _date
                parts = sp[:10].split("-")
                exp = _date(int(parts[0])+1, int(parts[1]), int(parts[2]))
            except:
                continue
            if exp == target:
                subj = f"InvoicePro Key Renewal Reminder — {c.get('name','')}"
                body = (f"Dear {c.get('name','Customer')},\n\n"
                        f"Your InvoicePro key plan expires in 7 days on {exp.strftime('%d %b %Y')}.\n\n"
                        f"Please renew your key to continue using InvoicePro without interruption.\n\n"
                        f"Reply to this email to proceed with renewal.\n\n"
                        f"Best regards,\nInvoicePro Team")
                try:
                    do_send_smtp(cfg, c["email"], subj, body)
                    sent += 1
                    print(f"  [Reminder] Sent to {c['email']}")
                except Exception as e:
                    print(f"  [Reminder] Failed for {c['email']}: {e}")
        if sent:
            print(f"  [Scheduler] Sent {sent} renewal reminders")
    except Exception as e:
        print(f"  [Scheduler] Error: {e}")


if __name__ == "__main__":
    main()
