"""
Helper utilities for Extended Exchange SDK.
"""

import asyncio
import concurrent.futures
from decimal import Decimal
from functools import wraps
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple, TypeVar

from x10.perpetual.orders import TimeInForce as X10TimeInForce

from extended.utils.constants import TIF_MAPPING

T = TypeVar("T")


def normalize_market_name(name: str) -> str:
    """
    Normalize market name to Extended format.

    Hyperliquid uses: "BTC", "ETH"
    Extended uses: "BTC-USD", "ETH-USD"

    Args:
        name: Market name in either format

    Returns:
        Market name in Extended format (e.g., "BTC-USD")
    """
    if "-" not in name:
        return f"{name}-USD"
    return name


def to_hyperliquid_market_name(name: str) -> str:
    """
    Convert Extended market name to Hyperliquid format.

    "BTC-USD" -> "BTC"

    Args:
        name: Market name in Extended format

    Returns:
        Market name in Hyperliquid format (e.g., "BTC")
    """
    return name.replace("-USD", "")


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run an async coroutine synchronously.

    Handles both cases:
    - When called from a thread without an event loop
    - When called from a thread with an existing event loop (uses thread pool)

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    try:
        asyncio.get_running_loop()
        # We're in an async context (e.g., Celery, FastAPI, etc.)
        # Run the coroutine in a separate thread to escape the async context

        def run_in_new_loop() -> T:
            """Run coroutine in a new event loop in this thread."""
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)

        # Use thread pool to run in a clean thread without event loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_new_loop)
            return future.result(timeout=30)  # 30 second timeout for API calls

    except RuntimeError:
        # No running loop, safe to run normally
        pass

    # Standard case: no existing event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


def sync_wrapper(
    async_method: Callable[..., Coroutine[Any, Any, T]]
) -> Callable[..., T]:
    """
    Decorator to create a synchronous version of an async method.

    Usage:
        class AsyncInfoAPI:
            async def user_state(self) -> Dict:
                ...

        class InfoAPI:
            def __init__(self, async_api: AsyncInfoAPI):
                self._async = async_api

            @sync_wrapper
            async def user_state(self) -> Dict:
                return await self._async.user_state()
    """

    @wraps(async_method)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return run_sync(async_method(*args, **kwargs))

    return wrapper


def parse_order_type(order_type: Dict[str, Any]) -> Tuple[X10TimeInForce, bool]:
    """
    Parse Hyperliquid order_type to Extended params.

    Args:
        order_type: Hyperliquid order type dict
            {"limit": {"tif": "Gtc"}} - Good-till-cancel
            {"limit": {"tif": "Ioc"}} - Immediate-or-cancel
            {"limit": {"tif": "Alo"}} - Add-liquidity-only (post-only)

    Returns:
        Tuple of (TimeInForce, post_only)
    """
    if "limit" in order_type:
        tif = order_type["limit"].get("tif", "Gtc")
        post_only = tif == "Alo"
        return TIF_MAPPING.get(tif, X10TimeInForce.GTT), post_only
    return X10TimeInForce.GTT, False


def parse_builder(
    builder: Optional[Dict[str, Any]]
) -> Tuple[Optional[int], Optional[Decimal]]:
    """
    Parse Hyperliquid builder format to Extended params.

    Hyperliquid: {"b": "123", "f": 10}
                 b = builder_id as string
                 f = fee in tenths of basis points

    Extended: builder_id (int), builder_fee (Decimal rate)

    Conversion:
        f=1  -> 0.1 bps  -> 0.000001
        f=10 -> 1 bps    -> 0.0001
        f=50 -> 5 bps    -> 0.0005

    Args:
        builder: Builder dict in Hyperliquid format or None

    Returns:
        Tuple of (builder_id, builder_fee) or (None, None)
    """
    if builder is None:
        return None, None

    # Parse builder_id from string to int
    builder_id = int(builder["b"])

    # Convert tenths of bps to decimal rate
    # f / 100000 = decimal rate
    fee_tenths_bps = builder.get("f", 0)
    builder_fee = Decimal(fee_tenths_bps) / Decimal(100000)

    return builder_id, builder_fee


def calculate_sz_decimals(min_order_size_change: Decimal) -> int:
    """
    Calculate size decimals from minimum order size change.

    Args:
        min_order_size_change: Minimum order size change (e.g., 0.001)

    Returns:
        Number of decimal places (e.g., 3)
    """
    if min_order_size_change <= 0:
        return 0
    return abs(int(min_order_size_change.log10()))
