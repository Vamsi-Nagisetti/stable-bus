
import logging
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError


logger = logging.getLogger("stablebus.dynamodb")


class DynamoDBAdaptee:

    def __init__(self):
        region = os.getenv("DYNAMODB_REGION")
        table_name = os.getenv("DYNAMODB_PASSENGERS_TABLE")

        if not region:
            raise ValueError("DYNAMODB_REGION is not configured")

        if not table_name:
            raise ValueError("DYNAMODB_PASSENGERS_TABLE is not configured")

        try:
            self.dynamodb = boto3.resource(
                "dynamodb",
                region_name=region
            )

            self.table = self.dynamodb.Table(table_name)

            # Verify table access and AWS credentials.
            self.table.load()

            logger.info(
                "DynamoDB connection initialized successfully: %s",
                table_name
            )

        except (BotoCoreError, ClientError):
            logger.exception("Failed to initialize DynamoDB connection")
            raise

    def get_table(self):
        return self.table

    def close(self):
        self.dynamodb.meta.client.close()
        logger.info("DynamoDB connection closed")
