"""
Unit tests for quantity precision handling in the Exchange API.

These tests validate that:
1. The quantize_to_precision function correctly formats Decimals
2. Orders are signed and serialized with correct precision
3. Different precision values (0, 2, 5, etc.) are handled correctly
4. The order hash remains consistent regardless of input decimal format
"""

import pytest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from hamcrest import assert_that, equal_to, has_entry, contains_string

from extended.api.exchange_native_sync import quantize_to_precision


class TestQuantizeToPrecision:
    """Tests for the quantize_to_precision helper function."""

    def test_precision_zero_from_float(self):
        """Test that float-derived Decimal is quantized to integer for precision=0."""
        # This is the problematic case: Decimal(str(14.0)) creates Decimal('14.0')
        value = Decimal(str(14.0))
        result = quantize_to_precision(value, 0)

        # Should be '14' not '14.0'
        assert_that(str(result), equal_to("14"))

    def test_precision_zero_from_int(self):
        """Test that int-derived Decimal stays as integer for precision=0."""
        value = Decimal("14")
        result = quantize_to_precision(value, 0)

        assert_that(str(result), equal_to("14"))

    def test_precision_zero_with_trailing_zeros(self):
        """Test that Decimal with many trailing zeros is quantized for precision=0."""
        value = Decimal("14.00000000")
        result = quantize_to_precision(value, 0)

        assert_that(str(result), equal_to("14"))

    def test_precision_zero_rounds_down(self):
        """Test that fractional values are rounded down for precision=0."""
        value = Decimal("14.9")
        result = quantize_to_precision(value, 0)

        assert_that(str(result), equal_to("14"))

    def test_precision_two_from_float(self):
        """Test precision=2 formatting."""
        value = Decimal(str(0.1))
        result = quantize_to_precision(value, 2)

        assert_that(str(result), equal_to("0.10"))

    def test_precision_two_rounds_down(self):
        """Test precision=2 rounds down correctly."""
        value = Decimal("0.129")
        result = quantize_to_precision(value, 2)

        assert_that(str(result), equal_to("0.12"))

    def test_precision_five_from_float(self):
        """Test precision=5 formatting (typical for BTC)."""
        value = Decimal(str(0.001))
        result = quantize_to_precision(value, 5)

        assert_that(str(result), equal_to("0.00100"))

    def test_precision_five_with_more_decimals(self):
        """Test precision=5 truncates extra decimals."""
        value = Decimal("0.00123456789")
        result = quantize_to_precision(value, 5)

        assert_that(str(result), equal_to("0.00123"))

    def test_large_value_precision_zero(self):
        """Test large values with precision=0."""
        value = Decimal("1000000.0")
        result = quantize_to_precision(value, 0)

        assert_that(str(result), equal_to("1000000"))

    def test_small_value_high_precision(self):
        """Test small values with high precision."""
        value = Decimal("0.000001")
        result = quantize_to_precision(value, 8)

        assert_that(str(result), equal_to("0.00000100"))


class TestOrderQuantityPrecisionSerialization:
    """Tests that verify order serialization uses correct precision."""

    def test_order_qty_serialization_precision_zero(self):
        """Test that order qty is serialized correctly for precision=0 markets (like LIT)."""
        from decimal import Decimal
        from pydantic import BaseModel

        class MockOrder(BaseModel):
            qty: Decimal

        # Simulate what happens when we quantize correctly
        qty_quantized = quantize_to_precision(Decimal(str(14.0)), 0)
        order = MockOrder(qty=qty_quantized)
        serialized = order.model_dump(mode="json")

        # The qty should be "14" not "14.0"
        assert_that(serialized["qty"], equal_to("14"))

    def test_order_qty_serialization_precision_five(self):
        """Test that order qty is serialized correctly for precision=5 markets (like BTC)."""
        from decimal import Decimal
        from pydantic import BaseModel

        class MockOrder(BaseModel):
            qty: Decimal

        qty_quantized = quantize_to_precision(Decimal(str(0.001)), 5)
        order = MockOrder(qty=qty_quantized)
        serialized = order.model_dump(mode="json")

        assert_that(serialized["qty"], equal_to("0.00100"))

    def test_without_quantization_causes_wrong_format(self):
        """Demonstrate that without quantization, serialization produces wrong format."""
        from decimal import Decimal
        from pydantic import BaseModel

        class MockOrder(BaseModel):
            qty: Decimal

        # Without quantization - this is the bug we're fixing
        qty_unquantized = Decimal(str(14.0))
        order = MockOrder(qty=qty_unquantized)
        serialized = order.model_dump(mode="json")

        # This would fail API validation for precision=0 markets
        assert_that(serialized["qty"], equal_to("14.0"))  # Wrong!


