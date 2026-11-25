"""Wallet background worker.

Run as a separate process (like the other workers):

    python -m Workers.wallet_worker

It credits coins for completed trips, expires coins on 1 January and
releases coins held by failed payments. Safe to run on several instances:
every operation is idempotent.
"""
import logging
import os
import time

from dotenv import load_dotenv

from core.logging_config import LoggingConfig
from Services.Wallet.WalletJobs import run_wallet_jobs

logger = logging.getLogger("stablebus.wallet.worker")


def main():
    load_dotenv()
    LoggingConfig.setup_logging()
    interval = int(os.getenv("WALLET_WORKER_INTERVAL_SECONDS", "900"))
    logger.info("Wallet worker started interval=%ss", interval)
    while True:
        try:
            summary = run_wallet_jobs()
            logger.info("Wallet jobs finished %s", summary)
        except Exception:
            logger.exception("Wallet jobs iteration failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
