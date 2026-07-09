#!/bin/sh
# Throwaway Phase 2 measurement: bring up daemon, run probe, capture result.
# Runs only after data-tactiq-dirs.service (unit deps guarantee /data ready).
set -u
SOCK=/run/tactiq/edge.sock
SHARE=/usr/share/edge-probe
OUT=/data/tactiq/measurement
# DEV: capture full journal (incl. all AVC) to persistent storage on any exit
trap 'dmesg > "$OUT/dmesg-dev.txt" 2>&1; journalctl -b > "$OUT/journal-dev.txt" 2>&1' EXIT
mkdir -p /run/tactiq
restorecon -F /run/tactiq
# DEV: auditd refuses to start unless log dir is root-owned
mkdir -p "$OUT/audit"
restorecon -Rv "$OUT"
chown root:root "$OUT/audit"
# DEV: lift kernel audit rate limit so kmsg keeps all AVC (auditd not required)
auditctl -r 0 2>/dev/null || true
systemctl status auditd.service > "$OUT/auditd-unit.txt" 2>&1 || true
# DEV: persistent AVC capture — auditd not boot-enabled (ordering cycle), start here
systemctl start auditd.service
j=0
while [ $j -lt 10 ] && ! auditctl -s >/dev/null 2>&1; do sleep 0.5; j=$((j+1)); done
auditctl -s > "$OUT/auditd-status.txt" 2>&1
systemctl status auditd.service > "$OUT/auditd-unit-after.txt" 2>&1 || true

# start daemon in background
/usr/bin/tactiq-edge-daemon "$SHARE/planthealth_cls_int8.tflite" "$SOCK" none "$SHARE/class_names.txt" > "$OUT/edge-daemon.log" 2>&1 &
DPID=$!

# wait for socket (max ~5s) — avoid connect-before-bind race
i=0
while [ ! -S "$SOCK" ] && [ $i -lt 50 ]; do sleep 0.1; i=$((i+1)); done

if [ ! -S "$SOCK" ]; then
  echo "FAIL: socket $SOCK never appeared after 5s" > "$OUT/edge-probe.txt"
  echo "--- daemon log follows ---" >> "$OUT/edge-probe.txt"
  cat "$OUT/edge-daemon.log" >> "$OUT/edge-probe.txt" 2>/dev/null
  kill $DPID 2>/dev/null
  exit 1
fi

/usr/bin/tactiq-edge-probe "$SOCK" "$SHARE/frame0.bin" 1000 0 > "$OUT/edge-probe.txt" 2>&1
RC=$?
kill $DPID 2>/dev/null
echo "exit=$RC" >> "$OUT/edge-probe.txt"
exit $RC
