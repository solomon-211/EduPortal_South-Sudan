-- Run this in psql as a PostgreSQL superuser (for example postgres)
-- Update placeholders before running.

SELECT 'CREATE ROLE eduportal_app LOGIN PASSWORD ''Shelomoh0126168@2005'''
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eduportal_app')
\gexec

SELECT 'CREATE DATABASE eduportal OWNER eduportal_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'eduportal')
\gexec

GRANT ALL PRIVILEGES ON DATABASE eduportal TO eduportal_app;
