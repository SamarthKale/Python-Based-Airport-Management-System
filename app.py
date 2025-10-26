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
    Check if a role has a specific permission.
    Returns True if the role has the permission, False otherwise.
    """
    query = """
        SELECT 1
        FROM role_permissions rp
        JOIN roles r ON rp.role_id = r.role_id
        JOIN permissions p ON rp.permission_id = p.permission_id
        WHERE r.role_name = %s AND p.permission_key = %s
        LIMIT 1
    """
    result = db_query(query, (role_name, perm_key), fetchone=True)
    return result is not None

def get_user_role():
    """Get the current user's role name from session."""
    return session.get('role', 'passenger')

def get_user_permissions():
    """Get all permissions for the current user's role."""
    user_role = get_user_role()
    query = """
        SELECT p.permission_key
        FROM role_permissions rp
        JOIN roles r ON rp.role_id = r.role_id
        JOIN permissions p ON rp.permission_id = p.permission_id
        WHERE r.role_name = %s
    """
    permissions = db_query(query, (user_role,), fetchall=True)
    # Add a default 'view_profile' permission for all logged-in employees
    all_permissions = [p['permission_key'] for p in permissions] if permissions else []
    if session.get('role') != 'passenger' and session.get('role') != 'admin':
        if 'view_profile' not in all_permissions:
            all_permissions.insert(0, 'view_profile') # Add to start
    return all_permissions

