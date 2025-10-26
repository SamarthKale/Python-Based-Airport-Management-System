import mysql.connector
from mysql.connector import errorcode, InterfaceError
import datetime
import sys

# ----------------------------------------
# Database connection configuration
# IMPORTANT: set your MySQL credentials below
# ----------------------------------------
config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Swami@2006',  # <<< REPLACE with your MySQL password
    'autocommit': True
}

DB_NAME = "airline_pro_db_v2"

# ----------------------------------------
# Connect to MySQL server
# ----------------------------------------
try:
    print("Connecting to MySQL server...")
    cnx = mysql.connector.connect(**config)
    cursor = cnx.cursor(buffered=True)
    print("✅ Connected to MySQL successfully.")
except mysql.connector.Error as err:
    if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        print("❌ Access denied. Check your username/password in the 'config' dictionary.")
    else:
        print(f"❌ Error connecting: {err}")
    sys.exit(1)

# ----------------------------------------
# Helper to execute multi-statement SQL blocks
# (Handles DELIMITER // blocks used for procedures/triggers)
# ----------------------------------------
def exec_sql_block(sql_block, section_name="SQL Block"):
    print(f"Executing {section_name}...")
    try:
        if 'DELIMITER //' in sql_block:
            parts = sql_block.split('DELIMITER //')
            # Exec statements before first DELIMITER //
            before = parts[0].split(';')
            for s in before:
                if s.strip():
                    cursor.execute(s)
            # Handle the procedure/trigger blocks and statements after DELIMITER ;
            for part in parts[1:]:
                if '\nDELIMITER ;' in part:
                    proc_chunk, after_chunk = part.split('\nDELIMITER ;', 1)
                    procedures = proc_chunk.split('//')
                    for proc in procedures:
                        if proc.strip():
                            cursor.execute(proc)
                    for s in after_chunk.split(';'):
                        if s.strip():
                            cursor.execute(s)
                else:
                    if part.strip():
                        cursor.execute(part)
        else:
            statements = sql_block.split(';')
            for statement in statements:
                if statement.strip():
                    cursor.execute(statement)
                    if statement.strip().upper().startswith('CALL'):
                        try:
                            for rs in cursor.stored_results():
                                rs.fetchall()
                        except InterfaceError as err:
                            if "No result set" in str(err) or getattr(err, 'errno', None) == 2014:
                                pass
        print(f"✅ Executed {section_name} successfully.")
    except mysql.connector.Error as err:
        print(f"❌ Error in {section_name}: {err}")
        # Uncomment next line to debug SQL
        # print("Failed SQL block:", sql_block)
        sys.exit(1)


# ----------------------------------------
# CREATE DATABASE
# ----------------------------------------
try:
    cursor.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
    cursor.execute(f"CREATE DATABASE {DB_NAME}")
    print(f"✅ Database '{DB_NAME}' created successfully.")
except mysql.connector.Error as err:
    print(f"❌ Failed to create database: {err}")
    sys.exit(1)

cursor.execute(f"USE {DB_NAME}")

