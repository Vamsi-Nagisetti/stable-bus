
import logging
from contextlib import asynccontextmanager
from api.routes.auth import router as auth_router
from api.routes.users import router as users_router
from fastapi import FastAPI
from Management.SessionManagement import SessionManagement
from core.logging_config import LoggingConfig
from api.middleware.request_logging import RequestLoggingMiddleware

from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor
from Services.OTP.FAST2SMS_OTP_Service import Fast2SMSOTPService
from Factories.AuthDependencyFactory import AuthDependencyFactory


# Initialize logging before creating application dependencies
LoggingConfig.setup_logging()

logger = logging.getLogger("stablebus.main")


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting StableBus application")

    redis_adaptee = None

    try:
        # 1. Initialize Redis connection
        redis_adaptee = RedisCacheAdaptee()

        # 2. Create cache adaptor
        cache = RedisCacheAdaptor(redis_adaptee)

        # 3. Initialize OTP service
        otp_service = Fast2SMSOTPService()

        # 4. Create authentication dependency factory
        auth_factory = AuthDependencyFactory(
            cache=cache,
            otp_service=otp_service
        )
        app.state.auth_orchestrator = auth_factory.get_auth_orchestrator()

        # Initialize JWT session management once
        session_management = SessionManagement()
        app.state.session_management = session_management


        app.state.redis_adaptee = redis_adaptee

        logger.info("StableBus dependencies initialized successfully")

        yield

    except Exception:
        logger.exception("StableBus application startup/runtime failure")
        raise

    finally:
        if redis_adaptee is not None:
            redis_adaptee.close()
            logger.info("Redis connection closed")

        logger.info("StableBus application shutdown completed")


# Create FastAPI application
app = FastAPI(
    title="StableBus API",
    description="Backend APIs for StableBus bus booking platform",
    version="1.0.0",
    lifespan=lifespan
)
app.include_router(auth_router)
app.include_router(users_router)

logger.info("StableBus application initialized")


@app.get("/health", tags=["Health"])
def health_check():
    logger.info("Health check requested")

    return {
        "status": "UP",
        "application": "StableBus",
        "message": "Application is running successfully"
    }


@app.get("/test-error", tags=["Testing"])
def test_error():
    logger.info("Testing exception logging")
    raise RuntimeError("StableBus test exception")


# Register middleware
app = RequestLoggingMiddleware(app)