# Make permissions available globally to templates
@app.context_processor
def inject_permissions():
    if 'user_id' in session:
        return {
            'user_permissions': get_user_permissions(),
            'user_role': get_user_role()
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
            
            user_role = get_user_role()
            if not has_permission(user_role, perm_key):
                flash(f"You do not have permission to perform this action. Required permission: {perm_key}", "danger")
                # Try to redirect back, or fall back to their main dashboard
                dashboard_url = get_dashboard_url(user_role)
                return redirect(request.referrer or url_for(dashboard_url))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================
# Authentication & Decorators
# ============================================

def get_dashboard_url(role_name):
    """
    Normalize role name to URL and return appropriate dashboard URL.
    This is now dynamic: admin and passenger go to their specific dashboards,
    all other roles go to the generic, permission-based dashboard.
    """
    role_map = {
        'admin': 'dashboard_admin',
        'passenger': 'dashboard_passenger',
    }
    # Default to 'dashboard_generic' for all other roles (e.g., engineer, hr, ground staff, new_role)
    return role_map.get(role_name.lower(), 'dashboard_generic')

def login_required(role=None):
    """Decorator to protect routes based on user role."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('index'))
            
            if role and session.get('role') != role:
                flash(f"You do not have permission to access this page. Requires '{role}' role.", "danger")
                # Redirect to their own dashboard
                user_role = session.get('role', 'passenger')
                dashboard_url = get_dashboard_url(user_role)
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
        role = session.get('role', 'passenger')
        dashboard_endpoint = get_dashboard_url(role)
        return redirect(url_for(dashboard_endpoint))
    return render_template('index.html')

@app.route('/login/admin', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        admin = db_query("SELECT * FROM admin WHERE username = %s AND password = %s", (username, password), fetchone=True)
        
        if admin:
            session['user_id'] = admin['admin_id']
            session['name'] = admin['full_name']
            session['role'] = 'admin'
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
            session['role'] = 'passenger'
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
            # Store role from database (could be Engineer, ATC, HR, Ground Staff, etc.)
            role_name = employee.get('role_name', 'employee')
            # Handle None case safely
            if role_name:
                role_name = role_name.lower()
            else:
                role_name = 'employee' # Fallback role
            session['role'] = role_name
            session['emp_role_name'] = employee.get('role', 'Employee')  # Job title
            flash(f"Welcome, {employee['name']}!", "success")
            
            # Redirect based on role using the UPDATED helper function
            dashboard_url = get_dashboard_url(role_name)
            return redirect(url_for(dashboard_url))
        else:
            flash("Invalid email or date of joining.", "danger")
            
    return render_template('login_employee.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('index'))

# ============================================
# Admin Dashboard & CRUD
# ============================================

@app.route('/dashboard/admin')
@login_required(role='admin')
def dashboard_admin():
    """Main admin dashboard page. Uses 'page' query param to render different sections."""
    page = request.args.get('page', 'dashboard')
    data = {}
    
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
@login_required(role='admin')
@requires_permission('manage_employees')
def add_employee():
    form = request.form
    # Get role name from role_id for the 'role' field (job title)
    role_id = int(form.get('role_id', 0))
    role_name = form.get('role_name', 'Employee')  # Job title/position
    
    # Insert employee with role_id linking to roles table
    db_query("INSERT INTO employee (name, role, role_id, email, date_of_joining, salary) VALUES (%s, %s, %s, %s, %s, %s)",
             (form['name'], role_name, role_id if role_id > 0 else None, form['email'], form['date_of_joining'], form['salary']), commit=True)
    flash("Employee added successfully.", "success")
    return redirect(url_for('dashboard_admin', page='employees'))

@app.route('/admin/employee/edit', methods=['POST'])
@login_required(role='admin')
@requires_permission('manage_employees')
def edit_employee():
    form = request.form
    role_id = int(form.get('role_id', 0))
    role_name = form.get('role_name', 'Employee')  # Job title
    
    db_query("UPDATE employee SET name=%s, role=%s, role_id=%s, email=%s, date_of_joining=%s, salary=%s WHERE emp_id=%s",
             (form['name'], role_name, role_id if role_id > 0 else None, form['email'], form['date_of_joining'], form['salary'], form['emp_id']), commit=True)
    flash("Employee updated successfully.", "success")
    return redirect(url_for('dashboard_admin', page='employees'))

# Flights
@app.route('/admin/flight/add', methods=['POST'])
@login_required(role='admin')
@requires_permission('manage_flights')
def add_flight():
    form = request.form
    db_query("INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare) VALUES (%s, %s, %s, %s, %s, %s, %s)",
             (form['flight_no'], form['airline'], form['route_id'], form['aircraft_id'], form['departure_time'], form['arrival_time'], form['base_fare']), commit=True)
    flash("Flight added successfully.", "success")
    return redirect(url_for('dashboard_admin', page='flights'))

# Vendors
@app.route('/admin/vendor/add', methods=['POST'])
@login_required(role='admin')
#@requires_permission('manage_vendors') # Assuming manage_vendors permission exists
def add_vendor():
    form = request.form
    db_query("INSERT INTO vendor (name, amenity_type, terminal, location_desc) VALUES (%s, %s, %s, %s)",
             (form['name'], form['amenity_type'], form['terminal'], form['location_desc']), commit=True)
    flash("Vendor added successfully.", "success")
    return redirect(url_for('dashboard_admin', page='vendors'))

# Payroll
@app.route('/admin/payroll/add', methods=['POST'])
@login_required(role='admin')
@requires_permission('manage_payroll')
def add_payroll():
    form = request.form
    emp = db_query("SELECT salary FROM employee WHERE emp_id = %s", (form['emp_id'],), fetchone=True)
    if emp:
        db_query("INSERT INTO payroll (emp_id, base_salary, bonus, deductions, pay_date) VALUES (%s, %s, %s, %s, %s)",
                 (form['emp_id'], emp['salary'], form['bonus'], form['deductions'], form['pay_date']), commit=True)
        flash("Payroll entry added.", "success")
    else:
        flash("Employee not found.", "danger")
    return redirect(url_for('dashboard_admin', page='payroll'))

# Admin Actions
@app.route('/admin/flight/cancel', methods=['POST'])
@login_required(role='admin')
@requires_permission('manage_flights')
def admin_cancel_flight():
    flight_id = request.form['flight_id']
    db_query("UPDATE flight SET status='Cancelled' WHERE flight_id=%s", (flight_id,), commit=True)
    flash("Flight marked as Cancelled.", "success")
    return redirect(url_for('dashboard_admin', page='flights'))

@app.route('/admin/run_status_update', methods=['POST'])
@login_required(role='admin')
def run_status_update():
    """Manually triggers the flight status update procedure."""
    db_query("CALL sp_update_flight_statuses()", commit=True)
    flash("Flight statuses updated (Completed/Cancelled) based on time.", "success")
    return redirect(url_for('dashboard_admin', page='flights'))

# ============================================
# Admin RBAC Routes
# ============================================

@app.route('/admin/roles', methods=['GET'])
@login_required(role='admin')
@requires_permission('manage_roles')
def admin_roles():
    """View and manage roles and their permissions."""
    roles = db_query("SELECT * FROM roles ORDER BY role_name", fetchall=True)
    permissions = db_query("SELECT * FROM permissions ORDER BY permission_key", fetchall=True)
    
    # Attach assigned permissions to each role
    for r in roles:
        query = """
            SELECT permission_id 
            FROM role_permissions 
            WHERE role_id = %s
        """
        assigned = db_query(query, (r['role_id'],), fetchall=True)
        r['assigned_perms'] = [a['permission_id'] for a in assigned] if assigned else []
    
    return render_template('dashboard_admin_roles.html', roles=roles, permissions=permissions)

@app.route('/admin/roles/update', methods=['POST'])
@login_required(role='admin')
@requires_permission('manage_roles')
def update_role_permissions():
    """Update permissions for all roles."""
    roles = db_query("SELECT * FROM roles", fetchall=True)
    permissions = db_query("SELECT * FROM permissions", fetchall=True)
    
    for r in roles:
        for p in permissions:
            checkbox = f"perm_{r['role_id']}_{p['permission_id']}"
            if checkbox in request.form:
                # Grant permission using stored procedure
                db_query("CALL grant_permission(%s, %s)", (r['role_id'], p['permission_key']), commit=True)
            else:
                # Revoke permission using stored procedure
                db_query("CALL revoke_permission(%s, %s)", (r['role_id'], p['permission_key']), commit=True)
    
    flash("Permissions updated successfully.", "success")
    return redirect(url_for('admin_roles'))

@app.route('/admin/role/add', methods=['POST'])
@login_required(role='admin')
@requires_permission('manage_roles')
def add_role():
    """Add a new role."""
    role_name = request.form['role_name']
    description = request.form.get('description', '')
    
    try:
        db_query("INSERT INTO roles (role_name, description) VALUES (%s, %s)", 
                (role_name, description), commit=True)
        flash(f"Role '{role_name}' created successfully.", "success")
    except mysql.connector.Error as err:
        if err.errno == 1062:  # Duplicate entry
            flash(f"Role '{role_name}' already exists.", "danger")
        else:
            flash(f"Error creating role: {err.msg}", "danger")
    
    return redirect(url_for('admin_roles'))

@app.route('/admin/permission/add', methods=['POST'])
@login_required(role='admin')
@requires_permission('manage_permissions')
def add_permission():
    """Add a new permission."""
    permission_key = request.form['permission_key']
    description = request.form.get('description', '')
    
    try:
        db_query("INSERT INTO permissions (permission_key, description) VALUES (%s, %s)", 
                (permission_key, description), commit=True)
        flash(f"Permission '{permission_key}' created successfully.", "success")
    except mysql.connector.Error as err:
        if err.errno == 1062:  # Duplicate entry
            flash(f"Permission '{permission_key}' already exists.", "danger")
        else:
            flash(f"Error creating permission: {err.msg}", "danger")
    
    return redirect(url_for('admin_roles'))


# ============================================
# Passenger Dashboard
# ============================================

@app.route('/dashboard/passenger', methods=['GET'])
@login_required(role='passenger')
def dashboard_passenger():
    page = request.args.get('page', 'search')
    passenger_id = session['user_id']
    data = {}

    # =======================================
    # ✈️  1. Search Flights Page
    # =======================================
    if page == 'search':
        data['results'] = []
        data['search'] = {'source': '', 'destination': '', 'date': ''}

        source = request.args.get('source', '')
        destination = request.args.get('destination', '')
        date = request.args.get('date', '')

        if source or destination or date:
            query = "SELECT * FROM upcoming_flights WHERE status = 'Scheduled'"
            params = []

            if source:
                query += " AND (source_code = %s OR source_name LIKE %s)"
                params.extend([source, f'%{source}%'])
            if destination:
                query += " AND (dest_code = %s OR dest_name LIKE %s)"
                params.extend([destination, f'%{destination}%'])
            if date:
                query += " AND DATE(departure_time) = %s"
                params.append(date)

            query += " ORDER BY departure_time"
            data['results'] = db_query(query, tuple(params), fetchall=True) or []
            data['search'] = {'source': source, 'destination': destination, 'date': date}

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
        data['vendors'] = []
        data['search'] = {'terminal': ''}
        terminal = request.args.get('terminal', '')

        if terminal:
            data['vendors'] = db_query(
                "SELECT * FROM vendor WHERE terminal LIKE %s ORDER BY name",
                (f'%{terminal}%',),
                fetchall=True
            )
            data['search'] = {'terminal': terminal}

    # =======================================
    # 👤  4. Profile Page
    # =======================================
    elif page == 'profile':
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
            GROUP BY p.passenger_id
        """, (passenger_id,), fetchone=True) or {}
        data['profile'] = profile

    # =======================================
    # ✅ Render Template Safely
    # =======================================
    return render_template('dashboard_passenger.html', page=page, data=data or {})

