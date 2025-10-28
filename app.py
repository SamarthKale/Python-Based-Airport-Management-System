import mysql.connector
from mysql.connector import pooling, InterfaceError # Added InterfaceError
from flask import (
    Flask, render_template, request, redirect, 
    url_for, session, flash, g, jsonify, get_flashed_messages
) # Added get_flashed_messages
from functools import wraps
from db_config import config # Import config from db_config.py
import datetime
import traceback # For detailed error logging
import re # For email validation

app = Flask(__name__)
app.secret_key = 'your_very_secret_key_for_flask_session'

# =G===========================================
# Database Connection Pool & Helpers
# =G===========================================
try:
    pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="airline_pool", pool_size=10, pool_reset_session=True, **config
    )
    print("[OK] Database connection pool created successfully.")
except mysql.connector.Error as err:
    print(f"[ERROR] Error creating connection pool: {err}")
    exit(1)

def get_db_connection():
    try:
        if 'db' not in g or g.db is None or not g.db.is_connected():
            g.db = pool.get_connection()
        return g.db
    except mysql.connector.errors.PoolError as pool_err:
        print(f"[ERROR] Pool Error getting connection: {pool_err}")
        g.db = None
        flash("System busy. Please try again later.", "warning")
        return None
    except mysql.connector.Error as err:
        print(f"[ERROR] Error getting connection from pool: {err}")
        g.db = None
        flash("Database connection error.", "danger")
        return None

@app.teardown_appcontext
def close_db_connection(exception=None):
    db = g.pop('db', None)
    if db is not None and db.is_connected():
        db.close()

def db_query(query, params=None, commit=False, fetchone=False, fetchall=False):
    conn = get_db_connection()
    if not conn:
        print("ERROR: db_query failed - No DB connection available.")
        g.db_error = True
        return None
    
    g.db_error = False
    cursor = None
    last_id = None
    
    try:
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute(query, params or ())
        
        result_data = None
        
        # START FIX: Handle stored procedure results
        if query.strip().upper().startswith("CALL"):
            try:
                # Iterate over all result sets produced by the procedure
                for i, result in enumerate(cursor.stored_results()):
                    # If we want data (fetchone/fetchall) and this is the first set, grab it
                    if (fetchone or fetchall) and i == 0:
                        if fetchone:
                            result_data = result.fetchone()
                        elif fetchall:
                            result_data = result.fetchall()
                    else:
                        # IMPORTANT: We must consume *all* rows from *all* other result sets
                        result.fetchall()
            except InterfaceError as ie:
                # "No result set" is a common and benign error from procedures
                if "No result set" not in str(ie): raise
        
        # ELSE: This is a simple query (non-CALL)
        # Only check cursor.description if it's NOT a CALL
        elif cursor.description:
            if fetchone: result_data = cursor.fetchone()
            elif fetchall: result_data = cursor.fetchall()
        
        # Now, commit or handle results
        if commit:
            conn.commit()
            last_id = cursor.lastrowid
        
        # Prioritize returning data from the procedure if it was fetched
        if result_data is not None:
            return result_data
        
        # Prioritize returning last_id if it was a commit operation that generated one
        return last_id if commit and last_id is not None else result_data

    except mysql.connector.Error as err:
        try: conn.rollback()
        except Exception as rb_err: print(f"ERROR: Exception during rollback: {rb_err}")
        print(f"❌ SQL Error executing query [{query[:100]}...]: {err} (Code: {err.errno}, State: {err.sqlstate})")
        g.db_error = True
        
        # User-friendly error flashing
        if err.sqlstate == '45000': flash(f"Operation Error: {err.msg}", "danger")
        elif err.errno == 1062: flash("Error: Conflict - Item already exists.", "warning")
        elif 'foreign key constraint' in str(err).lower(): flash("Error: Action blocked by related records.", "warning")
        elif err.errno in [1213, 1205]: flash("Database busy. Please try again.", "warning")
        else: flash("A database error occurred.", "danger")
        return None
    finally:
        if cursor: cursor.close()

# ============================================
# RBAC Helper Functions
# ============================================

def has_permission(role_name, perm_key):
    # Checks if a given role name has a specific permission key
    if not role_name or not perm_key: return False
    query = """SELECT 1 FROM role_permissions rp
               JOIN roles r ON rp.role_id = r.role_id
               JOIN permissions p ON rp.permission_id = p.permission_id
               WHERE LOWER(r.role_name) = LOWER(%s) AND p.permission_key = %s LIMIT 1"""
    return db_query(query, (role_name, perm_key), fetchone=True) is not None

def get_user_permissions():
    # Gets all permission keys for the role currently in the session
    user_role = session.get('role')
    if not user_role: return []
    query = """SELECT p.permission_key FROM role_permissions rp
               JOIN roles r ON rp.role_id = r.role_id
               JOIN permissions p ON rp.permission_id = p.permission_id
               WHERE LOWER(r.role_name) = LOWER(%s)"""
    perms_result = db_query(query, (user_role,), fetchall=True)
    if perms_result is None: return [] # DB error handling
    all_perms = {p['permission_key'] for p in perms_result}
    # Add implicit profile view for non-admin/passenger
    if user_role.lower() not in ['admin', 'passenger']: all_perms.add('view_profile')
    return sorted(list(all_perms))

@app.context_processor
def inject_permissions():
    # Makes user_permissions and user_role available to all templates
    user_perms = []
    user_role = None
    if 'user_id' in session:
        user_perms = get_user_permissions()
        user_role = session.get('role')
    return dict(user_permissions=user_perms, user_role=user_role)

