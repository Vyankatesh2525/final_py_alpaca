#!/bin/bash
# status.sh — Quick health check for all services
echo ""
echo "=== Backend ============================================"
sudo systemctl status clau-backend --no-pager -n 5

echo ""
echo "=== Nginx =============================================="
sudo systemctl status nginx --no-pager -n 5

echo ""
echo "=== Ports =============================================="
sudo ss -tlnp | grep -E ':80|:443|:8000'

echo ""
echo "=== API health ========================================="
curl -sf https://api.clau.app/ && echo "" || echo "  (no response)"
echo ""
