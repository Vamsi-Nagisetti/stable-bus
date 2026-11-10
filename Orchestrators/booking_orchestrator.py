
import hashlib
import hmac
import logging
import secrets

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError

from models.Booking import Booking
from models.BookingPassenger import BookingPassenger
from Repositories.BookingRepository import BookingRepository
from core.constants.booking_status import BookingStatus
from Services.Booking.booking_services import BookingStatusService


logger = logging.getLogger("stablebus.booking")


class BookingOrchestrationError(Exception):
    pass


class BookingOrchestrator:

    @staticmethod
    def generate_guest_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_guest_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def authorize_booking(
        booking: Booking | None,
        user_id: str | None,
        guest_access_token: str | None = None,
    ) -> bool:

        if booking is None:
            return False

        if user_id is not None:
            return (
                booking.user_id is not None
                and str(booking.user_id) == str(user_id)
            )

        if booking.user_id is not None or not guest_access_token:
            return False

        stored_hash = booking.guest_access_token_hash

        if not stored_hash:
            return False

        supplied_hash = BookingOrchestrator.hash_guest_token(
            guest_access_token
        )

        return hmac.compare_digest(stored_hash, supplied_hash)

    @staticmethod
    def resolve_passengers(
        user_id: str | None,
        passengers: list,
        passenger_repository,
    ) -> list[dict]:

        saved_passengers_by_id = {}

        if user_id is not None:
            saved_passengers = passenger_repository.get_passengers(user_id)

            saved_passengers_by_id = {
                str(passenger["passenger_id"]): passenger
                for passenger in saved_passengers
            }

        resolved_passengers = []

        for passenger in passengers:
            data = (
                passenger.model_dump()
                if hasattr(passenger, "model_dump")
                else passenger
            )

            passenger_id = data.get("passenger_id")

            if passenger_id:
                if user_id is None:
                    raise BookingOrchestrationError(
                        "Guests cannot use saved passengers"
                    )

                saved = saved_passengers_by_id.get(str(passenger_id))

                if saved is None:
                    raise BookingOrchestrationError(
                        "Saved passenger not found"
                    )

                resolved = {
                    "saved_passenger_id": saved["passenger_id"],
                    "name": saved["name"],
                    "age": saved["age"],
                    "gender": saved["gender"],
                    "title": data.get("title"),
                    "dob": data.get("dob"),
                    "seat_key": data["seat_key"],
                }

            else:
                resolved = {
                    "saved_passenger_id": None,
                    "name": data["name"],
                    "age": data["age"],
                    "gender": data["gender"],
                    "title": data.get("title"),
                    "dob": data.get("dob"),
                    "seat_key": data["seat_key"],
                }

            resolved_passengers.append(resolved)

        return resolved_passengers

    @staticmethod
    def validate_and_calculate_fare(
        seat_map_response: dict,
        passengers: list[dict],
    ) -> dict:

        if not isinstance(seat_map_response, dict):
            raise BookingOrchestrationError("Invalid seat map response")

        header = seat_map_response.get("response_Header", {})

        if not isinstance(header, dict) or header.get("error_Code") != "0000":
            raise BookingOrchestrationError(
                "Seat map provider returned an error"
            )

        seats = seat_map_response.get("seatMap")

        if not isinstance(seats, list):
            raise BookingOrchestrationError("Invalid seat map response")

        selected_keys = [p["seat_key"] for p in passengers]

        if len(selected_keys) != len(set(selected_keys)):
            raise BookingOrchestrationError("Duplicate seats selected")

        seats_by_key = {
            str(seat["seat_Key"]): seat
            for seat in seats
            if isinstance(seat, dict)
            and seat.get("seat_Key") is not None
        }

        total = Decimal("0.00")
        selected_seats = []

        for key in selected_keys:
            seat = seats_by_key.get(str(key))

            if seat is None or seat.get("bookable") is not True:
                raise BookingOrchestrationError(
                    f"Seat unavailable: {key}"
                )

            try:
                fare = Decimal(str(seat["fareMaster"]["total_Amount"]))
            except (KeyError, TypeError, InvalidOperation, ValueError):
                raise BookingOrchestrationError(
                    f"Invalid fare for seat: {key}"
                )

            if not fare.is_finite() or fare <= 0:
                raise BookingOrchestrationError(
                    f"Invalid fare for seat: {key}"
                )

            fare = fare.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            total += fare

            selected_seats.append({
                "seat_key": str(key),
                "seat_number": seat["seat_Number"],
                "fare": fare,
                "ladies_seat": seat.get("ladies_Seat") is True,
            })

        return {
            "selected_seats": selected_seats,
            "total_amount": total.quantize(Decimal("0.01")),
            "currency": "INR",
        }

    @staticmethod
    def create_booking_records(
        db,
        user_id: str | None,
        request,
        resolved_passengers: list[dict],
        fare_result: dict,
        guest_access_token_hash: str | None = None,
        customer_mobile: str | None = None,
        passenger_email: str | None = None,
    ) -> Booking:

        seat_details = {
            seat["seat_key"]: seat
            for seat in fare_result["selected_seats"]
        }

        booking_passengers = []

        for passenger in resolved_passengers:
            seat = seat_details.get(passenger["seat_key"])

            if seat is None:
                raise BookingOrchestrationError(
                    "Passenger seat details are missing"
                )

            booking_passengers.append(
                BookingPassenger(
                    saved_passenger_id=passenger["saved_passenger_id"],
                    name=passenger["name"],
                    age=passenger["age"],
                    gender=passenger["gender"],
                    seat_number=seat["seat_number"],
                    title=passenger.get("title"),
                    dob=passenger.get("dob"),
                )
            )

        booking = Booking(
            user_id=user_id,
            guest_access_token_hash=guest_access_token_hash,
            customer_mobile=customer_mobile,
            passenger_email=passenger_email,
            source_city_id=request.source_city_id,
            destination_city_id=request.destination_city_id,
            journey_date=request.journey_date,
            bus_id=request.bus_id,
            seat_numbers=[
                seat["seat_number"]
                for seat in fare_result["selected_seats"]
            ],
            total_amount=fare_result["total_amount"],
            currency="INR",
            status=BookingStatus.INITIATED,
            idempotency_key=getattr(request, "idempotency_key", None),
            passengers=booking_passengers,
        )

        repository = BookingRepository(db)
        repository.save(booking)

        BookingStatusService.transition(
            booking,
            BookingStatus.TEMP_BOOKING_PENDING,
        )

        db.flush()

        return booking

    @staticmethod
    def build_temp_booking_payload(
        request,
        resolved_passengers: list[dict],
        fare_result: dict,
        customer_mobile: str,
        passenger_email: str,
        seat_map_response: dict,
    ) -> dict:

        seat_details = {
            seat["seat_key"]: seat
            for seat in fare_result["selected_seats"]
        }

        gender_map = {
            "male": 0,
            "female": 1,
        }

        pax_details = []

        for passenger in resolved_passengers:
            seat = seat_details[passenger["seat_key"]]

            gender = gender_map.get(
                passenger["gender"].strip().lower()
            )

            if gender is None:
                raise BookingOrchestrationError(
                    "Invalid passenger gender"
                )

            dob = passenger.get("dob")

            pax_details.append({
                "age": passenger["age"],
                "dob": dob.strftime("%d/%m/%Y") if dob else "",
                "gender": gender,
                "paX_Name": passenger["name"],
                "paX_Id": str(len(pax_details) + 1),
                "seat_Number": seat["seat_number"],
                "title": passenger.get("title") or "",
                "primary": len(pax_details) == 0,
                "ladies_Seat": seat["ladies_seat"],
                "id_Number": "",
                "id_Type": 0,
                "penalty_Charge": "0",
                "status": "",
                "ticket_Number": "",
            })

        seat_map_key = seat_map_response.get("seatMap_Key")

        if not seat_map_key:
            raise BookingOrchestrationError(
                "seatMap_Key missing from provider seat-map response"
            )

        return {
            "boarding_Id": request.boarding_id,
            "dropping_Id": request.dropping_id,
            "search_Key": request.search_key,
            "bus_Key": request.bus_id,
            "seatMap_Key": seat_map_key,
            "customer_Mobile": customer_mobile,
            "passenger_Email": passenger_email,
            "paX_Details": pax_details,
        }

    @staticmethod
    def create_temporary_booking(
        db,
        booking: Booking,
        adapter,
        payload: dict,
    ) -> Booking:

        try:
            response = adapter.BusTempBooking(payload)

        except Exception as exc:
            db.commit()

            logger.exception(
                "BusTempBooking request failed for booking %s",
                booking.id,
            )

            raise BookingOrchestrationError(
                "Temporary booking outcome is unknown. "
                "Do not retry blindly."
            ) from exc

        if not isinstance(response, dict):
            raise BookingOrchestrationError(
                "Invalid temporary booking response"
            )

        header = response.get("response_Header", {})

        if not isinstance(header, dict):
            raise BookingOrchestrationError(
                "Invalid provider response header"
            )

        if header.get("error_Code") != "0000":
            BookingStatusService.transition(
                booking,
                BookingStatus.BOOKING_FAILED,
            )
            db.commit()

            raise BookingOrchestrationError(
                header.get("error_Desc", "Temporary booking failed")
            )

        booking_ref = response.get("booking_RefNo")

        if not booking_ref:
            raise BookingOrchestrationError(
                "Temporary booking reference missing from response"
            )

        booking.temp_booking_ref = booking_ref

        BookingStatusService.transition(
            booking,
            BookingStatus.TEMP_BOOKED,
        )

        db.commit()
        db.refresh(booking)

        logger.info(
            "Temporary booking created successfully: %s",
            booking.id,
        )

        return booking

    @staticmethod
    def start_booking(
        db,
        user_id: str | None,
        request,
        passenger_repository,
        adapter,
        seat_map_response: dict,
        customer_mobile: str,
        passenger_email: str,
    ) -> tuple[Booking, str | None]:

        repository = BookingRepository(db)

        idempotency_key = getattr(request, "idempotency_key", None)

        # Idempotent retry: rotate the guest token and return the new one.
        if idempotency_key:
            existing_booking = repository.get_by_idempotency_key(
                user_id=user_id,
                idempotency_key=idempotency_key,
            )

            if existing_booking is not None:
                raw_guest_token = None

                if user_id is None:
                    raw_guest_token = (
                        BookingOrchestrator.generate_guest_token()
                    )

                    existing_booking.guest_access_token_hash = (
                        BookingOrchestrator.hash_guest_token(
                            raw_guest_token
                        )
                    )

                    existing_booking.customer_mobile = customer_mobile
                    existing_booking.passenger_email = passenger_email

                    db.commit()
                    db.refresh(existing_booking)

                logger.info(
                    "Returning existing booking for idempotency key: %s",
                    existing_booking.id,
                )

                return existing_booking, raw_guest_token

        resolved_passengers = BookingOrchestrator.resolve_passengers(
            user_id,
            request.passengers,
            passenger_repository,
        )

        fare_result = BookingOrchestrator.validate_and_calculate_fare(
            seat_map_response,
            resolved_passengers,
        )

        payload = BookingOrchestrator.build_temp_booking_payload(
            request=request,
            resolved_passengers=resolved_passengers,
            fare_result=fare_result,
            customer_mobile=customer_mobile,
            passenger_email=passenger_email,
            seat_map_response=seat_map_response,
        )

        raw_guest_token = None
        guest_token_hash = None

        if user_id is None:
            raw_guest_token = BookingOrchestrator.generate_guest_token()
            guest_token_hash = BookingOrchestrator.hash_guest_token(
                raw_guest_token
            )

        try:
            booking = BookingOrchestrator.create_booking_records(
                db=db,
                user_id=user_id,
                request=request,
                resolved_passengers=resolved_passengers,
                fare_result=fare_result,
                guest_access_token_hash=guest_token_hash,
                customer_mobile=customer_mobile,
                passenger_email=passenger_email,
            )

        except IntegrityError:
            db.rollback()

            if idempotency_key:
                existing_booking = repository.get_by_idempotency_key(
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                )

                if existing_booking is not None:
                    raw_guest_token = None

                    if user_id is None:
                        raw_guest_token = (
                            BookingOrchestrator.generate_guest_token()
                        )

                        existing_booking.guest_access_token_hash = (
                            BookingOrchestrator.hash_guest_token(
                                raw_guest_token
                            )
                        )

                        existing_booking.customer_mobile = customer_mobile
                        existing_booking.passenger_email = passenger_email

                        db.commit()
                        db.refresh(existing_booking)

                    return existing_booking, raw_guest_token

            raise

        booking = BookingOrchestrator.create_temporary_booking(
            db=db,
            booking=booking,
            adapter=adapter,
            payload=payload,
        )

        return booking, raw_guest_token

    @staticmethod
    def initiate_booking_payment(
        db,
        booking_id: str,
        user_id: str | None,
        payment_service,
        customer: dict,
        idempotency_key: str,
        guest_access_token: str | None = None,
    ) -> dict:

        booking = BookingRepository(db).get_by_id(booking_id)

        if not BookingOrchestrator.authorize_booking(
            booking,
            user_id,
            guest_access_token,
        ):
            raise BookingOrchestrationError("Booking not found")

        if booking.status == BookingStatus.TEMP_BOOKED:
            BookingStatusService.transition(
                booking,
                BookingStatus.PAYMENT_PENDING,
            )

            db.commit()
            db.refresh(booking)

        elif booking.status != BookingStatus.PAYMENT_PENDING:
            raise BookingOrchestrationError(
                f"Payment cannot be initiated for booking status: "
                f"{booking.status}"
            )

        try:
            payment_result = payment_service.initiate_payment(
                booking_id=booking.id,
                idempotency_key=idempotency_key,
                customer=customer,
            )

        except Exception as exc:
            logger.exception(
                "Payment initiation failed for booking %s",
                booking.id,
            )

            raise BookingOrchestrationError(
                "Payment initiation outcome is uncertain. "
                "Retry using the same idempotency key."
            ) from exc

        return {
            "booking_id": booking.id,
            **payment_result,
        }

    @staticmethod
    def verify_booking_payment(
        db,
        booking_id: str,
        user_id: str | None,
        payment_service,
        payment_id: str,
        gateway_payment_id: str,
        signature: str,
        guest_access_token: str | None = None,
    ) -> dict:

        booking = BookingRepository(db).get_by_id(booking_id)

        if not BookingOrchestrator.authorize_booking(
            booking,
            user_id,
            guest_access_token,
        ):
            raise BookingOrchestrationError("Booking not found")

        if booking.status not in (
            BookingStatus.PAYMENT_PENDING,
            BookingStatus.PAYMENT_VERIFIED,
        ):
            raise BookingOrchestrationError(
                f"Payment cannot be verified for booking status: "
                f"{booking.status}"
            )

        payment = payment_service.payment_repository.get_by_id(payment_id)

        if payment is None or str(payment.booking_id) != str(booking.id):
            raise BookingOrchestrationError(
                "Payment does not belong to this booking"
            )

        payment_result = payment_service.verify_payment(
            payment_id=payment_id,
            gateway_payment_id=gateway_payment_id,
            signature=signature,
        )

        if payment_result.get("status") == "SUCCESS":
            if booking.status == BookingStatus.PAYMENT_PENDING:
                BookingStatusService.transition(
                    booking,
                    BookingStatus.PAYMENT_VERIFIED,
                )

                db.commit()
                db.refresh(booking)

        return {
            "booking_id": booking.id,
            **payment_result,
            "booking_status": booking.status,
        }

    @staticmethod
    def complete_ticketing(
        db,
        booking_id: str,
        user_id: str | None,
        adapter,
        guest_access_token: str | None = None,
    ) -> dict:

        booking = BookingRepository(db).get_by_id(booking_id)

        if not BookingOrchestrator.authorize_booking(
            booking,
            user_id,
            guest_access_token,
        ):
            raise BookingOrchestrationError("Booking not found")

        if booking.status != BookingStatus.PAYMENT_VERIFIED:
            raise BookingOrchestrationError(
                f"Ticketing cannot start from status: {booking.status}"
            )

        if not booking.temp_booking_ref:
            raise BookingOrchestrationError(
                "Temporary booking reference is missing"
            )

        BookingStatusService.transition(
            booking,
            BookingStatus.TICKETING_PENDING,
        )
        db.commit()
        db.refresh(booking)

        payload = {
            "booking_RefNo": booking.temp_booking_ref,
        }

        try:
            response = adapter.BusTicketing(payload)

        except Exception:
            logger.exception(
                "AO Pay ticketing outcome is uncertain for booking %s",
                booking.id,
            )

            BookingStatusService.transition(
                booking,
                BookingStatus.TICKETING_UNKNOWN,
            )
            db.commit()
            db.refresh(booking)

            return {
                "booking_id": booking.id,
                "booking_status": booking.status,
                "message": (
                    "Ticketing outcome is uncertain. "
                    "Check booking status using BusRequery."
                ),
            }

        if not isinstance(response, dict):
            BookingStatusService.transition(
                booking,
                BookingStatus.TICKETING_UNKNOWN,
            )
            db.commit()
            db.refresh(booking)

            return {
                "booking_id": booking.id,
                "booking_status": booking.status,
                "message": "Invalid provider response. Requery required.",
            }

        booking.supplier_refno = response.get("supplier_Refno")
        booking.transport_pnr = response.get("transport_PNR")

        response_header = response.get("response_Header") or {}
        error_code = str(response_header.get("error_Code", ""))

        if error_code and error_code != "0000":
            BookingStatusService.transition(
                booking,
                BookingStatus.BOOKING_FAILED,
            )
            db.commit()
            db.refresh(booking)

            return {
                "booking_id": booking.id,
                "booking_status": booking.status,
                "provider_error_code": error_code,
                "provider_message": response_header.get("error_Desc"),
            }

        BookingStatusService.transition(
            booking,
            BookingStatus.TICKETING_UNKNOWN,
        )

        db.commit()
        db.refresh(booking)

        return {
            "booking_id": booking.id,
            "booking_status": booking.status,
            "supplier_refno": booking.supplier_refno,
            "transport_pnr": booking.transport_pnr,
            "provider_status_id": response_header.get("status_Id"),
            "provider_status": response.get("statuss"),
            "message": (
                "Ticketing request accepted by provider. "
                "Final confirmation requires BusRequery."
            ),
        }

    @staticmethod
    def requery_ticketing(
        db,
        booking_id: str,
        user_id: str | None,
        adapter,
        guest_access_token: str | None = None,
    ) -> dict:

        booking = BookingRepository(db).get_by_id(booking_id)

        if not BookingOrchestrator.authorize_booking(
            booking,
            user_id,
            guest_access_token,
        ):
            raise BookingOrchestrationError("Booking not found")

        if booking.status == BookingStatus.CONFIRMED:
            return {
                "booking_id": booking.id,
                "booking_status": booking.status,
                "message": "Booking is already confirmed",
            }

        if booking.status not in (
            BookingStatus.TICKETING_PENDING,
            BookingStatus.TICKETING_UNKNOWN,
        ):
            raise BookingOrchestrationError(
                f"Requery cannot run from status: {booking.status}"
            )

        if not booking.temp_booking_ref:
            raise BookingOrchestrationError(
                "Temporary booking reference is missing"
            )

        try:
            response = adapter.BusRequery({
                "booking_RefNo": booking.temp_booking_ref,
            })

        except Exception:
            logger.exception(
                "BusRequery failed for booking %s",
                booking.id,
            )

            if booking.status == BookingStatus.TICKETING_PENDING:
                BookingStatusService.transition(
                    booking,
                    BookingStatus.TICKETING_UNKNOWN,
                )
                db.commit()
                db.refresh(booking)

            return {
                "booking_id": booking.id,
                "booking_status": booking.status,
                "message": "Requery failed. Booking outcome remains unknown.",
            }

        if not isinstance(response, dict):
            response = {}

        bus_detail = response.get("bus_Detail") or {}

        supplier_ref = (
            response.get("supplier_Refno")
            or bus_detail.get("supplier_RefNo")
        )
        transport_pnr = response.get("transport_PNR")

        if supplier_ref:
            booking.supplier_refno = supplier_ref

        if transport_pnr:
            booking.transport_pnr = transport_pnr

        passenger_details = response.get("paX_Details") or []

        provider_passengers_by_seat = {
            str(passenger.get("seat_Number", "")).strip(): passenger
            for passenger in passenger_details
            if passenger.get("seat_Number")
        }

        for booking_passenger in booking.passengers or []:
            provider_passenger = provider_passengers_by_seat.get(
                str(booking_passenger.seat_number).strip()
            )

            if provider_passenger:
                ticket_number = provider_passenger.get("ticket_Number")

                if ticket_number:
                    booking_passenger.ticket_number = str(ticket_number)

        mock_status = str(response.get("mock_status", "")).upper()

        if mock_status == "CONFIRMED":
            is_confirmed = True
        else:
            response_header = response.get("response_Header") or {}
            error_code = str(response_header.get("error_Code", ""))

            passenger_statuses = [
                str(passenger.get("status", "")).strip().casefold()
                for passenger in passenger_details
            ]

            expected_passengers = len(booking.passengers or [])

            is_confirmed = (
                error_code == "0000"
                and str(response.get("statuss", "")).strip().casefold()
                    == "true"
                and str(response.get("ticket_Status_Desc", ""))
                    .strip().casefold() == "confirmed"
                and expected_passengers > 0
                and len(passenger_details) == expected_passengers
                and all(
                    status == "confirmed"
                    for status in passenger_statuses
                )
            )

        if is_confirmed:
            BookingStatusService.transition(
                booking,
                BookingStatus.CONFIRMED,
            )
            db.commit()
            db.refresh(booking)

            return {
                "booking_id": booking.id,
                "booking_status": booking.status,
                "supplier_refno": booking.supplier_refno,
                "transport_pnr": booking.transport_pnr,
                "message": "All passengers are confirmed",
            }

        if booking.status == BookingStatus.TICKETING_PENDING:
            BookingStatusService.transition(
                booking,
                BookingStatus.TICKETING_UNKNOWN,
            )

        db.commit()
        db.refresh(booking)

        return {
            "booking_id": booking.id,
            "booking_status": booking.status,
            "ticket_status": response.get("ticket_Status_Desc"),
            "message": (
                "Booking is not fully confirmed. "
                "Requery again after checking with the provider."
            ),
        }
