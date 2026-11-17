# StableBus backend: manual testing, diagnostics, load testing and PRD readiness

Version: 1.0  
Scope: FastAPI backend, AO Pay bus integration, Razorpay/mock payments, Redis cache, PostgreSQL, event/outbox workers and notifications.

> Use a dedicated AO Pay UAT registration and test bookings. Never run destructive cancellation load tests against production or real customer tickets. Never paste live API keys, IMEI values, guest tokens, payment signatures or cancellation keys into tickets/logs.

## 1. AO Pay cancellation and history integration

StableBus exposes its own API. It calls the existing AO Pay base URL from `AOPAY_BASE_URL` and retains the provider paths under `/api/V1/Bus/Travel/`.

| StableBus endpoint | AO Pay endpoint | Purpose |
|---|---|---|
| `POST /api/v1/bookings/{booking_id}/cancellation/charges` | `POST /api/V1/Bus/Travel/BusCancellationCharges` | Check selected seats and obtain the penalty plus short-lived `cancellationCharge_Key` |
| `POST /api/v1/bookings/{booking_id}/cancellation` | `POST /api/V1/Bus/Travel/BusCancellation` | Execute cancellation using the exact key and exact ticket list used for the quote |
| `POST /api/v1/bookings/provider-history` | `POST /api/V1/Bus/Travel/BusHistory` | Retrieve the provider's booking history |
| `GET /api/v1/bookings/history` | Local PostgreSQL | Existing authenticated StableBus customer history; this is not replaced by AO Pay history |

### Cancellation lifecycle

1. Authenticate the customer (or validate the guest booking access token).
2. Load the local booking and verify ownership. Only `CONFIRMED` bookings are eligible.
3. Resolve each requested seat to its stored `ticket_number`; use the booking's `temp_booking_ref` and `transport_pnr`. Do not trust ticket numbers or PNRs supplied by the mobile client.
4. Call `BusCancellationCharges`. Check `response_Header.error_Code == "0000"`, `cancellable == "true"`, and that a non-empty `cancellationCharge_Key` was returned. Show the returned per-seat penalties and service charge to the customer.
5. The customer confirms. Send the same seat/ticket/PNR selection and the exact key to `BusCancellation`.
6. A cancellation is accepted locally only when the provider header code is `0000` **and** `statuss` is the string `"True"` (case-insensitive check in code).
7. The local booking stores cancelled seat numbers. The booking becomes `CANCELLED` only when all seats are cancelled; after a partial cancellation it returns to `CONFIRMED`.
8. If the cancellation request times out or the response cannot be interpreted, local status remains `CANCELLATION_PENDING`. This is intentional: the provider may have completed the cancellation even though StableBus did not receive the response. Check AO Pay/provider history or contact AO Pay before retrying. Do not blindly submit the same cancellation again.

The charge key is a provider-issued authorization for a specific quote. Treat it as short-lived and sensitive. Do not log it, store it in analytics, or reuse it after a failed/expired attempt. Request a fresh quote when appropriate.

### Provider response interpretation

- HTTP success is not enough. Validate the provider's `response_Header.error_Code`.
- For the final cancellation also validate `statuss == "True"`. The published cancellation page's example shows `statuss: "FALSE"` even with `error_Code: "0000"`; therefore StableBus deliberately does not interpret header success alone as proof of cancellation. Confirm with AO Pay whether that example is a failure/diagnostic case and what final success payload should look like before production enablement.
- `cancellationPenaltyValues` is per seat/ticket; do not assume all seats have the same penalty.
- Provider `BusHistory` is an AO Pay-side view. StableBus's `/history` endpoint remains the app's local history source and should continue to be used for customer-specific records.
- The example payload contains masked IP and sample IMEI values. Runtime values must come from protected server configuration, never from the mobile app.

## 2. Environment and startup checks

Use a non-production environment first. Confirm these settings exist and point to UAT/test resources:

- `APP_ENV=development` (or `uat`)
- `AOPAY_BASE_URL` — provider host only, without the endpoint path
- `AOPAY_REGISTRATION_ID`
- `AOPAY_IP_ADDRESS` — the whitelisted static outbound IP
- `AOPAY_IMEI_NUMBER` — use the value approved by AO Pay
- `BUS_BOOKING_PROVIDER=MOCK` for local/mock booking/cancellation tests; `REAL` only for AO Pay UAT
- `PAYMENT_GATEWAY=MOCK` for local tests; `RAZORPAY` only with test-mode credentials in UAT
- `DATABASE_URL`, Redis configuration, CORS origins, JWT keys and notification credentials
- `LOG_LEVEL=INFO` in UAT/production; use `DEBUG` temporarily for a controlled investigation

