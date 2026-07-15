CREATE DATABASE eduportal;
USE eduportal;

CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100),
  phone VARCHAR(20),
  email VARCHAR(100),
  password_hash VARCHAR(255),
  role ENUM('student','parent','teacher','school_admin','ngo_officer','platform_admin'),
  state VARCHAR(50),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE schools (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150),
  state VARCHAR(50),
  county VARCHAR(50),
  level VARCHAR(50),
  contact_phone VARCHAR(20),
  status ENUM('pending','approved','rejected'),
  admin_user_id INT,
  FOREIGN KEY (admin_user_id) REFERENCES users(id)
);

CREATE TABLE materials (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(150),
  subject VARCHAR(50),
  grade VARCHAR(20),
  year INT,
  file_path VARCHAR(255),
  approved BOOLEAN DEFAULT FALSE,
  uploaded_by INT,
  FOREIGN KEY (uploaded_by) REFERENCES users(id)
);

CREATE TABLE scholarships (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(150),
  description TEXT,
  deadline DATE,
  approved BOOLEAN DEFAULT FALSE,
  ngo_id INT,
  FOREIGN KEY (ngo_id) REFERENCES users(id)
);
