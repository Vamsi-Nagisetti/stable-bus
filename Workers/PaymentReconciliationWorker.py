
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from core.database import SessionLocal
from models.Payment import Payment
from models.Refund import Refund

from Repositories.PaymentRepository import PaymentRepository
from Repositories.RefundRepository import RefundRepository
from Repositories.BookingRepository import BookingRepository
from Repositories.PaymentCacheRepository import PaymentCacheRepository

from Services.Payments.PaymentService import PaymentService


logger = logging.getLogger("stablebus.payment_reconciliation")


class PaymentReconciliationWorker:

    RETRY_DELAYS_SECONDS = (
        60,
        300,
        900,
        1800,
        3600,
        10800,
    )

    TERMINAL_STATUSES = {
        "SUCCESS",
        "FAILED",
        "MANUAL_REVIEW",
    }

    def __init__(
        self,
        payment_provider,
        cache,
        gateway_name: str,
        session_factory=SessionLocal,
        interval_seconds: int = 30,
        batch_size: int = 5,
        lease_seconds: int = 600,
    ):
        self.payment_provider = payment_provider
        self.cache = cache
        self.gateway_name = gateway_name
        self.session_factory = session_factory
        self.interval_seconds = interval_seconds
        self.batch_size = batch_size
        self.lease_seconds = lease_seconds

    def _create_service(self, db):
        return PaymentService(
            payment_provider=self.payment_provider,
            payment_repository=PaymentRepository(db),
            booking_repository=BookingRepository(db),
            payment_cache_repository=PaymentCacheRepository(
                self.cache
            ),
            refund_repository=RefundRepository(db),
            gateway_name=self.gateway_name,
        )

    def _next_retry_at(self, attempts: int) -> datetime:
        index = min(
            max(attempts - 1, 0),
            len(self.RETRY_DELAYS_SECONDS) - 1,
        )

        return datetime.now(timezone.utc) + timedelta(
            seconds=self.RETRY_DELAYS_SECONDS[index]
        )

    def _claim_batch(self):
        db = self.session_factory()

        try:
            payment_ids = [
                payment.id
                for payment in PaymentRepository(
                    db
                ).claim_due_for_reconciliation(
                    limit=self.batch_size,
                    lease_seconds=self.lease_seconds,
                )
            ]

            refund_ids = [
                refund.id
                for refund in RefundRepository(
                    db
                ).claim_due_for_reconciliation(
                    limit=self.batch_size,
                    lease_seconds=self.lease_seconds,
                )
            ]

            # Release row locks while retaining reconciliation leases.
            db.commit()

            return payment_ids, refund_ids

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()

    def _process_payment(self, payment_id: str):
        db = self.session_factory()

        try:
            repository = PaymentRepository(db)
            service = self._create_service(db)

            payment = repository.get_by_id(payment_id)

            if payment is None:
                return

            if payment.status in self.TERMINAL_STATUSES:
                return

            service.reconcile_payment(payment_id)

            payment = repository.get_by_id(payment_id)

            if payment is None:
                return

            if payment.status in self.TERMINAL_STATUSES:
                db.commit()
                return

            now = datetime.now(timezone.utc)

            if payment.reconciliation_deadline_at <= now:
                repository.mark_manual_review(
                    payment_id,
                    "Payment reconciliation deadline exceeded",
                )
            else:
                repository.schedule_reconciliation(
                    payment_id,
                    self._next_retry_at(
                        payment.reconciliation_attempts
                    ),
                )

            db.commit()

        except Exception as exc:
            db.rollback()

            logger.exception(
                "Payment reconciliation failed: %s",
                payment_id,
            )

            try:
                payment = PaymentRepository(db).get_by_id(payment_id)

                if payment is not None:
                    now = datetime.now(timezone.utc)

                    if payment.status not in self.TERMINAL_STATUSES:
                        if payment.reconciliation_deadline_at <= now:
                            PaymentRepository(db).mark_manual_review(
                                payment_id,
                                str(exc),
                            )
                        else:
                            PaymentRepository(db).schedule_reconciliation(
                                payment_id,
                                self._next_retry_at(
                                    payment.reconciliation_attempts
                                ),
                                error=str(exc),
                            )

                        db.commit()

            except Exception:
                db.rollback()
                logger.exception(
                    "Failed to schedule payment retry: %s",
                    payment_id,
                )

        finally:
            db.close()

    def _process_refund(self, refund_id: str):
        db = self.session_factory()

        try:
            repository = RefundRepository(db)
            service = self._create_service(db)

            refund = repository.get_by_id(refund_id)

            if refund is None:
                return

            if refund.status in self.TERMINAL_STATUSES:
                return

            service.reconcile_refund(refund_id)

            refund = repository.get_by_id(refund_id)

            if refund is None:
                return

            if refund.status in self.TERMINAL_STATUSES:
                db.commit()
                return

            now = datetime.now(timezone.utc)

            if refund.reconciliation_deadline_at <= now:
                repository.mark_manual_review(
                    refund_id,
                    "Refund reconciliation deadline exceeded",
                )
            else:
                repository.schedule_reconciliation(
                    refund_id,
                    self._next_retry_at(
                        refund.reconciliation_attempts
                    ),
                )

            db.commit()

        except Exception as exc:
            db.rollback()

            logger.exception(
                "Refund reconciliation failed: %s",
                refund_id,
            )

            try:
                refund = RefundRepository(db).get_by_id(refund_id)

                if refund is not None:
                    now = datetime.now(timezone.utc)

                    if refund.status not in self.TERMINAL_STATUSES:
                        if refund.reconciliation_deadline_at <= now:
                            RefundRepository(db).mark_manual_review(
                                refund_id,
                                str(exc),
                            )
                        else:
                            RefundRepository(db).schedule_reconciliation(
                                refund_id,
                                self._next_retry_at(
                                    refund.reconciliation_attempts
                                ),
                                error=str(exc),
                            )

                        db.commit()

            except Exception:
                db.rollback()
                logger.exception(
                    "Failed to schedule refund retry: %s",
                    refund_id,
                )

        finally:
            db.close()

    def _expire_overdue_records(self):
        db = self.session_factory()

        try:
            now = datetime.now(timezone.utc)

            payments = list(
                db.scalars(
                    select(Payment)
                    .where(
                        Payment.status.in_(
                            PaymentRepository.RECONCILABLE_STATUSES
                        ),
                        Payment.reconciliation_deadline_at <= now,
                        or_(
                            Payment.reconciliation_locked_until.is_(None),
                            Payment.reconciliation_locked_until <= now,
                        ),
                    )
                    .limit(self.batch_size)
                    .with_for_update(skip_locked=True)
                ).all()
            )

            refunds = list(
                db.scalars(
                    select(Refund)
                    .where(
                        Refund.status.in_(
                            RefundRepository.RECONCILABLE_STATUSES
                        ),
                        Refund.reconciliation_deadline_at <= now,
                        or_(
                            Refund.reconciliation_locked_until.is_(None),
                            Refund.reconciliation_locked_until <= now,
                        ),
                    )
                    .limit(self.batch_size)
                    .with_for_update(skip_locked=True)
                ).all()
            )

            for payment in payments:
                payment.status = "MANUAL_REVIEW"
                payment.reconciliation_locked_until = None
                payment.last_reconciliation_error = (
                    "Payment reconciliation deadline exceeded"
                )

            for refund in refunds:
                refund.status = "MANUAL_REVIEW"
                refund.reconciliation_locked_until = None
                refund.last_reconciliation_error = (
                    "Refund reconciliation deadline exceeded"
                )

            db.commit()

            if payments or refunds:
                logger.warning(
                    "Moved overdue records to MANUAL_REVIEW: "
                    "%s payments, %s refunds",
                    len(payments),
                    len(refunds),
                )

        except Exception:
            db.rollback()
            logger.exception(
                "Failed to process overdue reconciliations"
            )

        finally:
            db.close()

    def run_once(self):
        payment_ids, refund_ids = self._claim_batch()

        for payment_id in payment_ids:
            self._process_payment(payment_id)

        for refund_id in refund_ids:
            self._process_refund(refund_id)

        self._expire_overdue_records()

        if payment_ids or refund_ids:
            logger.info(
                "Reconciliation batch completed: "
                "%s payments, %s refunds",
                len(payment_ids),
                len(refund_ids),
            )

    async def run_forever(self):
        logger.info("Payment reconciliation worker started")

        while True:
            try:
                await asyncio.to_thread(self.run_once)

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Payment reconciliation worker iteration failed"
                )

            await asyncio.sleep(self.interval_seconds)