# ----------------------------------------
# 1. CORE TABLES (base schema copied + enhancements)
# ----------------------------------------
tables_sql = """
SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS archived_flights, passenger_loyalty_summary, flight_revenue_summary, route_performance, maintenance_history, aircraft_seats, role_permissions, permissions, roles, loyalty_tiers;
DROP TABLE IF EXISTS admin, passenger, employee, aircraft, route, flight, booking, payment, vendor, staff_assignment, payroll, maintenance, audit_log;
SET FOREIGN_KEY_CHECKS=1;

CREATE TABLE admin (
  admin_id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) UNIQUE NOT NULL,
  password VARCHAR(255) NOT NULL,
  full_name VARCHAR(100),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE passenger (
  passenger_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(150) UNIQUE,
  phone VARCHAR(20),
  passport_no VARCHAR(50) UNIQUE NOT NULL,
  dob DATE,
  total_points INT DEFAULT 0,
  password_hash VARCHAR(255),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE employee (
  emp_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  role VARCHAR(50),
  role_id INT,
  email VARCHAR(150) UNIQUE NOT NULL,
  date_of_joining DATE NOT NULL,
  salary DECIMAL(12,2),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE SET NULL
);

CREATE TABLE aircraft (
  aircraft_id INT AUTO_INCREMENT PRIMARY KEY,
  registration_no VARCHAR(50) UNIQUE,
  model VARCHAR(100),
  capacity INT,
  last_maintenance DATETIME,
  status VARCHAR(30) DEFAULT 'Operational',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE route (
  route_id INT AUTO_INCREMENT PRIMARY KEY,
  source_code VARCHAR(10),
  source_name VARCHAR(100),
  dest_code VARCHAR(10),
  dest_name VARCHAR(100),
  distance_km INT
);

CREATE TABLE flight (
  flight_id INT AUTO_INCREMENT PRIMARY KEY,
  flight_no VARCHAR(20) UNIQUE NOT NULL,
  airline VARCHAR(100),
  route_id INT,
  aircraft_id INT,
  departure_time DATETIME,
  arrival_time DATETIME,
  base_fare DECIMAL(10,2),
  current_fare DECIMAL(10,2),
  status VARCHAR(30) DEFAULT 'Scheduled',
  gate VARCHAR(30),
  delay_minutes INT DEFAULT 0,
  reason_for_delay VARCHAR(255),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (route_id) REFERENCES route(route_id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (aircraft_id) REFERENCES aircraft(aircraft_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE booking (
  booking_id INT AUTO_INCREMENT PRIMARY KEY,
  passenger_id INT,
  flight_id INT,
  booking_date DATETIME DEFAULT CURRENT_TIMESTAMP,
  seat_no VARCHAR(5),
  status VARCHAR(20) DEFAULT 'Confirmed',
  booked_by VARCHAR(50) DEFAULT 'Passenger',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (passenger_id) REFERENCES passenger(passenger_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (flight_id) REFERENCES flight(flight_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE payment (
  payment_id INT AUTO_INCREMENT PRIMARY KEY,
  booking_id INT,
  amount DECIMAL(10,2),
  method VARCHAR(50) DEFAULT 'Internal',
  payment_date DATETIME DEFAULT CURRENT_TIMESTAMP,
  refunded BOOLEAN DEFAULT FALSE,
  refund_amount DECIMAL(10,2) DEFAULT 0,
  FOREIGN KEY (booking_id) REFERENCES booking(booking_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE vendor (
  vendor_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150),
  amenity_type VARCHAR(100),
  terminal VARCHAR(50),
  location_desc VARCHAR(200),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE staff_assignment (
  assignment_id INT AUTO_INCREMENT PRIMARY KEY,
  emp_id INT,
  flight_id INT,
  role_on_flight VARCHAR(50),
  assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (emp_id) REFERENCES employee(emp_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (flight_id) REFERENCES flight(flight_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE payroll (
  payroll_id INT AUTO_INCREMENT PRIMARY KEY,
  emp_id INT,
  base_salary DECIMAL(12,2),
  bonus DECIMAL(12,2) DEFAULT 0,
  deductions DECIMAL(12,2) DEFAULT 0,
  net_pay DECIMAL(12,2) GENERATED ALWAYS AS (base_salary + bonus - deductions) STORED,
  pay_date DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (emp_id) REFERENCES employee(emp_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE maintenance (
  maintenance_id INT AUTO_INCREMENT PRIMARY KEY,
  aircraft_id INT,
  emp_id INT,
  notes TEXT,
  maintenance_date DATETIME,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (aircraft_id) REFERENCES aircraft(aircraft_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (emp_id) REFERENCES employee(emp_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE audit_log (
  log_id INT AUTO_INCREMENT PRIMARY KEY,
  table_name VARCHAR(100),
  record_id INT,
  action_type VARCHAR(20),
  description TEXT,
  changed_by VARCHAR(100),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- RBAC core tables: roles, permissions, role_permissions
CREATE TABLE roles (
  role_id INT AUTO_INCREMENT PRIMARY KEY,
  role_name VARCHAR(50) UNIQUE NOT NULL,
  description TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE permissions (
  permission_id INT AUTO_INCREMENT PRIMARY KEY,
  permission_key VARCHAR(100) UNIQUE NOT NULL,
  description VARCHAR(255)
);

CREATE TABLE role_permissions (
  role_id INT,
  permission_id INT,
  PRIMARY KEY (role_id, permission_id),
  FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE,
  FOREIGN KEY (permission_id) REFERENCES permissions(permission_id) ON DELETE CASCADE
);

-- Aircraft seats table for seat validation & map
CREATE TABLE aircraft_seats (
  seat_id INT AUTO_INCREMENT PRIMARY KEY,
  aircraft_id INT,
  seat_no VARCHAR(5),
  is_window BOOLEAN DEFAULT FALSE,
  is_aisle BOOLEAN DEFAULT FALSE,
  FOREIGN KEY (aircraft_id) REFERENCES aircraft(aircraft_id) ON DELETE CASCADE
);

-- Loyalty tiers
CREATE TABLE loyalty_tiers (
  tier_name VARCHAR(50) PRIMARY KEY,
  min_points INT,
  max_points INT,
  discount_percent INT
);

-- Archived flights (lite copy)
CREATE TABLE archived_flights LIKE flight;
"""
exec_sql_block(tables_sql, "CORE TABLES AND RBAC")

