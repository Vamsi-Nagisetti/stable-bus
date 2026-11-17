
import logging
import uuid

from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key


logger = logging.getLogger("stablebus.passengers")

CONTACT_DETAILS_KEY = "CONTACT_DETAILS"


class UserPassengerRepository:

    def __init__(self, table):
        self.table = table

    # ---------------------------------------------------------
    # SAVED PASSENGERS
    # ---------------------------------------------------------

    def add_passenger(
        self,
        user_id: str,
        name: str,
        age: int,
        gender: str,
        title: str = None,
        date_of_birth: str = None,
    ) -> dict:

        passenger_id = str(uuid.uuid4())

        passenger = {
            "user_id": user_id,
            "passenger_id": passenger_id,
            "name": name,
            "age": age,
            "gender": gender,
        }

        if title is not None:
            passenger["title"] = title

        if date_of_birth is not None:
            passenger["date_of_birth"] = date_of_birth

        self.table.put_item(
            Item=passenger,
            ConditionExpression="attribute_not_exists(passenger_id)",
        )

        logger.info("Saved passenger created for user")

        return passenger

    def get_passengers(self, user_id: str) -> list:

        response = self.table.query(
            KeyConditionExpression=Key("user_id").eq(user_id)
        )

        passengers = response.get("Items", [])

        return [
            passenger
            for passenger in passengers
            if passenger.get("passenger_id") != CONTACT_DETAILS_KEY
        ]

    def update_passenger(
        self,
        user_id: str,
        passenger_id: str,
        name: str,
        age: int,
        gender: str,
        title: str = None,
        date_of_birth: str = None,
    ) -> dict:

        response = self.table.update_item(
            Key={
                "user_id": user_id,
                "passenger_id": passenger_id,
            },
            UpdateExpression=(
                "SET #name = :name, "
                "#age = :age, "
                "#gender = :gender, "
                "#title = :title, "
                "#dob = :dob"
            ),
            ConditionExpression="attribute_exists(passenger_id)",
            ExpressionAttributeNames={
                "#name": "name",
                "#age": "age",
                "#gender": "gender",
                "#title": "title",
                "#dob": "date_of_birth",
            },
            ExpressionAttributeValues={
                ":name": name,
                ":age": age,
                ":gender": gender,
                ":title": title,
                ":dob": date_of_birth,
            },
            ReturnValues="ALL_NEW",
        )

        logger.info("Saved passenger updated")

        return response["Attributes"]

    def delete_passenger(
        self,
        user_id: str,
        passenger_id: str,
    ) -> bool:

        response = self.table.delete_item(
            Key={
                "user_id": user_id,
                "passenger_id": passenger_id,
            },
            ConditionExpression="attribute_exists(passenger_id)",
            ReturnValues="ALL_OLD",
        )

        logger.info("Saved passenger deleted")

        return "Attributes" in response

    # ---------------------------------------------------------
    # USER CONTACT DETAILS
    # ---------------------------------------------------------

    def get_contact_details(self, user_id: str) -> dict:

        response = self.table.get_item(
            Key={
                "user_id": user_id,
                "passenger_id": CONTACT_DETAILS_KEY,
            },
            ConsistentRead=True,
        )

        return response.get("Item")

    def upsert_contact_details(
        self,
        user_id: str,
        mobile_number: str,
        email: str,
    ) -> dict:

        now = datetime.now(timezone.utc).isoformat()

        response = self.table.update_item(
            Key={
                "user_id": user_id,
                "passenger_id": CONTACT_DETAILS_KEY,
            },
            UpdateExpression=(
                "SET #record_type = :record_type, "
                "#mobile = :mobile, "
                "#email = :email, "
                "#updated_at = :updated_at, "
                "#created_at = if_not_exists(#created_at, :created_at)"
            ),
            ExpressionAttributeNames={
                "#record_type": "record_type",
                "#mobile": "mobile_number",
                "#email": "email",
                "#updated_at": "updated_at",
                "#created_at": "created_at",
            },
            ExpressionAttributeValues={
                ":record_type": "CONTACT_DETAILS",
                ":mobile": mobile_number,
                ":email": email,
                ":updated_at": now,
                ":created_at": now,
            },
            ReturnValues="ALL_NEW",
        )

        logger.info("User contact details saved or updated")

        return response["Attributes"]
