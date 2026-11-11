#!/usr/bin/env bash
# Scripted terminal demo: launch a lab, prove it, make a bad firewall change, catch it, roll back, destroy.
set -euo pipefail
say() { printf '\n\033[1;38;5;209m== %s\033[0m\n' "$*"; }
pause() { [ "${NO_PAUSE:-}" = 1 ] || read -rp "   (enter to continue) " _; }

say "The catalog"
labforge catalog; pause

say "Launch the Market Branch Office lab (auto-destroys in 30 minutes)"
out=$(labforge up branch-office --name "Demo branch" --ttl 30)
echo "$out"
LAB=$(echo "$out" | awk '{print $1}' | tail -1)
pause

say "Run the built-in tests"
labforge check "$LAB" || true; pause

say "Look at the edge router like you would on a real device"
labforge exec "$LAB" edge1 "show ip bgp summary"; pause

say "Push a BAD firewall change: guests may now go anywhere"
RULES='flush ruleset
table inet filter {
  chain forward {
    type filter hook forward priority filter; policy drop;
    ct state established,related counter accept
    iifname "eth1" counter accept comment "STAFF -> any"
    iifname "eth3" counter accept comment "GUEST -> anywhere (bad change)"
    counter drop
  }
}'
python3 - "$LAB" "$RULES" <<'PY'
import sys
from labforge.manager import LabManager
print(LabManager().apply_config(sys.argv[1], "fw1", sys.argv[2], by="demo")["output"])
PY
pause

say "Run the tests again: the guest isolation test catches it"
labforge check "$LAB" || true; pause

say "Roll back to the approved policy"
python3 - "$LAB" <<'PY'
import sys
from labforge import catalog
from labforge.manager import LabManager
rules = catalog.get("branch-office").nodes["fw1"].ruleset
print(LabManager().apply_config(sys.argv[1], "fw1", rules, by="demo")["output"])
PY
labforge check "$LAB"; pause

say "Destroy the lab"
labforge down "$LAB"
labforge stats
