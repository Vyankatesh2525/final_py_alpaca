#!/bin/bash
# restart.sh — Restart backend (and optionally nginx)
echo "==> Restarting clau-backend..."
sudo systemctl restart clau-backend
sleep 2
sudo systemctl status clau-backend --no-pager -n 8

if [[ "$1" == "--nginx" ]]; then
    echo ""
    echo "==> Reloading nginx..."
    sudo nginx -t && sudo systemctl reload nginx
fi
