import mysql.connector
from mysql.connector import errorcode, InterfaceError
import datetime

# ============================================
# Database connection configuration
# IMPORTANT: Replace 'your_mysql_password' with your actual MySQL password
# ============================================
config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Swami@2006', # <-- IMPORTANT: CHANGE THIS (or use 'your_mysql_password' below)
    'autocommit': True
}

DB_NAME = "airline_project_db"

# ============================================
# Connect to MySQL server
# ============================================
try:
    print("Connecting to MySQL server...")
    cnx = mysql.connector.connect(**config)
    # FIX: Use a buffered cursor to prevent 'Unread result found' errors
    cursor = cnx.cursor(buffered=True) 
    print("✅ Connected to MySQL successfully.")
except mysql.connector.Error as err:
    if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        print("❌ Error: Access denied. Check your username/password in the 'config' dictionary.")
    else:
        print(f"❌ Error: {err}")
    exit(1)

# ============================================
# Create Database
# ============================================
try:
    cursor.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
    cursor.execute(f"CREATE DATABASE {DB_NAME}")
    print(f"✅ Database '{DB_NAME}' created successfully.")
except mysql.connector.Error as err:
    print(f"❌ Failed to create database: {err}")
    exit(1)

cursor.execute(f"USE {DB_NAME}")

# ============================================
# Helper function to execute multi-statement SQL blocks
# ============================================
def exec_sql_block(sql_block, section_name="SQL Block"):
    print(f"Executing {section_name}...")
    try:
        # Handle blocks with custom delimiters
        if 'DELIMITER //' in sql_block:
            # Split into parts before, during, and after custom delimiters
            parts = sql_block.split('DELIMITER //')
            
            # 1. Execute any simple statements before the first DELIMITER //
            simple_statements_before = parts[0].split(';')
            for s in simple_statements_before:
                if s.strip():
                    cursor.execute(s)
            
            # 2. Execute complex statements
            for part in parts[1:]:
                # FIX: Split on '\nDELIMITER ;' NOT '//\nDELIMITER ;'
                if '\nDELIMITER ;' in part:
                    # This chunk contains procedure(s) and the end delimiter
                    proc_chunk, simple_statements_after = part.split('\nDELIMITER ;', 1)
                    
                    # Execute the procedure(s)
                    # Procedures are separated by '//'
                    procedures = proc_chunk.split('//')
                    for proc in procedures:
                        if proc.strip():
                            cursor.execute(proc)
                    
                    # 3. Execute any simple statements after the final DELIMITER ;
                    for s in simple_statements_after.split(';'):
                        if s.strip():
                            cursor.execute(s)
                else:
                    # This part is just a procedure (unlikely given my file structure, but safe)
                    if part.strip():
                        cursor.execute(part)
        
        else:
            # Handle simple SQL blocks (like TABLES, VIEWS, and SAMPLE DATA)
            statements = sql_block.split(';')
            for statement in statements:
                if statement.strip():
                    cursor.execute(statement)
                    
                    # Safety check for "Unread result found" from CALL statements
                    # Even with buffered=True, this is good practice
                    if statement.strip().upper().startswith('CALL'):
                        try:
                            # Consume any results from CALL to clear the buffer
                            results_iterator = cursor.stored_results()
                            for rs in results_iterator:
                                rs.fetchall() # Consume all rows in this result set
                        except InterfaceError as err:
                            if "No result set" in str(err) or err.errno == 2014:
                                pass # This is expected if the proc has no SELECT
                            else:
                                raise # Re-raise other interface errors
                        except mysql.connector.Error as err:
                            print(f"Warning: Error consuming procedure results: {err}")
                            pass
        
        print(f"✅ Executed {section_name} successfully.")
    
    except mysql.connector.Error as err:
        print(f"❌ Error in {section_name}: {err}")
        # print(f"Failed SQL: {sql_block}") # Uncomment for debugging

