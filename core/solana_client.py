import os
from solana.rpc.api import Client
from solders.pubkey import Pubkey

class SolanaClient:
    def __init__(self):
        # Initialize with devnet for testing
        self.client = Client("https://api.mainnet-beta.solana.com")
        
        # Get wallet address from environment
        wallet_address = os.getenv("SOLANA_WALLET_ADDRESS")
        if not wallet_address:
            raise ValueError("SOLANA_WALLET_ADDRESS environment variable is not set")
            
        self.wallet = Pubkey.from_string(wallet_address)
        
        # Get private key from environment
        private_key = os.getenv("SOLANA_PRIVATE_KEY")
        if not private_key:
            raise ValueError("SOLANA_PRIVATE_KEY environment variable is not set")
            
        self.private_key = private_key

    def get_balance(self):
        """Get wallet balance in SOL"""
        response = self.client.get_balance(self.wallet)
        # Convert lamports to SOL (1 SOL = 1e9 lamports)
        return response.value / 1e9

# Example usage
if __name__ == "__main__":
    solana = SolanaClient()
    print(f"Wallet address: {solana.wallet}")
    print(f"Wallet balance: {solana.get_balance():.9f} SOL")