def requires_permission(perm_key):
    # Decorator to protect routes based on permission key
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session: flash("Authentication required.", "warning"); return redirect(url_for('index'))
            user_role = session.get('role')
            if not user_role: flash("Role undefined.", "danger"); return redirect(url_for('logout'))
            if not has_permission(user_role, perm_key):
                print(f"ACCESS DENIED: Role '{user_role}' lacks perm '{perm_key}' for '{request.endpoint}'.")
                flash(f"Access Denied: Permission '{perm_key}' required.", "danger")
                # Redirect back if possible, else to user's dashboard
                if request.referrer and request.referrer != request.url: return redirect(request.referrer)
                else: return redirect(url_for(get_dashboard_url(user_role)))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================
# Authentication & Dashboard Routing
# ============================================

def get_dashboard_url(role_name):
    # Returns the correct dashboard endpoint based on role name
    if not role_name: return 'index'
    role_lower = role_name.lower()
    if role_lower == 'admin': return 'dashboard_admin'
    elif role_lower == 'passenger': return 'dashboard_passenger'
    else: return 'dashboard_generic' # All others use the generic dashboard

def login_required(role=None):
    # Decorator to ensure login and optionally check role
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session: flash("Please log in.", "warning"); return redirect(url_for('index'))
            if role: # If a specific role is required
                session_role = session.get('role')
                if not session_role or session_role.lower() != role.lower():
                    flash(f"Access restricted: Requires '{role}' role.", "danger")
                    print(f"ACCESS DENIED login_required: Session role '{session_role}' != required '{role}'.")
                    return redirect(url_for(get_dashboard_url(session_role or 'passenger')))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================
# Main & Login/Logout Routes
# ============================================
@app.route('/')
def index():
    # Redirect logged-in users to their dashboard
    if 'user_id' in session:
        role = session.get('role')
        if not role: flash("Session error.", "warning"); session.clear(); return render_template('index.html')
        dashboard = get_dashboard_url(role)
        try:
            if dashboard in app.view_functions: return redirect(url_for(dashboard))
            else: raise ValueError(f"Endpoint '{dashboard}' not found")
        except Exception as e:
             print(f"CRITICAL index redirect failed: {e}"); flash("System error.", "danger"); session.clear(); return render_template('index.html')
    return render_template('index.html') # Show landing page if not logged in

@app.route('/login/admin', methods=['GET', 'POST'])
def login_admin():
    # Handles admin login
    if request.method == 'POST':
        username = request.form.get('username'); password = request.form.get('password')
        if not username or not password: flash("Credentials required.", "danger"); return render_template('login_admin.html')
        admin = db_query("SELECT admin_id, full_name, password FROM admin WHERE username = %s", (username,), fetchone=True)
        # IMPORTANT: Use password hashing in production (e.g., werkzeug.security check_password_hash)
        if admin and admin['password'] == password:
            session.clear(); session['user_id'] = admin['admin_id']; session['name'] = admin['full_name']; session['role'] = 'Admin'
            flash(f"Welcome, {admin['full_name']}!", "success"); return redirect(url_for('dashboard_admin'))
        else: flash("Invalid credentials.", "danger")
    return render_template('login_admin.html')

@app.route('/register/passenger', methods=['GET', 'POST'])
def register_passenger():
    # Handles passenger registration
    if request.method == 'POST':
        form = request.form; passport = form.get('passport_no'); email = form.get('email'); name = form.get('name'); dob = form.get('dob')
        if not all([name, email, passport, dob]): flash("All fields except phone required.", "danger"); return render_template('register_passenger.html', form_data=form)
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email): flash("Invalid email.", "danger"); return render_template('register_passenger.html', form_data=form)
        if db_query("SELECT 1 FROM passenger WHERE passport_no = %s", (passport,), fetchone=True): flash("Passport already registered.", "warning"); return redirect(url_for('login_passenger'))
        if db_query("SELECT 1 FROM passenger WHERE email = %s", (email,), fetchone=True): flash("Email already registered.", "warning"); return render_template('register_passenger.html', form_data=form)
        try:
            insert_id = db_query("INSERT INTO passenger (name, email, phone, passport_no, dob) VALUES (%s, %s, %s, %s, %s)", (name, email, form.get('phone'), passport, dob), commit=True)
            if insert_id: flash("Registration successful! Please log in.", "success"); return redirect(url_for('login_passenger'))
            else: flash("Registration failed.", "danger"); return render_template('register_passenger.html', form_data=form)
        except Exception as e: print(f"CRITICAL registration error: {e}"); flash("Unexpected error.", "danger"); traceback.print_exc(); return render_template('register_passenger.html', form_data=form)
    return render_template('register_passenger.html', form_data={})

@app.route('/login/passenger', methods=['GET', 'POST'])
def login_passenger():
    # Handles passenger login
    if request.method == 'POST':
        passport = request.form.get('passport_no')
        if not passport: flash("Passport required.", "danger"); return render_template('login_passenger.html')
        passenger = db_query("SELECT passenger_id, name FROM passenger WHERE passport_no = %s", (passport,), fetchone=True)
        if passenger:
            session.clear(); session['user_id'] = passenger['passenger_id']; session['name'] = passenger['name']; session['role'] = 'Passenger'
            flash(f"Welcome, {passenger['name']}!", "success"); return redirect(url_for('dashboard_passenger'))
        else: flash("Passport not found.", "danger")
    return render_template('login_passenger.html')