# ============================================
# 1. TABLES
# ============================================
tables_sql = """
SET FOREIGN_KEY_CHECKS=0;
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
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE employee (
  emp_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  role VARCHAR(50),
  email VARCHAR(150) UNIQUE NOT NULL,
  date_of_joining DATE NOT NULL,
  salary DECIMAL(12,2),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (route_id) REFERENCES route(route_id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (aircraft_id) REFERENCES aircraft(aircraft_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE booking (
  booking_id INT AUTO_INCREMENT PRIMARY KEY,
  passenger_id INT,
  flight_id INT,
  booking_date DATETIME DEFAULT CURRENT_TIMESTAMP,
  seat_no VARCHAR(8),
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
  net_pay DECIMAL(12, 2) GENERATED ALWAYS AS (base_salary + bonus - deductions) STORED,
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
"""
exec_sql_block(tables_sql, "TABLE CREATION")

# ============================================
# 2. FUNCTIONS
# ============================================
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
  -- Pseudo-random deterministic distance generator
  RETURN (ABS(CAST(CRC32(CONCAT(LOWER(src_code), '|', LOWER(dest_code))) AS SIGNED)) % 4000) + 200;
END //

DELIMITER ;
"""
exec_sql_block(functions_sql, "FUNCTIONS")

# ============================================
# 3. STORED PROCEDURES
# ============================================
procedures_sql = """
DELIMITER //

CREATE PROCEDURE update_points(IN p_passenger_id INT, IN p_amount DECIMAL(10,2))
BEGIN
  -- Award 1 point for every 100 currency units spent
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
    
    -- Get flight details
    SELECT
        f.current_fare, f.status, ac.capacity
    INTO
        v_fare, v_flight_status, v_capacity
    FROM flight f
    JOIN aircraft ac ON f.aircraft_id = ac.aircraft_id
    WHERE f.flight_id = p_flight_id;
    
    -- Get current booking count
    SELECT COUNT(*)
    INTO v_booked_count
    FROM booking
    WHERE flight_id = p_flight_id AND status = 'Confirmed';
    
    -- Check flight status and capacity
    IF v_flight_status != 'Scheduled' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Flight is not available for booking.';
    ELSEIF v_booked_count >= v_capacity THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Flight is full.';
    ELSE
        -- 1. Create booking
        INSERT INTO booking (passenger_id, flight_id, seat_no, status, booked_by)
        VALUES (p_passenger_id, p_flight_id, p_seat_no, 'Confirmed', p_booked_by);
        
        SET v_booking_id = LAST_INSERT_ID();
        
        -- 2. Create payment record
        INSERT INTO payment (booking_id, amount, method)
        VALUES (v_booking_id, v_fare, 'Internal');
        
        -- 3. Update loyalty points
        CALL update_points(p_passenger_id, v_fare);
        
        -- 4. Log this action (will also be caught by trigger, but good for procedure logic)
        INSERT INTO audit_log (table_name, record_id, action_type, description, changed_by)
        VALUES ('booking', v_booking_id, 'CREATE', 'New booking via procedure', p_booked_by);
        
        SELECT v_booking_id AS new_booking_id, 'Booking successful' AS message;
    END IF;
END //

CREATE PROCEDURE sp_update_flight_statuses()
BEGIN
    -- This procedure can be run by an admin or a scheduled event
    -- to clean up flight statuses.
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

# ============================================
# 4. VIEWS
# ============================================
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

CREATE OR REPLACE VIEW employee_assignments AS
SELECT
    e.emp_id,
    e.name,
    e.role,
    f.flight_no,
    f.departure_time,
    f.status,
    sa.role_on_flight
FROM employee e
JOIN staff_assignment sa ON e.emp_id = sa.emp_id
JOIN flight f ON sa.flight_id = f.flight_id
WHERE f.departure_time > NOW() AND f.status = 'Scheduled';
"""
exec_sql_block(views_sql, "VIEWS CREATION")

# ============================================
# 5. TRIGGERS
# ============================================
triggers_sql = """
DELIMITER //

