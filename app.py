import mysql.connector
from mysql.connector import pooling
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
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
    print("✅ Database connection pool created successfully.")
except mysql.connector.Error as err:
    print(f"❌ Error creating connection pool: {err}")
    exit(1)

# Helper function to get a connection from the pool
def get_db_connection():
    try:
        if 'db' not in g:
            g.db = pool.get_connection()
        return g.db
    except mysql.connector.Error as err:
        print(f"❌ Error getting connection from pool: {err}")
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
            # Log to audit (if not handled by trigger)
            # This is a good place for manual audit logs if triggers aren't used
        
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
# Authentication & Decorators
# ============================================

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
                return redirect(url_for(f'dashboard_{user_role}'))
                
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
        return redirect(url_for(f'dashboard_{role}'))
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
        
        employee = db_query("SELECT * FROM employee WHERE email = %s AND date_of_joining = %s", (email, doj), fetchone=True)
        
        if employee:
            session['user_id'] = employee['emp_id']
            session['name'] = employee['name']
            session['role'] = 'employee'
            flash(f"Welcome, {employee['name']}!", "success")
            return redirect(url_for('dashboard_employee'))
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
        data['employees'] = db_query("SELECT * FROM employee ORDER BY name", fetchall=True)

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
def add_employee():
    form = request.form
    db_query("INSERT INTO employee (name, role, email, date_of_joining, salary) VALUES (%s, %s, %s, %s, %s)",
             (form['name'], form['role'], form['email'], form['date_of_joining'], form['salary']), commit=True)
    flash("Employee added successfully.", "success")
    return redirect(url_for('dashboard_admin', page='employees'))

@app.route('/admin/employee/edit', methods=['POST'])
@login_required(role='admin')
def edit_employee():
    form = request.form
    db_query("UPDATE employee SET name=%s, role=%s, email=%s, date_of_joining=%s, salary=%s WHERE emp_id=%s",
             (form['name'], form['role'], form['email'], form['date_of_joining'], form['salary'], form['emp_id']), commit=True)
    flash("Employee updated successfully.", "success")
    return redirect(url_for('dashboard_admin', page='employees'))

# Flights
@app.route('/admin/flight/add', methods=['POST'])
@login_required(role='admin')
def add_flight():
    form = request.form
    db_query("INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare) VALUES (%s, %s, %s, %s, %s, %s, %s)",
             (form['flight_no'], form['airline'], form['route_id'], form['aircraft_id'], form['departure_time'], form['arrival_time'], form['base_fare']), commit=True)
    flash("Flight added successfully.", "success")
    return redirect(url_for('dashboard_admin', page='flights'))

# Vendors
@app.route('/admin/vendor/add', methods=['POST'])
@login_required(role='admin')
def add_vendor():
    form = request.form
    db_query("INSERT INTO vendor (name, amenity_type, terminal, location_desc) VALUES (%s, %s, %s, %s)",
             (form['name'], form['amenity_type'], form['terminal'], form['location_desc']), commit=True)
    flash("Vendor added successfully.", "success")
    return redirect(url_for('dashboard_admin', page='vendors'))

# Payroll
@app.route('/admin/payroll/add', methods=['POST'])
@login_required(role='admin')
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
def admin_cancel_flight():
    flight_id = request.form['flight_id']
    db_query("UPDATE flight SET status='Cancelled' WHERE flight_id=%s", (flight_id,), commit=True)
    # Note: The trigger trg_audit_booking_update will handle cancelling associated bookings if needed,
    # or this could be done via a stored procedure.
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
        data['flights'] = []
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
            data['flights'] = db_query(query, tuple(params), fetchall=True)
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
# Employee Dashboard
# ============================================

@app.route('/dashboard/employee')
@login_required(role='employee')
def dashboard_employee():
    page = request.args.get('page', 'flights')
    data = {}
    emp_id = session['user_id']
    
    if page == 'flights':
        data['assignments'] = db_query("""
            SELECT f.flight_no, f.airline, r.source_name, r.dest_name, f.departure_time, f.gate, sa.role_on_flight
            FROM staff_assignment sa
            JOIN flight f ON sa.flight_id = f.flight_id
            JOIN route r ON f.route_id = r.route_id
            WHERE sa.emp_id = %s AND f.status = 'Scheduled'
            ORDER BY f.departure_time
        """, (emp_id,), fetchall=True)
    
    elif page == 'maintenance':
        # Only show if employee is in Maintenance
        emp = db_query("SELECT role FROM employee WHERE emp_id = %s", (emp_id,), fetchone=True)
        if 'Maintenance' in emp.get('role', ''):
            data['is_maintenance'] = True
            data['aircrafts'] = db_query("SELECT aircraft_id, registration_no, model, status FROM aircraft", fetchall=True)
            data['logs'] = db_query("""
                SELECT m.*, a.registration_no
                FROM maintenance m
                JOIN aircraft a ON m.aircraft_id = a.aircraft_id
                WHERE m.emp_id = %s
                ORDER BY m.maintenance_date DESC
            """, (emp_id,), fetchall=True)
        else:
            data['is_maintenance'] = False

    elif page == 'payroll':
        data['paychecks'] = db_query("""
            SELECT * FROM payroll
            WHERE emp_id = %s
            ORDER BY pay_date DESC
        """, (emp_id,), fetchall=True)

    return render_template('dashboard_employee.html', page=page, data=data)

@app.route('/employee/maintenance/add', methods=['POST'])
@login_required(role='employee')
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
    return redirect(url_for('dashboard_employee', page='maintenance'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
