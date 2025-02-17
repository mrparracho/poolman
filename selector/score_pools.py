import numpy as np
import pandas as pd
import requests
import logging
import json
import time
import os
from datetime import datetime
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def ensure_data_directories():
    """Create necessary data directories if they don't exist."""
    os.makedirs('data/raydium', exist_ok=True)
    os.makedirs('data/birdeye', exist_ok=True)
    os.makedirs('data/results', exist_ok=True)

def get_timestamp_str():
    """Get current timestamp string for filenames."""
    return datetime.now().strftime('%Y%m%d_%H')

def save_json_data(data, directory: str, filename: str):
    """Save JSON data to file with consistent formatting."""
    filepath = os.path.join('data', directory, filename)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4, sort_keys=True)
    logger.info(f"Saved data to {filepath}")

def fetch_raydium_pools():
    """
    Fetch liquidity pool data from Raydium API.
    Returns pools sorted by 24h volume, filtered by minimum thresholds.
    
    :return: DataFrame containing pool data including TVL and volume.
    """
    logger.info("Fetching Raydium pools data")
    url = "https://api.raydium.io/v2/main/pairs"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        logger.debug(f"Received {len(data)} pools from Raydium API")
        
        # Save raw API response
        timestamp = get_timestamp_str()
        save_json_data(data, 'raydium', f'raw_pools_{timestamp}.json')
        
        # Convert to DataFrame for easier manipulation
        pools_df = pd.DataFrame([{
            'pool_id': pool.get('ammId', ''),
            'symbol': pool.get('name', ''),
            'tvl': float(pool.get('liquidity', 0)),
            'volume_24h': float(pool.get('volume24h', 0)),
            'apr': float(pool.get('apr24h', 0))
        } for pool in data])
        
        # Apply minimum thresholds
        min_volume = 10_000_000  # $10M minimum volume
        min_tvl = 500_000      # $500k minimum TVL
        
        filtered_pools = pools_df[
            (pools_df['volume_24h'] >= min_volume) & 
            (pools_df['tvl'] >= min_tvl)
        ]
        
        # Sort by volume
        sorted_pools = filtered_pools.sort_values('volume_24h', ascending=False)
        
        # Save sorted pools
        save_json_data(
            sorted_pools.to_dict(orient='records'),
            'raydium',
            f'sorted_pools_{timestamp}.json'
        )
        
        # Add liquidity efficiency metric
        sorted_pools['liquidity_efficiency'] = sorted_pools['volume_24h'] / sorted_pools['tvl']
        
        logger.info(f"Successfully processed {len(sorted_pools)} valid Raydium pools with Volume > ${min_volume:,} and TVL > ${min_tvl:,}")
        logger.info(f"Top pool by volume: {sorted_pools.iloc[0]['symbol']} - Volume: ${sorted_pools.iloc[0]['volume_24h']:,.2f}")
        
        return sorted_pools
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch Raydium pools: {str(e)}")
        raise

def get_birdeye_filename(pool_id: str, start_time: int, end_time: int) -> str:
    """Generate consistent filename for Birdeye data."""
    start_date = datetime.fromtimestamp(start_time).strftime('%Y%m%d_%H')
    end_date = datetime.fromtimestamp(end_time).strftime('%Y%m%d_%H')
    return f"historical_{pool_id}_{start_date}_{end_date}.json"

def load_cached_birdeye_data(pool_id: str, start_time: int, end_time: int) -> pd.DataFrame:
    """
    Try to load cached Birdeye data from file.
    Returns None if file doesn't exist or is outdated.
    """
    filename = get_birdeye_filename(pool_id, start_time, end_time)
    filepath = os.path.join('data', 'birdeye', filename)
    
    if not os.path.exists(filepath):
        return None
        
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        if not data.get('data'):
            return None
            
        df = pd.DataFrame(data['data'])
        
        # Validate data
        required_columns = ['unixTime', 'value']
        if not all(col in df.columns for col in required_columns):
            return None
            
        # Process the data
        df['timestamp'] = pd.to_datetime(df['unixTime'], unit='s')
        df['value'] = df['value'].astype(float)
        df = df.sort_values('timestamp')
        df = df.drop_duplicates(subset=['timestamp'])
        df = df.dropna(subset=['value'])
        
        # Verify data freshness and completeness
        if len(df) < 24:
            return None
            
        logger.info(f"Using cached data from {filepath}")
        return df
        
    except Exception as e:
        logger.warning(f"Failed to load cached data: {str(e)}")
        return None

