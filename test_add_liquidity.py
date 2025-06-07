import json
import asyncio
import requests
import base64
import functools
from typing import Callable, Any
try:
    import base58
    HAS_BASE58 = True
except ImportError:
    HAS_BASE58 = False
    print("Warning: base58 package not found, using base64 fallback. Please run: pip install base58")

from solana.rpc.api import Client
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Commitment
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.instruction import Instruction, AccountMeta
from solders.system_program import ID as SYS_PROGRAM_ID, transfer as sys_transfer, TransferParams as SysTransferParams, create_account, CreateAccountParams
from solders.compute_budget import ID as COMPUTE_BUDGET_PROGRAM_ID
from solders.message import Message, MessageV0, VersionedMessage
from solders.instruction import CompiledInstruction

from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import get_associated_token_address, transfer, TransferParams, approve, ApproveParams, create_associated_token_account, InitializeAccountParams, initialize_account

from core.solana_client import SolanaClient

RAYDIUM_API = "https://api.raydium.io/v2/main"  # Updated API endpoint
RAYDIUM_PROGRAM_ID = Pubkey.from_string("DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1")  # Raydium Devnet Program ID
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")  # SPL Token Program ID (same on all networks)
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")  # SPL Associated Token Program ID (same on all networks)

# Use Solana devnet endpoint
RPC_ENDPOINT = "https://api.devnet.solana.com"

# Devnet pool configuration
DEVNET_POOL = {
    'id': '8nVTrwi7ZzqiWLd7tDvYWQqxM5ViKCFqJXggg9Jvf1Vs',  # Example devnet pool ID
    'baseMint': 'So11111111111111111111111111111111111111112',  # SOL
    'quoteMint': '4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU',  # Devnet USDC
    'baseDecimals': 9,
    'quoteDecimals': 6,
    'authority': '5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1'  # Pool authority
}

