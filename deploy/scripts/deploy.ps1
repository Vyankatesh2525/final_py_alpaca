# deploy.ps1 — Run from D:\Vivytech\Clau-APP-Main\final_py_alpaca on Windows
# Usage: .\deploy\scripts\deploy.ps1

$KEY      = "D:\Vivytech\Private Keys\clau-backend.pem"
$HOST     = "ubuntu@ec2-18-222-239-76.us-east-2.compute.amazonaws.com"
$REMOTE   = "/home/ubuntu/clau/final_py_alpaca"
$LOCAL    = "D:\Vivytech\Clau-APP-Main\final_py_alpaca"

Write-Host "`n==> Uploading Python files..." -ForegroundColor Cyan
scp -i $KEY -r "$LOCAL\*.py" "${HOST}:${REMOTE}/"
scp -i $KEY -r "$LOCAL\routers" "${HOST}:${REMOTE}/"
scp -i $KEY -r "$LOCAL\alembic" "${HOST}:${REMOTE}/"

Write-Host "`n==> Running migrations..." -ForegroundColor Cyan
ssh -i $KEY $HOST "cd $REMOTE && set -a && source /etc/clau/env.conf && set +a && $REMOTE/venv/bin/alembic upgrade head"

Write-Host "`n==> Restarting backend..." -ForegroundColor Cyan
ssh -i $KEY $HOST "sudo systemctl restart clau-backend"

Write-Host "`n==> Checking status..." -ForegroundColor Cyan
ssh -i $KEY $HOST "sudo systemctl status clau-backend --no-pager -n 10"

Write-Host "`n✓ Deploy complete — https://api.clau.app" -ForegroundColor Green
