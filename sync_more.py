import sqlite3
import psycopg2

DATABASE_URL = 'postgresql://postgres:abiXJrwSDcLZzVWvWRTgAMSGIBVOoyoP@yamanote.proxy.rlwy.net:52510/railway'
p_conn = psycopg2.connect(DATABASE_URL)
p_cur = p_conn.cursor()

# Ensure types on teams
p_cur.execute("ALTER TABLE teams ALTER COLUMN targetmonthly TYPE TEXT;")
p_cur.execute("ALTER TABLE teams ALTER COLUMN progress TYPE TEXT;")
p_conn.commit()

# Ensure extra columns on staff_users
for col in ['department', 'designation', 'upi_id', 'upi_qr_image']:
    try:
        p_cur.execute(f"ALTER TABLE staff_users ADD COLUMN IF NOT EXISTS {col} TEXT DEFAULT ''")
        p_conn.commit()
    except Exception as e:
        p_conn.rollback()

s_conn = sqlite3.connect('admin_data/admin.db')
s_cur = s_conn.cursor()

s_cur.execute('SELECT * FROM staff_users')
cols = [d[0] for d in s_cur.description]
rows = s_cur.fetchall()
for r in rows:
    cols_str = ', '.join(cols)
    placeholders = ', '.join(['%s'] * len(cols))
    query = f"INSERT INTO staff_users ({cols_str}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING"
    p_cur.execute(query, list(r))

s_cur.execute('SELECT * FROM teams')
t_cols = [d[0] for d in s_cur.description]
t_rows = s_cur.fetchall()
for r in t_rows:
    t_cols_str = ', '.join(t_cols)
    t_placeholders = ', '.join(['%s'] * len(t_cols))
    query = f"INSERT INTO teams ({t_cols_str}) VALUES ({t_placeholders}) ON CONFLICT (id) DO NOTHING"
    p_cur.execute(query, [str(x) if i in (9,10) else x for i, x in enumerate(r)])

p_conn.commit()

p_cur.execute("SELECT COUNT(*) FROM staff_users")
print("staff_users in PostgreSQL:", p_cur.fetchone()[0])
p_cur.execute("SELECT COUNT(*) FROM teams")
print("teams in PostgreSQL:", p_cur.fetchone()[0])

# Verify all tables in PostgreSQL
p_cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
tables = p_cur.fetchall()
print(f"\nTotal Live Tables in PostgreSQL ({len(tables)}):")
for t in tables:
    p_cur.execute(f"SELECT COUNT(*) FROM {t[0]};")
    cnt = p_cur.fetchone()[0]
    print(f"  - {t[0].ljust(22)}: {cnt} rows")

p_conn.close()
s_conn.close()