Do not commit `.env`, private keys, certificates containing secrets, or logs with customer data. Rotate any credential that has been committed or shared unintentionally.

Start the app:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Check `GET /health` only if a health route is implemented in this deployment; otherwise use the OpenAPI page at `http://127.0.0.1:8000/docs` and a harmless authenticated API request. Confirm startup logs say the intended bus/payment providers are selected and all required dependencies initialized.

Apply the new migration before running the cancellation routes:

```bash
alembic heads
alembic upgrade head
alembic current
```

The migration adds `bookings.cancelled_seat_numbers`. Verify the column exists in PostgreSQL before testing partial cancellations. If `alembic heads` reports multiple heads, stop and resolve the migration graph with the team before applying production migrations; do not stamp blindly.

## 3. Postman manual acceptance flow

Create a Postman environment:

| Variable | Example |
|---|---|
| `base_url` | `http://127.0.0.1:8000` |
| `access_token` | Fresh StableBus access token |
| `guest_access_token` | Only for a guest booking flow |
| `booking_id` | StableBus UUID returned by create booking |
| `seat_1` | Seat string from the booking response |
| `cancellation_charge_key` | Key returned by cancellation quote |

For authenticated calls use `Authorization: Bearer {{access_token}}`. For a guest booking use `X-Guest-Access-Token: {{guest_access_token}}` instead. Never send both unless the route contract requires it.

### A. Booking prerequisites

Run the existing end-to-end booking flow first:

1. `GET {{base_url}}/api/v1/buses/cities`
2. `POST {{base_url}}/api/v1/buses/search` with `from_city`, `to_city`, and `travel_date`.
3. `POST {{base_url}}/api/v1/buses/seat-map` using the selected `bus_key`, `search_key`, `boarding_id`, and `dropping_id`.
4. `POST {{base_url}}/api/v1/bookings` with unique seats/passengers and an idempotency key.
5. `POST {{base_url}}/api/v1/bookings/{booking_id}/payments` with a unique payment idempotency key.
6. Complete the mock-payment route in development or Razorpay test checkout in UAT, then verify ticketing/requery until the booking is `CONFIRMED`.

Record `booking_id`, provider booking reference, transport PNR, seat numbers and ticket numbers from the confirmed booking. The cancellation route uses the server-side stored references.

### B. Quote cancellation charges

`POST {{base_url}}/api/v1/bookings/{{booking_id}}/cancellation/charges`

```json
{
  "seat_numbers": ["14"]
}
```

Expected: HTTP 200, `cancellable: "true"`, `response_Header.error_Code: "0000"`, a non-empty `cancellationCharge_Key`, and a `cancellationPenaltyValues` item for each requested seat. Save the returned key as `cancellation_charge_key` in Postman. Check that the penalty matches the provider response, not a hard-coded StableBus value.

Negative tests:

- Unknown seat -> HTTP 400.
- Duplicate seat in the request -> schema validation error.
- Already cancelled seat -> HTTP 409.
- Booking not confirmed / missing provider references -> HTTP 409.
- Provider says not cancellable or returns non-zero error code -> HTTP 409.
- Customer does not own booking / invalid guest token -> HTTP 404.

### C. Execute cancellation

`POST {{base_url}}/api/v1/bookings/{{booking_id}}/cancellation`

```json
{
  "seat_numbers": ["14"],
  "cancellation_charge_key": "{{cancellation_charge_key}}"
}
```

Expected: HTTP 200, provider header code `0000`, provider `statuss: "True"`, and the cancelled seat included in `cancelled_seat_numbers`. If all booked seats were selected, expect `booking_status: "CANCELLED"`; if only some were selected, expect `CONFIRMED` with the cancelled seats recorded.

Negative/edge tests:

- Reuse the same cancellation key -> provider/mock rejects it.
- Change the seat list after quoting -> provider/mock rejects mismatched selection.
- Try to cancel the same seat twice -> HTTP 409.
- Simulate AO Pay timeout after request submission -> expect HTTP 502 and local `CANCELLATION_PENDING`; verify provider status before retrying.
- Try a second cancellation while pending -> it must not be allowed.

