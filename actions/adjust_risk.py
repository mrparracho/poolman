from .base import BaseAction, ActionExample

class AdjustRiskAction(BaseAction):
    @property
    def intent_name(self) -> str:
        return "adjust_risk"
    
    @property
    def parameters(self) -> dict[str, str]:
        return {
            "trading_pair": "Required - The trading pair to adjust risk for (e.g., 'ETH/USDC')",
            "risk_level": "Required - Risk level between 0.0 (conservative) and 1.0 (aggressive)"
        }
    
    @property
    def examples(self) -> list[ActionExample]:
        return [
            ActionExample(
                command="adjust risk to 0.8 for ETH/USDC",
                intent="adjust_risk",
                params={"trading_pair": "ETH/USDC", "risk_level": 0.8}
            ),
            ActionExample(
                command="set ETH/USDC risk level to 0.5",
                intent="adjust_risk",
                params={"trading_pair": "ETH/USDC", "risk_level": 0.5}
            )
        ]
    
    @property
    def description(self) -> str:
        return "Adjusts the risk parameters for an existing liquidity pool, with risk levels ranging from 0.0 (conservative) to 1.0 (aggressive)"
    
    def run(self, trading_pair: str, risk_level: float, **kwargs) -> str:
        if not trading_pair:
            raise ValueError("Trading pair is required")
        if not isinstance(risk_level, (int, float)) or not 0 <= risk_level <= 1:
            raise ValueError("Risk level must be between 0 and 1")
        
        # TODO: Add actual risk adjustment logic here
        return f"Successfully adjusted risk level to {risk_level} for {trading_pair}" 