@app.route('/passenger/search', methods=['GET'])
@login_required(role='passenger')
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
    
    return render_template('dashboard_passenger.html', page='search', data={'results': results, 'search': request.args})

@app.route('/api/flight/<flight_id>/seats', methods=['GET'])
@login_required(role='passenger')
def get_available_seats(flight_id):
    """API endpoint to get available seats for a flight."""
    # Get aircraft capacity and booked seats
    query = """
        SELECT 
            a.capacity,
            a.aircraft_id,
            GROUP_CONCAT(b.seat_no) as booked_seats
        FROM flight f
        JOIN aircraft a ON f.aircraft_id = a.aircraft_id
        LEFT JOIN booking b ON f.flight_id = b.flight_id AND b.status = 'Confirmed'
        WHERE f.flight_id = %s
        GROUP BY a.aircraft_id
    """
    result = db_query(query, (flight_id,), fetchone=True)
    
    if result:
        # Get all seats for this aircraft from aircraft_seats table
        seats_query = "SELECT seat_no FROM aircraft_seats WHERE aircraft_id = %s ORDER BY seat_no"
        all_seats = db_query(seats_query, (result['aircraft_id'],), fetchall=True) or []
        
        booked_seats_list = result['booked_seats'].split(',') if result['booked_seats'] else []
        
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
    
    return jsonify({'error': 'Flight not found'}), 404