### D. Provider booking history

`POST {{base_url}}/api/v1/bookings/provider-history`

```json
{
  "fromdate": "06/11/2025",
  "month": "06",
  "todate": "06/12/2025",
  "type": 0,
  "year": "2025"
}
```

Expected: `response_Header.error_Code == "0000"`; `busAvailableBookings` is an array. AO Pay documentation defines `fromdate`/`todate` as ticketing dates in `MM/DD/YYYY`, `type=0` as confirmed tickets and `type=1` as cancelled tickets. `month` is two digits and `year` is four digits; the StableBus request validates that month/year match the start date.

### E. Local booking history

`GET {{base_url}}/api/v1/bookings/history?limit=20&offset=0`

Expected: only the authenticated user's bookings, stable pagination, local cancellation state and passengers. Do not replace this endpoint with provider history without a product decision: the two histories have different ownership and data contracts.

## 4. Core functionality manual test matrix

| Area | Happy path | Failure/edge cases | Evidence to capture |
|---|---|---|---|
| OTP/auth | Request OTP, verify OTP, obtain tokens | Wrong/expired OTP, rate limit, expired access token, refresh replay, logout | Request ID, HTTP status, auth event logs (never OTP/token) |
| Cities | Cache miss fetches AO Pay; next request hits Redis | Redis down, malformed cache, provider timeout, stale-cache fallback | Cache hit/miss, provider duration, city count |
| Search | Search route/date returns buses and search key | Invalid city/date, no buses, provider error, timeout, cache corruption | Request ID, route/date identifiers, result count, latency |
| Seat map | Fetch current seat map and select available seats | Stale search key, sold seat, invalid boarding/drop point | Bus identifier, response code, seat count |
| Temporary booking | Hold selected seats | Duplicate idempotency key, seat unavailable, provider rejects | StableBus booking ID, provider reference, state transition |
| Payment | Create payment order and verify signature | Duplicate initiate, bad signature, failed/late webhook, gateway timeout | Payment ID, gateway order/payment ID, state transition |
| Ticketing | Confirm payment then ticket and requery | Provider pending, ticketing failure, timeout/unknown, duplicate request | Booking ID, provider reference, PNR, requery outcome |
| Cancellation quote | Obtain per-seat penalties and key | Invalid seat, expired/invalid booking, non-cancellable booking | Selected seats, penalty result, provider code (never key) |
| Cancellation | Confirm cancellation and update local state | Reused key, partial cancellation, timeout/unknown outcome | Cancelled seats, booking state, provider confirmation |
| History | Local and provider history return expected records | Empty range, large range, provider error, unauthorised local history | Counts, pagination, provider response code |
| Notifications | Booking confirmation delivered once | Provider down, duplicate event, retry/dead-letter | Outbox event ID, delivery attempt/status |
| Refunds | Refund request and reconciliation | Partial/full refund, duplicate idempotency, pending/unknown | Refund ID, payment ID, gateway refund ID/status |

For each test, record: environment, app build/commit, test user, booking ID, request ID, exact request timestamp, expected result, actual result, logs, and defect ID. Mask mobile numbers and tokens.

## 5. Logging and how to debug

Every HTTP request should have an `X-Request-ID` response header and the same ID in application logs. When reporting an issue, start with this ID and timestamp.

### Log levels

- `DEBUG`: cache hits, cache bookkeeping and internal branch diagnostics. Enable only during focused investigations.
- `INFO`: request completion, provider operation completion, state transitions, event publication and worker lifecycle.
- `WARNING`: expected business rejections, stale cache fallback, retryable dependency degradation.
- `ERROR`/`EXCEPTION`: unexpected failures with stack trace and enough identifiers to locate the failed operation.

### Diagnostic sequence

1. Find the API request log by `request_id` and inspect method, route, status and duration.
2. Follow the same request ID to the service/adaptor log.
3. If AO Pay was called, inspect endpoint, provider request ID, HTTP status, provider error code and duration. Do not log full request/response payloads.
4. If provider response is successful but app state is wrong, inspect the booking/payment/refund repository operation and transaction commit.
5. For delayed notifications, inspect outbox event state, publisher/consumer logs and notification delivery record.
6. For latency, compare API duration with AO Pay duration, Redis duration and DB query duration. A slow upstream and a slow local DB require different fixes.

