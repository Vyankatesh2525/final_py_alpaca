#!/bin/bash
# update-env.sh — Safely edit env.conf and restart backend
sudo nano /etc/clau/env.conf
echo ""
echo "==> Restarting backend to apply changes..."
sudo systemctl restart clau-backend
sleep 2
sudo systemctl status clau-backend --no-pager -n 5
