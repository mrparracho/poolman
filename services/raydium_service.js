const { Connection, Keypair, PublicKey, Transaction, clusterApiUrl } = require('@solana/web3.js');
const { 
  Liquidity,
  Token,
  TokenAmount,
  Percent,
  LIQUIDITY_STATE_LAYOUT_V4,
  jsonInfo2PoolKeys,
  Currency,
  CurrencyAmount,
  Price
} = require('@raydium-io/raydium-sdk');

class RaydiumService {
  constructor() {
    this.connection = new Connection(clusterApiUrl('mainnet-beta'), 'confirmed');
  }

  async addLiquidity(params) {
    try {
      // Create wallet from private key
      const wallet = Keypair.fromSecretKey(
        Buffer.from(params.walletPrivateKey, 'hex')
      );

      // Get pool info
      const poolInfo = await this.getPoolInfo(params.poolId);
      const poolKeys = jsonInfo2PoolKeys(poolInfo);
      
      // Get token info and decimals
      const tokenA = new Token(poolKeys.baseMint, poolInfo.baseDecimals);
      const tokenB = new Token(poolKeys.quoteMint, poolInfo.quoteDecimals);

      // Create token amounts
      const amountA = new TokenAmount(
        tokenA,
        params.amountA * (10 ** poolInfo.baseDecimals)
      );
      
      const amountB = new TokenAmount(
        tokenB,
        params.amountB * (10 ** poolInfo.quoteDecimals)
      );

      // Create slippage tolerance
      const slippage = new Percent(
        params.slippageTolerance,
        100
      );

      // Create liquidity instruction
      const userKeys = {
        owner: wallet.publicKey,
        baseToken: await this.findAssociatedTokenAccount(wallet.publicKey, poolKeys.baseMint),
        quoteToken: await this.findAssociatedTokenAccount(wallet.publicKey, poolKeys.quoteMint),
        lpToken: await this.findAssociatedTokenAccount(wallet.publicKey, poolKeys.lpMint)
      };

      const addLiquidityParams = {
        poolKeys,
        userKeys,
        amountInA: amountA,
        amountInB: amountB,
        fixedSide: 'base'
      };

      const instruction = await Liquidity.makeAddLiquidityInstruction(addLiquidityParams);

      // Create transaction
      const transaction = new Transaction();
      transaction.add(instruction);

      // Sign and send transaction
      const signature = await this.connection.sendTransaction(
        transaction,
        [wallet],
        { skipPreflight: false }
      );

      // Wait for confirmation
      const confirmation = await this.connection.confirmTransaction(signature);
      
      if (confirmation.value.err) {
        throw new Error(`Transaction failed: ${confirmation.value.err}`);
      }

      return {
        success: true,
        signature
      };

    } catch (error) {
      console.error('Error adding liquidity:', error.message);
      return {
        success: false,
        error: error.message || 'Unknown error occurred'
      };
    }
  }

  async getPoolInfo(poolId) {
    // Get pool account info
    const poolInfo = await this.connection.getAccountInfo(
      new PublicKey(poolId)
    );

    if (!poolInfo) {
      throw new Error(`Pool ${poolId} not found`);
    }

    // Parse pool state
    const state = LIQUIDITY_STATE_LAYOUT_V4.decode(poolInfo.data);

    return {
      id: poolId,
      baseMint: state.baseMint.toString(),
      quoteMint: state.quoteMint.toString(),
      lpMint: state.lpMint.toString(),
      baseVault: state.baseVault.toString(),
      quoteVault: state.quoteVault.toString(),
      baseDecimals: state.baseDecimal.toNumber(),
      quoteDecimals: state.quoteDecimal.toNumber(),
      lpDecimals: state.lpDecimal.toNumber(),
      version: 4,
      programId: state.owner.toString(),
      authority: state.owner.toString(),
      openOrders: state.openOrders.toString(),
      targetOrders: state.targetOrders.toString(),
      withdrawQueue: state.withdrawQueue.toString(),
      lpVault: state.lpVault.toString(),
      marketId: state.marketId.toString(),
      marketProgramId: state.marketProgramId.toString(),
      marketAuthority: state.marketAuthority.toString(),
      marketBaseVault: state.marketBaseVault.toString(),
      marketQuoteVault: state.marketQuoteVault.toString(),
      marketVersion: 3
    };
  }

  async findAssociatedTokenAccount(owner, mint) {
    const [address] = await PublicKey.findProgramAddress(
      [
        owner.toBuffer(),
        new PublicKey('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA').toBuffer(),
        mint.toBuffer()
      ],
      new PublicKey('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL')
    );
    return address;
  }
}

module.exports = RaydiumService; 