# ----------------------------------------
# 2. FUNCTIONS
# ----------------------------------------
functions_sql = """
DELIMITER //

CREATE FUNCTION flight_duration(dep DATETIME, arr DATETIME)
RETURNS VARCHAR(20)
DETERMINISTIC
BEGIN
  DECLARE mins INT;
  IF dep IS NULL OR arr IS NULL OR arr < dep THEN
    RETURN 'N/A';
  END IF;
  SET mins = TIMESTAMPDIFF(MINUTE, dep, arr);
  RETURN CONCAT(FLOOR(mins/60), 'h ', LPAD(MOD(mins,60),2,'0'),'m');
END //

CREATE FUNCTION calc_distance(src_code VARCHAR(10), dest_code VARCHAR(10))
RETURNS INT
DETERMINISTIC
BEGIN
  RETURN (ABS(CAST(CRC32(CONCAT(LOWER(src_code), '|', LOWER(dest_code))) AS SIGNED)) % 4000) + 200;
END //

DELIMITER ;
"""
exec_sql_block(functions_sql, "FUNCTIONS")

# ----------------------------------------
# 3. STORED PROCEDURES
# ----------------------------------------
procedures_sql = """
DELIMITER //

CREATE PROCEDURE update_points(IN p_passenger_id INT, IN p_amount DECIMAL(10,2))
BEGIN
  UPDATE passenger
  SET total_points = total_points + FLOOR(p_amount / 100)
  WHERE passenger_id = p_passenger_id;
END //

CREATE PROCEDURE book_flight(
    IN p_passenger_id INT,
    IN p_flight_id INT,
    IN p_seat_no VARCHAR(8),
    IN p_booked_by VARCHAR(50)
)
BEGIN
    DECLARE v_booking_id INT;
    DECLARE v_fare DECIMAL(10,2);
    DECLARE v_flight_status VARCHAR(30);
    DECLARE v_capacity INT;
    DECLARE v_booked_count INT;
    DECLARE v_exists INT;
    
    SELECT f.current_fare, f.status, ac.capacity
    INTO v_fare, v_flight_status, v_capacity
    FROM flight f
    JOIN aircraft ac ON f.aircraft_id = ac.aircraft_id
    WHERE f.flight_id = p_flight_id;
    
    SELECT COUNT(*) INTO v_booked_count
    FROM booking
    WHERE flight_id = p_flight_id AND status = 'Confirmed';
    
    SELECT COUNT(*) INTO v_exists
    FROM booking
    WHERE flight_id = p_flight_id AND seat_no = p_seat_no AND status = 'Confirmed';
    
    IF v_flight_status != 'Scheduled' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Flight is not available for booking.';
    ELSEIF v_booked_count >= v_capacity THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Flight is full.';
    ELSEIF v_exists > 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Seat already booked.';
    ELSE
        INSERT INTO booking (passenger_id, flight_id, seat_no, status, booked_by)
        VALUES (p_passenger_id, p_flight_id, p_seat_no, 'Confirmed', p_booked_by);
        
        SET v_booking_id = LAST_INSERT_ID();
        
        INSERT INTO payment (booking_id, amount, method)
        VALUES (v_booking_id, v_fare, 'Internal');
        
        CALL update_points(p_passenger_id, v_fare);
        
        INSERT INTO audit_log (table_name, record_id, action_type, description, changed_by)
        VALUES ('booking', v_booking_id, 'CREATE', 'New booking via procedure', p_booked_by);
        
        SELECT v_booking_id AS new_booking_id, 'Booking successful' AS message;
    END IF;
END //

CREATE PROCEDURE sp_update_flight_statuses()
BEGIN
    UPDATE flight
    SET status = 'Completed'
    WHERE arrival_time < NOW() AND status = 'Scheduled';
    
    UPDATE flight
    SET status = 'Cancelled'
    WHERE departure_time < NOW() AND status = 'Scheduled';
END //

DELIMITER ;
"""
exec_sql_block(procedures_sql, "STORED PROCEDURES")

