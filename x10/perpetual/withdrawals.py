from decimal import Decimal

from x10.utils.model import HexValue, SettlementSignatureModel, X10BaseModel


class Timestamp(X10BaseModel):
    seconds: int


class StarkWithdrawalSettlement(X10BaseModel):
    recipient: HexValue
    position_id: int
    collateral_id: HexValue
    amount: int
    expiration: Timestamp
    salt: int
    signature: SettlementSignatureModel


class PerpetualWithdrawal(X10BaseModel):
    amount: Decimal
    settlement: StarkWithdrawalSettlement
    description: str | None