def async_retry(retries: int = 3, delay: float = 1.0):
    """Simple retry decorator for async functions"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < retries - 1:
                        wait_time = delay * (2 ** attempt)  # Exponential backoff
                        print(f"Attempt {attempt + 1} failed, retrying in {wait_time:.1f}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"All {retries} attempts failed.")
                        raise last_exception
            return None
        return wrapper
    return decorator

@async_retry(retries=3, delay=1.0)
async def get_token_decimals(client: AsyncClient, mint: Pubkey) -> int:
    """Get token decimals from the Solana network"""
    try:
        mint_info = await client.get_account_info(mint)
        if not mint_info.value:
            raise ValueError(f"Token mint {mint} not found")
            
        data = mint_info.value.data
        decimals = data[44]
        print(f"Got decimals for {mint}: {decimals}")
        return decimals
        
    except Exception as e:
        print(f"Error getting token decimals for {mint}: {e}")
        raise

@async_retry(retries=3, delay=1.0)
async def get_token_balance(client: AsyncClient, token_account: Pubkey) -> int:
    """Get token balance from a token account"""
    try:
        account_info = await client.get_account_info(token_account)
        if not account_info.value:
            return 0
            
        data = account_info.value.data
        # Token account data layout:
        # https://github.com/solana-labs/solana-program-library/blob/master/token/program/src/state.rs#L86
        # Amount is a u64 at offset 64
        amount = int.from_bytes(data[64:72], byteorder='little')
        return amount
        
    except Exception as e:
        print(f"Error getting token balance: {e}")
        raise

@async_retry(retries=3, delay=1.0)
async def get_or_create_token_account(client: AsyncClient, wallet: Keypair, token_mint: Pubkey) -> Pubkey:
    """Get or create an associated token account"""
    try:
        # Calculate the ATA address
        ata = get_associated_token_address(wallet.pubkey(), token_mint)
        
        # Check if account exists
        account_info = await client.get_account_info(ata)
        if account_info.value:
            print(f"Found existing token account: {ata}")
            return ata
            
        print(f"Creating token account for mint {token_mint}")
        
        # Get recent blockhash
        recent_blockhash = await client.get_latest_blockhash()
        
        # Create ATA instruction
        create_ata_ix = create_associated_token_account(
            payer=wallet.pubkey(),
            owner=wallet.pubkey(),
            mint=token_mint
        )
        
        # Create versioned message
        message = MessageV0.try_compile(
            payer=wallet.pubkey(),
            instructions=[create_ata_ix],
            recent_blockhash=recent_blockhash.value.blockhash,
            address_lookup_table_accounts=[]
        )
        
        # Create and sign transaction
        transaction = VersionedTransaction(message, [wallet])
        
        # Send transaction
        print("Sending create account transaction...")
        result = await client.send_transaction(
            transaction,
            opts=TxOpts(skip_preflight=True)
        )
        print(f"Transaction sent: {result.value}")
        
        # Wait for confirmation
        await client.confirm_transaction(
            result.value,
            commitment=Commitment("confirmed")
        )
        print(f"Token account created: {ata}")
        
        return ata
        
    except Exception as e:
        print(f"Error creating token account: {e}")
        raise

@async_retry(retries=3, delay=1.0)
async def request_airdrop(client: AsyncClient, wallet: Pubkey, amount_sol: float = 1.0):
    """Request an airdrop of SOL from devnet"""
    try:
        amount_lamports = int(amount_sol * 1_000_000_000)
        print(f"Requesting airdrop of {amount_sol} SOL...")
        
        result = await client.request_airdrop(
            wallet,
            amount_lamports,
            commitment=Commitment("confirmed")
        )
        
        if not result.value:
            raise ValueError("Airdrop request failed")
            
        print(f"Airdrop requested. Signature: {result.value}")
        await client.confirm_transaction(result.value, commitment=Commitment("confirmed"))
        print(f"Airdrop confirmed!")
        
    except Exception as e:
        print(f"Error requesting airdrop: {e}")
        raise

@async_retry(retries=3, delay=1.0)
async def wrap_sol(client: AsyncClient, wallet: Keypair, amount_sol: float) -> Pubkey:
    """Wrap SOL into a token account"""
    try:
        # Get the associated token account for wrapped SOL
        wsol_mint = Pubkey.from_string("So11111111111111111111111111111111111111112")
        wsol_account = get_associated_token_address(wallet.pubkey(), wsol_mint)
        
        print(f"Wrapping {amount_sol} SOL...")
        print(f"WSOL account: {wsol_account}")
        
        # Convert SOL amount to lamports
        amount_lamports = int(amount_sol * 1_000_000_000)
        
        # Get recent blockhash
        recent_blockhash = await client.get_latest_blockhash()
        
        # Create instructions array
        instructions = []
        
        # Check if account exists
        account_info = await client.get_account_info(wsol_account)
        if not account_info.value:
            print("Creating wrapped SOL account...")
            create_ata_ix = create_associated_token_account(
                payer=wallet.pubkey(),
                owner=wallet.pubkey(),
                mint=wsol_mint
            )
            instructions.append(create_ata_ix)
        
        # Create transfer instruction to send SOL
        transfer_ix = sys_transfer(
            SysTransferParams(
                from_pubkey=wallet.pubkey(),
                to_pubkey=wsol_account,
                lamports=amount_lamports
            )
        )
        instructions.append(transfer_ix)
        
        # Create sync native instruction
        sync_native_ix = Instruction(
            program_id=TOKEN_PROGRAM_ID,
            accounts=[
                AccountMeta(pubkey=wsol_account, is_signer=False, is_writable=True)
            ],
            data=bytes([17])  # SyncNative instruction
        )
        instructions.append(sync_native_ix)
        
        # Create versioned message
        message = MessageV0.try_compile(
            payer=wallet.pubkey(),
            instructions=instructions,
            recent_blockhash=recent_blockhash.value.blockhash,
            address_lookup_table_accounts=[]
        )
        
        # Create and sign transaction
        transaction = VersionedTransaction(message, [wallet])
        
        # Send transaction
        print("Sending wrap SOL transaction...")
        result = await client.send_transaction(
            transaction,
            opts=TxOpts(skip_preflight=True)
        )
        print(f"Transaction sent: {result.value}")
        
        # Wait for confirmation
        await client.confirm_transaction(
            result.value,
            commitment=Commitment("confirmed")
        )
        print(f"SOL wrapped successfully")
        
        # Verify the balance
        balance = await get_token_balance(client, wsol_account)
        print(f"Wrapped SOL balance: {balance / 1_000_000_000} SOL")
        
        return wsol_account
        
    except Exception as e:
        print(f"Error wrapping SOL: {e}")
        raise

@async_retry(retries=3, delay=1.0)
async def request_usdc_airdrop(client: AsyncClient, wallet: Keypair, amount_usdc: float = 1.0):
    """Get USDC from pre-funded devnet account"""
    try:
        # Get or create USDC token account
        usdc_mint = Pubkey.from_string("4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU")  # Devnet USDC mint
        usdc_account = await get_or_create_token_account(client, wallet, usdc_mint)
        
        print(f"Getting {amount_usdc} USDC from pre-funded devnet account...")
        
        # Load the pre-funded account details
        try:
            with open("devnet_usdc_account.json", "r") as f:
                account_info = json.load(f)
                
            # Create keypair from saved private key
            funded_wallet = Keypair.from_bytes(bytes(account_info["private_key"]))
            funded_usdc_account = Pubkey.from_string(account_info["usdc_account"])
            
        except FileNotFoundError:
            raise ValueError(
                "Pre-funded account not found. Please run setup_devnet_usdc.py first "
                "and fund the created account with SOL and USDC."
            )
        
        # Get recent blockhash
        recent_blockhash = await client.get_latest_blockhash()
        
        # Create transfer instruction
        transfer_ix = transfer(
            TransferParams(
                program_id=TOKEN_PROGRAM_ID,
                source=funded_usdc_account,
                dest=usdc_account,
                owner=funded_wallet.pubkey(),
                amount=int(amount_usdc * 1_000_000)  # USDC has 6 decimals
            )
        )
        
        # Create versioned message
        message = MessageV0.try_compile(
            payer=funded_wallet.pubkey(),
            instructions=[transfer_ix],
            recent_blockhash=recent_blockhash.value.blockhash,
            address_lookup_table_accounts=[]
        )
        
        # Create and sign transaction
        transaction = VersionedTransaction(message, [funded_wallet])
        
        # Send transaction
        print("Sending transfer transaction...")
        result = await client.send_transaction(
            transaction,
            opts=TxOpts(skip_preflight=True)
        )
        print(f"Transaction sent: {result.value}")
        
        # Wait for confirmation
        print("Waiting for confirmation...")
        await asyncio.sleep(5)  # Give some time for the transaction to propagate
        await client.confirm_transaction(
            result.value,
            commitment=Commitment("confirmed")
        )
        print("USDC transfer successful")
        
        # Verify balance
        await asyncio.sleep(2)  # Wait a bit for balance to update
        balance = await get_token_balance(client, usdc_account)
        print(f"USDC balance: {balance / 1_000_000} USDC")
        
        if balance == 0:
            raise ValueError("Failed to get USDC - balance is still 0")
            
        return usdc_account
        
    except Exception as e:
        print(f"Error getting USDC: {e}")
        raise

async def add_liquidity(client: AsyncClient, wallet: Keypair, pool_id: str, amount_base: float, amount_quote: float):
    """
    Adds liquidity to a Raydium pool on devnet.
    :param client: Solana AsyncClient
    :param wallet: Keypair of the wallet providing liquidity
    :param pool_id: ID of the Raydium liquidity pool
    :param amount_base: Amount of base token to deposit
    :param amount_quote: Amount of quote token to deposit
    """
    try:
        # For devnet testing, we'll use the devnet pool configuration
        print("Using devnet pool configuration...")
        pool_info = {
            'baseMint': DEVNET_POOL['baseMint'],
            'quoteMint': DEVNET_POOL['quoteMint'],
            'baseDecimals': DEVNET_POOL['baseDecimals'],
            'quoteDecimals': DEVNET_POOL['quoteDecimals'],
            'lpMint': DEVNET_POOL['id'],
            'authority': DEVNET_POOL['authority']
        }
        
        print(f"Pool info: {json.dumps(pool_info, indent=2)}")
        
        # Extract pool data
        token_mint_base = Pubkey.from_string(pool_info['baseMint'])
        token_mint_quote = Pubkey.from_string(pool_info['quoteMint'])
        pool_authority = Pubkey.from_string(pool_info['authority'])
        
        # Get token decimals
        decimals_base = pool_info['baseDecimals']
        decimals_quote = pool_info['quoteDecimals']
        
        print(f"Base token decimals: {decimals_base}")
        print(f"Quote token decimals: {decimals_quote}")
        
        # Get or create token accounts
        print("Setting up token accounts...")
        # For base token (SOL), we need to wrap it first
        base_token_account = await wrap_sol(client, wallet, amount_base)
        quote_token_account = await get_or_create_token_account(client, wallet, token_mint_quote)
        
        # Get vault addresses
        base_vault = get_associated_token_address(pool_authority, token_mint_base)
        quote_vault = get_associated_token_address(pool_authority, token_mint_quote)
        
        print(f"Base token account: {base_token_account}")
        print(f"Quote token account: {quote_token_account}")
        print(f"Base vault: {base_vault}")
        print(f"Quote vault: {quote_vault}")
        
        # Check balances
        print("Checking token balances...")
        base_balance = await get_token_balance(client, base_token_account)
        quote_balance = await get_token_balance(client, quote_token_account)
        
        base_amount_lamports = int(amount_base * (10 ** decimals_base))
        quote_amount_lamports = int(amount_quote * (10 ** decimals_quote))
        
        print(f"Base balance: {base_balance / (10 ** decimals_base)} SOL")
        print(f"Quote balance: {quote_balance / (10 ** decimals_quote)} USDC")
        print(f"Required base: {amount_base} SOL")
        print(f"Required quote: {amount_quote} USDC")
        
        if base_balance < base_amount_lamports:
            raise ValueError(f"Insufficient base token balance. Have {base_balance / (10 ** decimals_base)}, need {amount_base}")
        
        if quote_balance < quote_amount_lamports:
            raise ValueError(f"Insufficient quote token balance. Have {quote_balance / (10 ** decimals_quote)}, need {amount_quote}")
        
        # Get recent blockhash
        recent_blockhash = await client.get_latest_blockhash()
        
        # Create transfer instructions
        transfer_base = transfer(
            TransferParams(
                program_id=TOKEN_PROGRAM_ID,
                source=base_token_account,
                dest=base_vault,
                owner=wallet.pubkey(),
                amount=base_amount_lamports
            )
        )
        
        transfer_quote = transfer(
            TransferParams(
                program_id=TOKEN_PROGRAM_ID,
                source=quote_token_account,
                dest=quote_vault,
                owner=wallet.pubkey(),
                amount=quote_amount_lamports
            )
        )
        
        # Create versioned message
        message = MessageV0.try_compile(
            payer=wallet.pubkey(),
            instructions=[transfer_base, transfer_quote],
            recent_blockhash=recent_blockhash.value.blockhash,
            address_lookup_table_accounts=[]
        )
        
        # Create and sign transaction
        transaction = VersionedTransaction(message, [wallet])
        
        # Send transaction
        print("Sending transaction...")
        txid = await client.send_transaction(
            transaction,
            opts=TxOpts(skip_preflight=True)  # Skip preflight for devnet
        )
        print(f"Transaction sent: {txid.value}")
        
        # Confirm transaction
        print("Confirming transaction...")
        await client.confirm_transaction(txid.value, commitment=Commitment("confirmed"))
        print("Liquidity added successfully.")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        if isinstance(e, requests.exceptions.RequestException):
            print(f"API Response: {e.response.text if hasattr(e, 'response') else 'No response'}")
        raise

async def test_add_liquidity():
    """
    Test function to demonstrate adding liquidity to a Raydium pool on devnet
    """
    try:
        # Initialize Solana client
        solana = SolanaClient()
        
        # Create async client for devnet
        async_client = AsyncClient(RPC_ENDPOINT, timeout=30)
        
        # Create keypair from private key
        try:
            if HAS_BASE58:
                private_key_bytes = base58.b58decode(solana.private_key)
                print("Decoded private key using base58")
            else:
                private_key_bytes = base64.b64decode(solana.private_key)
                print("Decoded private key using base64")
        except Exception as e1:
            print(f"Base58/64 decode failed: {e1}")
            try:
                clean_key = solana.private_key.strip('[]').replace(',', '').replace(' ', '')
                if all(c.isdigit() for c in clean_key.split()):
                    private_key_bytes = bytes([int(x) for x in clean_key.split()])
                    print("Decoded private key from number array")
                else:
                    private_key_bytes = bytes.fromhex(clean_key)
                    print("Decoded private key from hex")
            except Exception as e2:
                print(f"Raw key format: {solana.private_key[:32]}...")
                raise ValueError(f"Could not decode private key. Please ensure it's in base58, base64, hex, or number array format. Error: {e2}")

        print(f"Private key length: {len(private_key_bytes)} bytes")
        if len(private_key_bytes) != 64:
            raise ValueError(f"Invalid private key length: {len(private_key_bytes)} bytes. Expected 64 bytes.")
            
        wallet = Keypair.from_bytes(private_key_bytes)
        print(f"Successfully created keypair")
        
        # Check initial SOL balance
        sol_balance = solana.get_balance()
        print(f"SOL Balance: {sol_balance} SOL")
        
        # Request airdrop if balance is low
        if sol_balance < 1:
            print("Balance too low, requesting airdrop...")
            await request_airdrop(async_client, wallet.pubkey(), 2.0)
            sol_balance = solana.get_balance()
            print(f"New SOL Balance after airdrop: {sol_balance} SOL")
        
        if sol_balance < 0.05:
            raise ValueError(f"Insufficient SOL balance. Please fund your wallet with at least 0.1 SOL for transaction fees.")
        
        # Use devnet pool configuration
        pool_id = DEVNET_POOL['id']
        amount_base = 0.05   # Example: 0.05 SOL
        amount_quote = 1.0   # Example: 1 USDC
        
        print(f"Testing add_liquidity with:")
        print(f"Wallet: {wallet.pubkey()}")
        print(f"Pool ID: {pool_id}")
        print(f"Pool Authority: {DEVNET_POOL['authority']}")
        print(f"Base Amount: {amount_base}")
        print(f"Quote Amount: {amount_quote}")
        
        # Request USDC airdrop before adding liquidity
        await request_usdc_airdrop(async_client, wallet, amount_quote)
        
        # Add liquidity
        await add_liquidity(
            client=async_client,
            wallet=wallet,
            pool_id=pool_id,
            amount_base=amount_base,
            amount_quote=amount_quote
        )
        
        # Check final SOL balance
        sol_balance_after = solana.get_balance()
        print(f"Final SOL Balance: {sol_balance_after} SOL")
        print(f"SOL spent on fees: {sol_balance - sol_balance_after} SOL")
        
    except Exception as e:
        print(f"Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        await async_client.close()

if __name__ == "__main__":
    print("Starting Raydium add liquidity test on devnet...")
    asyncio.run(test_add_liquidity())