# ----------------------------------------
# 4. VIEWS
# ----------------------------------------
views_sql = """
CREATE OR REPLACE VIEW upcoming_flights AS
SELECT 
    f.flight_id, 
    f.flight_no, 
    f.airline, 
    r.source_code, 
    r.source_name,
    r.dest_code, 
    r.dest_name,
    f.departure_time, 
    f.arrival_time, 
    f.current_fare, 
    f.status, 
    f.gate,
    ac.model AS aircraft_model,
    ac.capacity,
    (SELECT COUNT(*) FROM booking b WHERE b.flight_id = f.flight_id AND b.status = 'Confirmed') AS seats_booked
FROM flight f
JOIN route r ON f.route_id = r.route_id
JOIN aircraft ac ON f.aircraft_id = ac.aircraft_id
WHERE f.departure_time > NOW() AND f.status = 'Scheduled';

CREATE OR REPLACE VIEW passenger_summary AS
SELECT 
    p.passenger_id, 
    p.name, 
    p.email,
    p.passport_no,
    p.total_points,
    COUNT(DISTINCT b.booking_id) AS total_bookings, 
    COALESCE(SUM(CASE WHEN b.status = 'Confirmed' THEN pay.amount ELSE 0 END), 0) AS total_spent
FROM passenger p
LEFT JOIN booking b ON p.passenger_id = b.passenger_id
LEFT JOIN payment pay ON b.booking_id = pay.booking_id
GROUP BY p.passenger_id, p.name, p.email, p.passport_no, p.total_points;

CREATE OR REPLACE VIEW flight_revenue_summary AS
SELECT 
  f.flight_id,
  f.flight_no,
  f.airline,
  COUNT(b.booking_id) AS total_bookings,
  COALESCE(SUM(p.amount), 0) AS total_revenue,
  AVG(p.amount) AS avg_ticket_price,
  f.departure_time,
  f.arrival_time
FROM flight f
LEFT JOIN booking b ON f.flight_id = b.flight_id
LEFT JOIN payment p ON b.booking_id = p.booking_id
GROUP BY f.flight_id;

CREATE OR REPLACE VIEW route_performance AS
SELECT 
  r.route_id,
  CONCAT(r.source_name, ' → ', r.dest_name) AS route,
  COUNT(DISTINCT f.flight_id) AS total_flights,
  COUNT(DISTINCT b.booking_id) AS total_bookings,
  COALESCE(SUM(p.amount), 0) AS total_revenue
FROM route r
LEFT JOIN flight f ON r.route_id = f.route_id
LEFT JOIN booking b ON f.flight_id = b.flight_id
LEFT JOIN payment p ON b.booking_id = p.booking_id
GROUP BY r.route_id;

CREATE OR REPLACE VIEW maintenance_history AS
SELECT 
  a.aircraft_id,
  a.registration_no,
  a.model,
  COUNT(m.maintenance_id) AS total_maintenance,
  MAX(m.maintenance_date) AS last_service,
  GROUP_CONCAT(DISTINCT e.name SEPARATOR ', ') AS engineers
FROM aircraft a
LEFT JOIN maintenance m ON a.aircraft_id = m.aircraft_id
LEFT JOIN employee e ON m.emp_id = e.emp_id
GROUP BY a.aircraft_id;

CREATE OR REPLACE VIEW passenger_loyalty_summary AS
SELECT 
  p.passenger_id,
  p.name,
  p.email,
  p.total_points,
  COALESCE(t.tier_name, 'None') AS tier_name,
  COALESCE(t.discount_percent, 0) AS discount_percent
FROM passenger p
LEFT JOIN loyalty_tiers t ON p.total_points BETWEEN t.min_points AND t.max_points;
"""
exec_sql_block(views_sql, "VIEWS")