-- Audit Log Triggers
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
        -- Log cancellation
        INSERT INTO audit_log (table_name, record_id, action_type, description, changed_by)
        VALUES ('booking', NEW.booking_id, 'CANCEL', CONCAT('Booking cancelled: ', NEW.booking_id), 'System');
        
        -- Trigger refund
        UPDATE payment
        SET refunded = TRUE, refund_amount = amount
        WHERE booking_id = NEW.booking_id;
    END IF;
END //

-- DBMS Logic Triggers
CREATE TRIGGER trg_auto_fare_adjust
AFTER INSERT ON booking
FOR EACH ROW
BEGIN
    DECLARE v_capacity INT;
    DECLARE v_booked_count INT;
    DECLARE v_base_fare DECIMAL(10,2);
    DECLARE v_percentage_full DECIMAL(5,2);

    -- Get flight capacity and booking count
    SELECT ac.capacity, f.base_fare
    INTO v_capacity, v_base_fare
    FROM flight f
    JOIN aircraft ac ON f.aircraft_id = ac.aircraft_id
    WHERE f.flight_id = NEW.flight_id;
    
    SELECT COUNT(*)
    INTO v_booked_count
    FROM booking
    WHERE flight_id = NEW.flight_id AND status = 'Confirmed';
    
    -- Calculate percentage
    SET v_percentage_full = (v_booked_count / v_capacity) * 100;
    
    -- Adjust fare if > 80% full
    IF v_percentage_full > 80.0 THEN
        UPDATE flight
        SET current_fare = v_base_fare * 1.25 -- 25% increase
        WHERE flight_id = NEW.flight_id;
    -- Adjust fare if > 50% full
    ELSEIF v_percentage_full > 50.0 THEN
        UPDATE flight
        SET current_fare = v_base_fare * 1.10 -- 10% increase
        WHERE flight_id = NEW.flight_id;
    END IF;
END //

-- Set initial fare on flight creation
CREATE TRIGGER trg_set_initial_fare
BEFORE INSERT ON flight
FOR EACH ROW
BEGIN
    SET NEW.current_fare = NEW.base_fare;
END //

DELIMITER ;
"""
exec_sql_block(triggers_sql, "TRIGGERS")

# ============================================
# 6. EVENTS
# ============================================
events_sql = """
SET GLOBAL event_scheduler = ON;

DELIMITER //
CREATE EVENT evt_auto_cancel_flights
ON SCHEDULE EVERY 1 HOUR
DO
BEGIN
    -- Mark flights as 'Cancelled' if they are past departure time but still 'Scheduled'
    UPDATE flight
    SET status = 'Cancelled'
    WHERE departure_time < NOW() AND status = 'Scheduled';
    
    -- Mark flights as 'Completed' if they are past arrival time
    UPDATE flight
    SET status = 'Completed'
    WHERE arrival_time < NOW() AND status IN ('Scheduled', 'Departed');
END //
DELIMITER ;
"""
exec_sql_block(events_sql, "EVENTS")


# ============================================
# 7. SAMPLE DATA
# ============================================
sample_data_sql = """
INSERT INTO admin (username, password, full_name)
VALUES ('admin', 'admin123', 'System Administrator');

INSERT INTO passenger (name, email, phone, passport_no, dob, total_points)
VALUES 
('Alice Smith', 'alice@example.com', '555-1234', 'P12345678', '1990-05-15', 150),
('Bob Johnson', 'bob@example.com', '555-5678', 'P87654321', '1985-11-30', 50),
('Charlie Brown', 'charlie@example.com', '555-9012', 'P55566777', '2000-01-20', 0);

INSERT INTO employee (name, role, email, date_of_joining, salary)
VALUES
('John Doe', 'Pilot', 'john.doe@airline.com', '2018-06-01', 120000.00),
('Jane Roe', 'Flight Attendant', 'jane.roe@airline.com', '2019-03-15', 55000.00),
('Mike Ross', 'Maintenance Engineer', 'mike.ross@airline.com', '2017-10-20', 75000.00),
('Sarah Jenkins', 'Ground Staff', 'sarah.j@airline.com', '2021-02-10', 48000.00);

