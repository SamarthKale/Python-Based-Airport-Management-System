import mysql.connector
from mysql.connector import pooling
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
from functools import wraps
from db_config import config # Import config from db_config.py
import datetime

app = Flask(__name__)
app.secret_key = 'your_very_secret_key_for_flask_session'

# =G===========================================
# Database Connection Pool
# =G===========================================
try:
    # Create a connection pool
    pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="airline_pool",
        pool_size=10,
        **config
    )
    print("[OK] Database connection pool created successfully.")
except mysql.connector.Error as err:
    print(f"[ERROR] Error creating connection pool: {err}")
    exit(1)

# Helper function to get a connection from the pool
def get_db_connection():
    try:
        if 'db' not in g:
            g.db = pool.get_connection()
        return g.db
    except mysql.connector.Error as err:
        print(f"[ERROR] Error getting connection from pool: {err}")
        return None

# Helper function to close connection
@app.teardown_appcontext
def close_db_connection(exception=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# =G===========================================
# Database Query Helper
# =G===========================================
# A robust helper to handle all DB interactions
def db_query(query, params=None, commit=False, fetchone=False, fetchall=False):
    """
    Executes a database query.
    :param query: SQL query string
    :param params: Tuple of parameters for the query
    :param commit: Boolean, True if transaction needs to be committed (INSERT, UPDATE, DELETE)
    :param fetchone: Boolean, True if one result is expected
    :param fetchall: Boolean, True if all results are expected
    :return: Query result or last insert ID
    """
    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "danger")
        return None

    cursor = conn.cursor(dictionary=True) # dictionary=True returns results as dicts
    last_id = None
    
    try:
        cursor.execute(query, params or ())
        
        if commit:
            conn.commit()
            last_id = cursor.lastrowid
        
        result = None
        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
            
        return last_id or result

    except mysql.connector.Error as err:
        conn.rollback() # Rollback on error
        print(f"❌ SQL Error: {err}")
        # Check for specific SQLSTATE errors from procedures
        if err.sqlstate == '45000':
            flash(f"Booking Error: {err.msg}", "danger")
        else:
            flash(f"Database error: {err.msg}", "danger")
        return None
    finally:
        cursor.close()

# ============================================
# RBAC Helper Functions
# ============================================

def has_permission(role_name, perm_key):
    """
    Check if a role has a specific permission (case-insensitive role check).
    Returns True if the role has the permission, False otherwise.
    """
    if not role_name or not perm_key: # Basic check
        return False
        
    query = """
        SELECT 1
        FROM role_permissions rp
        JOIN roles r ON rp.role_id = r.role_id
        JOIN permissions p ON rp.permission_id = p.permission_id
        WHERE LOWER(r.role_name) = LOWER(%s) AND p.permission_key = %s
        LIMIT 1
    """
    result = db_query(query, (role_name, perm_key), fetchone=True)
    return result is not None

# def get_user_role(): # No longer needed, use session['role'] directly
#     """Get the current user's role name from session."""
#     role_from_session = session.get('role', 'passenger')
#     return role_from_session


def get_user_permissions():
    """Get all permissions for the current user's role stored in session."""
    user_role_name_from_session = session.get('role') # Get role as stored in session (e.g., 'ATC', 'Admin')

    if not user_role_name_from_session:
        print("DEBUG: No role found in session for get_user_permissions")
        return [] # No role, no permissions

    # Query using the role name stored in the session, compare case-insensitively
    query = """
        SELECT p.permission_key
        FROM role_permissions rp
        JOIN roles r ON rp.role_id = r.role_id
        JOIN permissions p ON rp.permission_id = p.permission_id
        WHERE LOWER(r.role_name) = LOWER(%s) -- Use LOWER comparison for robustness
    """
    permissions = db_query(query, (user_role_name_from_session,), fetchall=True)

    # Add a default 'view_profile' permission for all logged-in employees
    all_permissions = [p['permission_key'] for p in permissions] if permissions else []

    # Check user type based on session role
    current_role_lower = user_role_name_from_session.lower()
    if current_role_lower not in ['admin', 'passenger']:
        if 'view_profile' not in all_permissions:
            all_permissions.insert(0, 'view_profile') # Add to start

    print(f"DEBUG: Permissions fetched for role '{user_role_name_from_session}': {all_permissions}") # Optional Debug
    return all_permissions


# Make permissions available globally to templates
@app.context_processor
def inject_permissions():
    if 'user_id' in session:
        # Fetch permissions dynamically each time context is needed
        current_permissions = get_user_permissions()
        # print(f"DEBUG: Injecting permissions into context: {current_permissions}") # Optional Debug
        return {
            'user_permissions': current_permissions,
            'user_role': session.get('role') # Return role as stored in session
        }
    return {}

def requires_permission(perm_key):
    """Decorator factory to check if user has specific permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('index'))
            
            # Use the role stored in session directly for permission check
            user_role_from_session = session.get('role')
            if not user_role_from_session:
                 flash("Your role is not defined. Please log in again.", "danger")
                 print("DEBUG: Role missing in session for requires_permission check.") # Debug
                 return redirect(url_for('logout'))

            # Check permission using has_permission helper
            if not has_permission(user_role_from_session, perm_key):
                print(f"DEBUG: Permission '{perm_key}' check FAILED for role '{user_role_from_session}'.") # Debug
                flash(f"Access Denied: You do not have the required permission ('{perm_key}').", "danger")
                dashboard_url = get_dashboard_url(user_role_from_session)
                # Avoid redirect loop if already on dashboard
                if request.endpoint == dashboard_url:
                     # If they are already on their dashboard and lack permission for an action,
                     # maybe just flash the message without redirecting, or redirect to a safe page.
                     # For now, let's try redirecting back to referrer if possible.
                     return redirect(request.referrer or url_for(dashboard_url))
                else:
                    return redirect(url_for(dashboard_url))
                
            # print(f"DEBUG: Permission '{perm_key}' check PASSED for role '{user_role_from_session}'.") # Debug
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================
# Authentication & Decorators
# ============================================

def get_dashboard_url(role_name):
    """
    Return appropriate dashboard URL based on role name (case-insensitive).
    """
    if not role_name: # Handle cases where role might be None or empty
        print("DEBUG: get_dashboard_url called with no role_name, returning 'index'.") # Debug
        return 'index'

    role_lower = role_name.lower()
    role_map = {
        'admin': 'dashboard_admin',
        'passenger': 'dashboard_passenger',
    }
    # Default to 'dashboard_generic' for all other roles
    dashboard = role_map.get(role_lower, 'dashboard_generic')
    # print(f"DEBUG: get_dashboard_url resolved role '{role_name}' to endpoint '{dashboard}'.") # Debug
    return dashboard


def login_required(role=None):
    """Decorator to protect routes based on user role."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('index'))
            
            # Compare roles case-insensitively if a specific role is required
            session_role = session.get('role')
            if role and (not session_role or session_role.lower() != role.lower()):
                flash(f"Access denied. Requires '{role}' role.", "danger")
                print(f"DEBUG: login_required failed. Session role '{session_role}' != required role '{role}'.") # Debug
                user_role_for_redirect = session_role or 'passenger' # Fallback
                dashboard_url = get_dashboard_url(user_role_for_redirect)
                return redirect(url_for(dashboard_url))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================
