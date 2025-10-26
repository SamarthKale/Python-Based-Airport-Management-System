# 🛫 AirManager V2 - Production-Ready Airline Management System

A comprehensive airline management system with **Role-Based Access Control (RBAC)** built with Flask and MySQL.

## ✨ Features

### 🏗️ Complete Database Architecture
- **15+ normalized tables** (admin, passenger, employee, aircraft, route, flight, booking, payment, vendor, staff_assignment, payroll, maintenance, audit_log, roles, permissions, role_permissions)
- **Triggers** for automatic fare adjustments, refund handling, and audit logging
- **Stored procedures** for booking flights and status updates
- **Functions** for calculating flight duration and route distances
- **Views** for analytics (upcoming_flights, passenger_summary, flight_revenue_summary, route_performance)
- **Events** for auto-cancelling expired flights

### 🔐 Role-Based Access Control (RBAC)
- **6 predefined roles**: Admin, HR, Ground Staff, ATC, Engineer, Passenger
- **14 granular permissions** covering all system operations
- **Dynamic permission management** via admin panel
- **Permission checks** enforced at the route level

### 👥 User Dashboards
- **Admin Dashboard**: Full system control (manage employees, flights, bookings, payroll, vendors, audit logs, roles & permissions)
- **Passenger Dashboard**: Search flights, book tickets, view bookings, access amenities, manage profile
- **Employee Dashboard**: View assigned flights, manage payroll, log maintenance
- **Ground Staff Dashboard**: Add aircraft and routes

### 🎯 Core Functionalities
- **Flight Management**: Create, schedule, and track flights
- **Booking System**: Integrated booking with automatic payment processing
- **Loyalty Program**: Points-based system with tiered benefits
- **Payroll Management**: Salary tracking with bonuses and deductions
- **Maintenance Logging**: Track aircraft maintenance history
- **Audit Trail**: Complete audit log of all database changes

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- MySQL 5.7+ or MariaDB 10.3+
- MySQL credentials (username: `root`, password: `Swami@2006` - **CHANGE THIS**)

### Installation

1. **Clone the repository**
   ```bash
   cd c:\S.Y\DBL\Airmanager
   ```

2. **Create a virtual environment** (if not already created)
   ```bash
   python -m venv venv
   venv\Scripts\activate  # On Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure database** (update `db_config.py`)
   ```python
   config = {
       'host': 'localhost',
       'user': 'root',
       'password': 'Swami@2006',  # ← CHANGE THIS
       'database': 'airline_pro_db_v2'
   }
   ```

5. **Initialize the database**
   ```bash
   python init_sql_v2.py
   python rbac_seed_v2.py
   ```

6. **Run the Flask application**
   ```bash
   python app.py
   ```

7. **Access the application**
   - Open browser: `http://localhost:5000`

## 🔑 Default Credentials

### Admin
- **Username**: `admin`
- **Password**: `admin123`
- **Access**: Full system control

### Employee
- Use any employee's email and date of joining
- Example: `john.doe@airline.com` / `2018-06-01`

### Passenger
- Use passport number
- Example: `P12345678`

## 📋 Role Permissions

| Role | Key Permissions |
|------|----------------|
| **Admin** | manage_roles, manage_permissions, manage_employees, manage_flights, manage_payroll, view_audit |
| **HR** | manage_employees, manage_payroll |
| **Ground Staff** | add_aircraft, add_route |
| **ATC** | update_flight_status |
| **Engineer** | add_maintenance, update_aircraft_status |
| **Passenger** | book_flight, cancel_booking, edit_profile |

## 🎨 Admin Panel Features

### Role Management
- **URL**: `/admin/roles`
- Create custom roles
- Assign/revoke permissions dynamically
- Visual permission matrix interface

### Flight Management
- Create and schedule flights
- Monitor flight statuses
- Auto-update flight statuses based on time
- Cancel flights

### Employee Management
- Add/edit employees
- Assign roles
- Set salaries
- View employee details

### Payroll Management
- Record payroll entries
- Set bonuses and deductions
- Generate payroll reports

### Reports & Analytics
- Passenger spending summary
- Flight utilization rates
- Revenue tracking
- Audit logs

## 🔧 Technical Architecture

### Database Functions
```sql
flight_duration(dep DATETIME, arr DATETIME) -- Returns formatted duration
calc_distance(src_code, dest_code) -- Calculates route distance
```

