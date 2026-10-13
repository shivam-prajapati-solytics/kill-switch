# Manual acceptance tests
1. Safe query returns 200 and a response.
2. `customer record` with role `general` returns 403 and exposes no email/phone.
3. Global kill returns `KILLED`; subsequent agent queries return 503.
4. Wrong admin token returns 401 for kill/status/reset.
5. Reset returns `ENABLED`; safe query works again.
6. Stop Redis: agent query returns 503 (fail closed).
7. Multiple Django workers all observe global kill state.
8. Verify logs contain no raw response body or PII.
