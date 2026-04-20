#!/bin/bash
# logs.sh — View backend logs
# Usage: ./logs.sh           (last 50 lines)
#        ./logs.sh -f        (follow live)
#        ./logs.sh -n 200    (last 200 lines)

LINES=50
FOLLOW=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -f) FOLLOW=true ;;
        -n) LINES="$2"; shift ;;
    esac
    shift
done

if $FOLLOW; then
    sudo journalctl -u clau-backend -f
else
    sudo journalctl -u clau-backend -n "$LINES" --no-pager
fi