@app.route('/login/employee', methods=['GET', 'POST'])
def login_employee():
    # Handles employee login
    if request.method == 'POST':
        email = request.form.get('email'); doj = request.form.get('date_of_joining')
        if not email or not doj: flash("Email and Date of Joining required.", "danger"); return render_template('login_employee.html')
        employee = db_query("SELECT e.emp_id, e.name, e.role AS job_title, r.role_name FROM employee e LEFT JOIN roles r ON e.role_id = r.role_id WHERE e.email = %s AND e.date_of_joining = %s", (email, doj), fetchone=True)
        if employee:
            db_role = employee.get('role_name')
            if not db_role: print(f"ERROR Login: User {email} lacks valid role."); flash("Login failed: Account lacks valid role.", "danger"); return render_template('login_employee.html')
            session.clear(); session['user_id'] = employee['emp_id']; session['name'] = employee['name']; session['role'] = db_role; session['emp_role_name'] = employee.get('job_title', db_role)
            flash(f"Welcome, {employee['name']}!", "success"); return redirect(url_for(get_dashboard_url(db_role)))
        else: flash("Invalid credentials or Date of Joining.", "danger")
    return render_template('login_employee.html')

@app.route('/logout')
def logout():
    # Clears session and redirects to index
    name = session.get('name', 'User'); session.clear()
    flash(f"Goodbye, {name}! Logged out.", "info"); return redirect(url_for('index'))

# ============================================
# Admin Dashboard & Data Fetching
# ============================================
@app.route('/dashboard/admin')
@login_required(role='Admin')
def dashboard_admin():
    # Renders different sections of the admin dashboard based on 'page' query param
    page = request.args.get('page', 'dashboard')
    data = {'page': page}
    try: # Fetch data specific to the requested admin page
        if page == 'dashboard':
            data['stats'] = {'passengers': (db_query("SELECT COUNT(*) AS c FROM passenger", fetchone=True) or {}).get('c', 0), 'employees': (db_query("SELECT COUNT(*) AS c FROM employee", fetchone=True) or {}).get('c', 0), 'flights': (db_query("SELECT COUNT(*) AS c FROM flight WHERE status = 'Scheduled'", fetchone=True) or {}).get('c', 0), 'bookings': (db_query("SELECT COUNT(*) AS c FROM booking WHERE status = 'Confirmed'", fetchone=True) or {}).get('c', 0)}
        elif page == 'passengers': data['passengers'] = db_query("SELECT * FROM passenger ORDER BY name", fetchall=True) or []
        elif page == 'employees':
            data['employees'] = db_query("SELECT e.*, r.role_name FROM employee e LEFT JOIN roles r ON e.role_id = r.role_id ORDER BY e.name", fetchall=True) or []
            data['roles'] = db_query("SELECT role_id, role_name FROM roles ORDER BY role_name", fetchall=True) or []
        elif page == 'flights':
            data['flights'] = db_query("SELECT * FROM upcoming_flights ORDER BY departure_time", fetchall=True) or []
            data['routes'] = db_query("SELECT route_id, source_code, source_name, dest_code, dest_name FROM route", fetchall=True) or []
            data['aircraft'] = db_query("SELECT aircraft_id, registration_no, model, capacity FROM aircraft WHERE status = 'Operational'", fetchall=True) or []
        elif page == 'bookings': data['bookings'] = db_query("SELECT b.*, p.name as passenger_name, f.flight_no FROM booking b JOIN passenger p ON b.passenger_id=p.passenger_id JOIN flight f ON b.flight_id=f.flight_id ORDER BY b.booking_date DESC", fetchall=True) or []
        elif page == 'vendors': data['vendors'] = db_query("SELECT * FROM vendor ORDER BY terminal, name", fetchall=True) or []
        elif page == 'payroll':
            data['payrolls'] = db_query("SELECT pr.*, e.name AS employee_name, e.role AS job_title FROM payroll pr JOIN employee e ON pr.emp_id=e.emp_id ORDER BY pr.pay_date DESC", fetchall=True) or []
            data['employees'] = db_query("SELECT emp_id, name, salary FROM employee ORDER BY name", fetchall=True) or []
        elif page == 'reports': data['passenger_summary'] = db_query("SELECT * FROM passenger_summary ORDER BY total_spent DESC", fetchall=True) or []
        elif page == 'audit': data['logs'] = db_query("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100", fetchall=True) or []
        # No else needed, template handles default/unknown page
    except Exception as e:
        flash(f"Error loading data: {e}", "danger"); print(f"--- ERROR admin page '{page}': {e} ---"); traceback.print_exc(); data['error'] = str(e)
    return render_template('dashboard_admin.html', page=page, data=data)

# ============================================
# Core Action Logic (Internal Helpers - DRY Principle)
# ============================================

def _add_employee_logic(form_data):
    """DB logic for adding employee. Returns True on success, False otherwise."""
    req = ['name', 'role_id', 'email', 'date_of_joining', 'salary']
    if not all(form_data.get(f) for f in req): flash("Missing required fields.", "danger"); return False
    try:
        role_id = int(form_data['role_id'])
        job_title = form_data.get('role_name', 'Employee') # Job title separate from system role
        db_query("INSERT INTO employee (name, role, role_id, email, date_of_joining, salary) VALUES (%s, %s, %s, %s, %s, %s)",
                 (form_data['name'], job_title, role_id, form_data['email'], form_data['date_of_joining'], form_data['salary']), commit=True)
        return not g.db_error
    except ValueError: flash("Invalid Role ID or Salary.", "danger"); return False
    # db_query handles general DB errors

def _edit_employee_logic(form_data):
    """DB logic for editing employee. Returns True on success, False otherwise."""
    req = ['emp_id', 'name', 'role_id', 'email', 'date_of_joining', 'salary']
    if not all(form_data.get(f) for f in req): flash("Missing required fields.", "danger"); return False
    try:
        role_id = int(form_data['role_id'])
        job_title = form_data.get('role_name', 'Employee')
        db_query("UPDATE employee SET name=%s, role=%s, role_id=%s, email=%s, date_of_joining=%s, salary=%s WHERE emp_id=%s",
                 (form_data['name'], job_title, role_id, form_data['email'], form_data['date_of_joining'], form_data['salary'], form_data['emp_id']), commit=True)
        return not g.db_error
    except ValueError: flash("Invalid Role ID or Salary.", "danger"); return False
    # db_query handles general DB errors