@app.route('/passenger/book', methods=['POST'])
@login_required(role='passenger')
def book_flight():
    flight_id = request.form['flight_id']
    seat_no = request.form['seat_no']
    passenger_id = session['user_id']
    
    # Call the stored procedure
    # Note: db_query handles commit and error flashing
    result = db_query("CALL book_flight(%s, %s, %s, %s)",
                      (passenger_id, flight_id, seat_no, 'Passenger'),
                      commit=True, fetchone=True)
    
    if result:
        flash(f"Booking successful! Your Booking ID is {result['new_booking_id']}.", "success")
        return redirect(url_for('dashboard_passenger', page='bookings'))
    else:
        # Error flash is handled by db_query
        return redirect(url_for('search_flights', **request.args))


@app.route('/passenger/booking/cancel', methods=['POST'])
@login_required(role='passenger')
def cancel_booking():
    booking_id = request.form['booking_id']
    
    # Check if this booking belongs to the logged-in passenger
    booking = db_query("SELECT * FROM booking WHERE booking_id = %s AND passenger_id = %s",
                       (booking_id, session['user_id']), fetchone=True)
    
    if booking:
        if booking['status'] == 'Cancelled':
            flash("This booking is already cancelled.", "info")
        else:
            # The trigger trg_audit_booking_update will handle the refund logic
            db_query("UPDATE booking SET status = 'Cancelled' WHERE booking_id = %s", (booking_id,), commit=True)
            flash("Booking successfully cancelled. A refund will be processed.", "success")
    else:
        flash("Booking not found or you do not have permission to cancel it.", "danger")
        
    return redirect(url_for('dashboard_passenger', page='bookings'))

