-- Create the database
CREATE DATABASE IF NOT EXISTS upi_spendsense;
USE upi_spendsense;

-- Create the main transactions table
CREATE TABLE transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    txn_date DATE NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    note VARCHAR(255),
    category VARCHAR(50) DEFAULT 'Uncategorized',
    source VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);