### Sensitive fields that must never be logged

Access/refresh tokens, OTPs, passwords, JWT/private keys, Razorpay signatures/secrets, cancellation charge keys, full passenger names/DOBs, full mobile numbers, complete provider payloads, and payment card/bank data. Log internal booking/payment IDs and masked identifiers only where needed.

### Expected high-value error context

A useful error log answers: which operation, which internal booking/payment ID, which provider endpoint, which request ID, provider error code (if available), duration, and exception stack. Avoid logging giant search payloads or every seat in a seat map.

## 6. Load and soak testing

### Important safety rule

Do not generate load against real booking, ticketing, payment, cancellation or refund endpoints. Those create irreversible provider and financial side effects. Use the mock booking/payment adapters and isolated test database for workflow load tests. For AO Pay UAT, obtain written permission and an agreed request rate; use read-only search/history first and keep cancellation to a few controlled test bookings.

### k6 install and baseline

Install k6 on the load-test machine, start StableBus with mock booking/payment providers, and use a dedicated database/Redis namespace. First establish a 5-minute baseline at 1 virtual user, then 5, 10, 25 and 50 VUs. Increase only while error rate, latency, DB pool, Redis and CPU remain healthy.

Example read/search load script (`load/search.js`):

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errors = new Rate('http_errors');
const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const FROM = __ENV.FROM_CITY;
const TO = __ENV.TO_CITY;
const DATE = __ENV.TRAVEL_DATE;

export const options = {
  scenarios: {
    search: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '2m', target: 5 },
        { duration: '3m', target: 10 },
        { duration: '3m', target: 25 },
        { duration: '2m', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1500', 'p(99)<3000'],
    http_errors: ['rate<0.01'],
  },
};

export default function () {
  const res = http.post(`${BASE}/api/v1/buses/search`, JSON.stringify({
    from_city: FROM,
    to_city: TO,
    travel_date: DATE,
  }), { headers: { 'Content-Type': 'application/json' } });
  const ok = check(res, { 'search HTTP 200': r => r.status === 200 });
  errors.add(!ok);
  sleep(1);
}
```

Run:

```bash
k6 run -e BASE_URL=http://127.0.0.1:8000 \
  -e FROM_CITY=3 -e TO_CITY=5 -e TRAVEL_DATE=11/20/2026 load/search.js