@app.route('/passenger/amenities/search', methods=['GET'])
@login_required(role='passenger')
def search_amenities():
    terminal = request.args.get('terminal', '')
    
    query = "SELECT * FROM vendor WHERE 1=1"
    params = []
    
    if terminal:
        query += " AND terminal = %s"
        params.append(terminal)
        
    query += " ORDER BY name"
    
    results = db_query(query, tuple(params), fetchall=True)
    
    return render_template('dashboard_passenger.html', page='amenities', data={'results': results, 'search': request.args})

# ============================================
# Generic Employee Dashboard (NEW & EXPANDED)
# ============================================

@app.route('/dashboard/generic')
@login_required()
def dashboard_generic():
    """
    A generic, permission-based dashboard for all non-admin, non-passenger roles.
    The content displayed is determined *directly* by the permissions assigned to the user's role.
    """
    data = {}
    emp_id = session['user_id']
    permissions = get_user_permissions() # e.g., ['view_profile', 'add_aircraft', 'view_payroll']
    
    # Get all pages the user is allowed to see. It's just their permissions list.
    allowed_pages = permissions

    # Determine which page to show
    page = request.args.get('page')
    
    # If no page is requested, or user doesn't have permission for it, pick the first available page as default
    if not page or page not in allowed_pages:
        page = allowed_pages[0] if allowed_pages else 'view_profile' # Default to profile
    
    data['page'] = page # Pass current page to template for highlighting

    # =======================================
    # 👤  1. My Profile Page (Default)
    # =======================================
    if page == 'view_profile':
        data['profile'] = db_query("""
            SELECT e.*, r.role_name 
            FROM employee e
            LEFT JOIN roles r ON e.role_id = r.role_id
            WHERE e.emp_id = %s
        """, (emp_id,), fetchone=True)

    # =======================================
    # ✈️  2. View Assigned Flights
    # =======================================
    elif page == 'view_assigned_flights':
        data['assignments'] = db_query("""
            SELECT f.flight_no, f.airline, r.source_name, r.dest_name, f.departure_time, f.gate, sa.role_on_flight
            FROM staff_assignment sa
            JOIN flight f ON sa.flight_id = f.flight_id
            JOIN route r ON f.route_id = r.route_id
            WHERE sa.emp_id = %s AND f.status = 'Scheduled'
            ORDER BY f.departure_time
        """, (emp_id,), fetchall=True)
    
    # =======================================
    # 🛠️  3. Maintenance (Permission: add_maintenance)
    # =======================================
    elif page == 'add_maintenance': 
        data['aircrafts'] = db_query("SELECT aircraft_id, registration_no, model, status FROM aircraft", fetchall=True)
        data['logs'] = db_query("""
            SELECT m.*, a.registration_no
            FROM maintenance m
            JOIN aircraft a ON m.aircraft_id = a.aircraft_id
            WHERE m.emp_id = %s
            ORDER BY m.maintenance_date DESC
        """, (emp_id,), fetchall=True)

    # =======================================
    # 💰  4. View Payroll (Permission: view_payroll)
    # =======================================
    elif page == 'view_payroll':
        data['paychecks'] = db_query("""
            SELECT * FROM payroll
            WHERE emp_id = %s
            ORDER BY pay_date DESC
        """, (emp_id,), fetchall=True)

    # =======================================
    # 🛫  5. Manage Aircraft (Permission: add_aircraft)
    # =======================================
    elif page == 'add_aircraft': 
        data['aircraft'] = db_query("SELECT * FROM aircraft ORDER BY registration_no", fetchall=True)

    # =======================================
    # 🗺️  6. Manage Routes (Permission: add_route)
    # =======================================
    elif page == 'add_route':
        data['routes'] = db_query("SELECT * FROM route ORDER BY source_code, dest_code", fetchall=True)

    # =======================================
    # 📊  7. View Reports (Permission: view_reports)
    # =======================================
    elif page == 'view_reports':
        # This is the same data logic from the admin 'reports' page
        data['passenger_summary'] = db_query("SELECT * FROM passenger_summary ORDER BY total_spent DESC", fetchall=True)
    
    # =======================================
    #  NEW CONTENT BLOCKS FROM SQL SCRIPTS
    # =======================================

    # ---------------------------------------
    # 🧑‍✈️ 8. Manage Flights (create_flights / manage_flights)
    # ---------------------------------------
    elif page == 'create_flights' or page == 'manage_flights':
        # This block serves both 'create_flights' and 'manage_flights'
        data['flights'] = db_query("SELECT * FROM upcoming_flights ORDER BY departure_time", fetchall=True)
        data['routes'] = db_query("SELECT * FROM route", fetchall=True)
        data['aircraft'] = db_query("SELECT * FROM aircraft WHERE status = 'Operational'", fetchall=True)
    
    # ---------------------------------------
    # 🚦 9. Update Flight Status (update_flights) -- CORRECTED KEY
    # ---------------------------------------
    elif page == 'update_flights':
        # Show scheduled flights that can be updated
        data['flights'] = db_query("SELECT * FROM flight WHERE status = 'Scheduled' ORDER BY departure_time", fetchall=True)

    # ---------------------------------------
    # 💰 10. Manage Payroll (manage_payroll)
    # ---------------------------------------
    elif page == 'manage_payroll':
        # Same as admin view
        data['payrolls'] = db_query("""
            SELECT pr.*, e.name, e.role
            FROM payroll pr
            JOIN employee e ON pr.emp_id = e.emp_id
            ORDER BY pr.pay_date DESC
        """, fetchall=True)
        data['employees'] = db_query("SELECT emp_id, name, salary FROM employee", fetchall=True)

    # ---------------------------------------
    # 👥 11. Manage Employees (manage_employees)
    # ---------------------------------------
    elif page == 'manage_employees':
        # Same as admin view
        data['employees'] = db_query("""
            SELECT e.*, r.role_name, r.role_id 
            FROM employee e
            LEFT JOIN roles r ON e.role_id = r.role_id
            ORDER BY e.name
        """, fetchall=True)
        data['roles'] = db_query("SELECT * FROM roles ORDER BY role_name", fetchall=True)

    # ---------------------------------------
    # 🛡️ 12. Manage Roles (manage_roles / manage_permissions)
    # ---------------------------------------
    elif page == 'manage_roles' or page == 'manage_permissions':
        # Redirect to the main admin roles page
        return redirect(url_for('admin_roles'))

    # ---------------------------------------
    # ⚙️ 13. Update Aircraft Status (update_aircraft_status)
    # ---------------------------------------
    elif page == 'update_aircraft_status':
        # Show all aircraft to update their status
        data['aircraft'] = db_query("SELECT * FROM aircraft ORDER BY registration_no", fetchall=True)

    # ---------------------------------------
    # 📋 14. View Audit Log (view_audit)
    # ---------------------------------------
    elif page == 'view_audit':
        # Same as admin view
        data['logs'] = db_query("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100", fetchall=True)


    return render_template('dashboard_generic.html', data=data)

