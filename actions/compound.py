from .base import BaseAction, ActionExample

class CompoundAction(BaseAction):
    @property
    def intent_name(self) -> str:
        return "compound_fees"
    
    @property
    def parameters(self) -> dict[str, str]:
        return {
            "trading_pair": "Required - The trading pair to compound fees for (e.g., 'ETH/USDC')",
            "wallet": "Required - The wallet address owning the position"
        }
    
    @property
    def examples(self) -> list[ActionExample]:
        return [
            ActionExample(
                command="compound fees for ETH/USDC pool using wallet 0x123",
                intent="compound_fees",
                params={"trading_pair": "ETH/USDC", "wallet": "0x123"}
            ),
            ActionExample(
                command="compound ETH/USDC fees with 0xabc",
                intent="compound_fees",
                params={"trading_pair": "ETH/USDC", "wallet": "0xabc"}
            )
        ]
    
    @property
    def description(self) -> str:
        return "Compounds accumulated trading fees back into the liquidity pool for a specified trading pair and wallet"
    
    def run(self, trading_pair: str, wallet: str, **kwargs) -> str:
        if not trading_pair or not wallet:
            raise ValueError("Trading pair and wallet address are required")
        
        # TODO: Add actual fee compounding logic here
        return f"Successfully compounded fees for {trading_pair} pool using wallet {wallet}"