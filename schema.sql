-- Smart Parking DBMS (BCS755A). Run: mysql -u root -p < schema.sql
-- Note: ye command purana smart_parking database delete karke naya banati hai.
DROP DATABASE IF EXISTS smart_parking;
CREATE DATABASE smart_parking;
USE smart_parking;

CREATE TABLE users (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL
);

CREATE TABLE vehicle (
    vehicle_id INT PRIMARY KEY AUTO_INCREMENT,
    reg_no VARCHAR(25) NOT NULL UNIQUE,
    vehicle_type VARCHAR(30) NOT NULL,
    user_id INT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE parking_lot (
    lot_id INT PRIMARY KEY AUTO_INCREMENT,
    lot_name VARCHAR(100) NOT NULL,
    location VARCHAR(255) NOT NULL,
    rate_per_hour DECIMAL(10,2) NOT NULL
);

CREATE TABLE parking_slot (
    slot_id INT PRIMARY KEY AUTO_INCREMENT,
    slot_no VARCHAR(30) NOT NULL,
    slot_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE',
    lot_id INT NOT NULL,
    UNIQUE (lot_id, slot_no),
    FOREIGN KEY (lot_id) REFERENCES parking_lot(lot_id)
);

CREATE TABLE booking (
    booking_id INT PRIMARY KEY AUTO_INCREMENT,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'BOOKED',
    vehicle_id INT NOT NULL,
    slot_id INT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicle(vehicle_id),
    FOREIGN KEY (slot_id) REFERENCES parking_slot(slot_id),
    CHECK (end_time > start_time)
);

CREATE TABLE payment (
    payment_id INT PRIMARY KEY AUTO_INCREMENT,
    amount DECIMAL(10,2) NOT NULL,
    mode VARCHAR(20) NOT NULL,
    paid_on DATETIME NOT NULL,
    booking_id INT NOT NULL UNIQUE,
    FOREIGN KEY (booking_id) REFERENCES booking(booking_id)
);

CREATE TABLE slot_log (
    log_id INT PRIMARY KEY AUTO_INCREMENT,
    old_status VARCHAR(20),
    new_status VARCHAR(20),
    changed_on DATETIME NOT NULL,
    slot_id INT NOT NULL,
    FOREIGN KEY (slot_id) REFERENCES parking_slot(slot_id)
);

-- Trigger: har slot status change ka history slot_log me
DELIMITER $$
CREATE TRIGGER trg_slot_status_log
AFTER UPDATE ON parking_slot
FOR EACH ROW
BEGIN
    IF OLD.status <> NEW.status THEN
        INSERT INTO slot_log (old_status, new_status, changed_on, slot_id)
        VALUES (OLD.status, NEW.status, NOW(), NEW.slot_id);
    END IF;
END$$
DELIMITER ;

-- Sample data
INSERT INTO parking_lot (lot_name, location, rate_per_hour) VALUES
    ('Main Lot', 'Block A, BIT Campus', 40.00),
    ('Visitor Lot', 'Gate 2', 60.00);

INSERT INTO parking_slot (slot_no, slot_type, lot_id) VALUES
    ('A1', 'CAR', 1), ('A2', 'CAR', 1), ('A3', 'BIKE', 1),
    ('B1', 'CAR', 2), ('B2', 'CAR', 2), ('B3', 'BIKE', 2);
