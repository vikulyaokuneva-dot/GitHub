# Architecture Rules

- Only `v2` is allowed to call WB API endpoints.
- All new modules read JSON inputs and write JSON outputs.
- Daily mode uses D-1 report date (Europe/Berlin policy).
- Reporting must not recalculate business data; it only assembles output from analytics JSON.