# ============================================
# Employee Actions (Protected by Permissions)
# =Example of new actions for new permissions
# ============================================

@app.route('/employee/flight/update_status', methods=['POST'])
@login_required()
@requires_permission('update_flights') # CORRECTED KEY
def update_flight_status_action(): # Renamed function to avoid conflict
    form = request.form
    db_query("UPDATE flight SET status = %s, gate = %s, delay_minutes = %s WHERE flight_id = %s",
             (form['status'], form.get('gate'), form.get('delay_minutes', 0), form['flight_id']), commit=True)
    flash("Flight status updated.", "success")
    return redirect(url_for('dashboard_generic', page='update_flights')) # CORRECTED KEY

@app.route('/employee/aircraft/update_status', methods=['POST'])
@login_required()
@requires_permission('update_aircraft_status')
def update_aircraft_status():
    form = request.form
    db_query("UPDATE aircraft SET status = %s WHERE aircraft_id = %s",
             (form['status'], form['aircraft_id']), commit=True)
    flash("Aircraft status updated.", "success")
    return redirect(url_for('dashboard_generic', page='update_aircraft_status'))

# (Admin actions like add_employee, add_payroll are already protected)

# ============================================
# Existing Employee Actions (FIXED REDIRECTS)
# ============================================

@app.route('/employee/maintenance/add', methods=['POST'])
@login_required()
@requires_permission('add_maintenance')
def add_maintenance_log():
    form = request.form
    emp_id = session['user_id']
    
    # Log the maintenance
    m_id = db_query("INSERT INTO maintenance (aircraft_id, emp_id, notes, maintenance_date) VALUES (%s, %s, %s, %s)",
             (form['aircraft_id'], emp_id, form['notes'], form['maintenance_date']), commit=True)
    
    # Update aircraft status and last maintenance date
    db_query("UPDATE aircraft SET status = %s, last_maintenance = %s WHERE aircraft_id = %s",
             (form['new_status'], form['maintenance_date'], form['aircraft_id']), commit=True)
    
    flash("Maintenance log added and aircraft status updated.", "success")
    return redirect(url_for('dashboard_generic', page='add_maintenance'))

