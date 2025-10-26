-- ============================================
-- DATABASE: airline_pro_db_v2
-- ============================================
DROP DATABASE IF EXISTS airline_pro_db_v2;
CREATE DATABASE airline_pro_db_v2;
USE airline_pro_db_v2;

-- ============================================
-- CORE TABLES
-- ============================================
SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS archived_flights, passenger_loyalty_summary, flight_revenue_summary, route_performance, maintenance_history, aircraft_seats, role_permissions, permissions, roles, loyalty_tiers;
DROP TABLE IF EXISTS admin, passenger, employee, aircraft, route, flight, booking, payment, vendor, staff_assignment, payroll, maintenance, audit_log;
SET FOREIGN_KEY_CHECKS=1;

-- Admin table
CREATE TABLE admin (
  admin_id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) UNIQUE NOT NULL,
  password VARCHAR(255) NOT NULL,
  full_name VARCHAR(100),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Passenger table
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

-- Roles and Permissions (RBAC)
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

-- Employee table
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

-- Aircraft table
CREATE TABLE aircraft (
  aircraft_id INT AUTO_INCREMENT PRIMARY KEY,
  registration_no VARCHAR(50) UNIQUE,
  model VARCHAR(100),
  capacity INT,
  last_maintenance DATETIME,
  status VARCHAR(30) DEFAULT 'Operational',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Route table
CREATE TABLE route (
  route_id INT AUTO_INCREMENT PRIMARY KEY,
  source_code VARCHAR(10),
  source_name VARCHAR(100),
  dest_code VARCHAR(10),
  dest_name VARCHAR(100),
  distance_km INT
);

-- Flight table
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

-- Booking and Payments
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

-- Vendors / Amenities
CREATE TABLE vendor (
  vendor_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150),
  amenity_type VARCHAR(100),
  terminal VARCHAR(50),
  location_desc VARCHAR(200),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Staff Flight Assignments
CREATE TABLE staff_assignment (
  assignment_id INT AUTO_INCREMENT PRIMARY KEY,
  emp_id INT,
  flight_id INT,
  role_on_flight VARCHAR(50),
  assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (emp_id) REFERENCES employee(emp_id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (flight_id) REFERENCES flight(flight_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Payroll
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

-- Maintenance Logs
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

-- Audit Logs
CREATE TABLE audit_log (
  log_id INT AUTO_INCREMENT PRIMARY KEY,
  table_name VARCHAR(100),
  record_id INT,
  action_type VARCHAR(20),
  description TEXT,
  changed_by VARCHAR(100),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Aircraft Seats
CREATE TABLE aircraft_seats (
  seat_id INT AUTO_INCREMENT PRIMARY KEY,
  aircraft_id INT,
  seat_no VARCHAR(5),
  is_window BOOLEAN DEFAULT FALSE,
  is_aisle BOOLEAN DEFAULT FALSE,
  FOREIGN KEY (aircraft_id) REFERENCES aircraft(aircraft_id) ON DELETE CASCADE
);

-- Loyalty Tiers
CREATE TABLE loyalty_tiers (
  tier_name VARCHAR(50) PRIMARY KEY,
  min_points INT,
  max_points INT,
  discount_percent INT
);

-- Archived Flights
CREATE TABLE archived_flights LIKE flight;

-- ============================================
-- FUNCTIONS
-- ============================================
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

-- ============================================
-- TRIGGERS
-- ============================================
DELIMITER //
CREATE TRIGGER trg_audit_passenger_insert
AFTER INSERT ON passenger
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (table_name, record_id, action_type, description, changed_by)
    VALUES ('passenger', NEW.passenger_id, 'CREATE', CONCAT('New passenger: ', NEW.name), 'System');
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
        UPDATE flight SET current_fare = v_base_fare * 1.25 WHERE flight_id = NEW.flight_id;
    ELSEIF v_percentage_full > 50.0 THEN
        UPDATE flight SET current_fare = v_base_fare * 1.10 WHERE flight_id = NEW.flight_id;
    END IF;
END //

CREATE TRIGGER trg_set_initial_fare
BEFORE INSERT ON flight
FOR EACH ROW
BEGIN
    SET NEW.current_fare = NEW.base_fare;
END //

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

-- ============================================
-- EVENT SCHEDULER
-- ============================================
SET GLOBAL event_scheduler = ON;
DELIMITER //
CREATE EVENT IF NOT EXISTS evt_auto_cancel_flights
ON SCHEDULE EVERY 1 HOUR
DO
BEGIN
    UPDATE flight SET status = 'Cancelled'
    WHERE departure_time < NOW() AND status = 'Scheduled';

    UPDATE flight SET status = 'Completed'
    WHERE arrival_time < NOW() AND status IN ('Scheduled','Departed');
END //
DELIMITER ;

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
