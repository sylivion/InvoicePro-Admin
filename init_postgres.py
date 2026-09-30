import psycopg2
import sqlite3
import os
import re

DATABASE_URL = 'postgresql://postgres:abiXJrwSDcLZzVWvWRTgAMSGIBVOoyoP@yamanote.proxy.rlwy.net:52510/railway'

print('Connecting to Railway PostgreSQL...')
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

ddl = """
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
    sold_by_emp_id       TEXT DEFAULT '',
    sold_by_emp_name     TEXT DEFAULT '',
    sales_person         TEXT DEFAULT '',
    added_by             TEXT DEFAULT '',
    plan_label           TEXT DEFAULT '',
    payment_method       TEXT DEFAULT '',
    transaction_id       TEXT DEFAULT '',
    checkout_source      TEXT DEFAULT '',
    status               TEXT DEFAULT 'active',
    order_id             TEXT DEFAULT '',
    created_at           TEXT DEFAULT '',
    updated_at           TEXT DEFAULT ''
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
    salary      REAL DEFAULT 0,
    target      REAL DEFAULT 0,
    team_id     TEXT DEFAULT '',
    active      INTEGER DEFAULT 1,
    extra_data  TEXT DEFAULT '{}',
    created_at  TEXT DEFAULT '',
    updated_at  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS employee_sales (
    id            TEXT PRIMARY KEY,
    employee_id   TEXT NOT NULL,
    emp_id        TEXT DEFAULT '',
    customer_id   TEXT DEFAULT '',
    customer_name TEXT DEFAULT '',
    plan_name     TEXT DEFAULT '',
    date          TEXT DEFAULT '',
    amount        REAL DEFAULT 499,
    commission    REAL DEFAULT 100,
    note          TEXT DEFAULT '',
    status        TEXT DEFAULT 'approved',
    target_month  TEXT DEFAULT '',
    created_at    TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS employee_payments (
    id          TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    date        TEXT DEFAULT '',
    amount      REAL DEFAULT 0,
    note        TEXT DEFAULT '',
    created_at  TEXT DEFAULT ''
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
    targetMonthly    TEXT DEFAULT '0',
    progress         TEXT DEFAULT '0',
    focus_area       TEXT DEFAULT '',
    created_at       TEXT DEFAULT '',
    updated_at       TEXT DEFAULT ''
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
    id                      TEXT PRIMARY KEY,
    customer_id             TEXT DEFAULT '',
    customer_name           TEXT DEFAULT '',
    customer_phone          TEXT DEFAULT '',
    subject                 TEXT DEFAULT '',
    priority                TEXT DEFAULT 'Medium',
    channel                 TEXT DEFAULT 'Web',
    claimed_by_leader_id    TEXT DEFAULT '',
    claimed_by_leader_name  TEXT DEFAULT '',
    claimed_team_id         TEXT DEFAULT '',
    claimed_team_name       TEXT DEFAULT '',
    claimed_at              TEXT DEFAULT '',
    assigned_member_id      TEXT DEFAULT '',
    assigned_member_name    TEXT DEFAULT '',
    assigned_at             TEXT DEFAULT '',
    resolved_by_member_name TEXT DEFAULT '',
    resolved_by_leader_name TEXT DEFAULT '',
    resolved_by_team        TEXT DEFAULT '',
    date                    TEXT DEFAULT '',
    message                 TEXT DEFAULT '',
    reply                   TEXT DEFAULT '',
    status                  TEXT DEFAULT 'open',
    created_at              TEXT DEFAULT '',
    resolved_at             TEXT DEFAULT ''
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
    added_at    TEXT DEFAULT ''
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
"""

cur.execute(ddl)
conn.commit()

# Copy data from SQLite to PostgreSQL
sqlite_path = os.path.join(os.path.dirname(__file__), 'admin_data', 'admin.db')
if os.path.exists(sqlite_path):
    s_conn = sqlite3.connect(sqlite_path)
    s_conn.row_factory = sqlite3.Row
    s_cur = s_conn.cursor()
    
    tables_to_sync = ['customers', 'employees', 'employee_sales', 'employee_payments', 'teams', 'reports', 'enquiries', 'staff_users', 'leave_requests', 'hr_candidates', 'hr_jobs', 'hr_grievances', 'hr_training', 'hr_goals', 'recurring_issues', 'checkout_orders', 'license_keys']
    
    print('Syncing SQLite records into PostgreSQL...')
    for tbl in tables_to_sync:
        try:
            s_cur.execute(f"SELECT * FROM {tbl}")
            rows = s_cur.fetchall()
            if not rows:
                continue
            cols = [d[0] for d in s_cur.description]
            cols_str = ', '.join(cols)
            placeholders = ', '.join(['%s'] * len(cols))
            insert_query = f"INSERT INTO {tbl} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
            
            for row in rows:
                val_list = []
                for v in list(row):
                    if isinstance(v, str):
                        # clean string
                        val_list.append(v)
                    else:
                        val_list.append(v)
                cur.execute(insert_query, val_list)
            conn.commit()
            print(f'  Synced {len(rows)} records into table: {tbl}')
        except Exception as e:
            conn.rollback()
            print(f'  Skipped/Handled table {tbl}')
    s_conn.close()

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
tables = cur.fetchall()
print(f"\nAll PostgreSQL Tables ({len(tables)} tables live in PostgreSQL):")
for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM {t[0]};")
    cnt = cur.fetchone()[0]
    print(f"  - {t[0].ljust(22)}: {cnt} rows")

conn.close()
print('\nPostgreSQL initialization and sync completed successfully!')