def _add_flight_logic(form_data):
    """DB logic for adding flight. Returns True on success, False otherwise."""
    req = ['flight_no', 'airline', 'route_id', 'aircraft_id', 'departure_time', 'arrival_time', 'base_fare']
    if not all(form_data.get(f) for f in req): flash("Missing required fields.", "danger"); return False
    try:
        # Trigger sets current_fare = base_fare
        db_query("INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (form_data['flight_no'], form_data['airline'], form_data['route_id'], form_data['aircraft_id'], form_data['departure_time'], form_data['arrival_time'], form_data['base_fare']), commit=True)
        return not g.db_error
    except Exception as e: flash(f"Error preparing flight data: {e}", "danger"); print(f"--- ERROR _add_flight_logic: {e} ---"); return False

def _cancel_flight_logic(flight_id):
    """DB logic for cancelling flight. Returns True on success, False otherwise."""
    if not flight_id: flash("No flight ID.", "danger"); return False
    db_query("UPDATE flight SET status='Cancelled' WHERE flight_id=%s AND status = 'Scheduled'", (flight_id,), commit=True)
    return not g.db_error # True even if no rows updated (already cancelled/departed)

def _add_payroll_logic(form_data):
    """DB logic for adding payroll. Returns True on success, False otherwise."""
    emp_id = form_data.get('emp_id'); pay_date = form_data.get('pay_date')
    if not emp_id or not pay_date: flash("Employee/Pay Date required.", "danger"); return False
    emp = db_query("SELECT salary FROM employee WHERE emp_id = %s", (emp_id,), fetchone=True)
    if not emp: flash(f"Employee {emp_id} not found.", "danger"); return False
    db_query("INSERT INTO payroll (emp_id, base_salary, bonus, deductions, pay_date) VALUES (%s, %s, %s, %s, %s)",
             (emp_id, emp['salary'], form_data.get('bonus', 0.0), form_data.get('deductions', 0.0), pay_date), commit=True)
    return not g.db_error

# ============================================
# Admin Action Routes (Use Helpers)
# ============================================
@app.route('/admin/employee/add', methods=['POST'])
@login_required(role='Admin')
@requires_permission('manage_employees')
def add_employee():
    if _add_employee_logic(request.form): flash("Employee added.", "success")
    return redirect(url_for('dashboard_admin', page='employees'))

@app.route('/admin/employee/edit', methods=['POST'])
@login_required(role='Admin')
@requires_permission('manage_employees')
def edit_employee():
    if _edit_employee_logic(request.form): flash("Employee updated.", "success")
    return redirect(url_for('dashboard_admin', page='employees'))

@app.route('/admin/flight/add', methods=['POST'])
@login_required(role='Admin')
@requires_permission('manage_flights')
def add_flight():
    if _add_flight_logic(request.form): flash("Flight added.", "success")
    return redirect(url_for('dashboard_admin', page='flights'))

@app.route('/admin/flight/cancel', methods=['POST'])
@login_required(role='Admin')
@requires_permission('manage_flights')
def admin_cancel_flight():
     if _cancel_flight_logic(request.form.get('flight_id')): flash("Flight cancelled.", "success")
     return redirect(url_for('dashboard_admin', page='flights'))

@app.route('/admin/payroll/add', methods=['POST'])
@login_required(role='Admin')
@requires_permission('manage_payroll')
def add_payroll():
     if _add_payroll_logic(request.form): flash("Payroll added.", "success")
     return redirect(url_for('dashboard_admin', page='payroll'))

@app.route('/admin/vendor/add', methods=['POST'])
@login_required(role='Admin')
#@requires_permission('manage_vendors')
def add_vendor():
    form=request.form; req=['name','amenity_type','terminal','location_desc']
    if not all(form.get(f) for f in req): flash("Missing vendor details.", "danger")
    else:
        db_query("INSERT INTO vendor (name, amenity_type, terminal, location_desc) VALUES (%s, %s, %s, %s)", (form['name'], form['amenity_type'], form['terminal'], form['location_desc']), commit=True)
        if not g.db_error: flash("Vendor added.", "success")
    return redirect(url_for('dashboard_admin', page='vendors'))

@app.route('/admin/run_status_update', methods=['POST'])
@login_required(role='Admin')
def run_status_update():
    db_query("CALL sp_update_flight_statuses()", commit=True)
    if not g.db_error: flash("Status update procedure run.", "success")
    return redirect(url_for('dashboard_admin', page='flights'))

# ============================================
# Admin RBAC Routes (Roles & Permissions Management)
# ============================================
@app.route('/admin/roles', methods=['GET'])
@login_required(role='Admin')
@requires_permission('manage_roles')
def admin_roles():
    """Displays all roles and permissions in a grid for the Admin to manage."""
    try:
        roles = db_query("SELECT * FROM roles ORDER BY role_name", fetchall=True) or []
        permissions = db_query("SELECT * FROM permissions ORDER BY permission_key", fetchall=True) or []
        if roles:
            # Preload all role-permission mappings for efficient display
            mappings = db_query("SELECT role_id, permission_id FROM role_permissions", fetchall=True) or []
            role_perm_map = {r['role_id']: set() for r in roles}
            for m in mappings:
                role_perm_map.setdefault(m['role_id'], set()).add(m['permission_id'])
            for r in roles:
                r['assigned_perms'] = role_perm_map.get(r['role_id'], set())
        return render_template('dashboard_admin_roles.html', roles=roles, permissions=permissions)
    except Exception as e:
        flash(f"Error loading roles: {e}", "danger")
        print(f"--- ERROR loading /admin/roles: {e} ---")
        traceback.print_exc()
        return redirect(url_for('dashboard_admin'))
    

@app.route('/admin/roles/update', methods=['POST'])
@login_required(role='Admin')
@requires_permission('manage_roles')
def update_role_permissions():
    """Processes checkbox updates from Role–Permission grid and updates the DB."""
    print("\n--- Starting /admin/roles/update ---")
    try:
        # Load current roles and permissions
        roles = db_query("SELECT role_id FROM roles", fetchall=True) or []
        permissions = db_query("SELECT permission_id, permission_key FROM permissions", fetchall=True) or []

        if not roles or not permissions:
            flash("Error fetching roles or permissions.", "danger")
            return redirect(url_for('admin_roles'))

        # Track changes
        total, success, failed = 0, 0, 0
        form_keys = set(request.form.keys())

        for role in roles:
            for perm in permissions:
                total += 1
                role_id = role['role_id']
                perm_id = perm['permission_id']
                perm_key = perm['permission_key']
                checkbox_key = f"perm_{role_id}_{perm_id}"
                should_have = checkbox_key in form_keys
                proc = "grant_permission" if should_have else "revoke_permission"
                try:
                    db_query(f"CALL {proc}(%s, %s)", (role_id, perm_key), commit=True)
                    if g.db_error:
                        failed += 1
                    else:
                        success += 1
                except Exception as e:
                    failed += 1
                    print(f"⚠️ Error calling {proc} for role {role_id}, perm {perm_key}: {e}")

        if failed > 0:
            flash(f"Update partially successful: {success}/{total} OK, {failed} failed.", "warning")
        else:
            flash("✅ Role permissions updated successfully!", "success")
        print(f"--- Finished /admin/roles/update ({success} OK / {failed} failed) ---")

    except Exception as e:
        flash(f"Critical error during update: {e}", "danger")
        print(f"--- CRITICAL ERROR in /admin/roles/update: {e} ---")
        traceback.print_exc()

    return redirect(url_for('admin_roles'))


@app.route('/admin/role/add', methods=['POST'])
@login_required(role='Admin')
@requires_permission('manage_roles')
def add_role():
    """Adds a new role with a description."""
    name = request.form.get('role_name', '').strip()
    desc = request.form.get('description', '').strip()
    if not name:
        flash("Role name required.", "danger")
        return redirect(url_for('admin_roles'))

    try:
        db_query("INSERT INTO roles (role_name, description) VALUES (%s, %s)", (name, desc), commit=True)
        if not g.db_error:
            flash(f"✅ Role '{name}' created successfully.", "success")
    except mysql.connector.IntegrityError:
        flash(f"⚠️ Role '{name}' already exists.", "warning")
    except Exception as e:
        flash(f"Error creating role: {e}", "danger")
        print(f"--- ERROR creating role '{name}': {e} ---")

    return redirect(url_for('admin_roles'))


@app.route('/admin/permission/add', methods=['POST'])
@login_required(role='Admin')
@requires_permission('manage_permissions')
def add_permission():
    """Adds a new permission type to the system."""
    key = request.form.get('permission_key', '').strip()
    desc = request.form.get('description', '').strip()
    if not key:
        flash("Permission key required.", "danger")
        return redirect(url_for('admin_roles'))

    if not re.match(r"^[a-z_]+$", key):
        flash("Permission key must be lowercase_with_underscores.", "warning")
        return redirect(url_for('admin_roles'))

    try:
        db_query("INSERT INTO permissions (permission_key, description) VALUES (%s, %s)", (key, desc), commit=True)
        if not g.db_error:
            flash(f"✅ Permission '{key}' added successfully.", "success")
    except mysql.connector.IntegrityError:
        flash(f"⚠️ Permission '{key}' already exists.", "warning")
    except Exception as e:
        flash(f"Error adding permission: {e}", "danger")
        print(f"--- ERROR adding permission '{key}': {e} ---")

    return redirect(url_for('admin_roles'))

# ============================================
# Passenger Routes & Actions
# ============================================
@app.route('/dashboard/passenger', methods=['GET'])
@login_required(role='Passenger')
def dashboard_passenger():
    # ... (Keep existing implementation) ...
    page = request.args.get('page', 'search')
    passenger_id = session['user_id']
    data = {'page': page} 
    try:
        if page == 'search': return search_flights()
        elif page == 'bookings': data['bookings'] = db_query("SELECT b.*, f.flight_no, f.airline, r.source_name, r.dest_name, f.departure_time, f.arrival_time, COALESCE(p.amount, 0) AS amount FROM booking b JOIN flight f ON b.flight_id = f.flight_id JOIN route r ON f.route_id = r.route_id LEFT JOIN payment p ON b.booking_id = p.booking_id WHERE b.passenger_id = %s ORDER BY b.booking_date DESC", (passenger_id,), fetchall=True) or []
        elif page == 'amenities': return search_amenities()
        elif page == 'profile':
            if not has_permission(session['role'], 'edit_profile'): flash("Denied.", "warning"); return redirect(url_for('dashboard_passenger', page='search')) 
            data['profile'] = db_query("SELECT p.name, p.email, p.passport_no, p.total_points, COUNT(DISTINCT b.booking_id) AS total_bookings, COALESCE(SUM(pay.amount), 0) AS total_spent FROM passenger p LEFT JOIN booking b ON p.passenger_id = b.passenger_id AND b.status = 'Confirmed' LEFT JOIN payment pay ON b.booking_id = pay.booking_id AND pay.refunded = FALSE WHERE p.passenger_id = %s GROUP BY p.passenger_id", (passenger_id,), fetchone=True) or {}
        else: flash("Invalid page.", "warning"); return redirect(url_for('dashboard_passenger', page='search'))
    except Exception as e: flash(f"Error: {e}", "danger"); print(f"--- ERROR passenger page '{page}': {e} ---"); traceback.print_exc(); return redirect(url_for('dashboard_passenger', page='search')) 
    return render_template('dashboard_passenger.html', page=page, data=data)

@app.route('/passenger/search', methods=['GET'])
@login_required(role='Passenger') 
def search_flights():
    # ... (Keep existing implementation) ...
    search_args = {k: request.args.get(k, '') for k in ['source', 'dest', 'date']}
    query = "SELECT * FROM upcoming_flights WHERE status = 'Scheduled'"
    params = []
    if search_args['source']: query += " AND (source_code = %s OR source_name LIKE %s)"; params.extend([search_args['source'], f"%{search_args['source']}%"])
    if search_args['dest']: query += " AND (dest_code = %s OR dest_name LIKE %s)"; params.extend([search_args['dest'], f"%{search_args['dest']}%"])
    if search_args['date']: query += " AND DATE(departure_time) = %s"; params.append(search_args['date'])
    query += " ORDER BY departure_time"
    results = db_query(query, tuple(params), fetchall=True)
    return render_template('dashboard_passenger.html', page='search', data={'results': results or [], 'search': search_args})

@app.route('/api/flight/<int:flight_id>/seats', methods=['GET']) 
@login_required(role='Passenger') 
def get_available_seats(flight_id):
    # ... (Keep existing implementation) ...
    if flight_id <= 0: return jsonify({'error': 'Invalid ID'}), 400
    query = "SELECT a.capacity, a.aircraft_id, GROUP_CONCAT(b.seat_no ORDER BY b.seat_no SEPARATOR ',') as booked FROM flight f JOIN aircraft a ON f.aircraft_id=a.aircraft_id LEFT JOIN booking b ON f.flight_id=b.flight_id AND b.status='Confirmed' WHERE f.flight_id=%s GROUP BY a.aircraft_id, a.capacity"
    result = db_query(query, (flight_id,), fetchone=True)
    if result and result.get('aircraft_id'):
        seats = db_query("SELECT seat_no FROM aircraft_seats WHERE aircraft_id=%s ORDER BY seat_no", (result['aircraft_id'],), fetchall=True) or []
        booked = set(result['booked'].split(',')) if result['booked'] else set()
        seat_map = [{'seat_no': s['seat_no'], 'available': s['seat_no'] not in booked} for s in seats]
        return jsonify({'seats': seat_map, 'capacity': result['capacity']})
    elif g.get('db_error'): return jsonify({'error': 'DB error'}), 500
    else: return jsonify({'error': 'Not found'}), 404

@app.route('/passenger/book', methods=['POST'])
@login_required(role='Passenger')
@requires_permission('book_flight') 
def book_flight():
    # START FIX: Handle NameError and redundant flashing
    fid=request.form.get('flight_id'); seat=request.form.get('seat_no'); pid=session.get('user_id')
    search= {k:v for k,v in request.args.items() if k in ['source','dest','date']}
    
    if not all([fid,seat,pid]): 
        flash("Missing flight or seat info.", "danger")
        return redirect(url_for('dashboard_passenger', page='search', **search))
    
    try:
        res = db_query("CALL book_flight(%s, %s, %s, %s)", (pid, fid, seat, 'Passenger'), commit=True, fetchone=True) 
        
        if res and 'new_booking_id' in res: 
            flash(f"Booking Successful! Your Booking ID is: {res['new_booking_id']}.", "success")
            return redirect(url_for('dashboard_passenger', page='bookings'))
        
        # If 'res' is None, db_query already flashed the error (e.g., "Seat already booked")
        elif res is None:
            # db_query already handled flashing the SQL error
            pass
        else:
            # This case is unlikely, but good to have
            flash("Booking failed. (Unexpected procedure result)", "danger")
        
        return redirect(url_for('dashboard_passenger', page='search', **search)) 
    
    except Exception as e: 
        flash(f"Error: {e}", "danger")
        print(f"--- CRITICAL booking error: {e} ---"); traceback.print_exc()
        return redirect(url_for('dashboard_passenger', page='search', **search))
    # END FIX

@app.route('/passenger/booking/cancel', methods=['POST'])
@login_required(role='Passenger')
@requires_permission('cancel_booking') 
def cancel_booking():
    # ... (Keep existing implementation) ...
    bid=request.form.get('booking_id'); pid=session.get('user_id')
    if not bid: flash("No booking ID.", "danger"); return redirect(url_for('dashboard_passenger', page='bookings'))
    try:
        book = db_query("SELECT status FROM booking WHERE booking_id = %s AND passenger_id = %s", (bid, pid), fetchone=True)
        if book:
            if book['status'] == 'Cancelled': flash("Already cancelled.", "info")
            elif book['status'] != 'Confirmed': flash("Cannot cancel.", "warning")
            else: db_query("UPDATE booking SET status = 'Cancelled' WHERE booking_id = %s", (bid,), commit=True); flash("Booking cancelled.", "success")
        else: flash("Not found/yours.", "danger")
    except Exception as e: flash(f"Error: {e}", "danger"); print(f"--- ERROR cancelling {bid}: {e} ---"); traceback.print_exc()
    return redirect(url_for('dashboard_passenger', page='bookings'))

@app.route('/passenger/amenities/search', methods=['GET'])
@login_required(role='Passenger') 
def search_amenities():
    # ... (Keep existing implementation) ...
    term = request.args.get('terminal', ''); query = "SELECT * FROM vendor"; params = []
    if term: query += " WHERE terminal LIKE %s"; params.append(f'%{term}%')
    query += " ORDER BY name"
    results = db_query(query, tuple(params), fetchall=True)
    return render_template('dashboard_passenger.html', page='amenities', data={'results': results or [], 'search': {'terminal': term}})

# ============================================
# Generic Employee Dashboard & Actions (Main Logic)
# ============================================
@app.route('/dashboard/generic')
@login_required()
def dashboard_generic():
    """Renders the generic dashboard, fetching data based on the selected page (permission key)."""
    current_role = session.get('role')
    if not current_role or current_role.lower() in ['admin', 'passenger']:
        flash("Invalid access.", "danger"); print(f"ERROR: Invalid role '{current_role}' to /dashboard/generic."); return redirect(url_for('logout'))
    
    data = {}; emp_id = session['user_id']
    permissions = get_user_permissions() # Get current permissions from DB via helpers
    
    if not permissions:
        flash("No permissions assigned.", "warning"); print(f"WARNING: No perms for role '{current_role}'."); data['page'] = None; return render_template('dashboard_generic.html', data=data)
    
    # Determine page to display: requested & allowed, or first allowed as default
    requested_page = request.args.get('page'); page = requested_page if requested_page and requested_page in permissions else permissions[0]
    data['page'] = page # Pass validated page name to template
    
    print(f"DEBUG: Rendering generic page '{page}' (Role: '{current_role}')") 

    # --- Fetch Data based on the specific page being rendered ---
    try:
        if page == 'view_profile': data['profile'] = db_query("SELECT e.*, r.role_name FROM employee e LEFT JOIN roles r ON e.role_id = r.role_id WHERE e.emp_id = %s", (emp_id,), fetchone=True) or {}
        elif page == 'view_assigned_flights': data['assignments'] = db_query("SELECT f.flight_no, f.airline, r.source_name, r.dest_name, f.departure_time, f.gate, sa.role_on_flight FROM staff_assignment sa JOIN flight f ON sa.flight_id = f.flight_id JOIN route r ON f.route_id = r.route_id WHERE sa.emp_id = %s AND f.status = 'Scheduled' ORDER BY f.departure_time", (emp_id,), fetchall=True) or []
        elif page == 'add_maintenance':
            data['aircrafts'] = db_query("SELECT aircraft_id, registration_no, model, status FROM aircraft ORDER BY registration_no", fetchall=True) or []
            data['logs'] = db_query("SELECT m.*, a.registration_no FROM maintenance m JOIN aircraft a ON m.aircraft_id = a.aircraft_id WHERE m.emp_id = %s ORDER BY m.maintenance_date DESC", (emp_id,), fetchall=True) or []
        elif page == 'view_payroll': data['paychecks'] = db_query("SELECT * FROM payroll WHERE emp_id = %s ORDER BY pay_date DESC", (emp_id,), fetchall=True) or []
        elif page == 'add_aircraft': data['aircraft'] = db_query("SELECT * FROM aircraft ORDER BY registration_no", fetchall=True) or []
        elif page == 'add_route': data['routes'] = db_query("SELECT * FROM route ORDER BY source_code, dest_code", fetchall=True) or []
        elif page == 'view_reports': data['passenger_summary'] = db_query("SELECT * FROM passenger_summary ORDER BY total_spent DESC", fetchall=True) or []
        elif page == 'manage_flights':
            data['flights'] = db_query("SELECT * FROM upcoming_flights ORDER BY departure_time", fetchall=True) or []
            data['routes'] = db_query("SELECT route_id, source_code, source_name, dest_code, dest_name FROM route", fetchall=True) or [] # For modal
            data['aircraft'] = db_query("SELECT aircraft_id, registration_no, model, capacity FROM aircraft WHERE status = 'Operational'", fetchall=True) or [] # For modal
        elif page == 'update_flight_status': data['flights'] = db_query("SELECT f.*, r.source_code, r.dest_code FROM flight f JOIN route r ON f.route_id=r.route_id WHERE f.status IN ('Scheduled', 'Boarding', 'Delayed', 'Departed') ORDER BY f.departure_time", fetchall=True) or []
        elif page == 'manage_payroll':
            data['payrolls'] = db_query("SELECT pr.*, e.name AS employee_name, e.role AS job_title FROM payroll pr JOIN employee e ON pr.emp_id=e.emp_id ORDER BY pr.pay_date DESC", fetchall=True) or []
            data['employees'] = db_query("SELECT emp_id, name, salary FROM employee ORDER BY name", fetchall=True) or [] # For modal
        elif page == 'manage_employees':
            data['employees'] = db_query("SELECT e.*, r.role_name FROM employee e LEFT JOIN roles r ON e.role_id = r.role_id ORDER BY e.name", fetchall=True) or []
            data['roles'] = db_query("SELECT role_id, role_name FROM roles ORDER BY role_name", fetchall=True) or [] # For modal
        elif page == 'manage_roles' or page == 'manage_permissions': flash("Access Denied.", "danger"); return redirect(url_for('dashboard_generic')) # Should not be reachable by non-admins
        elif page == 'update_aircraft_status': data['aircraft'] = db_query("SELECT * FROM aircraft ORDER BY registration_no", fetchall=True) or []
        elif page == 'view_audit': data['logs'] = db_query("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100", fetchall=True) or []
        # Add elif blocks for any other permission keys that need specific data loaded
    except Exception as e:
         flash(f"Error loading dashboard: {e}", "danger"); print(f"--- ERROR loading generic page '{page}': {e} ---"); traceback.print_exc(); data['error'] = str(e)
    
    data.setdefault('page', page) # Ensure page key exists even on error
    # print(f"DEBUG Data sent to template: {data.keys()}") # Verify data keys
    return render_template('dashboard_generic.html', data=data)


# ============================================
# Generic Employee Action Routes (Use Helpers or Own Logic)
# ============================================

@app.route('/generic/employee/add', methods=['POST'])
@login_required()
@requires_permission('manage_employees')
def generic_add_employee():
    if _add_employee_logic(request.form): flash("Employee added.", "success")
    return redirect(url_for('dashboard_generic', page='manage_employees'))

@app.route('/generic/employee/edit', methods=['POST'])
@login_required()
@requires_permission('manage_employees')
def generic_edit_employee():
    if _edit_employee_logic(request.form): flash("Employee updated.", "success")
    return redirect(url_for('dashboard_generic', page='manage_employees'))

@app.route('/generic/flight/add', methods=['POST'])
@login_required()
@requires_permission('manage_flights')
def generic_add_flight():
    if _add_flight_logic(request.form): flash("Flight added.", "success")
    return redirect(url_for('dashboard_generic', page='manage_flights'))

@app.route('/generic/flight/cancel', methods=['POST'])
@login_required()
@requires_permission('manage_flights')
def generic_cancel_flight():
     if _cancel_flight_logic(request.form.get('flight_id')): flash("Flight cancelled.", "success")
     return redirect(url_for('dashboard_generic', page='manage_flights'))

@app.route('/generic/payroll/add', methods=['POST'])
@login_required()
@requires_permission('manage_payroll')
def generic_add_payroll():
     if _add_payroll_logic(request.form): flash("Payroll added.", "success")
     return redirect(url_for('dashboard_generic', page='manage_payroll'))

# --- Actions without direct Admin equivalents ---

@app.route('/generic/flight/update_status', methods=['POST'])
@login_required()
@requires_permission('update_flight_status')
def generic_update_flight_status_action():
    form=request.form; fid=form.get('flight_id'); status=form.get('status')
    if not fid or not status: flash("ID/status required.", "danger")
    else:
        db_query("UPDATE flight SET status=%s, gate=%s, delay_minutes=%s WHERE flight_id=%s", (status, form.get('gate'), form.get('delay_minutes', 0), fid), commit=True)
        if not g.db_error: flash("Status updated.", "success")
    return redirect(url_for('dashboard_generic', page='update_flight_status'))

@app.route('/generic/aircraft/add', methods=['POST'])
@login_required()
@requires_permission('add_aircraft')
def generic_add_aircraft():
    form=request.form; req=['registration_no','model','capacity']
    if not all(form.get(f) for f in req): flash("Reg No, Model, Capacity required.", "danger")
    else:
        reg=form.get('registration_no')
        db_query("INSERT INTO aircraft (registration_no, model, capacity, status) VALUES (%s, %s, %s, %s)", (reg, form['model'], form['capacity'], form.get('status', 'Operational')), commit=True)
        if not g.db_error: flash("Aircraft added.", "success") # db_query flashes on duplicate error
    return redirect(url_for('dashboard_generic', page='add_aircraft'))

@app.route('/generic/aircraft/update_status', methods=['POST'])
@login_required()
@requires_permission('update_aircraft_status')
def generic_update_aircraft_status_action():
    form=request.form; aid=form.get('aircraft_id'); status=form.get('status')
    if not aid or not status: flash("ID/status required.", "danger")
    else:
        db_query("UPDATE aircraft SET status = %s WHERE aircraft_id = %s", (status, aid), commit=True)
        if not g.db_error: flash("Status updated.", "success")
    return redirect(url_for('dashboard_generic', page='update_aircraft_status'))

@app.route('/generic/route/add', methods=['POST'])
@login_required()
@requires_permission('add_route')
def generic_add_route():
    form=request.form; req=['source_code','source_name','dest_code','dest_name']
    if not all(form.get(f) for f in req): flash("All fields required.", "danger")
    else:
        sc=form.get('source_code'); dc=form.get('dest_code')
        dist_res = db_query("SELECT calc_distance(%s, %s) AS dist", (sc, dc), fetchone=True)
        dist_km = dist_res['dist'] if dist_res else 0
        db_query("INSERT INTO route (source_code, source_name, dest_code, dest_name, distance_km) VALUES (%s, %s, %s, %s, %s)", (sc, form['source_name'], dc, form['dest_name'], dist_km), commit=True)
        if not g.db_error: flash("Route added.", "success") # db_query flashes duplicate error
    return redirect(url_for('dashboard_generic', page='add_route'))

@app.route('/generic/maintenance/add', methods=['POST'])
@login_required()
@requires_permission('add_maintenance')
def generic_add_maintenance_log():
    form=request.form; eid=session['user_id']; aid=form.get('aircraft_id'); date=form.get('maintenance_date'); status=form.get('new_status')
    if not all([aid,date,status]): flash("Aircraft, Date, Status required.", "danger")
    else:
        notes=form.get('notes')
        try: # Simple transaction - log first, then update status
            db_query("INSERT INTO maintenance (aircraft_id, emp_id, notes, maintenance_date) VALUES (%s, %s, %s, %s)", (aid, eid, notes, date), commit=True)
            if not g.db_error:
                 db_query("UPDATE aircraft SET status = %s, last_maintenance = %s WHERE aircraft_id = %s", (status, date, aid), commit=True)
                 if not g.db_error: flash("Maintenance logged & status updated.", "success")
            # Else: first query failed, db_query flashed
        except Exception as e: flash(f"Error: {e}", "danger"); print(f"--- ERROR logging maint: {e} ---"); traceback.print_exc()
    return redirect(url_for('dashboard_generic', page='add_maintenance'))

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0') # Host 0.0.0.0 makes it accessible externally/in Docker