```

The p95/p99 thresholds above are initial test targets, not proven StableBus capacity or an SLA. Adjust them after measuring real UAT baseline and user experience. If search cache is active, run two distinct tests: cache-warm repeated route/date requests and cache-cold/high-cardinality route/date requests. The latter is more likely to expose AO Pay rate limits and upstream bottlenecks.

### Workflow load test

Build a separate k6 script against the MOCK provider and a seeded isolated database. Use unique user/booking/idempotency keys per VU. Exercise create booking -> mock payment -> ticket confirmation -> cancellation quote -> cancellation, but keep the test dataset disposable and ensure each VU owns its own booking. Do not share cancellation keys between VUs. Use a fixed, finite number of iterations rather than an infinite loop.

### Test stages

1. Smoke: 1 VU, 1 minute; all APIs reachable.
2. Baseline: 5 VUs, 5 minutes.
3. Ramp: 5 -> 10 -> 25 -> 50 VUs, 3-5 minutes per stage.
4. Stress: increase by 25% only after the previous stage is stable; stop on sustained errors or resource saturation.
5. Spike: a short 2x increase to observe queueing/recovery.
6. Soak: expected peak concurrency for 1-4 hours to find leaks, pool exhaustion and worker backlog.
7. Recovery: return to zero/low load and confirm latency, queues and DB connections return to baseline.

### Monitor during the run

- API: request rate, 4xx/5xx, p50/p95/p99 latency, in-flight requests.
- Python: CPU, RSS, event-loop lag, thread count, worker restarts.
- PostgreSQL: active/idle connections, pool wait, slow queries, locks, deadlocks, CPU, IOPS and storage.
- Redis: memory, evictions, hit ratio, command latency, connection count.
- AO Pay: request rate, timeout/error rate, latency and any provider throttling.
- Outbox/notifications: pending event count, oldest event age, retry count, consumer lag.

### Interpreting failures

- p95 increases while AO Pay duration increases: upstream latency/rate limit; use bounded timeouts, retry only safe/idempotent reads, and provider-approved rate limits.
- p95 increases while AO Pay duration is flat: inspect Python CPU, DB pool waits, serialization and synchronous blocking work.
- DB pool exhausted: inspect leaked sessions/long transactions and pool sizing; do not blindly increase pool size beyond PostgreSQL capacity.
- Redis errors with stable API latency: cache fallback may be masking dependency failure; alert on Redis degradation, not just HTTP 500s.
- Outbox age grows: publisher/consumer throughput or downstream notification failures; inspect retry policy and dead-letter/manual replay process.
- Memory grows during soak: inspect unbounded caches, large response retention and worker lifecycle.

## 7. Where StableBus can break as traffic grows

Capacity cannot be honestly stated as a single requests-per-second number from source code alone. It depends on Lightsail CPU/RAM, Uvicorn worker count, database pool, Redis plan, AO Pay rate limits, payload size and request mix. Measure the actual deployment using the stages above.

Likely pressure points to validate:

1. **AO Pay is an external dependency.** Search, seat map, booking and cancellation are bounded by provider latency, concurrency and rate limits. A larger StableBus server cannot remove provider limits.
2. **Synchronous `requests` calls.** AO Pay calls block the FastAPI worker thread. Under high concurrent upstream latency, worker/thread capacity becomes a bottleneck. Consider an async HTTP client or a bounded thread pool after profiling.
3. **Single Lightsail instance.** CPU/RAM/network and process restarts create a single failure domain. Use health checks, restart policy, backups and a tested recovery procedure.
4. **PostgreSQL connection pool.** Too many Uvicorn workers multiplied by per-worker pool size can exceed the DB connection limit. Set an explicit pool budget and monitor pool wait.
5. **Redis cache metadata.** Search cache metadata updates can contend under concurrent cache hits. Verify atomicity and race behaviour under load; Redis is an optimization, not the source of truth.
6. **Large bus-search responses.** Large JSON responses increase upstream time, parsing, memory, serialization and mobile transfer time. Track response bytes and avoid logging full payloads.
7. **Outbox and event consumers.** A background publisher/consumer can fall behind; alert on oldest pending event and provide safe replay/dead-letter handling.
8. **Booking/cancellation concurrency.** Two operations against the same booking must not race. Add DB row locking/optimistic versioning and provider reconciliation for ambiguous timeouts before production scale.
9. **Cancellation pending state.** The current API intentionally blocks blind retries when provider outcome is unknown. A production operations process/job is still needed to reconcile `CANCELLATION_PENDING` records and close them safely.
10. **Observability volume.** INFO logs on every cache operation can overwhelm useful events. Keep high-cardinality details and cache bookkeeping at DEBUG; use metrics for counts and latency.

## 8. Production acceptance checklist

### Provider and booking
- [ ] AO Pay UAT credentials, static IP whitelist and registration ID confirmed.
- [ ] All endpoint paths, request field casing, date formats and response semantics confirmed by AO Pay.
- [ ] City/search/seat-map/temp-book/ticket/requery happy and failure paths pass.
- [ ] Search and seat-map data are not treated as a seat reservation; provider is revalidated at booking time.
- [ ] Idempotency and duplicate booking protections tested with concurrent requests.
- [ ] Provider timeout/unknown ticketing outcomes have an operational reconciliation path.

### Cancellation and history
- [ ] Migration applied and verified in staging and production plan.
- [ ] Quote response is validated; per-seat penalty and service charge shown before confirmation.
- [ ] Final cancellation requires both provider error code `0000` and `statuss == "True"`.
- [ ] Partial cancellation and full cancellation are tested.
- [ ] Reused/expired key and changed ticket selection are rejected.
- [ ] Timeout leaves a visible pending state and support runbook tells staff how to reconcile it.
- [ ] Refund amount equals eligible paid amount minus provider cancellation penalties/approved fees; this financial calculation and Razorpay refund flow must be implemented/tested separately if not already wired.
- [ ] Provider history and local customer history are clearly distinguished.
- [ ] AO Pay confirms the meaning of `type` in BusHistory and the cancellation key expiry/validity rules.

### Payments and money movement
- [ ] Razorpay test and live credentials separated; webhook signature verified.
- [ ] Duplicate payment verification/webhook does not double-confirm or double-refund.
- [ ] Payment reconciliation worker, refund reconciliation worker and manual review paths tested.
- [ ] Refunds reconcile with gateway state; no refund is inferred solely from bus cancellation success.
- [ ] Daily booking/payment/refund settlement reconciliation process and owner defined.

### Security and privacy
- [ ] HTTPS enforced; CORS allowlist contains only actual app origins.
- [ ] JWT secrets/private keys and provider credentials stored outside source control.
- [ ] Guest token access, user ownership and rate limiting tested.
- [ ] PII and secrets redacted from logs, analytics and error responses.
- [ ] Dependency and OS patching, secret rotation and access reviews scheduled.
- [ ] Database backups encrypted; restore drill completed.

### Reliability and operations
- [ ] Structured request-correlated logs and dashboards/alerts deployed.
- [ ] Alerts cover 5xx, p95/p99, provider timeouts, DB pool saturation, Redis failures, pending cancellations, refund backlog and outbox age.
- [ ] Process supervisor/restart policy and server reboot recovery tested.
- [ ] Database migrations rehearsed with backup and rollback plan.
- [ ] Load, spike, soak and recovery tests pass against agreed targets.
- [ ] AO Pay UAT and production rate limits documented.
- [ ] Support runbooks exist for booking pending, ticketing unknown, cancellation pending, refund pending and notification failure.
- [ ] Customer support channel, escalation owner and provider escalation contacts assigned.

### Release gate
- [ ] No open P0/P1 defects.
- [ ] All critical manual acceptance cases pass on the release candidate.
- [ ] Regression suite passes in CI.
- [ ] Staging smoke test and rollback rehearsal completed.
- [ ] Production feature flags/provider mode/payment mode verified before enabling traffic.
- [ ] First-day launch monitoring owner and go/no-go approver named.

## 9. Known integration boundaries / follow-up engineering

- `BusHistory` is registration-wide at the provider. The StableBus route filters its results to the authenticated user's mobile number before returning them. The current local `/api/v1/bookings/history` endpoint is retained; the app should not silently switch to AO Pay's data contract.
- AO Pay cancellation success does not itself issue a Razorpay refund. Refund calculation, refund initiation and refund reconciliation must remain a separate money-movement workflow.
- The cancellation route records cancelled seat numbers and booking status. A durable per-seat cancellation ledger with penalty, service charge, provider response, refund linkage and audit timestamps is recommended before handling meaningful production volume.
- `CANCELLATION_PENDING` requires an operational reconciliation worker/process. Do not automatically retry a non-idempotent provider cancellation until AO Pay confirms the operation's idempotency semantics.
- Confirm with AO Pay whether `booking_RefNo` must be the temp booking reference or a different final reference for cancellation/history. The current adapter uses the local booking's stored `temp_booking_ref`, matching the provider's booking reference used by ticketing/requery in this codebase.


## Reviews, ratings, pre-registration and OTP lifetime (17 Nov 2026)

### OTP lifetime
- `POST /api/v1/auth/send-otp` now reports `expires_in: 300`.
- Redis stores the OTP for 300 seconds (5 minutes). Failed-attempt limits and single-use verification remain unchanged.

### Reviews and ratings
- `POST /api/v1/reviews/bookings/{booking_id}` accepts `{ "rating": 1..5, "comment": "optional text" }`.
- The caller must own the booking (authenticated user) or supply its guest access token in `X-Guest-Access-Token`.
- The booking must be `CONFIRMED`, and its journey date must have passed. One review per booking is enforced by a database unique constraint.
- `GET /api/v1/reviews/buses/{bus_id}` returns the latest 100 reviews and aggregate average/count for that provider bus ID.
- Important limitation: this code snapshot does not persist an authoritative AO Pay operator ID or a provider-confirmed trip-completion event. Eligibility is therefore based on a confirmed booking whose journey date has passed, and ratings aggregate by provider `bus_id`, not by operator. Before presenting this as a verified operator rating, capture the provider's stable operator identifier and completion signal.

### Pre-registration
- `POST /api/v1/preregistrations` accepts `mobile` and `email` (both mandatory), plus optional `name` and `city`.
- Mobile numbers are validated as 10-digit Indian mobile numbers. Emails are trimmed and lowercased.
- Mobile and email are individually unique; duplicate registration returns HTTP 409.

### Database migration
- New Alembic revision: `9f3c2a7b1d40_add_reviews_and_pre_registered_users.py`.
- Run `alembic upgrade head` after taking a database backup. Confirm `alembic heads` reports one head before deployment.
