#!/bin/bash
# db.sh — Connect to RDS PostgreSQL
# Usage: ./db.sh             (interactive psql)
#        ./db.sh "SELECT * FROM users;"   (run a query)

source <(sudo cat /etc/clau/env.conf) 2>/dev/null

HOST="clau-postgres-db.cf4issoo4rch.us-east-2.rds.amazonaws.com"
USER="clau_admin"
DB="clau_db"

if [[ -n "$1" ]]; then
    PGSSLMODE=require psql -h "$HOST" -U "$USER" -d "$DB" -c "$1"
else
    PGSSLMODE=require psql -h "$HOST" -U "$USER" -d "$DB"
fi