INSERT INTO aircraft (registration_no, model, capacity, last_maintenance, status)
VALUES 
('VT-A320','Airbus A320', 160, '2025-10-15 08:00:00', 'Operational'),
('VT-B737','Boeing 737', 180, '2025-10-01 10:00:00', 'Operational'),
('VT-A321','Airbus A321neo', 220, '2025-09-20 12:00:00', 'Operational'),
('VT-B787','Boeing 787', 250, '2025-10-22 14:00:00', 'Maintenance');

INSERT INTO route (source_code, source_name, dest_code, dest_name, distance_km)
VALUES 
('BOM', 'Mumbai', 'DEL', 'New Delhi', 1400),
('BOM', 'Mumbai', 'BLR', 'Bengaluru', 830),
('DEL', 'New Delhi', 'JFK', 'New York', 11760),
('LHR', 'London', 'BOM', 'Mumbai', 7170),
('BLR', 'Bengaluru', 'SIN', 'Singapore', 3600);

-- Note: We are on Oct 26, 2025.
-- Flight 1: Already departed
INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare, gate)
VALUES ('AI-202','Air India', 1, 1, '2025-10-25 18:00:00', '2025-10-25 20:15:00', 6500.00, 'T1-A6');

-- Flight 2: Upcoming today
INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare, gate)
VALUES ('6E-505','IndiGo', 2, 2, '2025-10-26 09:30:00', '2025-10-26 11:00:00', 3200.00, 'T2-B2');

-- Flight 3: Upcoming in 2 days
INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare, gate)
VALUES ('UK-901','Vistara', 1, 3, '2025-10-28 14:00:00', '2025-10-28 16:20:00', 7000.00, 'T2-C1');

-- Flight 4: International
INSERT INTO flight (flight_no, airline, route_id, aircraft_id, departure_time, arrival_time, base_fare, gate)
VALUES ('BA-198','British Airways', 4, 3, '2025-11-01 10:00:00', '2025-11-01 23:30:00', 45000.00, 'T5-G8');

-- Bookings
-- Alice books flight 6E-505
CALL book_flight(1, 2, '12A', 'Passenger');
-- Bob books flight UK-901
CALL book_flight(2, 3, '5F', 'Passenger');

-- Staff Assignments
INSERT INTO staff_assignment (emp_id, flight_id, role_on_flight)
VALUES
(1, 2, 'Captain'), (2, 2, 'Lead Attendant'),
(1, 3, 'Captain'), (2, 3, 'Lead Attendant');

-- Payroll
INSERT INTO payroll (emp_id, base_salary, bonus, deductions, pay_date)
VALUES
(1, 120000.00, 5000.00, 1500.00, '2025-10-01 00:00:00'),
(2, 55000.00, 1000.00, 500.00, '2025-10-01 00:00:00'),
(3, 75000.00, 0.00, 800.00, '2025-10-01 00:00:00');

-- Vendors
INSERT INTO vendor (name, amenity_type, terminal, location_desc)
VALUES
('Starbucks', 'Cafe', 'T2', 'Near Gate B5'),
('Duty Free Shoppe', 'Retail', 'T2', 'International Departures Hall'),
('Plaza Premium Lounge', 'Lounge', 'T1', 'Domestic, After Security');

-- Maintenance
INSERT INTO maintenance (aircraft_id, emp_id, notes, maintenance_date)
VALUES
(4, 3, 'Scheduled C-Check. Engine diagnostics.', '2025-10-22 14:00:00');
"""
exec_sql_block(sample_data_sql, "SAMPLE DATA INSERTS")

print("\n" + "="*50)
print(f"✅ DATABASE '{DB_NAME}' IS READY!")
print("All tables, procedures, views, triggers, and sample data installed.")
print("You can now run 'python app.py' to start the Flask server.")
print("="*50 + "\n")

cursor.close()
cnx.close()