@app.route('/groundstaff/aircraft/add', methods=['POST'])
@login_required()
@requires_permission('add_aircraft')
def add_aircraft_route():
    """Add new aircraft."""
    form = request.form
    try:
        db_query("INSERT INTO aircraft (registration_no, model, capacity, status) VALUES (%s, %s, %s, %s)",
                (form['registration_no'], form['model'], form['capacity'], form.get('status', 'Operational')), commit=True)
        flash("Aircraft added successfully!", "success")
    except mysql.connector.Error as err:
        if err.errno == 1062:
            flash("Aircraft with this registration number already exists.", "danger")
        else:
            flash(f"Error: {err.msg}", "danger")
    
    # FIX: Redirect to generic dashboard
    return redirect(url_for('dashboard_generic', page='add_aircraft'))

@app.route('/groundstaff/route/add', methods=['POST'])
@login_required()
@requires_permission('add_route')
def add_route_groundstaff():
    """Add new route."""
    form = request.form
    try:
        distance = db_query("SELECT calc_distance(%s, %s) AS dist", 
                           (form['source_code'], form['dest_code']), fetchone=True)
        distance_km = distance['dist'] if distance else 0
        
        db_query("INSERT INTO route (source_code, source_name, dest_code, dest_name, distance_km) VALUES (%s, %s, %s, %s, %s)",
                (form['source_code'], form['source_name'], form['dest_code'], form['dest_name'], distance_km), commit=True)
        flash("Route added successfully!", "success")
    except mysql.connector.Error as err:
        if err.errno == 1062:
            flash("This route already exists.", "danger")
        else:
            flash(f"Error: {err.msg}", "danger")
    
    # FIX: Redirect to generic dashboard
    return redirect(url_for('dashboard_generic', page='add_route'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)

