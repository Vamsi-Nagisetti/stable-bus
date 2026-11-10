
import logging
import uuid

from boto3.dynamodb.conditions import Key


logger = logging.getLogger("stablebus.passengers")


class UserPassengerRepository:

    def __init__(self, table):
        self.table = table

    def add_passenger(
        self,
        user_id: str,
        name: str,
        age: int,
        gender: str
    ) -> dict:

        passenger_id = str(uuid.uuid4())

        passenger = {
            "user_id": user_id,
            "passenger_id": passenger_id,
            "name": name,
            "age": age,
            "gender": gender
        }

        self.table.put_item(
            Item=passenger,
            ConditionExpression="attribute_not_exists(passenger_id)"
        )

        logger.info("Saved passenger created for user")

        return passenger

    def get_passengers(self, user_id: str) -> list:

        response = self.table.query(
            KeyConditionExpression=Key("user_id").eq(user_id)
        )

        return response.get("Items", [])

    def update_passenger(
        self,
        user_id: str,
        passenger_id: str,
        name: str,
        age: int,
        gender: str
    ) -> dict:

        response = self.table.update_item(
            Key={
                "user_id": user_id,
                "passenger_id": passenger_id
            },
            UpdateExpression="SET #name = :name, #age = :age, #gender = :gender",
            ConditionExpression="attribute_exists(passenger_id)",
            ExpressionAttributeNames={
                "#name": "name",
                "#age": "age",
                "#gender": "gender"
            },
            ExpressionAttributeValues={
                ":name": name,
                ":age": age,
                ":gender": gender
            },
            ReturnValues="ALL_NEW"
        )

        logger.info("Saved passenger updated")

        return response["Attributes"]

    def delete_passenger(
        self,
        user_id: str,
        passenger_id: str
    ) -> bool:

        response = self.table.delete_item(
            Key={
                "user_id": user_id,
                "passenger_id": passenger_id
            },
            ConditionExpression="attribute_exists(passenger_id)",
            ReturnValues="ALL_OLD"
        )

        logger.info("Saved passenger deleted")

        return "Attributes" in response
