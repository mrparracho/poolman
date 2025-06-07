from typing import Dict
import logging
import json
import subprocess
from pathlib import Path
from .base import BaseAction, ActionExample

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class AddLiquidityAction(BaseAction):
    def __init__(self):
        # Ensure TypeScript service is built
        services_dir = Path(__file__).parent.parent / 'services'
        self.service_path = services_dir / 'dist' / 'raydium_service.js'
        
        if not self.service_path.exists():
            logger.info("Building TypeScript service...")
            subprocess.run(['npm', 'install'], cwd=services_dir, check=True)
            subprocess.run(['npm', 'run', 'build'], cwd=services_dir, check=True)

    @property
    def intent_name(self) -> str:
        return "add_liquidity"
    
    @property
    def parameters(self) -> Dict[str, str]:
        return {
            "pool_id": "Required - The Raydium pool ID to add liquidity to",
            "wallet": "Required - The wallet private key to use for adding liquidity",
            "amount_a": "Required - Amount of first token to add",
            "amount_b": "Required - Amount of second token to add",
            "slippage_tolerance": "Optional - Maximum allowed slippage (default: 0.5%)"
        }
    
    @property
    def examples(self) -> list[ActionExample]:
        return [
            ActionExample(
                command="add 100 USDC and 0.5 SOL liquidity to pool abc123 using wallet xyz789",
                intent="add_liquidity",
                params={
                    "pool_id": "abc123",
                    "wallet": "xyz789",
                    "amount_a": "100",
                    "amount_b": "0.5",
                    "slippage_tolerance": "0.5"
                }
            )
        ]
    
    @property
    def description(self) -> str:
        return "Adds liquidity to a specified Raydium pool using the provided wallet and token amounts"

    def run(self, pool_id: str, wallet: str, amount_a: float, amount_b: float, 
            slippage_tolerance: float = 0.5, **kwargs) -> str:
        """
        Add liquidity to a Raydium pool using the TypeScript service
        
        :param pool_id: The Raydium pool ID
        :param wallet: The wallet private key (hex string)
        :param amount_a: Amount of first token to add
        :param amount_b: Amount of second token to add
        :param slippage_tolerance: Maximum allowed slippage percentage (default: 0.5%)
        :return: Transaction result message
        """
        try:
            logger.info(f"Adding liquidity to pool {pool_id}")
            
            # Prepare parameters for TypeScript service
            params = {
                "poolId": pool_id,
                "walletPrivateKey": wallet,
                "amountA": amount_a,
                "amountB": amount_b,
                "slippageTolerance": slippage_tolerance
            }
            
            # Call TypeScript service
            result = subprocess.run(
                ['node', str(self.service_path)],
                input=json.dumps(params),
                text=True,
                capture_output=True,
                check=True
            )
            
            # Parse result
            response = json.loads(result.stdout)
            
            if not response["success"]:
                raise ValueError(response["error"])
            
            logger.info(f"Successfully added liquidity to pool {pool_id}")
            return (f"Successfully added {amount_a} of token A and {amount_b} of token B "
                   f"to pool {pool_id}. Transaction signature: {response['signature']}")
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Service error: {e.stderr}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"Failed to add liquidity: {str(e)}"
            logger.error(error_msg)
            return error_msg

if __name__ == "__main__":
    # Example usage
    action = AddLiquidityAction()
    # Replace these with actual values
    pool_id = "your_pool_id"
    wallet = "your_wallet_private_key"  # Private key in hex format
    result = action.run(pool_id, wallet, 100, 0.5, slippage_tolerance=0.5)