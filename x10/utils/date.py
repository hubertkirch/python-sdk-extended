from datetime import datetime, timezone
import math


def utc_now():
    return datetime.now(tz=timezone.utc)


def to_epoch_millis(value: datetime):
    assert value.tzinfo == timezone.utc, "`value` must be in UTC"

    # Use ceiling to match the hash_order logic which uses math.ceil
    return int(math.ceil(value.timestamp() * 1000))
