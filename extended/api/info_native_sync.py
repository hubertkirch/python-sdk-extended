"""
Native Sync Info API for Extended Exchange SDK.

Provides read-only operations matching Hyperliquid's Info class interface.
Uses direct HTTP calls with requests instead of async X10 client.
MIRRORS Pacifica InfoAPI architecture exactly.
"""

import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from x10.perpetual.configuration import EndpointConfig

from extended.api.base_native_sync import BaseNativeSyncClient
from extended.auth import ExtendedAuth
from extended.transformers import AccountTransformer, MarketTransformer, OrderTransformer
from extended.utils.constants import INTERVAL_MAPPING, DEFAULT_CANDLE_TYPE
from extended.utils.helpers import normalize_market_name, to_hyperliquid_market_name


class NativeSyncInfoAPI(BaseNativeSyncClient):
    """
    Extended Exchange Native Sync Info API with Hyperliquid-compatible interface.

    MIRRORS Pacifica InfoAPI architecture exactly - uses requests directly
    instead of async X10 client operations.

    Note: Unlike Hyperliquid, Extended requires authentication for
    user-specific data. The `address` parameter is accepted for
    interface compatibility but ignored (uses authenticated user).

    Example:
        info = NativeSyncInfoAPI(auth, config)
        state = info.user_state()
        orders = info.open_orders()
    """

    def __init__(self, auth: ExtendedAuth, config: EndpointConfig):
        """
        Initialize the native sync Info API.

        Args:
            auth: ExtendedAuth instance with credentials
            config: Endpoint configuration
        """
        super().__init__(auth, config)

    def user_state(self, address: Optional[str] = None) -> Dict[str, Any]:
        """
        Get user's account state (balance + positions) - NATIVE SYNC.

        Args:
            address: Ignored (Extended requires auth, uses authenticated user)

        Returns:
            Dict with Hyperliquid-compatible structure containing:
            - assetPositions: List of position info
            - crossMarginSummary: Account value and margin info
            - marginSummary: Margin details
            - withdrawable: Available for withdrawal
        """
        if address is not None and address != self.auth.address:
            warnings.warn(
                "Extended Exchange does not support querying other users. "
                f"Ignoring address={address}, using authenticated user.",
                UserWarning,
            )

        # Make direct HTTP calls instead of using async client
        balance_response = self.get("/account/balance", authenticated=True)
        positions_response = self.get("/account/positions", authenticated=True)

        return AccountTransformer.transform_user_state(
            balance_response.get("data", {}),
            positions_response.get("data", []) or [],
        )

    def open_orders(self, address: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get user's open orders - NATIVE SYNC.

        Args:
            address: Ignored (uses authenticated user)

        Returns:
            List of orders in Hyperliquid format
        """
        if address is not None and address != self.auth.address:
            warnings.warn(
                "Extended Exchange does not support querying other users. "
                f"Ignoring address={address}, using authenticated user.",
                UserWarning,
            )

        response = self.get("/account/open-orders", authenticated=True)
        return OrderTransformer.transform_open_orders(response.get("data", []) or [])

    def meta(self) -> Dict[str, Any]:
        """
        Get exchange metadata (markets info) - NATIVE SYNC.

        Returns:
            Dict with Hyperliquid-compatible structure with universe list
        """
        response = self.get("/markets", authenticated=False)
        return MarketTransformer.transform_meta(response.get("data", []) or [])

    def all_mids(self) -> Dict[str, str]:
        """
        Get mid prices for all markets - NATIVE SYNC.

        Returns:
            Dict mapping coin name to mid price string
        """
        response = self.get("/markets", authenticated=False)
        return MarketTransformer.transform_all_mids(response.get("data", []) or [])

    def l2_snapshot(self, name: str) -> Dict[str, Any]:
        """
        Get order book snapshot - NATIVE SYNC.

        Args:
            name: Market name (e.g., "BTC-USD" or "BTC")

        Returns:
            Dict in Hyperliquid format with coin, levels, and time
        """
        market_name = normalize_market_name(name)
        response = self.get(f"/orderbook/{market_name}", authenticated=False)
        return MarketTransformer.transform_l2_snapshot(response.get("data"))

    def candles_snapshot(
        self,
        name: str,
        interval: str,
        startTime: int,
        endTime: int,
        candle_type: str = DEFAULT_CANDLE_TYPE,
    ) -> List[Dict[str, Any]]:
        """
        Get historical candles - NATIVE SYNC.

        Args:
            name: Market name (e.g., "BTC" or "BTC-USD")
            interval: "1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"
            startTime: Start timestamp (ms)
            endTime: End timestamp (ms)
            candle_type: Type of candle data (default "trades")

        Returns:
            List of candles in Hyperliquid format
        """
        market_name = normalize_market_name(name)
        extended_interval = INTERVAL_MAPPING.get(interval, "PT1M")

        # Convert endTime to datetime for API
        end_dt = datetime.fromtimestamp(endTime / 1000, tz=timezone.utc)

        params = {
            "market": market_name,
            "type": candle_type,
            "interval": extended_interval,
            "end_time": end_dt.isoformat(),
            "limit": 1000
        }

        response = self.get("/candles", params=params, authenticated=False)

        # Filter candles by startTime
        candles = response.get("data", [])
        filtered_candles = [c for c in candles if c.get("timestamp", 0) >= startTime]

        coin = to_hyperliquid_market_name(name)
        return MarketTransformer.transform_candles(filtered_candles, coin, interval)

    def user_fills(
        self,
        coin: Optional[str] = None,
        address: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get user's trade fills - NATIVE SYNC.

        Args:
            coin: Market name (optional - if None, returns fills for all markets)
            address: Ignored (uses authenticated user)
            start_time: Optional start timestamp (ms)
            end_time: Optional end timestamp (ms)

        Returns:
            List of fills in Hyperliquid format (up to 1000 most recent)
        """
        if address is not None and address != self.auth.address:
            warnings.warn(
                "Extended Exchange does not support querying other users. "
                f"Ignoring address={address}, using authenticated user.",
                UserWarning,
            )

        params = {}
        if coin:
            params["market"] = normalize_market_name(coin)
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        response = self.get("/account/trades", params=params, authenticated=True)
        trades = response.get("data", []) or []

        return OrderTransformer.transform_user_fills(trades)

    def get_position_leverage(
        self,
        symbol: str,
        address: Optional[str] = None,
    ) -> Optional[int]:
        """
        Get current leverage for a position - NATIVE SYNC.

        Args:
            symbol: Market name (e.g., "BTC" or "BTC-USD")
            address: Ignored (uses authenticated user)

        Returns:
            Current leverage as integer, or None if not found
        """
        if address is not None and address != self.auth.address:
            warnings.warn(
                "Extended Exchange does not support querying other users. "
                f"Ignoring address={address}, using authenticated user.",
                UserWarning,
            )

        market_name = normalize_market_name(symbol)
        params = {"markets": [market_name]}

        response = self.get("/account/leverage", params=params, authenticated=True)

        leverage_data = response.get("data", [])
        if leverage_data:
            for lev in leverage_data:
                if lev.get("market") == market_name:
                    return int(lev.get("leverage", 0))

        return None