# ----------------------------------------
# 5. TRIGGERS
# ----------------------------------------
triggers_sql = """
DELIMITER //

CREATE TRIGGER trg_audit_passenger_insert
AFTER INSERT ON passenger
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (table_name, record_id, action_type, description, changed_by)
    VALUES ('passenger', NEW.passenger_id, 'CREATE', CONCAT('New passenger: ', NEW.name), 'System');
END //

CREATE TRIGGER trg_audit_passenger_update
AFTER UPDATE ON passenger
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (table_name, record_id, action_type, description, changed_by)
    VALUES ('passenger', NEW.passenger_id, 'UPDATE', CONCAT('Updated passenger: ', NEW.name), 'System');
END //

CREATE TRIGGER trg_audit_flight_insert
AFTER INSERT ON flight
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (table_name, record_id, action_type, description, changed_by)
    VALUES ('flight', NEW.flight_id, 'CREATE', CONCAT('New flight: ', NEW.flight_no), 'Admin');
END //

CREATE TRIGGER trg_audit_booking_update
AFTER UPDATE ON booking
FOR EACH ROW
BEGIN
    IF NEW.status = 'Cancelled' AND OLD.status != 'Cancelled' THEN
        INSERT INTO audit_log (table_name, record_id, action_type, description, changed_by)
        VALUES ('booking', NEW.booking_id, 'CANCEL', CONCAT('Booking cancelled: ', NEW.booking_id), 'System');
        
        UPDATE payment
        SET refunded = TRUE, refund_amount = amount
        WHERE booking_id = NEW.booking_id;
    END IF;
END //

CREATE TRIGGER trg_auto_fare_adjust
AFTER INSERT ON booking
FOR EACH ROW
BEGIN
    DECLARE v_capacity INT;
    DECLARE v_booked_count INT;
    DECLARE v_base_fare DECIMAL(10,2);
    DECLARE v_percentage_full DECIMAL(5,2);

    SELECT ac.capacity, f.base_fare
    INTO v_capacity, v_base_fare
    FROM flight f
    JOIN aircraft ac ON f.aircraft_id = ac.aircraft_id
    WHERE f.flight_id = NEW.flight_id;
    
    SELECT COUNT(*) INTO v_booked_count
    FROM booking
    WHERE flight_id = NEW.flight_id AND status = 'Confirmed';
    
    SET v_percentage_full = (v_booked_count / v_capacity) * 100;
    
    IF v_percentage_full > 80.0 THEN
        UPDATE flight
        SET current_fare = v_base_fare * 1.25
        WHERE flight_id = NEW.flight_id;
    ELSEIF v_percentage_full > 50.0 THEN
        UPDATE flight
        SET current_fare = v_base_fare * 1.10
        WHERE flight_id = NEW.flight_id;
    END IF;
END //

CREATE TRIGGER trg_set_initial_fare
BEFORE INSERT ON flight
FOR EACH ROW
BEGIN
    SET NEW.current_fare = NEW.base_fare;
END //

-- Trigger: generate aircraft seats automatically after aircraft is inserted
CREATE TRIGGER trg_generate_aircraft_seats
AFTER INSERT ON aircraft
FOR EACH ROW
BEGIN
  DECLARE i INT DEFAULT 1;
  DECLARE total INT;
  DECLARE row_no INT DEFAULT 1;
  DECLARE seat_letter CHAR(1);

  SET total = NEW.capacity;
  WHILE i <= total DO
    SET seat_letter = ELT(((i-1) % 6) + 1, 'A','B','C','D','E','F');
    INSERT INTO aircraft_seats (aircraft_id, seat_no)
    VALUES (NEW.aircraft_id, CONCAT(row_no, seat_letter));
    IF MOD(i,6) = 0 THEN
      SET row_no = row_no + 1;
    END IF;
    SET i = i + 1;
  END WHILE;
END //

DELIMITER ;
"""
exec_sql_block(triggers_sql, "TRIGGERS")

# ----------------------------------------
# 6. EVENTS
# ----------------------------------------
events_sql = """
SET GLOBAL event_scheduler = ON;

DELIMITER //
CREATE EVENT IF NOT EXISTS evt_auto_cancel_flights
ON SCHEDULE EVERY 1 HOUR
DO
BEGIN
    UPDATE flight
    SET status = 'Cancelled'
    WHERE departure_time < NOW() AND status = 'Scheduled';

    UPDATE flight
    SET status = 'Completed'
    WHERE arrival_time < NOW() AND status IN ('Scheduled','Departed');
END //
DELIMITER ;
"""
exec_sql_block(events_sql, "EVENTS")