def fetch_birdeye_data(pool_id: str) -> pd.DataFrame:
    """
    Fetch historical price data from Birdeye API for a given pool.
    Returns data for the last 14 days in 15-minute intervals.
    Checks for cached data first to reduce API calls.
    
    :param pool_id: The pool ID to fetch data for
    :return: DataFrame with historical price data
    """
    logger.info(f"Fetching Birdeye data for pool {pool_id}")
    
    # Calculate time windows
    current_time = int(time.time())
    seven_days_ago = current_time - 7 * 24 * 60 * 60  
    fourteen_days_ago = current_time - 14 * 24 * 60 * 60
    
    # Try to load cached data first
    cached_data = load_cached_birdeye_data(pool_id, fourteen_days_ago, current_time)
    if cached_data is not None:
        return cached_data
    
    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        raise ValueError("BIRDEYE_API_KEY environment variable is not set")
        
    headers = {
        "accept": "application/json",
        "x-chain": "solana",
        "X-API-KEY": api_key
    }
    
    try:
        # First API call - 14 days to 7 days ago
        url1 = f"https://public-api.birdeye.so/defi/history_price?address={pool_id}&address_type=pair&type=15m&time_from={fourteen_days_ago}&time_to={seven_days_ago}"
        response1 = requests.get(url1, headers=headers)
        response1.raise_for_status()
        data1 = response1.json()
        
        time.sleep(1)  # Rate limiting
        
        # Second API call - 7 days ago to now
        url2 = f"https://public-api.birdeye.so/defi/history_price?address={pool_id}&address_type=pair&type=15m&time_from={seven_days_ago}&time_to={current_time}"
        response2 = requests.get(url2, headers=headers)
        response2.raise_for_status()
        data2 = response2.json()
        
        # Validate and merge the data
        if not data1.get('success') or not data2.get('success'):
            error_msg = data1.get('error') or data2.get('error') or "Unknown API error"
            raise ValueError(f"API error: {error_msg}")
            
        price_data1 = data1.get('data', {}).get('items', [])
        price_data2 = data2.get('data', {}).get('items', [])
        
        if not price_data1 and not price_data2:
            raise ValueError("No price data available")
            
        merged_data = price_data1 + price_data2
        
        # Save data with consistent naming
        filename = get_birdeye_filename(pool_id, fourteen_days_ago, current_time)
        save_json_data(
            {'data': merged_data},
            'birdeye',
            filename
        )
        
        # Convert to DataFrame
        df = pd.DataFrame(merged_data)
        
        # Ensure required columns exist
        required_columns = ['unixTime', 'value']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        # Process the data
        df['timestamp'] = pd.to_datetime(df['unixTime'], unit='s')
        df['value'] = df['value'].astype(float)
        df = df.sort_values('timestamp')
        
        # Remove duplicates and ensure data quality
        df = df.drop_duplicates(subset=['timestamp'])
        df = df.dropna(subset=['value'])
        
        if len(df) < 24:  # Require at least 24 data points
            raise ValueError(f"Insufficient data points: {len(df)} < 24")
        
        logger.info(f"Successfully fetched {len(df)} data points for {pool_id}")
        return df
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching Birdeye data: {str(e)}")
        raise
    except ValueError as e:
        logger.error(f"Data validation error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing Birdeye data: {str(e)}")
        raise

def get_top_pools(n_pairs: int = 10) -> pd.DataFrame:
    """
    Get top n pools from Raydium and fetch their historical data from Birdeye.
    Pools are ordered by 24h volume.
    
    :param n_pairs: Number of pairs to return
    :return: DataFrame with top pools and their historical data
    """
    logger.info(f"Getting top {n_pairs} pools by volume")
    
    # Get Raydium pools (already sorted by volume)
    raydium_pools = fetch_raydium_pools()
    
    # Take top n pairs and fetch their historical data
    top_pools = raydium_pools.head(n_pairs).copy()  # Create a copy to avoid SettingWithCopyWarning
    valid_pairs = []
    
    for _, pool in top_pools.iterrows():
        time.sleep(1)  # Rate limiting
        try:
            historical_data = fetch_birdeye_data(pool['pool_id'])
            pool_data = pool.to_dict()
            pool_data['historical_data'] = historical_data
            valid_pairs.append(pool_data)
            logger.info(f"Added historical data for {pool['symbol']}")
        except Exception as e:
            logger.warning(f"Failed to fetch historical data for {pool['symbol']}: {str(e)}")
            continue
    
    if not valid_pairs:
        raise ValueError("No valid pairs found with historical data")
    
    valid_pools_df = pd.DataFrame(valid_pairs)
    logger.info(f"Successfully found {len(valid_pools_df)} pairs with historical data")
    
    return valid_pools_df

