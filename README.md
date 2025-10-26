# ✈️ Airline Management System (DBMS Project)

A Flask + MySQL based **Airline Management System** designed as a **DBMS project**.
This version **does not include RBAC (Role-Based Access Control)** — all administrative actions are accessible directly from the Admin interface.

---

## 🧱 Project Overview

This project manages:

* ✅ Passenger registration and bookings
* ✅ Flight management and scheduling
* ✅ Aircraft and route data
* ✅ Payroll and maintenance logs
* ✅ Analytics via SQL views
* ✅ Audit logs and triggers for updates

Built using:

* **Flask (Python)** — Web framework
* **MySQL** — Database backend
* **Bootstrap 5** — Frontend styling

---

## 🗂️ Folder Structure

```
Airmanager/
│
├── app.py                  # Main Flask application
├── db_config.py            # MySQL connection config
├── init_sql_v2.py          # Creates database schema + sample data
├── templates/
│   ├── index.html
│   ├── dashboard_admin.html
│   ├── dashboard_generic.html
│   ├── dashboard_passenger.html
│   └── partials/            # Page sections (flights, payroll, etc.)
│
├── static/
│   ├── css/
│   └── js/
│
├── venv/                   # Python virtual environment
└── README.md               # You are here
```

---

## ⚙️ Setup Instructions

### 1. Install Requirements

```bash
pip install flask mysql-connector-python
```

### 2. Configure Database

Edit `db_config.py` with your MySQL credentials:

```python
config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',
    'database': 'airline_project_db',
    'autocommit': False
}
```

### 3. Initialize Database

Run:

```bash
python init_sql_v2.py
```

This creates:

* Tables, triggers, views, and procedures
* Sample data for passengers, flights, etc.

### 4. Start Flask App

```bash
python app.py
```

Visit:

> 🔗 [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 👥 Default Logins

| Role                    | Credentials                          | Dashboard              |
| ----------------------- | ------------------------------------ | ---------------------- |
| **Admin**               | `admin / admin123`                   | `/dashboard/admin`     |
| **Employee (Engineer)** | `mike.ross@airline.com / 2017-10-20` | `/dashboard/generic`   |
| **Passenger**           | `P12345678 (Passport)`               | `/dashboard/passenger` |

---

## 💾 Database Highlights

* **Triggers** automatically adjust flight fares and audit updates.
* **Stored Procedures** manage bookings and loyalty points.
* **Views:** `upcoming_flights`, `passenger_summary`, `route_performance`, etc.
* **Events:** Auto-cancel and archive old flights.

---

## 🚀 Future Upgrades (RBAC Version)

A newer branch introduces:

* 🔐 **Role-Based Access Control** (Admin, HR, Engineer, etc.)
* 🧩 **Permission-based actions**
* 🧱 **Web UI for managing roles & permissions**

That branch is named:

```bash
FinalSubmit
```

---

## 🧭 Switch to RBAC-Enabled Version

When you’re ready to use RBAC, switch to the new branch:

```bash
git checkout FinalSubmit
```

You’ll see:

* Full RBAC integrated into Flask routes
* Permission-based dashboards
* Role/permission management UI (`dashboard_admin_roles.html`)

---

## 🏁 Credits

**Author:** Samarth Kale
**Database:** MySQL 8+
**Framework:** Flask 3.0
**License:** Open Academic / Educational Use

---

## 🪶 Explanation of Next Step

Now that you have this `README.md` for the **non-RBAC version**, here’s what happens next:

### 🔀 When you switch to the new branch (`FinalSubmit`)

You can **replace this README** automatically or append a message at the top, such as:

```markdown
> ⚠️ You are viewing the **RBAC-enabled branch (FinalSubmit)**  
> This version adds full Role-Based Access Control (Admin, HR, Engineer, etc.)  
> The old non-RBAC info is preserved in the `FGemini` branch README.
```

That way, developers or teachers who open the project in the RBAC branch will instantly know this version adds advanced access control.