# ----------------------------------------
# 7. PERMISSIONS SEED (RBAC)
# ----------------------------------------
permissions_sql = """
INSERT INTO permissions (permission_key, description) VALUES
('add_aircraft', 'Can add aircraft'),
('add_routes', 'Can add routes'),
('create_flights', 'Can create flights'),
('update_flights', 'Can update flight statuses'),
('log_maintenance', 'Can log maintenance'),
('manage_payroll', 'Can manage payroll'),
('manage_employees', 'Can manage employee records'),
('view_reports', 'Can view analytics and reports'),
('manage_roles', 'Can create/edit roles and permissions');
"""
exec_sql_block(permissions_sql, "PERMISSIONS SEED")

# ----------------------------------------
# 8. ROLES + ROLE_PERMISSIONS SEED
# ----------------------------------------
roles_seed_sql = """
INSERT INTO roles (role_name, description) VALUES
('Admin', 'System administrator with full access'),
('HR', 'Human Resources - manage employees and payroll'),
('Ground Staff', 'Ground operations - add aircraft and routes'),
('ATC', 'Air Traffic Control - update flight statuses'),
('Engineer', 'Aircraft engineer - log maintenance'),
('Passenger', 'End user - can register and book flights');

-- Link default permissions
-- Admin gets all permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r, permissions p
WHERE r.role_name = 'Admin';

-- HR
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r JOIN permissions p ON p.permission_key IN ('manage_payroll','manage_employees','view_reports')
WHERE r.role_name = 'HR';

-- Ground Staff
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r JOIN permissions p ON p.permission_key IN ('add_aircraft','add_routes')
WHERE r.role_name = 'Ground Staff';

-- ATC
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r JOIN permissions p ON p.permission_key IN ('update_flights','view_reports')
WHERE r.role_name = 'ATC';

-- Engineer
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r JOIN permissions p ON p.permission_key IN ('log_maintenance','view_reports')
WHERE r.role_name = 'Engineer';
"""
exec_sql_block(roles_seed_sql, "ROLES + ROLE_PERMISSIONS SEED")

# ----------------------------------------
# 9. LOYALTY TIERS SEED
# ----------------------------------------
loyalty_sql = """
INSERT INTO loyalty_tiers (tier_name, min_points, max_points, discount_percent) VALUES
('Bronze', 0, 499, 0),
('Silver', 500, 999, 5),
('Gold', 1000, 1999, 10),
('Platinum', 2000, 999999, 15);
"""
exec_sql_block(loyalty_sql, "LOYALTY TIERS SEED")

