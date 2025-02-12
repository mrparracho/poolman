from .base import BaseAction, ActionExample
from typing import Dict

class FetchMarketAction(BaseAction):
    @property
    def intent_name(self) -> str:
        return "fetch_market_data"
    
    @property
    def parameters(self) -> Dict[str, str]:
        return {
            "trading_pair": "Optional - The trading pair to fetch data for (e.g., 'ETH/USDC')"
        }
    
    @property
    def examples(self) -> list[ActionExample]:
        return [
            ActionExample(
                command="fetch market data for ETH/USDC",
                intent="fetch_market_data",
                params={"trading_pair": "ETH/USDC"}
            ),
            ActionExample(
                command="show me the market data",
                intent="fetch_market_data",
                params={}
            )
        ]
    
    @property
    def description(self) -> str:
        return "Fetches current market data for a specific trading pair or provides a global market summary if no pair is specified"
    
    def run(self, trading_pair: str = None, **kwargs) -> str:
        """
        Fetches market data for specified trading pair(s).
        
        Args:
            trading_pair (str, optional): Specific trading pair to fetch data for
            **kwargs: Additional optional parameters
            
        Returns:
            str: Market data information
        """
        # TODO: Add actual market data fetching logic
        # This would typically involve calling an external API
        
        if trading_pair:
            return f"Market data for {trading_pair}: Price: $X,XXX.XX, 24h Volume: $XX,XXX,XXX"
        else:
            return "Global market summary: Total Volume: $XX,XXX,XXX,XXX" 