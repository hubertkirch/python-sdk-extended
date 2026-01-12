"""
Extended Exchange SDK - Hyperliquid-compatible interface.

This SDK provides a Hyperliquid/Pacifica-compatible interface for Extended Exchange,
allowing seamless integration with existing trading engines.

Usage:
    # Using Client class
    from extended import Client

    client = Client(
        api_key="your-api-key",
        vault=12345,
        stark_private_key="0x...",
        stark_public_key="0x...",
        testnet=True,
    )

    # Info operations
    state = client.info.user_state()
    orders = client.info.open_orders()

    # Exchange operations
    client.exchange.order("BTC", is_buy=True, sz=0.01, limit_px=50000)
    client.exchange.cancel("BTC", oid=12345)

    # Using setup() function (Hyperliquid-style)
    from extended import setup

    address, info, exchange = setup(
        api_key="your-api-key",
        vault=12345,
        stark_private_key="0x...",
        stark_public_key="0x...",
        testnet=True
    )

    state = info.user_state()
    exchange.order("BTC", is_buy=True, sz=0.01, limit_px=50000)

Note:
    Credentials (api_key, vault, stark keys) must be obtained from your
    onboarding infrastructure. This SDK does not perform onboarding.

Key Differences from Hyperliquid:
    - Credentials: Extended requires 4 credentials from external onboarding
    - No address param: Can't query other users (Extended requires auth)
    - Market names: Extended uses "BTC-USD" internally (auto-converted from "BTC")
    - Bulk orders: Not atomic on Extended
    - Isolated margin: Not supported on Extended
    - Market orders: Simulated as IOC limit orders (may not fill completely)
"""

__version__ = "0.1.0"

# Main clients
from extended.client import Client
from extended.async_client import AsyncClient

# Setup functions (Hyperliquid-style)
from extended.setup import setup, async_setup

# API classes (for type hints)
from extended.api import InfoAPI, AsyncInfoAPI, ExchangeAPI, AsyncExchangeAPI

# Configuration
from extended.config import TESTNET_CONFIG, MAINNET_CONFIG, EndpointConfig

# Exceptions
from extended.exceptions import (
    ExtendedError,
    ExtendedAPIError,
    ExtendedAuthError,
    ExtendedRateLimitError,
    ExtendedValidationError,
    ExtendedNotFoundError,
)

# Types
from extended.types import (
    Side,
    TimeInForce,
    OrderTypeSpec,
    BuilderInfo,
)

__all__ = [
    # Version
    "__version__",
    # Main clients
    "Client",
    "AsyncClient",
    # Setup functions (Hyperliquid-style)
    "setup",
    "async_setup",
    # API classes
    "InfoAPI",
    "AsyncInfoAPI",
    "ExchangeAPI",
    "AsyncExchangeAPI",
    # Config
    "TESTNET_CONFIG",
    "MAINNET_CONFIG",
    "EndpointConfig",
    # Exceptions
    "ExtendedError",
    "ExtendedAPIError",
    "ExtendedAuthError",
    "ExtendedRateLimitError",
    "ExtendedValidationError",
    "ExtendedNotFoundError",
    # Types
    "Side",
    "TimeInForce",
    "OrderTypeSpec",
    "BuilderInfo",
]
