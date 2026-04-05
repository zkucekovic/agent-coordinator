#!/bin/bash
# Extracts NEXT field from the last valid ---HANDOFF--- block in handoff.md
file="${1:-/home/operater/Projects/coordination/handoff.md}"
awk '
/---HANDOFF---/ { in_block=1; block="" }
in_block { block = block "\n" $0 }
/---END---/ { if (in_block) { last_block=block; in_block=0 } }
END { print last_block }
' "$file" | grep "^NEXT:" | awk '{print $2}'