class TestOrderSigningConsistency:
    """Tests that verify signing is consistent regardless of input format."""

    @pytest.fixture
    def mock_market_precision_zero(self):
        """Create a mock market with asset_precision=0 (like LIT)."""
        market = MagicMock()
        market.name = "LIT-USD"
        market.asset_precision = 0
        market.synthetic_asset = MagicMock()
        market.synthetic_asset.settlement_resolution = 1
        market.collateral_asset = MagicMock()
        return market

    @pytest.fixture
    def mock_market_precision_five(self):
        """Create a mock market with asset_precision=5 (like BTC)."""
        market = MagicMock()
        market.name = "BTC-USD"
        market.asset_precision = 5
        market.synthetic_asset = MagicMock()
        market.synthetic_asset.settlement_resolution = 1000000
        market.collateral_asset = MagicMock()
        return market

    def test_quantized_decimal_formats_match(self):
        """Verify that different input formats produce same quantized result."""
        # All these should produce the same result for precision=0
        inputs = [
            Decimal("14"),
            Decimal("14.0"),
            Decimal("14.00"),
            Decimal(str(14.0)),
            Decimal(str(14)),
            Decimal("14.000000"),
        ]

        results = [quantize_to_precision(v, 0) for v in inputs]

        # All should equal Decimal('14')
        for result in results:
            assert_that(str(result), equal_to("14"))

        # All should be equal to each other
        for i in range(1, len(results)):
            assert_that(results[i], equal_to(results[0]))

    def test_quantized_values_have_same_hash(self):
        """Verify that quantized values from different inputs have same hash behavior."""
        inputs = [
            Decimal("14"),
            Decimal("14.0"),
            Decimal(str(14.0)),
        ]

        quantized = [quantize_to_precision(v, 0) for v in inputs]

        # When used in a hash (like for signing), they should be equivalent
        # This simulates how the stark amount conversion works
        stark_amounts = [int(q * 1) for q in quantized]  # resolution=1 for simplicity

        for i in range(1, len(stark_amounts)):
            assert_that(stark_amounts[i], equal_to(stark_amounts[0]))


class TestIntegrationWithOrderCreation:
    """Integration tests for order creation with precision handling."""

    @pytest.mark.asyncio
    async def test_create_order_with_precision_zero_market(
        self, create_trading_account, btc_usd_market_json_data
    ):
        """Test creating an order for a market that requires integer quantities."""
        from x10.perpetual.order_object import create_order_object
        from x10.perpetual.orders import OrderSide
        from x10.perpetual.configuration import TESTNET_CONFIG
        from tests.fixtures.markets import create_btc_usd_market

        # Create a modified market with precision=0 (like LIT)
        import json
        market_data = json.loads(btc_usd_market_json_data)
        market_data["data"][0]["assetPrecision"] = 0
        market_data["data"][0]["name"] = "LIT-USD"
        market_data["data"][0]["assetName"] = "LIT"

        from x10.perpetual.markets import MarketModel
        from x10.utils.http import WrappedApiResponse
        from typing import List

        result = WrappedApiResponse[List[MarketModel]].model_validate(market_data)
        market = result.data[0]

        trading_account = create_trading_account()

        # Quantize the amount before passing to create_order_object
        amount = quantize_to_precision(Decimal(str(14.0)), market.asset_precision)

        order = create_order_object(
            account=trading_account,
            market=market,
            amount_of_synthetic=amount,
            price=Decimal("1.80"),
            side=OrderSide.SELL,
            starknet_domain=TESTNET_CONFIG.starknet_domain,
        )

        order_json = order.to_api_request_json()

        # The qty should be "14" not "14.0" or "14.00000"
        assert_that(order_json["qty"], equal_to("14"))

    @pytest.mark.asyncio
    async def test_order_signature_consistent_with_quantization(
        self, create_trading_account, btc_usd_market_json_data
    ):
        """Test that order signatures are consistent when using quantized values."""
        from x10.perpetual.order_object import create_order_object
        from x10.perpetual.orders import OrderSide
        from x10.perpetual.configuration import TESTNET_CONFIG
        from tests.fixtures.markets import create_btc_usd_market
        from datetime import datetime, timezone

        market = create_btc_usd_market(btc_usd_market_json_data)
        trading_account = create_trading_account()

        # Create same order with different input formats but same quantized value
        fixed_expire = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        fixed_nonce = 12345

        amount1 = quantize_to_precision(Decimal("0.001"), market.asset_precision)
        amount2 = quantize_to_precision(Decimal(str(0.001)), market.asset_precision)
        amount3 = quantize_to_precision(Decimal("0.00100000"), market.asset_precision)

        orders = []
        for amount in [amount1, amount2, amount3]:
            order = create_order_object(
                account=trading_account,
                market=market,
                amount_of_synthetic=amount,
                price=Decimal("50000.00"),
                side=OrderSide.BUY,
                starknet_domain=TESTNET_CONFIG.starknet_domain,
                expire_time=fixed_expire,
                nonce=fixed_nonce,
            )
            orders.append(order)

        # All orders should have the same signature
        signatures = [o.settlement.signature for o in orders]
        for i in range(1, len(signatures)):
            assert_that(signatures[i].r, equal_to(signatures[0].r))
            assert_that(signatures[i].s, equal_to(signatures[0].s))

        # All orders should have the same qty in JSON
        qtys = [o.to_api_request_json()["qty"] for o in orders]
        for qty in qtys:
            assert_that(qty, equal_to(qtys[0]))
