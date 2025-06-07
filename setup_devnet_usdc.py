import asyncio
import json
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Commitment
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import get_associated_token_address, create_associated_token_account
import httpx
import random

# Devnet USDC mint address
USDC_MINT = Pubkey.from_string("4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU")

# List of backup RPC endpoints
RPC_ENDPOINTS = [
    "https://api.devnet.solana.com",
    "https://devnet.solana.com",
    "https://rpc-devnet.helius.xyz/?api-key=1aec9f15-e8f3-41c2-9ffb-1e0b7e4c8b1a"  # Free tier API key
]

async def try_request_airdrop(client: AsyncClient, wallet: Pubkey, amount_sol: float = 0.5) -> bool:
    """Try to request an airdrop once"""
    try:
        amount_lamports = int(amount_sol * 1_000_000_000)
        result = await client.request_airdrop(
            wallet,
            amount_lamports,
            commitment=Commitment("confirmed")
        )
        
        if not result.value:
            return False
            
        print(f"Airdrop requested. Signature: {result.value}")
        await asyncio.sleep(2)  # Wait for confirmation
        
        try:
            await client.confirm_transaction(result.value, commitment=Commitment("confirmed"))
            print(f"Airdrop confirmed!")
            return True
        except Exception as e:
            print(f"Failed to confirm transaction: {str(e)}")
            return False
            
    except Exception as e:
        print(f"Airdrop request failed: {str(e)}")
        return False

async def request_airdrop(wallet: Pubkey, amount_sol: float = 0.5, max_retries: int = 3) -> bool:
    """Request an airdrop using multiple RPC endpoints"""
    for endpoint in RPC_ENDPOINTS:
        print(f"\nTrying RPC endpoint: {endpoint}")
        client = AsyncClient(endpoint)
        
        try:
            for attempt in range(max_retries):
                print(f"Requesting {amount_sol} SOL (attempt {attempt + 1}/{max_retries})...")
                
                if await try_request_airdrop(client, wallet, amount_sol):
                    return True
                    
                if attempt < max_retries - 1:
                    delay = 2 * (2 ** attempt) + random.uniform(0, 1)
                    print(f"Retrying in {delay:.1f} seconds...")
                    await asyncio.sleep(delay)
                    
        except Exception as e:
            print(f"Error with endpoint {endpoint}: {str(e)}")
            continue
        finally:
            await client.close()
            
    return False

async def setup_devnet_usdc():
    """Set up a devnet USDC token account for testing"""
    client = None
    try:
        # Create a new keypair for the test account
        test_wallet = Keypair()
        print(f"Created test wallet: {test_wallet.pubkey()}")
        
        # Request SOL airdrop first
        if not await request_airdrop(test_wallet.pubkey(), 0.5):
            raise Exception("Failed to get SOL airdrop from any endpoint")
        
        # Connect to devnet for remaining operations
        client = AsyncClient(RPC_ENDPOINTS[0])
        
        # Get the associated token account address
        ata = get_associated_token_address(test_wallet.pubkey(), USDC_MINT)
        print(f"Associated token account: {ata}")
        
        # Get recent blockhash
        recent_blockhash = await client.get_latest_blockhash()
        
        # Create the token account
        create_ata_ix = create_associated_token_account(
            payer=test_wallet.pubkey(),
            owner=test_wallet.pubkey(),
            mint=USDC_MINT
        )
        
        # Create versioned message
        message = MessageV0.try_compile(
            payer=test_wallet.pubkey(),
            instructions=[create_ata_ix],
            recent_blockhash=recent_blockhash.value.blockhash,
            address_lookup_table_accounts=[]
        )
        
        # Create and sign transaction
        transaction = VersionedTransaction(message, [test_wallet])
        
        # Send transaction
        print("Sending create account transaction...")
        result = await client.send_transaction(
            transaction,
            opts=TxOpts(skip_preflight=True)
        )
        print(f"Transaction sent: {result.value}")
        
        # Wait for confirmation
        print("Waiting for confirmation...")
        await asyncio.sleep(5)  # Give more time for the transaction to propagate
        await client.confirm_transaction(
            result.value,
            commitment=Commitment("confirmed")
        )
        print(f"Token account created: {ata}")
        
        # Save the account details
        account_info = {
            "pubkey": str(test_wallet.pubkey()),
            "private_key": list(test_wallet.secret()),
            "usdc_account": str(ata)
        }
        
        with open("devnet_usdc_account.json", "w") as f:
            json.dump(account_info, f, indent=2)
            
        print("\nAccount details saved to devnet_usdc_account.json")
        print("\nTo use this account:")
        print("1. Fund it with more SOL if needed using:")
        print("   solana airdrop 2 " + str(test_wallet.pubkey()) + " --url https://api.devnet.solana.com")
        print("2. Fund it with USDC using:")
        print("   spl-token transfer 4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU 1000000000 " + str(ata) + " --url https://api.devnet.solana.com --fund-recipient --allow-unfunded-recipient")
        print(f"\nWallet address: {test_wallet.pubkey()}")
        print(f"USDC account address: {ata}")
        
    except Exception as e:
        print(f"Error setting up devnet USDC account: {str(e)}")
        raise
    finally:
        if client:
            await client.close()

if __name__ == "__main__":
    print("Setting up devnet USDC account...")
    asyncio.run(setup_devnet_usdc()) 