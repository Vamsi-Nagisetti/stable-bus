"""Trip ratings & reviews stored in DynamoDB.

One table, string keys ``pk`` (partition) and ``sk`` (sort):

  pk = BOOKING#<booking_id>   sk = REVIEW    one review per booking
  pk = OPERATOR#<key>         sk = SUMMARY   rating_sum / rating_count (atomic counters)
  pk = CONFIG                 sk = REVIEW_REWARD   coins given for a review (admin-editable)

The review item and the operator summary are written in ONE transaction, so the
average can never drift from the reviews.
"""
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("stablebus.reviews")

DEFAULT_REWARD_COINS = 20


class AlreadyReviewed(Exception):
    pass


def operator_key(name: str | None, fallback: str = "") -> str:
    """Stable identity of a bus operator (case / spacing insensitive)."""
    base = re.sub(r"\s+", " ", (name or "").strip().lower())
    return base or (fallback or "").strip().lower()


def _plain(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


# NOTE: table.meta.client belongs to a boto3 *resource*, so it already converts
# plain Python values to/from DynamoDB types. Do not serialize by hand.


class ReviewRepository:
    def __init__(self, table):
        self.table = table
        self.client = table.meta.client
        self.table_name = table.name

    # ---------------- reviews ----------------

    def create_review(
        self,
        booking_id: str,
        user_id: str | None,
        operator_name: str,
        op_key: str,
        rating: int,
        comment: str | None,
        tags: list[str] | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        review = {
            "pk": f"BOOKING#{booking_id}",
            "sk": "REVIEW",
            "booking_id": booking_id,
            "operator_key": op_key,
            "operator_name": operator_name,
            "rating": int(rating),
            "coins_awarded": 0,
            "created_at": now,
        }
        if user_id:
            review["user_id"] = str(user_id)
        if comment:
            review["comment"] = comment
        if tags:
            review["tags"] = list(tags)

        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": review,
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": {"pk": f"OPERATOR#{op_key}", "sk": "SUMMARY"},
                            "UpdateExpression": (
                                "ADD rating_sum :r, rating_count :one "
                                "SET operator_name = :n, updated_at = :t"
                            ),
                            "ExpressionAttributeValues": {":r": int(rating), ":one": 1, ":n": operator_name, ":t": now},
                        }
                    },
                ]
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
                reasons = exc.response.get("CancellationReasons") or []
                if any(r.get("Code") == "ConditionalCheckFailed" for r in reasons):
                    raise AlreadyReviewed() from exc
            raise
        return review

    def get_review(self, booking_id: str) -> dict | None:
        response = self.table.get_item(
            Key={"pk": f"BOOKING#{booking_id}", "sk": "REVIEW"}, ConsistentRead=True
        )
        return _plain(response.get("Item")) if response.get("Item") else None

    def get_reviews(self, booking_ids: list[str]) -> dict[str, dict]:
        """booking_id -> review item (only those that exist)."""
        out: dict[str, dict] = {}
        ids = list(dict.fromkeys(booking_ids))
        for i in range(0, len(ids), 100):
            keys = [{"pk": f"BOOKING#{b}", "sk": "REVIEW"} for b in ids[i:i + 100]]
            for item in self._batch_get(keys):
                out[item["booking_id"]] = item
        return out

    def mark_reward(self, booking_id: str, coins: int) -> None:
        self.table.update_item(
            Key={"pk": f"BOOKING#{booking_id}", "sk": "REVIEW"},
            UpdateExpression="SET coins_awarded = :c",
            ExpressionAttributeValues={":c": int(coins)},
        )

    # ---------------- operator summaries ----------------

    def get_summaries(self, op_keys: list[str]) -> dict[str, dict]:
        """operator_key -> {"average": 4.3, "count": 12}."""
        out: dict[str, dict] = {}
        keys_all = [k for k in dict.fromkeys(op_keys) if k]
        for i in range(0, len(keys_all), 100):
            keys = [{"pk": f"OPERATOR#{k}", "sk": "SUMMARY"} for k in keys_all[i:i + 100]]
            for item in self._batch_get(keys):
                count = int(item.get("rating_count") or 0)
                if count > 0:
                    key = item["pk"].split("#", 1)[1]
                    out[key] = {
                        "average": round(int(item.get("rating_sum") or 0) / count, 1),
                        "count": count,
                    }
        return out

    def _batch_get(self, keys: list[dict]) -> list[dict]:
        items: list[dict] = []
        request = {self.table_name: {"Keys": keys}}
        for _ in range(5):  # retry unprocessed keys
            response = self.client.batch_get_item(RequestItems=request)
            items += [_plain(i) for i in response.get("Responses", {}).get(self.table_name, [])]
            request = response.get("UnprocessedKeys") or {}
            if not request:
                break
        return items

    # ---------------- reward config ----------------

    def get_reward_coins(self) -> int:
        """Coins for one review. DynamoDB value (set by admin) wins; else env; else 20."""
        try:
            response = self.table.get_item(Key={"pk": "CONFIG", "sk": "REVIEW_REWARD"})
            item = response.get("Item")
            if item is not None and item.get("coins") is not None:
                return max(0, int(item["coins"]))
        except (BotoCoreError, ClientError):
            logger.exception("Could not read review reward config")
        try:
            return max(0, int(os.getenv("REVIEW_REWARD_COINS", DEFAULT_REWARD_COINS)))
        except ValueError:
            return DEFAULT_REWARD_COINS

    def set_reward_coins(self, coins: int) -> None:
        self.table.put_item(
            Item={
                "pk": "CONFIG",
                "sk": "REVIEW_REWARD",
                "coins": int(coins),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )


def get_review_repository(app) -> "ReviewRepository | None":
    """Lazily connect to the reviews table. None when it is not configured/reachable,
    so the rest of the app (e.g. bus search) never breaks because of ratings."""
    existing = getattr(app.state, "review_repository", None)
    if existing is not None:
        return existing

    table_name = os.getenv("DYNAMODB_REVIEWS_TABLE")
    region = os.getenv("DYNAMODB_REGION")
    if not table_name or not region:
        return None
    try:
        import boto3

        table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        repository = ReviewRepository(table)
        app.state.review_repository = repository
        return repository
    except Exception:
        logger.exception("Reviews table unavailable")
        return None