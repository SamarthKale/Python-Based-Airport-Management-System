# 🛫 AirManager V2  
### ✈️ A Role-Based Airline Management System (Flask + MySQL)

A **production-ready airline management system** built using **Flask**, **MySQL**, and **Jinja2**, featuring complete **Role-Based Access Control (RBAC)**, **modular dashboards**, and a **fully normalized relational database**.  

---

## 🌟 Highlights

### 🧩 Robust Database Design
- **15+ relational tables** with normalization up to 3NF  
- **Triggers, Views, Stored Procedures, and Functions** integrated for automation  
- **Audit Logging** for every critical update  
- **Events** for scheduled auto-updates (e.g., expired flight cancellations)

### 🔐 Secure Role-Based Access Control (RBAC)
- **6 predefined roles**: `Admin`, `HR`, `Ground Staff`, `ATC`, `Engineer`, `Passenger`
- **Granular permissions**: 14+ unique keys for system-wide actions  
- **Dynamic role-permission assignment** via the Admin panel  
- **Route-level permission checks** for maximum security  

### 🖥️ Dashboards for Every User Type
| Role | Key Features |
|------|---------------|
| **Admin** | Manage employees, flights, payroll, audit logs, roles & permissions |
| **HR** | Manage employee records and payroll |
| **Ground Staff** | Add aircraft and routes |
| **ATC** | Monitor & update flight statuses |
| **Engineer** | Log maintenance and update aircraft status |
| **Passenger** | Search flights, book/cancel tickets, view bookings |

---

## ⚙️ Core Functionalities

✅ **Flight Management** – Schedule, track, and update flights  
✅ **Booking & Payment System** – Real-time booking with automated payments  
✅ **Loyalty Program** – Points-based passenger rewards  
✅ **Payroll Module** – Salary calculation with bonuses/deductions  
✅ **Maintenance Tracker** – Logs for aircraft maintenance  
✅ **Comprehensive Audit Trail** – Auto-logged DB changes  

---

## 🗄️ Database Components

### 🧮 Functions
```sql
flight_duration(dep DATETIME, arr DATETIME); -- Returns formatted duration
calc_distance(src_code, dest_code); -- Calculates route distance

## Project Structure
```
| Role          | Username               | Password     | Access             |
| ------------- | ---------------------- | ------------ | ------------------ |
| **Admin**     | `admin`                | `admin123`   | Full control       |
| **Employee**  | `john.doe@airline.com` | `2018-06-01` | Role-based         |
| **Passenger** | `P12345678`            | —            | Limited (bookings) |


| Role             | Key Permissions                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------- |
| **Admin**        | manage_roles, manage_permissions, manage_employees, manage_flights, manage_payroll, view_audit |
| **HR**           | manage_employees, manage_payroll                                                               |
| **Ground Staff** | add_aircraft, add_route                                                                        |
| **ATC**          | update_flight_status                                                                           |
| **Engineer**     | add_maintenance, update_aircraft_status                                                        |
| **Passenger**    | book_flight, cancel_booking, edit_profile                                                      |


🚀 Quick Setup Guide
🧩 Prerequisites

Python ≥ 3.8
MySQL ≥ 5.7

MySQL credentials (default: root / Swami@2006) ⚠️ Change before deployment!

🧰 Installation Steps
cd C:\S.Y\DBL\Airmanager
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

🗃️ Database Configuration

Edit db_config.py:
```
config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Swami@2006',  # Change this
    'database': 'airline_pro_db_v2'
}
```
🏗️ Initialize the Database
```
python init_sql_v2.py
python rbac_seed_v2.py
```
▶️ Run the Application
```
python app.py
```

Then open → http://localhost:5000

🔒 Security & Best Practices

Session-based authentication

RBAC enforced at route-level

SQL injection-safe parameterized queries

Full operation audit trail

Change SECRET_KEY and DB credentials for production

Add password hashing (bcrypt) for real users

📊 Reports & Analytics

Flight utilization reports

Route performance summaries

Payroll and revenue insights

Audit logs accessible via admin dashboard

🧩 Extending the System
Adding a New Permission
INSERT INTO permissions (permission_key, description) VALUES ('new_key', 'New Action');


Then:

Map it in 
```
rbac_seed_v2.py
```
Add @requires_permission('new_key') decorator in Flask routes
Adding a New Role
Go to /admin/roles
Create a role → Assign permissions
Update relevant employee’s role_id
