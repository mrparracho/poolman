import requests

def fetch_raydium_pool_data(pool_id):
    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pool_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        if "pairs" in data and data["pairs"]:
            pool_data = data["pairs"][0]  # Assuming the first entry is the correct one
            return pool_data
        else:
            print("No data found for the given pool ID.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

if __name__ == "__main__":
    
    pool_data = fetch_raydium_pool_data("8sn9549p3zn6xpqrqpapn57xzkch6sjxlwuejcg2w4ji")
    
    if pool_data:
        print("Fetched Pool Data:")
        print(pool_data)
