# StableBus backend update — notifications, wallet, trip stats

Unzip this over your project root (same folder layout; 18 files, 6 are new).

## Run (in this order)
1. Add to .env:
   ADMIN_API_KEY=<random string, 16+ chars>      # protects /api/v1/admin/*
   # optional: EXPO_ACCESS_TOKEN=..., WALLET_WORKER_INTERVAL_SECONDS=900,
   #           WALLET_WORKER_ENABLED=true (default)
   CANCELLATION_PENALTY_MODE=amount   # or 'percent' - see Cancellation refunds
2. alembic upgrade head      # creates wallet_lots, wallet_transactions, payments.coins_used/coin_value
3. Restart the API.

(No new pip packages.)

## 1. Notifications
Root causes fixed: with EVENT_TRANSPORT=direct the push handler was never registered;
BookingNotificationHandler.py had an IndentationError (broke kafka mode);
dead tokens retried forever.

Send a custom notification:
  POST /api/v1/admin/notifications/send     header: X-Admin-Key: <ADMIN_API_KEY>
  {"title":"Diwali offer","body":"Flat 10% off","broadcast":true}
  {"title":"Hi","body":"...","user_ids":["12","57"]}
  {"title":"Hi","body":"...","mobile_numbers":["9876543210"],"data":{"route":"/offers"}}
Optional "platform":"android"|"ios". Exactly one of user_ids / mobile_numbers / broadcast.

## 2. Wallet
GET  /api/v1/wallet                    -> {coins, rupee_value, next_expiry}
GET  /api/v1/wallet/transactions?limit&offset
POST /api/v1/bookings/{id}/payments    body adds  "coins_to_use": <int>   (default 0)
     response: amount (cash), coins_used, coin_value, gateway, status
     If coins cover 100%: gateway="WALLET", status="SUCCESS", booking_status="PAYMENT_VERIFIED"
     -> app must skip Razorpay and go straight to ticketing.
POST /api/v1/admin/wallet/credit       {user_id, coins, reason, reference}
POST /api/v1/admin/wallet/run-jobs

Rules: earn floor(total x 2.5% / 0.25) coins once the trip date has passed (IST) and the
booking is CONFIRMED; none for cancelled tickets; partial cancellations earn pro-rata;
lots expire 1 Jan 00:00 IST; spending uses the soonest-expiring coins first.
Backend checks cash + coins x 0.25 == ticket price at payment creation AND at verify.

## 3. Trips
GET /api/v1/users/me/trips/stats?days=30
 -> {total_completed_trips, days, completed_trips_in_period, since}

## 4. Other fixes
- /test-error and /debug/routes are not registered when APP_ENV=production
- removed the duplicate (overridden) reconcile_refund in PaymentService
- BOOKING_CONFIRMED event now carries operator_name and bus_id

## 5. Cancellation refunds (cash + coins)
POST /api/v1/bookings/{id}/cancellation now refunds automatically and returns
  "refund": {refund_amount, refund_cash, refund_coins, cancellation_charge, status}
refund = (total / seats x cancelled seats) - provider cancellation charge
split in the ratio the customer paid: coin share -> coins back to wallet (original
expiry kept if still valid), cash share -> gateway refund to the original method.
Idempotent; a refund failure never fails the cancellation (status FAILED_NEEDS_REVIEW + log).
IMPORTANT: AO Pay's `cancellation_Penalty` unit is not documented in your code. Default
treats it as rupees per ticket; set CANCELLATION_PENALTY_MODE=percent if it is a percentage.
Assumes equal fare per seat (seat fares are not stored per passenger).

## Partial cancellation earning
A booking of 4 seats, Rs 2000, 1 seat cancelled: coins are earned on 3/4 of the price
(Rs 1500 x 2.5% = Rs 37.5 -> 150 coins). All cancelled: 0 coins.
