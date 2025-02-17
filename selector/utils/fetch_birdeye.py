import requests
import time
import json
import os

pool_id = "8sn9549p3zn6xpqrqpapn57xzkch6sjxlwuejcg2w4ji"

# Calculate time windows
current_time = int(time.time())
seven_days_ago = current_time - 7 * 24 * 60 * 60  
fourteen_days_ago = current_time - 14 * 24 * 60 * 60

headers = {
    "accept": "application/json", 
    "x-chain": "solana",
    "X-API-KEY": os.getenv("BIRDEYE_API_KEY")
}

# First API call - 14 days to 7 days ago
url1 = f"https://public-api.birdeye.so/defi/history_price?address={pool_id}&address_type=pair&type=15m&time_from={fourteen_days_ago}&time_to={seven_days_ago}"
response1 = requests.get(url1, headers=headers)
data1 = response1.json()
print(data1)

time.sleep(1)
# Second API call - 7 days ago to now
url2 = f"https://public-api.birdeye.so/defi/history_price?address={pool_id}&address_type=pair&type=15m&time_from={seven_days_ago}&time_to={current_time}"
response2 = requests.get(url2, headers=headers)
data2 = response2.json()
print(data2)
# Merge the data
if 'data' in data1 and 'data' in data2:
    merged_data = {
        'data': data1['data']['items'] + data2['data']['items']
    }
    print(json.dumps(merged_data))
else:
    print("Error: Invalid response format")