class LiquidityPoolSelector:
    def __init__(self, historical_data: pd.DataFrame, raydium_data: pd.DataFrame, 
                 volume_weight=0.4, liquidity_weight=0.3, volatility_weight=0.3):
        """
        Initialize the Liquidity Pool Selector.
        
        :param historical_data: DataFrame containing historical price data from Birdeye
        :param raydium_data: DataFrame containing Raydium pool data
        :param volume_weight: Weight for the volume metric
        :param liquidity_weight: Weight for the liquidity efficiency metric
        :param volatility_weight: Weight for the volatility metric
        """
        self.historical_data = historical_data
        self.raydium_data = raydium_data
        self.volume_weight = volume_weight
        self.liquidity_weight = liquidity_weight
        self.volatility_weight = volatility_weight
        
        logger.debug("Initialized LiquidityPoolSelector with weights: "
                    f"volume={volume_weight}, liquidity={liquidity_weight}, "
                    f"volatility={volatility_weight}")
    
    def compute_liquidity_efficiency(self) -> float:
        """
        Compute liquidity efficiency as volume/TVL ratio.
        Higher ratio means more efficient use of liquidity.
        Normalized using a sigmoid function to handle extreme values better.
        """
        if self.raydium_data.empty:
            logger.warning("No Raydium data available for efficiency calculation")
            return 0.0
            
        volume = self.raydium_data['volume_24h'].iloc[0]
        tvl = self.raydium_data['tvl'].iloc[0]
        
        if tvl <= 0:
            logger.warning("Invalid TVL value for efficiency calculation")
            return 0.0
            
        efficiency = volume / tvl
        
        # Use sigmoid normalization for smoother scaling
        # Center around 1.0 (100% daily volume/TVL ratio)
        # Scale to ensure reasonable spread
        normalized_efficiency = 1 / (1 + np.exp(-2 * (efficiency - 1)))
        
        logger.debug(
            f"Liquidity efficiency: raw={efficiency:.4f}, "
            f"normalized={normalized_efficiency:.4f}"
        )
        return normalized_efficiency
    
    def compute_weighted_volume(self) -> float:
        """
        Compute weighted volume score using logarithmic scaling.
        Uses 24h volume from Raydium data.
        """
        if self.raydium_data.empty:
            logger.warning("No Raydium data available for volume calculation")
            return 0.0
            
        volume = self.raydium_data['volume_24h'].iloc[0]
        
        # Use logarithmic scaling for better handling of large volumes
        # Normalize against $10M baseline
        log_volume = np.log10(max(volume, 1))
        log_baseline = np.log10(10_000_000)  # $10M baseline
        
        # Normalize to [0,1] range
        normalized_volume = min(log_volume / log_baseline, 1.0)
        
        logger.debug(
            f"Volume score: raw=${volume:,.2f}, "
            f"normalized={normalized_volume:.4f}"
        )
        return normalized_volume
    
    def compute_volatility(self) -> float:
        """
        Compute price volatility using standard deviation of returns.
        Uses Birdeye historical data for more accurate volatility calculation.
        Applies sigmoid normalization for better scaling.
        """
        if len(self.historical_data) < 2:
            logger.warning("Insufficient data points to compute volatility")
            return 0.0
        
        prices = self.historical_data['value'].astype(float)
        log_returns = np.log(prices / prices.shift(1))
        
        # Compute annualized volatility (15-min data to annual)
        periods_per_year = 4 * 24 * 365  # 15-min periods in a year
        volatility = log_returns.std() * np.sqrt(periods_per_year)
        
        # Use sigmoid normalization centered around 100% annual volatility
        # This provides smoother scaling for both low and high volatility
        normalized_volatility = 1 / (1 + np.exp(-3 * (volatility - 1)))
        
        logger.debug(
            f"Volatility: annual={volatility*100:.1f}%, "
            f"normalized={normalized_volatility:.4f}"
        )
        return normalized_volatility
    
    def compute_pool_score(self) -> float:
        """
        Compute the final pool score using a weighted formula of volume, liquidity efficiency,
        and volatility, normalized between 0 and 100.
        """
        logger.debug("Computing pool score")
        
        # Get base metrics
        volume_score = self.compute_weighted_volume()
        liquidity_score = self.compute_liquidity_efficiency()
        volatility_score = self.compute_volatility()
        
        # Add APR bonus if available
        apr_bonus = 0
        if not self.raydium_data.empty:
            apr = self.raydium_data['apr'].iloc[0]
            # Use sigmoid for APR bonus too
            apr_bonus = 0.1 * (1 / (1 + np.exp(-0.1 * (apr - 50))))  # Center around 50% APR
        
        # Calculate raw score with volatility
        raw_score = (self.volume_weight * volume_score) + \
                   (self.liquidity_weight * liquidity_score) + \
                   (self.volatility_weight * volatility_score) + \
                   apr_bonus
        
        # Convert to percentage (0-100)
        final_score = raw_score * 100
        
        logger.info(
            f"Pool score: {final_score:.2f} "
            f"(Volume: {volume_score:.2f}, "
            f"Efficiency: {liquidity_score:.2f}, "
            f"Volatility: {volatility_score:.2f}, "
            f"APR Bonus: {apr_bonus:.2f})"
        )
        return final_score

