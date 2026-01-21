"""
Native Sync Exchange API for Extended Exchange SDK.

Provides trading operations matching Hyperliquid's Exchange class interface.
Uses direct HTTP calls with requests instead of async X10 client.
MIRRORS Pacifica ExchangeAPI architecture exactly.
"""

import warnings
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from x10.perpetual.configuration import EndpointConfig
from x10.perpetual.orders import OrderSide, TimeInForce as X10TimeInForce

from extended.api.base_native_sync import BaseNativeSyncClient
from extended.auth import ExtendedAuth
from extended.exceptions import ExtendedAPIError, ExtendedValidationError
from extended.transformers import OrderTransformer
from extended.utils.constants import (
    DEFAULT_SLIPPAGE,
    MARKET_ORDER_PRICE_CAP,
    MARKET_ORDER_PRICE_FLOOR,
    SIDE_MAPPING,
)
from extended.utils.helpers import normalize_market_name, parse_builder, parse_order_type


class NativeSyncExchangeAPI(BaseNativeSyncClient):
    """
    Extended Exchange Native Sync trading API with Hyperliquid-compatible interface.

    MIRRORS Pacifica ExchangeAPI architecture exactly - uses requests directly
    instead of async X10 client operations.

    Handles order placement, cancellation, and account management.

    Example:
        exchange = NativeSyncExchangeAPI(auth, config)
        result = exchange.order("BTC", is_buy=True, sz=0.01, limit_px=50000)
        exchange.cancel("BTC", oid=12345)
    """

    def __init__(self, auth: ExtendedAuth, config: EndpointConfig):
        """
        Initialize the native sync Exchange API.

        Args:
            auth: ExtendedAuth instance with credentials
            config: Endpoint configuration
        """
        super().__init__(auth, config)

    def order(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: Optional[Dict[str, Any]] = None,
        reduce_only: bool = False,
        cloid: Optional[str] = None,
        builder: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Place a limit order - NATIVE SYNC.

        Args:
            name: Market name (e.g., "BTC" or "BTC-USD")
            is_buy: True for buy, False for sell
            sz: Size in base asset
            limit_px: Limit price
            order_type: {"limit": {"tif": "Gtc"}} or {"limit": {"tif": "Ioc"}}
                       or {"limit": {"tif": "Alo"}} (post-only)
            reduce_only: Only reduce position
            cloid: Client order ID (maps to external_id)
            builder: {"b": builder_id, "f": fee_bps_tenths}

        Returns:
            Hyperliquid-format response:
            {"status": "ok", "response": {"type": "order", "data": {"statuses": [...]}}}
        """
        if order_type is None:
            order_type = {"limit": {"tif": "Gtc"}}

        market_name = normalize_market_name(name)
        side = "BUY" if is_buy else "SELL"
        tif, post_only = parse_order_type(order_type)
        builder_id, builder_fee = parse_builder(builder)

        # Prepare order data for HTTP request
        order_data = {
            "market": market_name,
            "amount": str(sz),
            "price": str(limit_px),
            "side": side,
            "post_only": post_only,
            "time_in_force": tif.value if hasattr(tif, 'value') else str(tif),
            "reduce_only": reduce_only,
        }

        if cloid:
            order_data["external_id"] = cloid
        if builder_id is not None:
            order_data["builder_id"] = builder_id
        if builder_fee is not None:
            order_data["builder_fee"] = str(builder_fee)

        try:
            response = self.post("/orders", data=order_data, authenticated=True)
            return OrderTransformer.transform_order_response(response.get("data"))

        except Exception as e:
            return OrderTransformer.transform_error_response(str(e))

    def bulk_orders(
        self,
        order_requests: List[Dict[str, Any]],
        builder: Optional[Dict[str, Any]] = None,
        grouping: str = "na",
    ) -> Dict[str, Any]:
        """
        Place multiple orders in parallel - NATIVE SYNC.

        WARNING: Unlike Hyperliquid, Extended does not support atomic
        bulk orders. Orders are sent sequentially and may partially fail.

        Args:
            order_requests: List of order dicts with keys:
                - coin, is_buy, sz, limit_px, order_type, reduce_only, cloid
            builder: Builder info applied to all orders
            grouping: Ignored (no native support)

        Returns:
            Combined results from all orders
        """
        results = []

        for request in order_requests:
            try:
                result = self.order(
                    name=request["coin"],
                    is_buy=request["is_buy"],
                    sz=request["sz"],
                    limit_px=request["limit_px"],
                    order_type=request.get("order_type", {"limit": {"tif": "Gtc"}}),
                    reduce_only=request.get("reduce_only", False),
                    cloid=request.get("cloid"),
                    builder=builder or request.get("builder"),
                )

                # Extract the placed order data from the response
                if result.get("status") == "ok":
                    statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                    if statuses and "resting" in statuses[0]:
                        results.append({
                            "status": "ok",
                            "data": {
                                "id": statuses[0]["resting"]["oid"],
                                "external_id": statuses[0]["resting"]["cloid"],
                            }
                        })
                    else:
                        results.append({"status": "error", "error": result.get("response", "Unknown error")})
                else:
                    results.append({"status": "error", "error": result.get("response", "Unknown error")})

            except Exception as e:
                results.append({"status": "error", "error": str(e)})

        return OrderTransformer.transform_bulk_orders_response(results)

    def cancel(
        self,
        name: str,
        oid: Optional[int] = None,
        cloid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cancel an order by oid or cloid - NATIVE SYNC.

        Args:
            name: Market name (required for Hyperliquid compat, may be ignored)
            oid: Internal order ID
            cloid: Client order ID (external_id)

        Returns:
            Hyperliquid-format response:
            {"status": "ok", "response": {"type": "cancel", "data": {"statuses": [...]}}}
        """
        if oid is None and cloid is None:
            raise ExtendedValidationError("Either oid or cloid must be provided")

        try:
            if oid is not None:
                response = self.delete(f"/orders/{oid}", authenticated=True)
            else:
                # Cancel by external_id
                cancel_data = {"external_id": cloid}
                response = self.post("/orders/cancel", data=cancel_data, authenticated=True)

            return OrderTransformer.transform_cancel_response(success=True, order_id=oid)

        except Exception as e:
            return OrderTransformer.transform_error_response(str(e))

    def cancel_by_cloid(self, name: str, cloid: str) -> Dict[str, Any]:
        """
        Cancel order by client order ID - NATIVE SYNC.

        Args:
            name: Market name
            cloid: Client order ID

        Returns:
            Cancel response in Hyperliquid format
        """
        return self.cancel(name, cloid=cloid)

    def bulk_cancel(
        self,
        cancel_requests: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Cancel multiple orders - NATIVE SYNC.

        Args:
            cancel_requests: List of {"coin": str, "oid": int}
                            or {"coin": str, "cloid": str}

        Returns:
            Combined cancel results
        """
        # Group by oids and cloids for mass cancel
        oids = []
        cloids = []

        for req in cancel_requests:
            if "oid" in req and req["oid"] is not None:
                oids.append(req["oid"])
            elif "cloid" in req and req["cloid"] is not None:
                cloids.append(req["cloid"])

        try:
            cancel_data = {}
            if oids:
                cancel_data["order_ids"] = oids
            if cloids:
                cancel_data["external_order_ids"] = cloids

            response = self.post("/orders/mass-cancel", data=cancel_data, authenticated=True)

            return {
                "status": "ok",
                "response": {
                    "type": "cancel",
                    "data": {
                        "statuses": ["success"] * len(cancel_requests)
                    },
                },
            }

        except Exception as e:
            return OrderTransformer.transform_error_response(str(e))

    def update_leverage(
        self,
        leverage: int,
        name: str,
        is_cross: bool = True,
    ) -> Dict[str, Any]:
        """
        Update leverage for a market - NATIVE SYNC.

        Args:
            leverage: Target leverage (1-50)
            name: Market name
            is_cross: Ignored (Extended only supports cross margin)

        Returns:
            Hyperliquid-format response:
            {"status": "ok", "response": {"type": "leverage"}}
        """
        if not is_cross:
            warnings.warn(
                "Extended Exchange only supports cross margin. "
                "is_cross=False will be ignored.",
                UserWarning,
            )

        market_name = normalize_market_name(name)

        try:
            leverage_data = {
                "market": market_name,
                "leverage": leverage
            }

            response = self.post("/account/leverage", data=leverage_data, authenticated=True)
            return OrderTransformer.transform_leverage_response()

        except Exception as e:
            return OrderTransformer.transform_error_response(str(e))

    def _calculate_market_order_price(
        self,
        name: str,
        is_buy: bool,
        slippage: float,
    ) -> Decimal:
        """
        Calculate limit price for simulated market order - NATIVE SYNC.

        Extended constraints:
        - Buy: price <= mark_price * 1.05
        - Sell: price >= mark_price * 0.95

        Args:
            name: Market name
            is_buy: True for buy
            slippage: Max slippage (e.g., 0.05 for 5%)

        Returns:
            Calculated limit price (rounded to market precision)
        """
        from decimal import ROUND_CEILING, ROUND_FLOOR

        market_name = normalize_market_name(name)

        # Get orderbook and market stats via HTTP
        orderbook_response = self.get(f"/orderbook/{market_name}", authenticated=False)
        stats_response = self.get(f"/markets/{market_name}/stats", authenticated=False)
        markets_response = self.get("/markets", authenticated=False)

        orderbook = orderbook_response.get("data", {})
        stats = stats_response.get("data", {})
        mark_price = Decimal(str(stats.get("mark_price", 0)))

        # Find market config
        markets = markets_response.get("data", [])
        market = None
        for m in markets:
            if m.get("name") == market_name:
                market = m
                break

        if not market:
            raise ExtendedAPIError(404, f"Market {market_name} not found")

        if is_buy:
            # Use best ask with slippage, capped at mark * 1.05
            asks = orderbook.get("asks", [])
            best_ask = Decimal(str(asks[0].get("price", mark_price))) if asks else mark_price

            target_price = best_ask * Decimal(1 + slippage)
            max_price = mark_price * Decimal(str(MARKET_ORDER_PRICE_CAP))
            price = min(target_price, max_price)

            # Round up for buys to ensure fill
            tick_size = Decimal(str(market.get("tick_size", "0.01")))
            return (price / tick_size).quantize(Decimal('1'), rounding=ROUND_CEILING) * tick_size
        else:
            # Use best bid with slippage, floored at mark * 0.95
            bids = orderbook.get("bids", [])
            best_bid = Decimal(str(bids[0].get("price", mark_price))) if bids else mark_price

            target_price = best_bid * Decimal(1 - slippage)
            min_price = mark_price * Decimal(str(MARKET_ORDER_PRICE_FLOOR))
            price = max(target_price, min_price)

            # Round down for sells to ensure fill
            tick_size = Decimal(str(market.get("tick_size", "0.01")))
            return (price / tick_size).quantize(Decimal('1'), rounding=ROUND_FLOOR) * tick_size

    def market_open(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        px: Optional[float] = None,
        slippage: float = DEFAULT_SLIPPAGE,
        cloid: Optional[str] = None,
        builder: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Open a position with a market order - NATIVE SYNC.

        Note: Extended simulates market orders as IOC limit orders.

        Args:
            name: Market name
            is_buy: True for long, False for short
            sz: Size in base asset
            px: Optional price hint (uses orderbook if not provided)
            slippage: Max slippage (default 5%)
            cloid: Client order ID
            builder: Builder info

        Returns:
            Order response in Hyperliquid format
        """
        if px is not None:
            limit_price = Decimal(str(px))
        else:
            limit_price = self._calculate_market_order_price(name, is_buy, slippage)

        return self.order(
            name=name,
            is_buy=is_buy,
            sz=sz,
            limit_px=float(limit_price),
            order_type={"limit": {"tif": "Ioc"}},
            reduce_only=False,
            cloid=cloid,
            builder=builder,
        )

    def market_close(
        self,
        coin: str,
        sz: Optional[float] = None,
        px: Optional[float] = None,
        slippage: float = DEFAULT_SLIPPAGE,
        cloid: Optional[str] = None,
        builder: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Close a position with a market order - NATIVE SYNC.

        Args:
            coin: Market name
            sz: Size to close (None = close entire position)
            px: Optional price hint
            slippage: Max slippage
            cloid: Client order ID
            builder: Builder info

        Returns:
            Order response in Hyperliquid format
        """
        market_name = normalize_market_name(coin)

        # Get current position to determine size and side
        params = {"markets": [market_name]}
        positions_response = self.get("/account/positions", params=params, authenticated=True)

        positions = positions_response.get("data", [])
        if not positions:
            return OrderTransformer.transform_error_response(
                f"No open position found for {coin}"
            )

        position = positions[0]

        # Determine size to close
        close_sz = float(sz) if sz is not None else float(position.get("size", 0))

        # Close is opposite side (side can be str or PositionSide enum)
        side = position.get("side")
        if hasattr(side, 'value'):
            side = side.value
        is_buy = side == "SHORT"

        if px is not None:
            limit_price = Decimal(str(px))
        else:
            limit_price = self._calculate_market_order_price(coin, is_buy, slippage)

        return self.order(
            name=coin,
            is_buy=is_buy,
            sz=close_sz,
            limit_px=float(limit_price),
            order_type={"limit": {"tif": "Ioc"}},
            reduce_only=True,
            cloid=cloid,
            builder=builder,
        )