# Main & Login Routes
# ============================================

@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role') # Use role from session
        if not role:
             print("DEBUG: Role missing in session at index route. Logging out.") # Debug
             session.clear()
             return render_template('index.html')

        dashboard_endpoint = get_dashboard_url(role) # Use helper
        # Ensure endpoint exists before redirecting
        try:
             # Check if the endpoint function exists
             view_func = app.view_functions.get(dashboard_endpoint)
             if view_func:
                 # print(f"DEBUG: Redirecting logged-in user (role: {role}) to {dashboard_endpoint}") # Debug
                 return redirect(url_for(dashboard_endpoint))
             else:
                  print(f"ERROR: Dashboard endpoint '{dashboard_endpoint}' not found for role '{role}'. Logging out.") # Debug Error
                  flash("Configuration error: Your dashboard endpoint is missing. Please contact support.", "danger")
                  session.clear() # Log out if dashboard is invalid
                  return render_template('index.html')
        except Exception as e:
             print(f"ERROR: Exception resolving dashboard URL '{dashboard_endpoint}': {e}. Logging out.") # Debug Error
             flash("An error occurred while redirecting to your dashboard.", "danger")
             session.clear()
             return render_template('index.html')

    return render_template('index.html')


@app.route('/login/admin', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'] # NOTE: Passwords should be hashed in production!
        
        # In production, compare hashed password
        admin = db_query("SELECT * FROM admin WHERE username = %s AND password = %s", (username, password), fetchone=True)
        
        if admin:
            session['user_id'] = admin['admin_id']
            session['name'] = admin['full_name']
            session['role'] = 'Admin' # Store with consistent casing (matching roles table if needed)
            flash(f"Welcome, {admin['full_name']}!", "success")
            return redirect(url_for('dashboard_admin'))
        else:
            flash("Invalid username or password.", "danger")
            
    return render_template('login_admin.html')

@app.route('/register/passenger', methods=['GET', 'POST'])
def register_passenger():
    """Passenger registration page."""
    if request.method == 'POST':
        form = request.form
        passport_no = form['passport_no']
        
        # Check if passenger already exists
        existing = db_query("SELECT * FROM passenger WHERE passport_no = %s", (passport_no,), fetchone=True)
        
        if existing:
            flash("This passport number is already registered. Please log in instead.", "danger")
            return redirect(url_for('login_passenger'))
        
        # Create new passenger
        try:
            db_query("""
                INSERT INTO passenger (name, email, phone, passport_no, dob) 
                VALUES (%s, %s, %s, %s, %s)
            """, (form['name'], form['email'], form['phone'], passport_no, form['dob']), commit=True)
            
            flash("Registration successful! Please log in with your passport number.", "success")
            return redirect(url_for('login_passenger'))
        except mysql.connector.Error as err:
            flash(f"Registration failed: {err.msg}", "danger")
            
    return render_template('register_passenger.html')

@app.route('/login/passenger', methods=['GET', 'POST'])
def login_passenger():
    if request.method == 'POST':
        passport_no = request.form['passport_no']
        
        passenger = db_query("SELECT * FROM passenger WHERE passport_no = %s", (passport_no,), fetchone=True)
        
        if passenger:
            session['user_id'] = passenger['passenger_id']
            session['name'] = passenger['name']
            session['role'] = 'Passenger' # Store with consistent casing (matching roles table)
            flash(f"Welcome, {passenger['name']}!", "success")
            return redirect(url_for('dashboard_passenger'))
        else:
            flash("Invalid Passport Number. Please register or try again.", "danger")
            
    return render_template('login_passenger.html')

@app.route('/login/employee', methods=['GET', 'POST'])
def login_employee():
    if request.method == 'POST':
        email = request.form['email']
        doj = request.form['date_of_joining']
        
        # Get employee with their role information
        employee = db_query("""
            SELECT e.*, r.role_name 
            FROM employee e
            LEFT JOIN roles r ON e.role_id = r.role_id
            WHERE e.email = %s AND e.date_of_joining = %s
        """, (email, doj), fetchone=True)
        
        if employee:
            session['user_id'] = employee['emp_id']
            session['name'] = employee['name']
            # Store the canonical role name from the DB (e.g., 'ATC', 'Engineer', 'Admin')
            # This name is crucial for permission checks
            db_role_name = employee.get('role_name')

            if not db_role_name: # If role_id was NULL or invalid
                print(f"ERROR: Employee {email} logged in but has no valid role assigned in DB. Denying access.") # Debug Error
                flash("Login failed: No valid role assigned. Please contact administrator.", "danger")
                return redirect(url_for('login_employee')) # Stay on login page
            else:
                 session['role'] = db_role_name # Store the actual role name (e.g., ATC)
                 print(f"DEBUG: Storing role '{db_role_name}' in session for user {email}") # Debug

            session['emp_role_name'] = employee.get('role', db_role_name) # Job title (can differ from system role, fallback to system role)
            flash(f"Welcome, {employee['name']}!", "success")
            
            # Redirect based on the actual role name from DB stored in session
            dashboard_url = get_dashboard_url(session['role']) 
            print(f"DEBUG: Redirecting user {email} (role: {session['role']}) to {dashboard_url}") # Debug
            return redirect(url_for(dashboard_url))
        else:
            flash("Invalid email or date of joining.", "danger")
            
    return render_template('login_employee.html')


@app.route('/logout')
def logout():
    role = session.get('role') # Get role before clearing
    session.clear()
    flash("You have been logged out.", "success")
    # Redirect to appropriate login page based on previous role? Or just index.
    # if role and role.lower() == 'admin':
    #     return redirect(url_for('login_admin'))
    # elif role and role.lower() == 'passenger':
    #      return redirect(url_for('login_passenger'))
    # elif role: # Any other employee role
    #      return redirect(url_for('login_employee'))
    return redirect(url_for('index')) # Simple redirect to index

# ============================================
# Admin Dashboard & CRUD
# ============================================

@app.route('/dashboard/admin')
@login_required(role='Admin') # Use consistent casing matching session role
def dashboard_admin():
    """Main admin dashboard page. Uses 'page' query param to render different sections."""
    page = request.args.get('page', 'dashboard')
    data = {}
    
    # Permission checks for accessing admin sections (optional but good practice)
    current_admin_role = session['role'] # Should be 'Admin'
    # Example:
    # if page == 'employees' and not has_permission(current_admin_role, 'manage_employees'):
    #     flash("Access Denied: You lack 'manage_employees' permission.", "danger")
    #     return redirect(url_for('dashboard_admin', page='dashboard'))
    
    if page == 'dashboard':
        stats = {
            'passengers': db_query("SELECT COUNT(*) AS c FROM passenger", fetchone=True)['c'],
            'employees': db_query("SELECT COUNT(*) AS c FROM employee", fetchone=True)['c'],
            'flights': db_query("SELECT COUNT(*) AS c FROM flight WHERE status = 'Scheduled'", fetchone=True)['c'],
            'bookings': db_query("SELECT COUNT(*) AS c FROM booking WHERE status = 'Confirmed'", fetchone=True)['c'],
        }
        data['stats'] = stats
    
    elif page == 'passengers':
        data['passengers'] = db_query("SELECT * FROM passenger ORDER BY name", fetchall=True)
    
    elif page == 'employees':
        data['employees'] = db_query("""
            SELECT e.*, r.role_name, r.role_id 
            FROM employee e
            LEFT JOIN roles r ON e.role_id = r.role_id
            ORDER BY e.name
        """, fetchall=True)
        data['roles'] = db_query("SELECT * FROM roles ORDER BY role_name", fetchall=True)

    elif page == 'flights':
        data['flights'] = db_query("SELECT * FROM upcoming_flights ORDER BY departure_time", fetchall=True)
        data['routes'] = db_query("SELECT * FROM route", fetchall=True)
        data['aircraft'] = db_query("SELECT * FROM aircraft WHERE status = 'Operational'", fetchall=True)

    elif page == 'bookings':
        data['bookings'] = db_query("""
            SELECT b.*, p.name, f.flight_no 
            FROM booking b
            JOIN passenger p ON b.passenger_id = p.passenger_id
            JOIN flight f ON b.flight_id = f.flight_id
            ORDER BY b.booking_date DESC
        """, fetchall=True)

    elif page == 'vendors':
        data['vendors'] = db_query("SELECT * FROM vendor ORDER BY terminal, name", fetchall=True)

    elif page == 'payroll':
        data['payrolls'] = db_query("""
            SELECT pr.*, e.name, e.role
            FROM payroll pr
            JOIN employee e ON pr.emp_id = e.emp_id
            ORDER BY pr.pay_date DESC
        """, fetchall=True)
        data['employees'] = db_query("SELECT emp_id, name, salary FROM employee", fetchall=True)

    elif page == 'reports':
        data['passenger_summary'] = db_query("SELECT * FROM passenger_summary ORDER BY total_spent DESC", fetchall=True)

    elif page == 'audit':
        data['logs'] = db_query("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100", fetchall=True)
    
    return render_template('dashboard_admin.html', page=page, data=data)

# --- Admin CRUD Routes ---

# Employees
@app.route('/admin/employee/add', methods=['POST'])
@login_required(role='Admin') 
@requires_permission('manage_employees')
def add_employee():
    form = request.form
    role_id = int(form.get('role_id', 0))
    job_title = form.get('role_name', 'Employee')  # Job title/position from form

    # Insert employee with role_id linking to roles table
    db_query("INSERT INTO employee (name, role, role_id, email, date_of_joining, salary) VALUES (%s, %s, %s, %s, %s, %s)",
             (form['name'], job_title, role_id if role_id > 0 else None, form['email'], form['date_of_joining'], form['salary']), commit=True)
    flash("Employee added successfully.", "success")
    return redirect(url_for('dashboard_admin', page='employees'))


@app.route('/admin/employee/edit', methods=['POST'])
@login_required(role='Admin') 
@requires_permission('manage_employees')
def edit_employee():
    form = request.form
    role_id = int(form.get('role_id', 0))
    job_title = form.get('role_name', 'Employee')  # Job title from form
    
    db_query("UPDATE employee SET name=%s, role=%s, role_id=%s, email=%s, date_of_joining=%s, salary=%s WHERE emp_id=%s",
             (form['name'], job_title, role_id if role_id > 0 else None, form['email'], form['date_of_joining'], form['salary'], form['emp_id']), commit=True)
    flash("Employee updated successfully.", "success")
    return redirect(url_for('dashboard_admin', page='employees'))


# Flights
@app.route('/admin/flight/add', methods=['POST'])
@login_required(role='Admin') 
@requires_permission('manage_flights')
def add_flight():
    form = request.form
    # Basic validation before DB call
    required_fields = ['flight_no', 'airline', 'route_id', 'aircraft_id', 'departure_time', 'arrival_time', 'base_fare']
    if not all(form.get(field) for field in required_fields):
        flash("Missing required flight details.", "danger")
        return redirect(url_for('dashboard_admin', page='flights'))
        
    db_query("INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare) VALUES (%s, %s, %s, %s, %s, %s, %s)",
             (form['flight_no'], form['airline'], form['route_id'], form['aircraft_id'], form['departure_time'], form['arrival_time'], form['base_fare']), commit=True)
    flash("Flight added successfully.", "success")
    return redirect(url_for('dashboard_admin', page='flights'))

# Vendors
@app.route('/admin/vendor/add', methods=['POST'])
@login_required(role='Admin') 
#@requires_permission('manage_vendors') # Add this permission if needed
def add_vendor():
    form = request.form
    # Basic validation
    if not form.get('name') or not form.get('amenity_type') or not form.get('terminal') or not form.get('location_desc'):
         flash("Missing required vendor details.", "danger")
         return redirect(url_for('dashboard_admin', page='vendors'))

    db_query("INSERT INTO vendor (name, amenity_type, terminal, location_desc) VALUES (%s, %s, %s, %s)",
             (form['name'], form['amenity_type'], form['terminal'], form['location_desc']), commit=True)
    flash("Vendor added successfully.", "success")
    return redirect(url_for('dashboard_admin', page='vendors'))

# Payroll
@app.route('/admin/payroll/add', methods=['POST'])
@login_required(role='Admin') 
@requires_permission('manage_payroll')
def add_payroll():
    form = request.form
    emp_id = form.get('emp_id')
    pay_date = form.get('pay_date')
    bonus = form.get('bonus', 0.0)
    deductions = form.get('deductions', 0.0)

    if not emp_id or not pay_date:
        flash("Missing employee ID or pay date.", "danger")
        return redirect(url_for('dashboard_admin', page='payroll'))

    emp = db_query("SELECT salary FROM employee WHERE emp_id = %s", (emp_id,), fetchone=True)
    if emp:
        db_query("INSERT INTO payroll (emp_id, base_salary, bonus, deductions, pay_date) VALUES (%s, %s, %s, %s, %s)",
                 (emp_id, emp['salary'], bonus, deductions, pay_date), commit=True)
        flash("Payroll entry added.", "success")
    else:
        flash(f"Employee with ID {emp_id} not found.", "danger")
    return redirect(url_for('dashboard_admin', page='payroll'))

# Admin Actions
@app.route('/admin/flight/cancel', methods=['POST'])
@login_required(role='Admin') 
@requires_permission('manage_flights')
def admin_cancel_flight():
    flight_id = request.form.get('flight_id')
    if not flight_id:
        flash("No flight ID specified for cancellation.", "danger")
        return redirect(url_for('dashboard_admin', page='flights'))
        
    db_query("UPDATE flight SET status='Cancelled' WHERE flight_id=%s AND status = 'Scheduled'", (flight_id,), commit=True) # Only cancel scheduled flights
    # Consider checking affected rows to confirm cancellation
    flash("Flight marked as Cancelled (if it was scheduled).", "success")
    return redirect(url_for('dashboard_admin', page='flights'))

@app.route('/admin/run_status_update', methods=['POST'])
@login_required(role='Admin') 
def run_status_update():
    """Manually triggers the flight status update procedure."""
    try:
        db_query("CALL sp_update_flight_statuses()", commit=True)
        flash("Flight statuses update procedure executed.", "success")
    except Exception as e:
         flash(f"Error executing status update procedure: {e}", "danger")
         print(f"ERROR calling sp_update_flight_statuses: {e}") # Debug Error
    return redirect(url_for('dashboard_admin', page='flights'))

# ============================================
# Admin RBAC Routes
# ============================================

@app.route('/admin/roles', methods=['GET'])
@login_required(role='Admin') 
@requires_permission('manage_roles')
def admin_roles():
    """View and manage roles and their permissions."""
    roles = db_query("SELECT * FROM roles ORDER BY role_name", fetchall=True)
    permissions = db_query("SELECT * FROM permissions ORDER BY permission_key", fetchall=True)
    
    # Attach assigned permissions to each role
    if roles: # Check if roles list is not empty
        for r in roles:
            query = """
                SELECT permission_id 
                FROM role_permissions 
                WHERE role_id = %s
            """
            assigned = db_query(query, (r['role_id'],), fetchall=True)
            r['assigned_perms'] = [a['permission_id'] for a in assigned] if assigned else []
    
    return render_template('dashboard_admin_roles.html', roles=roles or [], permissions=permissions or [])


@app.route('/admin/roles/update', methods=['POST'])
@login_required(role='Admin') 
@requires_permission('manage_roles')
def update_role_permissions():
    """Update permissions for all roles."""
    print("--- Starting update_role_permissions ---") # DEBUG
    # Limit logging form data if it gets too large in production
    # print("Form data received:", request.form)       # DEBUG

    roles = db_query("SELECT role_id, role_name FROM roles", fetchall=True) # Fetch only needed fields
    permissions = db_query("SELECT permission_id, permission_key FROM permissions", fetchall=True) # Fetch only needed fields

    if not roles or not permissions:
        flash("Error fetching roles or permissions.", "danger")
        print("--- ERROR: Could not fetch roles or permissions ---") # DEBUG Error
        return redirect(url_for('admin_roles'))

    try: 
        for r in roles:
            for p in permissions:
                checkbox = f"perm_{r['role_id']}_{p['permission_id']}"
                permission_key = p['permission_key'] 
                role_id = r['role_id']

                should_have_perm = checkbox in request.form

                if should_have_perm: 
                    # print(f"Attempting to GRANT '{permission_key}' to role_id {role_id}") # DEBUG
                    result = db_query("CALL grant_permission(%s, %s)", (role_id, permission_key), commit=True)
                    # Optional: Check result if procedure returns status
                else: 
                    # print(f"Attempting to REVOKE '{permission_key}' from role_id {role_id}") # DEBUG
                    result = db_query("CALL revoke_permission(%s, %s)", (role_id, permission_key), commit=True)
                    # Optional: Check result

        flash("Permissions updated successfully.", "success")
        print("--- Finished update_role_permissions successfully ---") # DEBUG

    except Exception as e:
        flash(f"An error occurred while updating permissions: {e}", "danger")
        print(f"--- ERROR in update_role_permissions: {e} ---") # DEBUG Error
        # Log the full traceback for detailed debugging
        import traceback
        traceback.print_exc()


    return redirect(url_for('admin_roles'))


@app.route('/admin/role/add', methods=['POST'])
@login_required(role='Admin') 
@requires_permission('manage_roles')
def add_role():
    """Add a new role."""
    role_name = request.form.get('role_name')
    description = request.form.get('description', '')
    
    try:
        if not role_name or not role_name.strip():
             flash("Role name cannot be empty.", "danger")
             return redirect(url_for('admin_roles'))

        db_query("INSERT INTO roles (role_name, description) VALUES (%s, %s)", 
                (role_name.strip(), description), commit=True) 
        flash(f"Role '{role_name.strip()}' created successfully.", "success")
    except mysql.connector.Error as err:
        if err.errno == 1062:  # Duplicate entry
            flash(f"Role '{role_name.strip()}' already exists.", "danger")
        else:
            flash(f"Error creating role: {err.msg}", "danger")
            print(f"ERROR adding role: {err}") # Debug Error
    
    return redirect(url_for('admin_roles'))


@app.route('/admin/permission/add', methods=['POST'])
@login_required(role='Admin') 
@requires_permission('manage_permissions')
def add_permission():
    """Add a new permission."""
    permission_key = request.form.get('permission_key')
    description = request.form.get('description', '')
    
    try:
        if not permission_key or not permission_key.strip():
             flash("Permission key cannot be empty.", "danger")
             return redirect(url_for('admin_roles'))
             
        # Optional: Add validation for permission key format (e.g., lowercase, underscores)

        db_query("INSERT INTO permissions (permission_key, description) VALUES (%s, %s)", 
                (permission_key.strip(), description), commit=True) 
        flash(f"Permission '{permission_key.strip()}' created successfully.", "success")
    except mysql.connector.Error as err:
        if err.errno == 1062:  # Duplicate entry
            flash(f"Permission '{permission_key.strip()}' already exists.", "danger")
        else:
            flash(f"Error creating permission: {err.msg}", "danger")
            print(f"ERROR adding permission: {err}") # Debug Error
    
    return redirect(url_for('admin_roles'))


# ============================================
# Passenger Dashboard
# ============================================

@app.route('/dashboard/passenger', methods=['GET'])
@login_required(role='Passenger') 
def dashboard_passenger():
    page = request.args.get('page', 'search')
    passenger_id = session['user_id']
    data = {}

    # =======================================
    # ✈️  1. Search Flights Page
    # =======================================
    if page == 'search':
         # Delegate to the search function
         return search_flights()

    # =======================================
    # 🧾  2. My Bookings Page
    # =======================================
    elif page == 'bookings':
        data['bookings'] = db_query("""
            SELECT 
                b.booking_id,
                b.status,
                b.booking_date,
                f.flight_no,
                f.airline,
                r.source_name,
                r.dest_name,
                f.departure_time,
                f.arrival_time,
                b.seat_no,
                COALESCE(p.amount, 0) AS amount
            FROM booking b
            JOIN flight f ON b.flight_id = f.flight_id
            JOIN route r ON f.route_id = r.route_id
            LEFT JOIN payment p ON b.booking_id = p.booking_id
            WHERE b.passenger_id = %s
            ORDER BY b.booking_date DESC
        """, (passenger_id,), fetchall=True) or []

    # =======================================
    # 🏬  3. Amenities Page
    # =======================================
    elif page == 'amenities':
        # Delegate to the search function
        return search_amenities()


    # =======================================
    # 👤  4. Profile Page
    # =======================================
    elif page == 'profile':
        # Added permission check for passengers to view/edit their profile
        # Use session['role'] which should be 'Passenger'
        if not has_permission(session['role'], 'edit_profile'): 
            flash("You don't have permission to view your profile details.", "warning")
            return redirect(url_for('dashboard_passenger', page='search')) 

        profile = db_query("""
            SELECT 
                p.name,
                p.email,
                p.passport_no,
                p.total_points,
                COUNT(DISTINCT b.booking_id) AS total_bookings,
                COALESCE(SUM(pay.amount), 0) AS total_spent
            FROM passenger p
            LEFT JOIN booking b ON p.passenger_id = b.passenger_id
            LEFT JOIN payment pay ON b.booking_id = pay.booking_id
            WHERE p.passenger_id = %s
            GROUP BY p.passenger_id, p.name, p.email, p.passport_no, p.total_points -- Added all non-aggregated columns
        """, (passenger_id,), fetchone=True) or {}
        data['profile'] = profile

    # =======================================
    # ✅ Render Template Safely
    # =======================================
    # Only render if not delegated to another function
    if page in ['bookings', 'profile']:
        return render_template('dashboard_passenger.html', page=page, data=data or {})
    else:
        # If page wasn't 'search' or 'amenities' (which return directly), it's an invalid page
        flash(f"Invalid page requested: {page}", "warning")
        return redirect(url_for('dashboard_passenger', page='search'))


@app.route('/passenger/search', methods=['GET'])
@login_required(role='Passenger') 
def search_flights():
    source = request.args.get('source')
    dest = request.args.get('dest')
    date = request.args.get('date')
    
    query = "SELECT * FROM upcoming_flights WHERE status = 'Scheduled'"
    params = []
    
    if source:
        query += " AND (source_code = %s OR source_name LIKE %s)"
        params.extend([source, f'%{source}%'])
    if dest:
        query += " AND (dest_code = %s OR dest_name LIKE %s)"
        params.extend([dest, f'%{dest}%'])
    if date:
        query += " AND DATE(departure_time) = %s"
        params.append(date)
        
    query += " ORDER BY departure_time"
    
    results = db_query(query, tuple(params), fetchall=True)
    
    # Render within the passenger dashboard template structure
    return render_template('dashboard_passenger.html', page='search', data={'results': results or [], 'search': request.args})


@app.route('/api/flight/<int:flight_id>/seats', methods=['GET']) # Added type hint
@login_required(role='Passenger') 
def get_available_seats(flight_id):
    """API endpoint to get available seats for a flight."""
    
    # Validate flight_id (basic)
    if not isinstance(flight_id, int) or flight_id <= 0:
         return jsonify({'error': 'Invalid flight ID format'}), 400

    # Get aircraft capacity and booked seats
    query = """
        SELECT 
            a.capacity,
            a.aircraft_id,
            GROUP_CONCAT(b.seat_no ORDER BY b.seat_no SEPARATOR ',') as booked_seats 
        FROM flight f
        JOIN aircraft a ON f.aircraft_id = a.aircraft_id
        LEFT JOIN booking b ON f.flight_id = b.flight_id AND b.status = 'Confirmed'
        WHERE f.flight_id = %s
        GROUP BY a.aircraft_id, a.capacity 
    """
    result = db_query(query, (flight_id,), fetchone=True)
    
    if result and result['aircraft_id']:
        # Get all seats for this aircraft from aircraft_seats table
        seats_query = "SELECT seat_no FROM aircraft_seats WHERE aircraft_id = %s ORDER BY seat_no"
        all_seats = db_query(seats_query, (result['aircraft_id'],), fetchall=True) or []
        
        booked_seats_list = set(result['booked_seats'].split(',')) if result['booked_seats'] else set()
        
        # Build seat map
        seat_map = []
        for seat in all_seats:
            seat_no = seat['seat_no']
            is_booked = seat_no in booked_seats_list
            seat_map.append({
                'seat_no': seat_no,
                'available': not is_booked
            })
        
        return jsonify({'seats': seat_map, 'capacity': result['capacity']})
    elif result is None and g.get('db_error'): # Check if db_query failed internally
         print(f"ERROR fetching seats for flight {flight_id}: DB query failed.") # Debug Error
         return jsonify({'error': 'Database error fetching seat data'}), 500
    else: # Flight found but maybe no aircraft_id or no result?
        print(f"WARNING: No seat data found for flight {flight_id}. Result: {result}") # Debug Warning
        return jsonify({'error': 'Flight or Aircraft seat data not found'}), 404



@app.route('/passenger/book', methods=['POST'])
@login_required(role='Passenger') 
@requires_permission('book_flight') 
def book_flight():
    flight_id = request.form.get('flight_id')
    seat_no = request.form.get('seat_no')
    passenger_id = session.get('user_id')

    if not flight_id or not seat_no or not passenger_id:
        flash("Missing information for booking.", "danger")
        return redirect(url_for('dashboard_passenger', page='search'))

    try:
        # Call the stored procedure
        result = db_query("CALL book_flight(%s, %s, %s, %s)",
                        (passenger_id, flight_id, seat_no, 'Passenger'),
                        commit=True, fetchone=True) # Fetch the output param
        
        if result and 'new_booking_id' in result:
            flash(f"Booking successful! Your Booking ID is {result['new_booking_id']}.", "success")
            return redirect(url_for('dashboard_passenger', page='bookings'))
        else:
            # Error flash should be handled by db_query if procedure SIGNALed
            # Add a generic fallback if no specific message was flashed
            if not get_flashed_messages():
                 flash("Booking failed. The seat might be taken or the flight unavailable.", "danger") 
            print(f"DEBUG: book_flight procedure call failed or returned unexpected result: {result}") # Debug
            return redirect(url_for('dashboard_passenger', page='search')) # Redirect back to search

    except Exception as e:
         # Catch unexpected errors during the process
         flash(f"An unexpected error occurred during booking: {e}", "danger")
         print(f"--- ERROR during booking: {e} ---") # Debug Error
         import traceback
         traceback.print_exc()
         return redirect(url_for('dashboard_passenger', page='search'))


@app.route('/passenger/booking/cancel', methods=['POST'])
@login_required(role='Passenger') 
@requires_permission('cancel_booking') 
def cancel_booking():
    booking_id = request.form.get('booking_id')
    passenger_id = session.get('user_id')

    if not booking_id:
         flash("No booking ID provided.", "danger")
         return redirect(url_for('dashboard_passenger', page='bookings'))

    try:
        # Check if this booking belongs to the logged-in passenger
        booking = db_query("SELECT status FROM booking WHERE booking_id = %s AND passenger_id = %s",
                        (booking_id, passenger_id), fetchone=True)
        
        if booking:
            if booking['status'] == 'Cancelled':
                flash("This booking is already cancelled.", "info")
            else:
                # Update status
                db_query("UPDATE booking SET status = 'Cancelled' WHERE booking_id = %s", (booking_id,), commit=True)
                # Assume trigger handles refund logging/payment update
                flash("Booking successfully cancelled.", "success")
        else:
            flash("Booking not found or you do not have permission to cancel it.", "danger")

    except Exception as e:
        flash(f"An error occurred while cancelling the booking: {e}", "danger")
        print(f"--- ERROR cancelling booking {booking_id}: {e} ---") # Debug Error
        import traceback
        traceback.print_exc()

    return redirect(url_for('dashboard_passenger', page='bookings'))


@app.route('/passenger/amenities/search', methods=['GET'])
@login_required(role='Passenger') 
def search_amenities():
    terminal = request.args.get('terminal', '')
    
    query = "SELECT * FROM vendor WHERE 1=1"
    params = []
    
    if terminal:
        query += " AND terminal LIKE %s" 
        params.append(f'%{terminal}%')
        
    query += " ORDER BY name"
    
    results = db_query(query, tuple(params), fetchall=True)
    
    # Render within the passenger dashboard template structure
    return render_template('dashboard_passenger.html', page='amenities', data={'results': results or [], 'search': request.args})


# ============================================
# Generic Employee Dashboard (Using rbac_seed_v2.py keys)
# ============================================

@app.route('/dashboard/generic')
@login_required() 
def dashboard_generic():
    """
    A generic, permission-based dashboard for all non-admin, non-passenger roles.
    Uses permission keys from rbac_seed_v2.py.
    """
    current_role = session.get('role')
    print(f"DEBUG: Entering dashboard_generic for role: {current_role}") # Debug Entry

    # Immediate logout if role invalid or admin/passenger somehow gets here
    if not current_role or current_role.lower() in ['admin', 'passenger']:
        flash("Invalid access attempt for generic dashboard.", "danger")
        print(f"ERROR: Invalid role '{current_role}' tried accessing generic dashboard. Logging out.") # Debug Error
        return redirect(url_for('logout')) 

    data = {}
    emp_id = session['user_id']
    permissions = get_user_permissions() # Fetches permissions based on session['role']
    # print(f"DEBUG: Fetched permissions for {current_role}: {permissions}") # Debug Permissions

    if not permissions:
        flash("You have no permissions assigned. Please contact an administrator.", "warning")
        print(f"WARNING: No permissions found for role '{current_role}'. Displaying minimal page.") # Debug Warning
        data['page'] = None # Indicate no specific page content applies
        return render_template('dashboard_generic.html', data=data)


    # Determine which page to show
    page = request.args.get('page')
    print(f"DEBUG: Requested page = {page}") # Debug Requested Page
    
    # Default page logic: Use first permission if requested page is invalid or missing
    if not page or page not in permissions:
        original_page_request = page # Store for logging
        page = permissions[0] # Default to the first permission in their list
        print(f"DEBUG: Requested page '{original_page_request}' invalid or not permitted. Defaulting to '{page}'.") # Debug Defaulting

    data['page'] = page # Pass actual page key being rendered to template

    print(f"DEBUG: Rendering page '{page}' for role '{current_role}'") # Debug Rendering Page

    # --- Data Fetching Logic based on permission key ---
    # Standardize on keys from rbac_seed_v2.py

    try: # Wrap data fetching in try block
        if page == 'view_profile': # Default for all employees
            data['profile'] = db_query("""
                SELECT e.*, r.role_name 
                FROM employee e
                LEFT JOIN roles r ON e.role_id = r.role_id
                WHERE e.emp_id = %s
            """, (emp_id,), fetchone=True)

        elif page == 'view_assigned_flights': # Useful common task
            data['assignments'] = db_query("""
                SELECT f.flight_no, f.airline, r.source_name, r.dest_name, f.departure_time, f.gate, sa.role_on_flight
                FROM staff_assignment sa
                JOIN flight f ON sa.flight_id = f.flight_id
                JOIN route r ON f.route_id = r.route_id
                WHERE sa.emp_id = %s AND f.status = 'Scheduled'
                ORDER BY f.departure_time
            """, (emp_id,), fetchall=True)
        
        elif page == 'add_maintenance': # Key from rbac_seed
            data['aircrafts'] = db_query("SELECT aircraft_id, registration_no, model, status FROM aircraft", fetchall=True)
            data['logs'] = db_query("""
                SELECT m.*, a.registration_no
                FROM maintenance m
                JOIN aircraft a ON m.aircraft_id = a.aircraft_id
                WHERE m.emp_id = %s
                ORDER BY m.maintenance_date DESC
            """, (emp_id,), fetchall=True)

        elif page == 'view_payroll': # Common task, assume needed if granted
            data['paychecks'] = db_query("""
                SELECT * FROM payroll
                WHERE emp_id = %s
                ORDER BY pay_date DESC
            """, (emp_id,), fetchall=True)

        elif page == 'add_aircraft': # Key from rbac_seed
            data['aircraft'] = db_query("SELECT * FROM aircraft ORDER BY registration_no", fetchall=True)

        elif page == 'add_route': # Key from rbac_seed
            data['routes'] = db_query("SELECT * FROM route ORDER BY source_code, dest_code", fetchall=True)

        elif page == 'view_reports': # Often admin/manager, but allow if granted
            data['passenger_summary'] = db_query("SELECT * FROM passenger_summary ORDER BY total_spent DESC", fetchall=True)
        
        elif page == 'manage_flights': # Key from rbac_seed
            data['flights'] = db_query("SELECT * FROM upcoming_flights ORDER BY departure_time", fetchall=True)
            data['routes'] = db_query("SELECT * FROM route", fetchall=True)
            data['aircraft'] = db_query("SELECT * FROM aircraft WHERE status = 'Operational'", fetchall=True)
        
        elif page == 'update_flight_status': # Key from rbac_seed
            data['flights'] = db_query("SELECT f.*, r.source_code, r.dest_code FROM flight f JOIN route r ON f.route_id=r.route_id WHERE f.status = 'Scheduled' ORDER BY f.departure_time", fetchall=True) # Added route info

        elif page == 'manage_payroll': # Key from rbac_seed
            data['payrolls'] = db_query("""
                SELECT pr.*, e.name, e.role
                FROM payroll pr
                JOIN employee e ON pr.emp_id = e.emp_id
                ORDER BY pr.pay_date DESC
            """, fetchall=True)
            data['employees'] = db_query("SELECT emp_id, name, salary FROM employee", fetchall=True)

        elif page == 'manage_employees': # Key from rbac_seed
            data['employees'] = db_query("""
                SELECT e.*, r.role_name, r.role_id 
                FROM employee e
                LEFT JOIN roles r ON e.role_id = r.role_id
                ORDER BY e.name
            """, fetchall=True)
            data['roles'] = db_query("SELECT * FROM roles ORDER BY role_name", fetchall=True)

        # manage_roles & manage_permissions redirect handled directly
        elif page == 'manage_roles' or page == 'manage_permissions':
             # Only Admin should have these. If a non-admin gets here, redirect them.
             flash("Access Denied: Role and Permission management is Admin-only.", "danger")
             print(f"WARNING: Role '{current_role}' attempted to access '{page}'. Redirecting.") # Debug Warning
             return redirect(url_for('dashboard_generic'))


        elif page == 'update_aircraft_status': # Key from rbac_seed
            data['aircraft'] = db_query("SELECT * FROM aircraft ORDER BY registration_no", fetchall=True)

        elif page == 'view_audit': # Key from rbac_seed
            data['logs'] = db_query("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100", fetchall=True)

        # Passenger permissions should not be fetched here for employee roles
        # Add elif blocks for any other valid employee permissions from rbac_seed_v2.py
        # elif page == 'another_employee_permission':
        #     data['some_data'] = db_query(...)

        # else block removed - if page is in permissions but no elif matches,
        # the template's final else block will handle the "Not Implemented" message.

    except Exception as e:
         # Catch unexpected errors during data fetching for the specific page
         flash(f"An error occurred loading data for page '{page}': {e}", "danger")
         print(f"--- ERROR loading data for page '{page}', role '{current_role}': {e} ---") # Debug Error
         import traceback
         traceback.print_exc()
         # Render the template with the error message in the 'else' block
         data['page'] = page # Still pass the page name so the correct 'else' block shows

    # Ensure data dict always exists, even if fetching failed
    data = data or {}
    data['page'] = page # Ensure page key is always present

    return render_template('dashboard_generic.html', data=data)


# ============================================
# Employee Actions (Protected by Permissions, using rbac_seed_v2.py keys)
# ============================================

@app.route('/employee/flight/update_status', methods=['POST'])
@login_required()
@requires_permission('update_flight_status') # Key from rbac_seed
def update_flight_status_action():
    form = request.form
    flight_id = form.get('flight_id')
    new_status = form.get('status')
    gate = form.get('gate') # Optional
    delay = form.get('delay_minutes', 0) # Optional, default 0

    if not flight_id or not new_status:
        flash("Missing flight ID or new status.", "danger")
        return redirect(url_for('dashboard_generic', page='update_flight_status'))

    try:
        db_query("UPDATE flight SET status = %s, gate = %s, delay_minutes = %s WHERE flight_id = %s",
                (new_status, gate, delay, flight_id), commit=True)
        flash("Flight status updated successfully.", "success")
    except Exception as e:
         flash(f"Error updating flight status: {e}", "danger")
         print(f"--- ERROR updating flight {flight_id}: {e} ---") # Debug Error

    return redirect(url_for('dashboard_generic', page='update_flight_status'))


@app.route('/employee/aircraft/update_status', methods=['POST'])
@login_required()
@requires_permission('update_aircraft_status') # Key from rbac_seed
def update_aircraft_status_action(): 
    form = request.form
    aircraft_id = form.get('aircraft_id')
    new_status = form.get('status')

    if not aircraft_id or not new_status:
         flash("Missing aircraft ID or new status.", "danger")
         return redirect(url_for('dashboard_generic', page='update_aircraft_status'))

    try:
        db_query("UPDATE aircraft SET status = %s WHERE aircraft_id = %s",
                (new_status, aircraft_id), commit=True)
        flash("Aircraft status updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating aircraft status: {e}", "danger")
        print(f"--- ERROR updating aircraft {aircraft_id}: {e} ---") # Debug Error

    return redirect(url_for('dashboard_generic', page='update_aircraft_status'))


# --- Actions previously under /groundstaff or /employee, now generic ---

@app.route('/generic/aircraft/add', methods=['POST'])
@login_required()
@requires_permission('add_aircraft') # Key from rbac_seed
def generic_add_aircraft():
    """Add new aircraft."""
    form = request.form
    reg_no = form.get('registration_no')
    model = form.get('model')
    capacity = form.get('capacity')
    status = form.get('status', 'Operational')

    if not reg_no or not model or not capacity:
         flash("Missing required aircraft details.", "danger")
         return redirect(url_for('dashboard_generic', page='add_aircraft'))

    try:
        db_query("INSERT INTO aircraft (registration_no, model, capacity, status) VALUES (%s, %s, %s, %s)",
                (reg_no, model, capacity, status), commit=True)
        flash("Aircraft added successfully!", "success")
    except mysql.connector.Error as err:
        if err.errno == 1062: # Duplicate entry
            flash(f"Aircraft with registration '{reg_no}' already exists.", "danger")
        else:
            flash(f"Database error adding aircraft: {err.msg}", "danger")
            print(f"❌ Error adding aircraft: {err}") # Log detailed error
    
    return redirect(url_for('dashboard_generic', page='add_aircraft'))


@app.route('/generic/route/add', methods=['POST'])
@login_required()
@requires_permission('add_route') # Key from rbac_seed
def generic_add_route():
    """Add new route."""
    form = request.form
    source_code = form.get('source_code')
    source_name = form.get('source_name')
    dest_code = form.get('dest_code')
    dest_name = form.get('dest_name')

    if not source_code or not source_name or not dest_code or not dest_name:
         flash("Missing required route details.", "danger")
         return redirect(url_for('dashboard_generic', page='add_route'))

    try:
        # Assuming calc_distance exists and works
        distance_result = db_query("SELECT calc_distance(%s, %s) AS dist",
                           (source_code, dest_code), fetchone=True)
        distance_km = distance_result['dist'] if distance_result else 0
        
        db_query("INSERT INTO route (source_code, source_name, dest_code, dest_name, distance_km) VALUES (%s, %s, %s, %s, %s)",
                (source_code, source_name, dest_code, dest_name, distance_km), commit=True)
        flash("Route added successfully!", "success")
    except mysql.connector.Error as err:
        if err.errno == 1062: # Duplicate entry
            flash(f"Route from {source_code} to {dest_code} already exists.", "danger")
        else:
            flash(f"Database error adding route: {err.msg}", "danger")
            print(f"❌ Error adding route: {err}") # Log detailed error

    return redirect(url_for('dashboard_generic', page='add_route'))


@app.route('/generic/maintenance/add', methods=['POST'])
@login_required()
@requires_permission('add_maintenance') # Key from rbac_seed
def generic_add_maintenance_log():
    form = request.form
    emp_id = session['user_id']
    aircraft_id = form.get('aircraft_id')
    maint_date = form.get('maintenance_date')
    notes = form.get('notes')
    new_status = form.get('new_status')

    if not aircraft_id or not maint_date or not new_status:
         flash("Missing required maintenance details.", "danger")
         return redirect(url_for('dashboard_generic', page='add_maintenance'))

    try:
        # Log the maintenance
        m_id = db_query("INSERT INTO maintenance (aircraft_id, emp_id, notes, maintenance_date) VALUES (%s, %s, %s, %s)",
                (aircraft_id, emp_id, notes, maint_date), commit=True)
        
        # Update aircraft status and last maintenance date
        db_query("UPDATE aircraft SET status = %s, last_maintenance = %s WHERE aircraft_id = %s",
                (new_status, maint_date, aircraft_id), commit=True)
        flash("Maintenance log added and aircraft status updated.", "success")

    except Exception as e:
         flash(f"Error logging maintenance: {e}", "danger")
         print(f"--- ERROR logging maintenance: {e} ---") # Log detailed error
         import traceback
         traceback.print_exc()

    return redirect(url_for('dashboard_generic', page='add_maintenance'))


# --- Reusing Admin logic for shared permissions ---
# These functions now redirect correctly to the generic dashboard

@app.route('/generic/employee/add', methods=['POST'])
@login_required()
@requires_permission('manage_employees')
def generic_add_employee():
    form = request.form
    role_id = int(form.get('role_id', 0))
    job_title = form.get('role_name', 'Employee') 
    
    try:
        db_query("INSERT INTO employee (name, role, role_id, email, date_of_joining, salary) VALUES (%s, %s, %s, %s, %s, %s)",
             (form['name'], job_title, role_id if role_id > 0 else None, form['email'], form['date_of_joining'], form['salary']), commit=True)
        flash("Employee added successfully.", "success")
    except Exception as e:
        flash(f"Error adding employee: {e}", "danger")
        print(f"--- ERROR adding employee (generic): {e} ---")
    return redirect(url_for('dashboard_generic', page='manage_employees'))

@app.route('/generic/employee/edit', methods=['POST'])
@login_required()
@requires_permission('manage_employees')
def generic_edit_employee():
    form = request.form
    role_id = int(form.get('role_id', 0))
    job_title = form.get('role_name', 'Employee') 
    emp_id = form.get('emp_id')

    if not emp_id:
        flash("Employee ID missing.", "danger")
        return redirect(url_for('dashboard_generic', page='manage_employees'))

    try:
        db_query("UPDATE employee SET name=%s, role=%s, role_id=%s, email=%s, date_of_joining=%s, salary=%s WHERE emp_id=%s",
                (form['name'], job_title, role_id if role_id > 0 else None, form['email'], form['date_of_joining'], form['salary'], emp_id), commit=True)
        flash("Employee updated successfully.", "success")
    except Exception as e:
        flash(f"Error editing employee: {e}", "danger")
        print(f"--- ERROR editing employee {emp_id} (generic): {e} ---")
    return redirect(url_for('dashboard_generic', page='manage_employees'))


@app.route('/generic/payroll/add', methods=['POST'])
@login_required()
@requires_permission('manage_payroll')
def generic_add_payroll():
    form = request.form
    emp_id = form.get('emp_id')
    pay_date = form.get('pay_date')
    bonus = form.get('bonus', 0.0)
    deductions = form.get('deductions', 0.0)

    if not emp_id or not pay_date:
        flash("Missing employee ID or pay date.", "danger")
        return redirect(url_for('dashboard_generic', page='manage_payroll'))
        
    try:
        emp = db_query("SELECT salary FROM employee WHERE emp_id = %s", (emp_id,), fetchone=True)
        if emp:
            db_query("INSERT INTO payroll (emp_id, base_salary, bonus, deductions, pay_date) VALUES (%s, %s, %s, %s, %s)",
                    (emp_id, emp['salary'], bonus, deductions, pay_date), commit=True)
            flash("Payroll entry added.", "success")
        else:
            flash(f"Employee with ID {emp_id} not found.", "danger")
    except Exception as e:
        flash(f"Error adding payroll: {e}", "danger")
        print(f"--- ERROR adding payroll for emp {emp_id} (generic): {e} ---")

    return redirect(url_for('dashboard_generic', page='manage_payroll'))


@app.route('/generic/flight/add', methods=['POST'])
@login_required()
@requires_permission('manage_flights') 
def generic_add_flight():
    form = request.form
    required_fields = ['flight_no', 'airline', 'route_id', 'aircraft_id', 'departure_time', 'arrival_time', 'base_fare']
    if not all(form.get(field) for field in required_fields):
        flash("Missing required flight details.", "danger")
        return redirect(url_for('dashboard_generic', page='manage_flights'))
        
    try:
        db_query("INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (form['flight_no'], form['airline'], form['route_id'], form['aircraft_id'], form['departure_time'], form['arrival_time'], form['base_fare']), commit=True)
        flash("Flight added successfully.", "success")
    except Exception as e:
        flash(f"Error adding flight: {e}", "danger")
        print(f"--- ERROR adding flight {form.get('flight_no')} (generic): {e} ---")

    return redirect(url_for('dashboard_generic', page='manage_flights'))

@app.route('/generic/flight/cancel', methods=['POST'])
@login_required()
@requires_permission('manage_flights')
def generic_cancel_flight():
    flight_id = request.form.get('flight_id')
    if not flight_id:
        flash("No flight ID specified for cancellation.", "danger")
        return redirect(url_for('dashboard_generic', page='manage_flights'))
        
    try:
        # Only cancel scheduled flights
        db_query("UPDATE flight SET status='Cancelled' WHERE flight_id=%s AND status = 'Scheduled'", (flight_id,), commit=True) 
        flash("Flight marked as Cancelled (if it was scheduled).", "success")
    except Exception as e:
        flash(f"Error cancelling flight: {e}", "danger")
        print(f"--- ERROR cancelling flight {flight_id} (generic): {e} ---")

    return redirect(url_for('dashboard_generic', page='manage_flights'))


if __name__ == '__main__':
    # Add host='0.0.0.0' for Docker/external access if needed
    app.run(debug=True, port=5000)

