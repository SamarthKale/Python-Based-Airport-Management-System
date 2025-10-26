import mysql.connector

# ============================================
# DB Connection
# ============================================
config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Swami@2006',
    'database': 'airline_pro_db_v2',
    'autocommit': True
}

try:
    cnx = mysql.connector.connect(**config)
    cursor = cnx.cursor()
    print("[OK] Connected to airline_pro_db_v2")
except mysql.connector.Error as err:
    print(f"[ERROR] Error connecting to database: {err}")
    exit(1)


# ============================================
# Detect Columns Safely
# ============================================
try:
    cursor.execute("SHOW COLUMNS FROM permissions")
    columns = [row[0] for row in cursor.fetchall()]
    
    # FIX: Correctly detect 'permission_key' from init_sql_v2.py
    if "permission_key" in columns:
        PERM_KEY_COL = "permission_key"
    elif "perm_key" in columns:
        PERM_KEY_COL = "perm_key"
    elif "permission_name" in columns:
        PERM_KEY_COL = "permission_name"
    else:
        # This block should not be needed if init_sql_v2.py ran successfully
        print("[ERROR] Critical schema error: 'permission_key' column not found.")
        print("Please ensure init_sql_v2.py has run successfully.")
        PERM_KEY_COL = "permission_key" # Assume for script to continue
        # exit(1) # More robust scripts would exit here

except mysql.connector.Error as err:
    print(f"❌ Error checking 'permissions' table: {err}")
    exit(1)


# ============================================
# Data
# ============================================
roles = [
    ('Admin', 'Full system control'),
    ('HR', 'Manages employees and payroll'),
    ('Ground Staff', 'Adds routes and aircraft'),
    ('ATC', 'Controls flight statuses'),
    ('Engineer', 'Handles maintenance operations'),
    ('Passenger', 'Can book and manage flights')
]

permissions = [
    ('manage_roles', 'Create and edit roles'),
    ('manage_permissions', 'Assign permissions to roles'),
    ('manage_employees', 'Add or modify employees'),
    ('manage_payroll', 'Add payroll entries'),
    ('add_aircraft', 'Add new aircraft'),
    ('add_route', 'Add new route'),
    ('manage_flights', 'Create or cancel flights'),
    ('update_flight_status', 'Mark flights as Departed/Arrived'),
    ('add_maintenance', 'Add maintenance records'),
    ('update_aircraft_status', 'Mark aircraft as operational or under repair'),
    ('book_flight', 'Book flight tickets'),
    ('cancel_booking', 'Cancel existing booking'),
    ('edit_profile', 'Edit passenger profile'),
    ('view_audit', 'Access system audit logs')
]

role_permissions = {
    'Admin': [
        'manage_roles', 'manage_permissions', 'manage_employees',
        'manage_flights', 'manage_payroll', 'view_audit'
    ],
    'HR': ['manage_employees', 'manage_payroll'],
    'Ground Staff': ['add_aircraft', 'add_route'],
    'ATC': ['update_flight_status'],
    'Engineer': ['add_maintenance', 'update_aircraft_status'],
    'Passenger': ['book_flight', 'cancel_booking', 'edit_profile']
}

# ============================================
# Helper Insert
# ============================================
def insert_if_not_exists(table, column, value, extra_values=()):
    # FIX: Explicitly define primary key columns based on schema
    pk_col = "permission_id" if table == "permissions" else "role_id"
    
    cursor.execute(f"SELECT {pk_col} FROM {table} WHERE {column} = %s", (value,))
    row = cursor.fetchone()
    if not row:
        cols = f"{column}" + (", description" if extra_values else "")
        placeholders = ", ".join(["%s"] * (1 + len(extra_values)))
        
        # This query will now correctly use 'permission_key' and insert into all required columns
        cursor.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", (value,) + extra_values)
        cnx.commit()
        print(f"[OK] Inserted into {table}: {value}")
        return cursor.lastrowid
    return row[0]

# ============================================
# Insert Roles
# ============================================
print("\n[INFO] Inserting Roles...")
# Note: init_sql_v2.py already inserts 'Admin', 'HR', 'Ground Staff', 'ATC', 'Engineer', 'Passenger'
# This script will just find them and skip.
role_ids = {r[0]: insert_if_not_exists('roles', 'role_name', r[0], (r[1],)) for r in roles}

# ============================================
# Insert Permissions
# ============================================
print("\n[INFO] Inserting Permissions...")
# Note: init_sql_v2.py already inserts some permissions. This will add the missing ones.
perm_ids = {p[0]: insert_if_not_exists('permissions', PERM_KEY_COL, p[0], (p[1],)) for p in permissions}

# ============================================
# Role ↔ Permission Mapping
# ============================================
print("\n🔗 Mapping Roles to Permissions...")
for role, perms in role_permissions.items():
    for p in perms:
        # FIX: Use correct table structure (role_id, permission_id)
        # FIX: Use correct column names (permission_id, permission_key)
        # We can use the dictionaries we just built
        role_id_val = role_ids.get(role)
        perm_id_val = perm_ids.get(p)
        
        if role_id_val and perm_id_val:
            cursor.execute("""
                INSERT IGNORE INTO role_permissions (role_id, permission_id)
                VALUES (%s, %s)
            """, (role_id_val, perm_id_val))
        else:
            print(f"⚠️ Skipping mapping for Role: {role} or Perm: {p} (ID not found)")
            
cnx.commit()
print("✅ Role-Permission mapping completed.")

# ============================================
# Stored Procedures
# ============================================
print("\n⚙️ Creating grant/revoke procedures...")
for name, sql in {
    "grant_permission": f"""
        CREATE PROCEDURE grant_permission(IN p_role_id INT, IN p_perm_key VARCHAR(100))
        BEGIN
            DECLARE v_perm_id INT;
            -- FIX: Select correct 'permission_id' using 'permission_key'
            SELECT permission_id INTO v_perm_id FROM permissions WHERE {PERM_KEY_COL} = p_perm_key;
            IF v_perm_id IS NOT NULL THEN
                -- FIX: Insert into correct schema (role_id, permission_id)
                INSERT IGNORE INTO role_permissions (role_id, permission_id)
                VALUES (p_role_id, v_perm_id);
            END IF;
        END
    """,
    "revoke_permission": f"""
        CREATE PROCEDURE revoke_permission(IN p_role_id INT, IN p_perm_key VARCHAR(100))
        BEGIN
            DECLARE v_perm_id INT;
            -- FIX: Select correct 'permission_id' using 'permission_key'
            SELECT permission_id INTO v_perm_id FROM permissions WHERE {PERM_KEY_COL} = p_perm_key;
            IF v_perm_id IS NOT NULL THEN
                -- FIX: Delete from correct schema
                DELETE FROM role_permissions WHERE role_id = p_role_id AND permission_id = v_perm_id;
            END IF;
        END
    """
}.items():
    cursor.execute(f"DROP PROCEDURE IF EXISTS {name}")
    cursor.execute(sql)
    print(f"✅ Created {name}")

# ============================================
# Done
# ============================================
print("\n🎯 RBAC Seeding Complete!")
print("✅ All roles, permissions, and procedures installed successfully.")
cursor.close()
cnx.close()