# ----------------------------------------
# 10. SAMPLE DATA (admin, passengers, employees, aircraft, routes, flights, bookings)
# ----------------------------------------
sample_data_sql = """
INSERT INTO admin (username, password, full_name) VALUES ('admin', 'admin123', 'System Administrator');

INSERT INTO passenger (name, email, phone, passport_no, dob, total_points)
VALUES 
('Alice Smith', 'alice@example.com', '555-1234', 'P12345678', '1990-05-15', 150),
('Bob Johnson', 'bob@example.com', '555-5678', 'P87654321', '1985-11-30', 50),
('Charlie Brown', 'charlie@example.com', '555-9012', 'P55566777', '2000-01-20', 0);

INSERT INTO roles (role_name, description) VALUES ('DemoGround','Demo ground role');

INSERT INTO employee (name, role, role_id, email, date_of_joining, salary)
VALUES
('John Doe', 'Pilot', NULL, 'john.doe@airline.com', '2018-06-01', 120000.00),
('Jane Roe', 'Flight Attendant', NULL, 'jane.roe@airline.com', '2019-03-15', 55000.00),
('Mike Ross', 'Engineer', (SELECT role_id FROM roles WHERE role_name='Engineer'), 'mike.ross@airline.com', '2017-10-20', 75000.00),
('Sara Ground', 'Ground Staff', (SELECT role_id FROM roles WHERE role_name='Ground Staff'), 'sara.g@airline.com', '2021-02-10', 48000.00);

INSERT INTO aircraft (registration_no, model, capacity, last_maintenance, status)
VALUES 
('VT-A320','Airbus A320', 160, NOW(), 'Operational'),
('VT-B737','Boeing 737', 180, NOW(), 'Operational'),
('VT-A321','Airbus A321neo', 220, NOW(), 'Operational'),
('VT-B787','Boeing 787', 250, NOW(), 'Maintenance');

INSERT INTO route (source_code, source_name, dest_code, dest_name, distance_km)
VALUES 
('BOM', 'Mumbai', 'DEL', 'New Delhi', 1400),
('BOM', 'Mumbai', 'BLR', 'Bengaluru', 830),
('DEL', 'New Delhi', 'JFK', 'New York', 11760),
('LHR', 'London', 'BOM', 'Mumbai', 7170),
('BLR', 'Bengaluru', 'SIN', 'Singapore', 3600);

INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare, gate)
VALUES ('AI-202','Air India', 1, 1, DATE_ADD(NOW(), INTERVAL -1 DAY), DATE_ADD(NOW(), INTERVAL -1 DAY + INTERVAL 2 HOUR), 6500.00, 'T1-A6');

INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare, gate)
VALUES ('6E-505','IndiGo', 2, 2, DATE_ADD(NOW(), INTERVAL 2 HOUR), DATE_ADD(NOW(), INTERVAL 4 HOUR), 3200.00, 'T2-B2');

INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare, gate)
VALUES ('UK-901','Vistara', 1, 3, DATE_ADD(NOW(), INTERVAL 48 HOUR), DATE_ADD(NOW(), INTERVAL 50 HOUR), 7000.00, 'T2-C1');

-- Create bookings using procedure (safe)
CALL book_flight(1, 2, '12A', 'Passenger'); -- Alice
CALL book_flight(2, 3, '5F', 'Passenger');  -- Bob

INSERT INTO vendor (name, amenity_type, terminal, location_desc)
VALUES
('Starbucks', 'Cafe', 'T2', 'Near Gate B5'),
('Duty Free Shoppe', 'Retail', 'T2', 'International Departures Hall'),
('Plaza Premium Lounge', 'Lounge', 'T1', 'Domestic, After Security');

INSERT INTO maintenance (aircraft_id, emp_id, notes, maintenance_date)
VALUES
(4, 3, 'Scheduled check', DATE_SUB(NOW(), INTERVAL 5 DAY));
"""
exec_sql_block(sample_data_sql, "SAMPLE DATA INSERTS")

# ----------------------------------------
# 11. Ensure aircraft_seats populated for existing aircraft (in case trigger didn't run for imported aircraft)
# ----------------------------------------
populate_seats_sql = """
-- Populate seats for existing aircraft if none exist
INSERT INTO aircraft_seats (aircraft_id, seat_no)
SELECT a.aircraft_id, CONCAT( FLOOR((seq - 1) / 6) + 1, ELT(((seq - 1) % 6) + 1, 'A','B','C','D','E','F'))
FROM aircraft a
JOIN (
  SELECT @row := @row + 1 AS seq FROM
  (SELECT 0 UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) t1,
  (SELECT 0 UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) t2,
  (SELECT @row := 0) vars
) seqs
WHERE seqs.seq <= a.capacity
AND NOT EXISTS (SELECT 1 FROM aircraft_seats s WHERE s.aircraft_id = a.aircraft_id AND s.seat_no = CONCAT( FLOOR((seq - 1) / 6) + 1, ELT(((seq - 1) % 6) + 1, 'A','B','C','D','E','F')));
"""
exec_sql_block(populate_seats_sql, "POPULATE AIRCRAFT SEATS")

# ----------------------------------------
# 12. ARCHIVAL EVENT (move completed flights to archived_flights)
# ----------------------------------------
archive_sql = """
DELIMITER //
CREATE EVENT IF NOT EXISTS evt_archive_completed_flights
ON SCHEDULE EVERY 1 DAY
DO
BEGIN
    INSERT INTO archived_flights
    SELECT * FROM flight WHERE status = 'Completed';
    DELETE FROM flight WHERE status = 'Completed';
END //
DELIMITER ;
"""
exec_sql_block(archive_sql, "ARCHIVAL EVENT")

# ----------------------------------------
# FINAL: Wrap up
# ----------------------------------------
print("\n" + "="*60)
print(f"✅ DATABASE '{DB_NAME}' (v2) IS READY!")
print("Includes RBAC (roles/permissions), seat table, loyalty tiers, analytics views, triggers, procedures, events, and sample data.")
print("Next: update your Flask app to point to this DB and implement RBAC checks and seat-map UI.")
print("="*60 + "\n")

cursor.close()
cnx.close()
