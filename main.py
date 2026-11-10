
import logging
import os
from contextlib import asynccontextmanager
from Adaptors.Notifications.ResendEmailAdapter import ResendEmailAdapter
from Services.Notifications.NotificationService import NotificationService
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from api.routes.auth import router as auth_router
from api.routes.users import router as users_router
from api.routes.buses import router as buses_router
from api.routes.passengers import router as passengers_router
from api.routes.Booking import router as bookings_router

from Management.SessionManagement import SessionManagement
from core.logging_config import LoggingConfig
from api.middleware.request_logging import RequestLoggingMiddleware

from Adaptors.Cache.RedisCacheAdaptee import RedisCacheAdaptee
from Adaptors.Cache.RedisCacheAdaptor import RedisCacheAdaptor

from Adaptors.AOPayBusAPI.AOPayAdaptee import AOPayAdaptee
from Adaptors.AOPayBusAPI.AOPayAdapter import AOPayAdapter
from Adaptors.AOPayBusAPI.MockAOPayBookingAdaptee import (
    MockAOPayAdaptee,
)

from Adaptors.Payments.MockPaymentAdapter import MockPaymentAdapter
from Adaptors.Payments.RazorpayAdapter import RazorpayAdapter

from Services.OTP.FAST2SMS_OTP_Service import Fast2SMSOTPService
from Services.Bus.bus_service import BusService

from Factories.AuthDependencyFactory import AuthDependencyFactory
from Adaptors.Databases.DynamoDBAdaptee import DynamoDBAdaptee


LoggingConfig.setup_logging()

logger = logging.getLogger("stablebus.main")


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting StableBus application")

    redis_adaptee = None
    dynamodb_adaptee = None
    payment_provider = None
    notification_service = None

    try:
        # 1. Initialize Redis
        redis_adaptee = RedisCacheAdaptee()

        # 2. Initialize DynamoDB
        dynamodb_adaptee = DynamoDBAdaptee()
        app.state.dynamodb = dynamodb_adaptee.get_table()

        # 3. Initialize cache adaptor
        cache = RedisCacheAdaptor(redis_adaptee)
        app.state.cache = cache

        # 4. Initialize OTP service
        otp_service = Fast2SMSOTPService()

        # 5. Initialize authentication
        auth_factory = AuthDependencyFactory(
            cache=cache,
            otp_service=otp_service,
        )

        app.state.auth_orchestrator = (
            auth_factory.get_auth_orchestrator()
        )

        # 6. Initialize session management
        app.state.session_management = SessionManagement()

        # 7. Initialize real AO Pay provider
        aopay_adaptee = AOPayAdaptee(
            base_url=os.environ["AOPAY_BASE_URL"],
            timeout=30,
        )

        # 8. Select booking provider
        booking_provider_mode = os.getenv(
            "BUS_BOOKING_PROVIDER",
            "MOCK",
        ).upper()

        if booking_provider_mode not in {"MOCK", "REAL"}:
            raise ValueError(
                "BUS_BOOKING_PROVIDER must be MOCK or REAL"
            )

        app_env = os.getenv("APP_ENV", "development").lower()

        if app_env == "production" and booking_provider_mode == "MOCK":
            raise ValueError(
                "Mock bus booking provider is not allowed in production"
            )

        booking_adaptee = None

        if booking_provider_mode == "MOCK":
            booking_adaptee = MockAOPayAdaptee()
            logger.warning("Using MOCK AO Pay booking provider")

        else:
            logger.info("Using REAL AO Pay booking provider")

        # 9. Create AO Pay adapter.
        # Search and seat map always use real AO Pay.
        # Only booking methods use the selected booking adaptee.
        aopay_adapter = AOPayAdapter(
            adaptee=aopay_adaptee,
            registration_id=os.environ["AOPAY_REGISTRATION_ID"],
            ip_address=os.environ["AOPAY_IP_ADDRESS"],
            imei_number=os.environ["AOPAY_IMEI_NUMBER"],
            booking_adaptee=booking_adaptee,
        )

        app.state.booking_adapter = aopay_adapter

        # 10. Initialize Bus Service with real AO Pay
        app.state.bus_service = BusService(
            bus_provider=aopay_adapter,
            cache=cache,
        )

        # 11. Select payment provider
        payment_gateway = os.getenv(
            "PAYMENT_GATEWAY",
            "MOCK",
        ).upper()

        if payment_gateway == "MOCK":
            if app_env == "production":
                raise ValueError(
                    "Mock payment provider is not allowed in production"
                )

            payment_provider = MockPaymentAdapter()
            logger.warning("Using MOCK payment provider")

        elif payment_gateway == "RAZORPAY":
            payment_provider = RazorpayAdapter()
            logger.info("Using RAZORPAY payment provider")

        else:
            raise ValueError(
                "PAYMENT_GATEWAY must be MOCK or RAZORPAY"
            )

        app.state.payment_provider = payment_provider
        app.state.payment_gateway_name = payment_gateway

        # 12. Initialize email notification service
        notification_provider = ResendEmailAdapter()
        notification_service = NotificationService(notification_provider)

        app.state.notification_service = notification_service

        logger.info("Resend email notification service initialized")

        # 13. Store Redis reference
        app.state.redis_adaptee = redis_adaptee

        logger.info(
            "StableBus dependencies initialized successfully"
        )

        yield

    except Exception:
        logger.exception(
            "StableBus application startup/runtime failure"
        )
        raise

    finally:
        if payment_provider is not None:
            payment_provider.close()

        if redis_adaptee is not None:
            redis_adaptee.close()
            logger.info("Redis connection closed")

        if dynamodb_adaptee is not None:
            dynamodb_adaptee.close()
        
        if notification_service is not None:
            notification_service.close()

        logger.info(
            "StableBus application shutdown completed"
        )


app = FastAPI(
    title="StableBus API",
    description="Backend APIs for StableBus bus booking platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Register API routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(buses_router)
app.include_router(passengers_router)
app.include_router(bookings_router)

logger.info("StableBus application initialized")


@app.get("/health", tags=["Health"])
def health_check():
    logger.info("Health check requested")

    return {
        "status": "UP",
        "application": "StableBus",
        "message": "Application is running successfully",
    }


@app.get("/test-error", tags=["Testing"])
def test_error():
    logger.info("Testing exception logging")
    raise RuntimeError("StableBus test exception")


app = RequestLoggingMiddleware(app)