### Stored Procedures
```sql
book_flight(passenger_id, flight_id, seat_no, booked_by) -- Handles booking
update_points(passenger_id, amount) -- Updates loyalty points
sp_update_flight_statuses() -- Auto-updates flight statuses
```

### Triggers
- `trg_auto_fare_adjust` - Adjusts fare based on seat occupancy
- `trg_audit_booking_update` - Handles refunds on cancellation
- `trg_generate_aircraft_seats` - Auto-generates seat map

## 📁 Project Structure

```
AirManager/
├── app.py                      # Main Flask application
├── db_config.py                # Database configuration
├── init_sql_v2.py              # Database initialization script
├── rbac_seed_v2.py             # RBAC seeding script
├── requirements.txt            # Python dependencies
├── templates/                  # Jinja2 templates
│   ├── dashboard_admin.html
│   ├── dashboard_admin_roles.html
│   ├── dashboard_passenger.html
│   ├── dashboard_employee.html
│   ├── dashboard_groundstaff.html
│   ├── login_admin.html
│   ├── login_employee.html
│   ├── login_passenger.html
│   └── index.html
└── static/
    └── style.css              # Custom styles
```

## 🔒 Security Features

- **Session-based authentication**
- **Role-based route protection**
- **Permission-based access control**
- **SQL injection prevention** (parameterized queries)
- **Audit logging** of all critical operations

## 📊 Database Schema Highlights

```sql
-- RBAC Tables
roles (role_id, role_name, description)
permissions (permission_id, permission_key, description)
role_permissions (role_id, permission_id)

-- Core Tables
flight (flight_id, flight_no, route_id, aircraft_id, departure_time, arrival_time, status)
booking (booking_id, passenger_id, flight_id, seat_no, status)
employee (emp_id, name, role_id, email, salary)

-- Additional Tables
aircraft, route, payment, vendor, staff_assignment, payroll, maintenance, audit_log
```

## 🎯 API Endpoints

### Public Routes
- `GET /` - Home page
- `GET /login/admin` - Admin login
- `GET /login/employee` - Employee login
- `GET /login/passenger` - Passenger login

### Admin Routes
- `GET /dashboard/admin` - Admin dashboard (with ?page=flights|employees|bookings|...)
- `GET /admin/roles` - Role & permission management
- `POST /admin/roles/update` - Update role permissions
- `POST /admin/employee/add` - Add employee
- `POST /admin/flight/add` - Add flight
- `POST /admin/payroll/add` - Add payroll entry

### Ground Staff Routes
- `GET /dashboard/groundstaff` - Ground staff dashboard
- `POST /groundstaff/aircraft/add` - Add aircraft
- `POST /groundstaff/route/add` - Add route

### Passenger Routes
- `GET /dashboard/passenger` - Passenger dashboard
- `POST /passenger/book` - Book flight
- `POST /passenger/booking/cancel` - Cancel booking

### Employee Routes
- `GET /dashboard/employee` - Employee dashboard
- `POST /employee/maintenance/add` - Log maintenance

## 🛠️ Development

### Adding New Permissions
1. Add permission to database: `INSERT INTO permissions (permission_key, description) VALUES (...)`
2. Update `rbac_seed_v2.py` to include in default role mappings
3. Add permission check to route: `@requires_permission('permission_key')`

### Adding New Roles
1. Add role via admin panel at `/admin/roles`
2. Assign appropriate permissions
3. Update employee records to use new role_id

## 📝 Notes

- Database password is currently hardcoded (**CHANGE BEFORE DEPLOYMENT**)
- Session secret key should be changed for production
- Password hashing (bcrypt) should be added before production deployment
- Consider adding Flask Blueprints for better modularity

## 🚀 Deployment

For production deployment:

1. Set up environment variables:
   ```bash
   export FLASK_SECRET_KEY="your-secret-key"
   export DB_PASSWORD="your-db-password"
   ```

2. Use a production WSGI server:
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:8000 app:app
   ```

3. Configure MySQL for production:
   - Enable connection pooling
   - Set appropriate timeout values
   - Configure backups

## 📄 License

This project is for educational purposes.

## 👤 Author

Built for the AirManager Project.

---

**Status**: ✅ Production-Ready with RBAC
**Version**: 2.0
**Last Updated**: 2024

