import json
import asyncio
import requests
import base64
import functools
import random
import httpx
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
from solders.system_program import ID as SYS_PROGRAM_ID, transfer as sys_transfer, TransferParams as SysTransferParams
from solders.compute_budget import ID as COMPUTE_BUDGET_PROGRAM_ID
from solders.message import Message, MessageV0, VersionedMessage
from solders.instruction import CompiledInstruction

from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import get_associated_token_address, transfer, TransferParams, approve, ApproveParams, create_associated_token_account

from core.solana_client import SolanaClient

RAYDIUM_API = "https://api.raydium.io/v2/main"  # Updated API endpoint
RAYDIUM_PROGRAM_ID = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")  # Raydium Liquidity Pool Program ID
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")  # SPL Token Program ID
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")  # SPL Associated Token Program ID

# List of reliable public RPC endpoints
RPC_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com"  # Use only the main Solana endpoint
]

def async_retry(retries: int = 5, delay: float = 1.0):
    """
    Retry decorator with exponential backoff and jitter for async functions.
    Handles rate limits and other transient errors with increased delays.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_msg = str(e)
                    
                    # Check if it's a rate limit error
                    is_rate_limit = (
                        isinstance(e, httpx.HTTPStatusError) and 
                        getattr(e.response, 'status_code', None) == 429
                    ) or "429 Too Many Requests" in error_msg or "rate limit" in error_msg.lower()
                    
                    if attempt < retries - 1:
                        # Exponential backoff with jitter
                        wait_time = delay * (4 ** attempt)  # Increased exponential factor
                        if is_rate_limit:
                            # Add much more backoff for rate limits
                            wait_time *= 4
                            print(f"Rate limit hit. Waiting longer...")
                        
                        # Add jitter (up to 50% of wait time)
                        jitter = random.uniform(0, wait_time * 0.5)
                        wait_time += jitter
                        
                        print(f"Attempt {attempt + 1} failed: {error_msg}")
                        print(f"Retrying in {wait_time:.1f}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"All {retries} attempts failed.")
                        if is_rate_limit:
                            print("Failed due to rate limits. Consider using a different RPC endpoint or reducing request frequency.")
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
    token_account = get_associated_token_address(wallet.pubkey(), token_mint)
    try:
        # First check if account exists
        account_info = await client.get_account_info(token_account)
        
        if account_info.value:
            print(f"Found existing token account: {token_account}")
            return token_account
            
        print(f"Creating token account for mint {token_mint}")
        
        # Get recent blockhash
        recent_blockhash = await client.get_latest_blockhash()
        
        # Create ATA instruction
        ix = create_associated_token_account(
            payer=wallet.pubkey(),
            owner=wallet.pubkey(),
            mint=token_mint
        )
        
        # Create and sign transaction
        message = Message.new_with_blockhash(
            [ix],
            wallet.pubkey(),
            recent_blockhash.value.blockhash
        )
        
        tx = VersionedTransaction(
            message=message,
            keypairs=[wallet]
        )
        
        try:
            # Send with no confirmation first
            result = await client.send_transaction(
                bytes(tx),
                opts=TxOpts(skip_confirmation=True)
            )
            print(f"Token account creation transaction sent: {result.value}")
            
            # Wait a moment before checking
            await asyncio.sleep(1)
            
            # Check if account was created
            verify_account = await client.get_account_info(token_account)
            if verify_account.value:
                print(f"Verified token account creation: {token_account}")
                return token_account
                
            # If not created, try to confirm transaction
            try:
                await client.confirm_transaction(
                    result.value,
                    commitment=Commitment("confirmed")
                )
                print(f"Token account creation confirmed: {token_account}")
            except Exception as confirm_error:
                print(f"Warning: Could not confirm transaction: {confirm_error}")
                # Check one more time if account exists despite confirmation error
                final_check = await client.get_account_info(token_account)
                if not final_check.value:
                    raise confirm_error
                
        except Exception as tx_error:
            print(f"Transaction error: {tx_error}")
            # Final verification in case transaction succeeded but we got rate limited
            final_verify = await client.get_account_info(token_account)
            if not final_verify.value:
                raise tx_error
            
    except Exception as e:
        print(f"Error checking/creating token account: {e}")
        raise
        
    return token_account

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
        
        print(f"Checking wrapped SOL account: {wsol_account}")
        
        # Convert SOL amount to lamports
        amount_lamports = int(amount_sol * 1_000_000_000)
        
        # Check if account exists and get its balance
        account_info = await client.get_account_info(wsol_account)
        current_wrapped_balance = 0
        
        if account_info.value:
            print("Found existing wrapped SOL account")
            current_wrapped_balance = await get_token_balance(client, wsol_account)
            print(f"Current wrapped SOL balance: {current_wrapped_balance / 1_000_000_000:.9f} SOL")
            
            # If we already have enough wrapped SOL, return early
            if current_wrapped_balance >= amount_lamports:
                print(f"Already have sufficient wrapped SOL, skipping wrap")
                return wsol_account
                
            # Calculate how much more SOL we need to wrap
            amount_lamports = amount_lamports - current_wrapped_balance
            print(f"Need to wrap additional {amount_lamports / 1_000_000_000:.9f} SOL")
        
        print(f"Wrapping {amount_lamports / 1_000_000_000:.9f} SOL...")
        
        # Get recent blockhash
        recent_blockhash = await client.get_latest_blockhash()
        
        # Create instructions array
        instructions = []
        
        # Add rent exempt amount for token account (about 0.00204928 SOL)
        rent_exempt_amount = 2039280
        total_lamports = amount_lamports + (0 if account_info.value else rent_exempt_amount)
        
        # Check if we have enough SOL
        balance_resp = await client.get_balance(wallet.pubkey())
        sol_balance = balance_resp.value
        print(f"Current SOL balance: {sol_balance/1e9:.9f} SOL")
        print(f"Required SOL: {total_lamports/1e9:.9f} SOL")
        
        if sol_balance < total_lamports:
            raise ValueError(f"Insufficient SOL balance. Have {sol_balance/1e9:.9f} SOL, need {total_lamports/1e9:.9f} SOL (including rent)")
        
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
                lamports=total_lamports
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
            opts=TxOpts(skip_preflight=True)  # Skip preflight for better error handling
        )
        print(f"Transaction sent: {result.value}")
        
        # Wait for confirmation
        print("Confirming transaction...")
        await client.confirm_transaction(
            result.value,
            commitment=Commitment("confirmed")
        )
        print(f"SOL wrapped successfully")
        
        # Verify the balance
        final_balance = await get_token_balance(client, wsol_account)
        print(f"Final wrapped SOL balance: {final_balance / 1_000_000_000:.9f} SOL")
        
        return wsol_account
        
    except Exception as e:
        print(f"Error wrapping SOL: {e}")
        raise

@async_retry(retries=10, delay=2.0)  # Increased retries and initial delay for swaps
async def swap_tokens(
    client: AsyncClient,
    wallet: Keypair,
    pool_id: str,
    input_token: str,  # 'base' or 'quote'
    amount_in: float,
    min_amount_out: float = None
) -> float:
    """
    Swap tokens using Raydium swap pool with improved error handling
    """
    try:
        print(f"\nInitiating swap of {amount_in} {input_token} tokens...")
        
        # Get pool info with retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(f"{RAYDIUM_API}/pairs", timeout=30)
                response.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise ValueError(f"Failed to fetch pool info after {max_retries} attempts: {e}")
                await asyncio.sleep(2 ** attempt)
                
        pools = response.json()
        pool_info = None
        for pool in pools:
            if pool.get('ammId') == pool_id:
                pool_info = pool
                break
                
        if not pool_info:
            raise ValueError(f"Pool {pool_id} not found")
            
        # Extract pool data
        token_mint_base = Pubkey.from_string(pool_info['baseMint'])
        token_mint_quote = Pubkey.from_string(pool_info['quoteMint'])
        market_id = Pubkey.from_string(pool_info['market'])
        amm_id = Pubkey.from_string(pool_id)
        
        # Get token decimals
        decimals_base = await get_token_decimals(client, token_mint_base)
        decimals_quote = await get_token_decimals(client, token_mint_quote)
        
        # Determine input/output token details
        if input_token == 'base':
            amount_in_lamports = int(amount_in * (10 ** decimals_base))
            input_mint = token_mint_base
            output_mint = token_mint_quote
            input_decimals = decimals_base
            output_decimals = decimals_quote
        else:
            amount_in_lamports = int(amount_in * (10 ** decimals_quote))
            input_mint = token_mint_quote
            output_mint = token_mint_base
            input_decimals = decimals_quote
            output_decimals = decimals_base
        
        # Get or create user token accounts
        if input_token == 'base':
            input_token_account = await wrap_sol(client, wallet, amount_in)
        else:
            input_token_account = await get_or_create_token_account(client, wallet, input_mint)
            
        output_token_account = await get_or_create_token_account(client, wallet, output_mint)
        
        # Check input token balance
        input_balance = await get_token_balance(client, input_token_account)
        if input_balance < amount_in_lamports:
            raise ValueError(f"Insufficient {input_token} token balance. Have {input_balance / (10 ** input_decimals)}, need {amount_in}")
        
        # Calculate minimum output amount if not provided (1% slippage)
        if min_amount_out is None:
            price = float(pool_info['price'])
            if input_token == 'base':
                expected_out = amount_in * price
            else:
                expected_out = amount_in / price
            min_amount_out = expected_out * 0.99  # 1% slippage tolerance
            print(f"Calculated minimum output amount: {min_amount_out}")
        
        min_out_lamports = int(min_amount_out * (10 ** output_decimals))
        
        # Get AMM accounts
        amm_authority = amm_id  # For simplicity, using AMM ID as authority
        base_vault = get_associated_token_address(amm_authority, token_mint_base)
        quote_vault = get_associated_token_address(amm_authority, token_mint_quote)
        
        # Get market accounts
        market_info = await client.get_account_info(market_id)
        if not market_info.value:
            raise ValueError(f"Market {market_id} not found")
            
        # Get recent blockhash with retry
        for _ in range(3):
            try:
                recent_blockhash = await client.get_latest_blockhash()
                break
            except Exception as e:
                print(f"Error getting blockhash: {e}")
                await asyncio.sleep(2)
        else:
            raise ValueError("Failed to get recent blockhash after 3 attempts")
        
        # Create compute budget instruction to increase compute units
        compute_ix = Instruction(
            program_id=COMPUTE_BUDGET_PROGRAM_ID,
            accounts=[],
            data=bytes([0, *int(400_000).to_bytes(4, 'little'), 0, *int(1_000_000).to_bytes(8, 'little')])  # Set compute unit limit and price
        )
        
        # Create swap instruction
        swap_ix = Instruction(
            program_id=RAYDIUM_PROGRAM_ID,
            accounts=[
                AccountMeta(pubkey=amm_id, is_signer=False, is_writable=True),  # amm
                AccountMeta(pubkey=amm_authority, is_signer=False, is_writable=False),  # authority
                AccountMeta(pubkey=input_token_account, is_signer=False, is_writable=True),  # user source
                AccountMeta(pubkey=output_token_account, is_signer=False, is_writable=True),  # user destination
                AccountMeta(pubkey=base_vault, is_signer=False, is_writable=True),  # pool source
                AccountMeta(pubkey=quote_vault, is_signer=False, is_writable=True),  # pool destination
                AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),  # token program
                AccountMeta(pubkey=market_id, is_signer=False, is_writable=True),  # serum market
                AccountMeta(pubkey=wallet.pubkey(), is_signer=True, is_writable=False),  # user owner
            ],
            data=bytes([
                1,  # Swap instruction
                *amount_in_lamports.to_bytes(8, 'little'),  # Amount in
                *min_out_lamports.to_bytes(8, 'little'),  # Minimum amount out
            ])
        )
        
        # Create versioned message
        message = MessageV0.try_compile(
            payer=wallet.pubkey(),
            instructions=[compute_ix, swap_ix],
            recent_blockhash=recent_blockhash.value.blockhash,
            address_lookup_table_accounts=[]
        )
        
        # Create and sign transaction
        transaction = VersionedTransaction(message, [wallet])
        
        # Send transaction with retry
        print("Sending swap transaction...")
        for attempt in range(3):
            try:
                result = await client.send_transaction(
                    transaction,
                    opts=TxOpts(
                        skip_preflight=True,
                        preflight_commitment=Commitment("confirmed"),
                        max_retries=5
                    )
                )
                print(f"Swap transaction sent: {result.value}")
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"Error sending transaction (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2 ** attempt)
        
        # Wait for confirmation with increased timeout and better error handling
        print("Confirming swap transaction...")
        confirmation_attempts = 0
        max_confirmation_attempts = 5
        
        while confirmation_attempts < max_confirmation_attempts:
            try:
                await client.confirm_transaction(
                    result.value,
                    commitment=Commitment("confirmed")
                )
                break
            except Exception as e:
                confirmation_attempts += 1
                if confirmation_attempts >= max_confirmation_attempts:
                    print(f"Failed to confirm transaction after {max_confirmation_attempts} attempts")
                    raise
                print(f"Confirmation attempt {confirmation_attempts} failed: {e}")
                await asyncio.sleep(2 ** confirmation_attempts)
        
        # Wait a moment for balances to update
        await asyncio.sleep(5)
        
        # Get final output balance with retry
        for attempt in range(3):
            try:
                output_balance_after = await get_token_balance(client, output_token_account)
                amount_out = output_balance_after / (10 ** output_decimals)
                print(f"Swap successful! Received {amount_out} tokens")
                return amount_out
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"Error getting final balance (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2)
        
    except Exception as e:
        print(f"Error during swap: {str(e)}")
        raise

async def add_liquidity(client: AsyncClient, wallet: Keypair, pool_id: str, amount_base: float, amount_quote: float):
    """
    Adds liquidity to a Raydium pool.
    :param client: Solana AsyncClient
    :param wallet: Keypair of the wallet providing liquidity
    :param pool_id: ID of the Raydium liquidity pool
    :param amount_base: Amount of base token to deposit
    :param amount_quote: Amount of quote token to deposit
    """
    try:
        # Step 1: Get Pool Info
        print("Fetching pool info...")
        response = requests.get(f"{RAYDIUM_API}/pairs")
        if response.status_code != 200:
            print(f"API Response: {response.text}")
            raise ValueError(f"Failed to fetch pool info: {response.status_code}")
            
        pools = response.json()
        pool_info = None
        for pool in pools:
            if pool.get('ammId') == pool_id:
                pool_info = pool
                break
                
        if not pool_info:
            raise ValueError(f"Pool {pool_id} not found in Raydium pools list")
            
        print(f"Pool info: {json.dumps(pool_info, indent=2)}")
        
        # Extract pool data
        token_mint_base = Pubkey.from_string(pool_info['baseMint'])
        token_mint_quote = Pubkey.from_string(pool_info['quoteMint'])
        
        # Get token decimals from Solana network
        print("Fetching token decimals...")
        decimals_base = await get_token_decimals(client, token_mint_base)
        decimals_quote = await get_token_decimals(client, token_mint_quote)
        
        print(f"Base token decimals: {decimals_base}")
        print(f"Quote token decimals: {decimals_quote}")
        
        # Step 2: Get Pool Keys
        print("Fetching pool keys...")
        # Get AMM account info to extract authority
        amm_info = await client.get_account_info(Pubkey.from_string(pool_id))
        if not amm_info.value:
            raise ValueError(f"AMM account {pool_id} not found")
            
        # Get AMM data
        amm_data = amm_info.value.data
        print(f"AMM data length: {len(amm_data)} bytes")
        
        # For now, use a simpler approach with the pool ID as authority
        pool_authority = Pubkey.from_string(pool_id)
        
        # Get vault addresses from market
        market_id = Pubkey.from_string(pool_info['market'])
        base_vault = get_associated_token_address(pool_authority, token_mint_base)
        quote_vault = get_associated_token_address(pool_authority, token_mint_quote)
        lp_mint = Pubkey.from_string(pool_info['lpMint'])
        
        print(f"Base token: {token_mint_base}")
        print(f"Quote token: {token_mint_quote}")
        print(f"LP token: {lp_mint}")
        print(f"Pool authority: {pool_authority}")
        print(f"Base vault: {base_vault}")
        print(f"Quote vault: {quote_vault}")
        
        # Step 3: Get or Create User Token Accounts
        print("Getting/Creating user token accounts...")
        # For base token (SOL), we need to wrap it first
        base_token_account = await wrap_sol(client, wallet, amount_base)
        quote_token_account = await get_or_create_token_account(client, wallet, token_mint_quote)
        lp_token_account = await get_or_create_token_account(client, wallet, lp_mint)
        
        print(f"Base token account: {base_token_account}")
        print(f"Quote token account: {quote_token_account}")
        print(f"LP token account: {lp_token_account}")
        
        # Step 4: Check Wallet Balances and Swap if needed
        print("Checking token balances...")
        base_balance = await get_token_balance(client, base_token_account)
        quote_balance = await get_token_balance(client, quote_token_account)
        
        base_amount_lamports = int(amount_base * (10 ** decimals_base))
        quote_amount_lamports = int(amount_quote * (10 ** decimals_quote))
        
        print(f"Base balance: {base_balance / (10 ** decimals_base)} SOL")
        print(f"Quote balance: {quote_balance / (10 ** decimals_quote)} USDC")
        print(f"Required base: {amount_base} SOL")
        print(f"Required quote: {amount_quote} USDC")
        
        # Check if we need to swap for quote tokens
        if quote_balance < quote_amount_lamports:
            print(f"Insufficient quote token balance. Attempting to swap SOL for {amount_quote} USDC...")
            
            # Calculate required SOL amount based on current pool price (add 1% for slippage and fees)
            price = float(pool_info['price'])
            sol_needed = (amount_quote / price) * 1.01
            
            # Check if we have enough SOL to swap
            balance_resp = await client.get_balance(wallet.pubkey())
            available_sol = balance_resp.value / 1_000_000_000
            
            if available_sol < sol_needed:
                raise ValueError(f"Insufficient SOL to swap. Need {sol_needed} SOL but only have {available_sol} SOL")
                
            # Perform the swap
            await swap_tokens(
                client=client,
                wallet=wallet,
                pool_id=pool_id,
                input_token='base',
                amount_in=sol_needed,
                min_amount_out=amount_quote
            )
            
            # Verify quote balance after swap
            quote_balance = await get_token_balance(client, quote_token_account)
            if quote_balance < quote_amount_lamports:
                raise ValueError(f"Failed to acquire enough quote tokens after swap. Have {quote_balance / (10 ** decimals_quote)}, need {amount_quote}")
        
        # Verify final balances
        base_balance = await get_token_balance(client, base_token_account)
        quote_balance = await get_token_balance(client, quote_token_account)
        
        if base_balance < base_amount_lamports:
            raise ValueError(f"Insufficient base token balance. Have {base_balance / (10 ** decimals_base)}, need {amount_base}")
        
        if quote_balance < quote_amount_lamports:
            raise ValueError(f"Insufficient quote token balance. Have {quote_balance / (10 ** decimals_quote)}, need {amount_quote}")
        
        # Step 5: Create Transaction
        print("Creating transaction...")
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
        result = await client.send_transaction(
            transaction,
            opts=TxOpts(skip_preflight=True)  # Skip preflight for better error handling
        )
        print(f"Transaction sent: {result.value}")
        
        # Wait for confirmation
        print("Confirming transaction...")
        await client.confirm_transaction(
            result.value,
            commitment=Commitment("confirmed")
        )
        print("Liquidity added successfully.")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        if isinstance(e, requests.exceptions.RequestException):
            print(f"API Response: {e.response.text if hasattr(e, 'response') else 'No response'}")
        raise

async def get_best_endpoint():
    """Get the Solana mainnet endpoint"""
    return RPC_ENDPOINTS[0]  # Simply return the main endpoint

async def test_add_liquidity():
    """
    Test function to demonstrate adding liquidity to a Raydium pool
    """
    async_client = None
    try:
        # Initialize Solana client
        solana = SolanaClient()
        
        # Get best RPC endpoint
        print("Finding best RPC endpoint...")
        endpoint = await get_best_endpoint()
        print(f"Using endpoint: {endpoint}")
        
        # Create async client with increased timeout
        async_client = AsyncClient(endpoint, timeout=60)
        
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
        balance_resp = await async_client.get_balance(wallet.pubkey())
        sol_balance = balance_resp.value / 1_000_000_000  # Convert lamports to SOL
        print(f"SOL Balance: {sol_balance:.9f} SOL")
        
        min_sol_balance = 0.01
        if sol_balance < min_sol_balance:
            raise ValueError(f"Insufficient SOL balance. Please fund your wallet with at least {min_sol_balance} SOL for transaction fees.")
        
        # Example pool and amounts (using real mainnet pool)
        pool_id = "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"  # SOL-USDC pool
        amount_base = 0.01   # 0.01 SOL
        amount_quote = 1.0   # 1 USDC
        
        print(f"Testing add_liquidity with:")
        print(f"Wallet: {wallet.pubkey()}")
        print(f"Pool ID: {pool_id}")
        print(f"Base Amount: {amount_base}")
        print(f"Quote Amount: {amount_quote}")
        
        # Add liquidity
        await add_liquidity(
            client=async_client,
            wallet=wallet,
            pool_id=pool_id,
            amount_base=amount_base,
            amount_quote=amount_quote
        )
        
        # Check final SOL balance
        final_balance_resp = await async_client.get_balance(wallet.pubkey())
        sol_balance_after = final_balance_resp.value / 1_000_000_000  # Convert lamports to SOL
        print(f"Final SOL Balance: {sol_balance_after:.9f} SOL")
        print(f"SOL spent on fees: {sol_balance - sol_balance_after:.9f} SOL")
        
    except Exception as e:
        print(f"Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        if async_client:
            try:
                await async_client.close()
            except Exception as e:
                print(f"Warning: Error closing client: {e}")

if __name__ == "__main__":
    print("Starting Raydium add liquidity test on mainnet...")
    asyncio.run(test_add_liquidity())

