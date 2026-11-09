
import logging

from core.logging_config import LoggingConfig

LoggingConfig.setup_logging()

logger = logging.getLogger("stablebus.test")

logger.info("StableBus logging initialized")
logger.warning("Sample warning")
logger.error("Sample error")

print("Logging test completed")