def compute_pool_scores(pairs_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute final pool scores using both Raydium and Birdeye historical data.
    
    :param pairs_df: DataFrame with valid pairs from get_top_pools
    :return: DataFrame with computed scores
    """
    logger.info(f"Computing pool scores for {len(pairs_df)} pairs")
    results = []
    
    for _, pair in pairs_df.iterrows():
        try:
            logger.debug(f"Processing pair: {pair['symbol']}")
            
            # Create selector with both Raydium and historical data
            selector = LiquidityPoolSelector(
                historical_data=pair['historical_data'],
                raydium_data=pd.DataFrame([{
                    'tvl': pair['tvl'],
                    'volume_24h': pair['volume_24h'],
                    'apr': pair['apr']
                }])
            )
            
            # Compute all metrics
            volatility = selector.compute_volatility()
            volume_weighted = selector.compute_weighted_volume()
            liquidity_efficiency = selector.compute_liquidity_efficiency()
            score = selector.compute_pool_score()
            
            results.append({
                'symbol': pair['symbol'],
                'pool_id': pair['pool_id'],
                'pool_score': score,
                'volatility': volatility,
                'volume_weighted': volume_weighted,
                'liquidity_efficiency': liquidity_efficiency,
                'tvl': pair['tvl'],
                'volume_24h': pair['volume_24h'],
                'apr': pair['apr']
            })
            
            logger.info(
                f"Scored {pair['symbol']}: "
                f"Score={score:.2f}, "
                f"Vol={volatility:.4f}, "
                f"Eff={liquidity_efficiency:.4f}"
            )
            
        except Exception as e:
            logger.error(f"Error processing {pair['symbol']}: {str(e)}")
            continue
    
    if not results:
        raise ValueError("Failed to compute scores for any pools")
    
    # Sort by final pool score
    scored_pools = pd.DataFrame(results).sort_values('pool_score', ascending=False)
    
    # Save results with timestamp
    timestamp = get_timestamp_str()
    save_json_data(
        scored_pools.to_dict(orient='records'),
        'results',
        f'scored_pools_{timestamp}.json'
    )
    
    return scored_pools

if __name__ == "__main__":
    try:
        # Ensure data directories exist
        ensure_data_directories()
        
        # Get top pools and compute scores
        top_pools = get_top_pools(10)
        final_scores = compute_pool_scores(top_pools)
        
        # Print summary
        print("\nTop Pools Summary:")
        print("=================")
        for _, pool in final_scores.iterrows():
            print(f"\nPool: {pool['symbol']}")
            print(f"Score: {pool['pool_score']:.2f}")
            print(f"Volatility: {pool['volatility']:.4f}")
            print(f"Volume (24h): ${pool['volume_24h']:,.2f}")
            print(f"TVL: ${pool['tvl']:,.2f}")
            print(f"APR: {pool['apr']:.2f}%")
            print(f"Liquidity Efficiency: {pool['liquidity_efficiency']:.4f}")
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        raise
