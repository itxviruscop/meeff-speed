import asyncio
import aiohttp
import logging
from db import get_current_account

# All available country ISO codes
countries = [
    "AF", "AL", "DZ", "AD", "AO", "AG", "AR", "AM", "AU", "AT", "AZ", "BS", "BH", "BD", "BB", "BY", "BE", "BZ", "BJ", "BT", "BO", "BA", "BW", "BR", "BN", "BG", "BF", "BI", "KH", "CM", "CA", "CV", "CF", "TD", "CL", "CN", "CO", "KM", "CG", "CD", "CR", "HR", "CU", "CY", "CZ", "DK", "DJ", "DM", "DO", "EC", "EG", "SV", "GQ", "ER", "EE", "SZ", "ET", "FJ", "FI", "FR", "GA", "GM", "GE", "DE", "GH", "GR", "GD", "GT", "GN", "GW", "GY", "HT", "HN", "HU", "IS", "IN", "ID", "IR", "IQ", "IE", "IL", "IT", "JM", "JP", "JO", "KZ", "KE", "KI", "KR", "KW", "KG", "LA", "LV", "LB", "LS", "LR", "LY", "LI", "LT", "LU", "MG", "MW", "MY", "MV", "ML", "MT", "MH", "MR", "MU", "MX", "FM", "MD", "MC", "MN", "ME", "MA", "MZ", "MM", "NA", "NR", "NP", "NL", "NZ", "NI", "NE", "NG", "MK", "NO", "OM", "PK", "PW", "PA", "PG", "PY", "PE", "PH", "PL", "PT", "QA", "RO", "RU", "RW", "KN", "LC", "VC", "WS", "SM", "ST", "SA", "SN", "RS", "SC", "SL", "SG", "SK", "SI", "SB", "SO", "ZA", "SS", "ES", "LK", "SD", "SR", "SE", "CH", "SY", "TJ", "TZ", "TH", "TL", "TG", "TO", "TT", "TN", "TR", "TM", "TV", "UG", "UA", "AE", "GB", "US", "UY", "UZ", "VU", "VA", "VE", "VN", "YE", "ZM", "ZW"
]

# Switch to the next country after a few interactions
REQUESTS_PER_COUNTRY = 2

async def update_country_filter(session, token, country_code):
    """Updates the Meeff filter to the specified country."""
    url = "https://api.meeff.com/user/updateFilter/v1"
    data = {
        "filterGenderType": 5,
        "filterBirthYearFrom": 1981,
        "filterBirthYearTo": 2007,
        "filterDistance": 510,
        "filterLanguageCodes": "",
        "filterNationalityBlock": 0,
        "filterNationalityCode": country_code,
        "locale": "en"
    }
    headers = {"meeff-access-token": token, "Content-Type": "application/json"}
    
    async with session.post(url, json=data, headers=headers) as response:
        if response.status != 200:
            logging.error(f"Failed to update country: {country_code} - {response.status}")
            return False
        return True

async def fetch_users(session, token):
    """Fetches users from the Meeff explore endpoint."""
    url = "https://api.meeff.com/user/explore/v2/?lat=-3.7895238&lng=-38.5327365"
    headers = {"meeff-access-token": token, "Connection": "keep-alive"}
    
    async with session.get(url, headers=headers) as response:
        if response.status != 200:
            logging.error(f"Failed to fetch users: {response.status}")
            return []
        data = await response.json()
        return data.get("users", [])

async def like_user(session, token, user_id):
    """Sends a like request to a user."""
    url = f"https://api.meeff.com/user/undoableAnswer/v5/?userId={user_id}&isOkay=1"
    headers = {"meeff-access-token": token, "Connection": "keep-alive"}
    
    async with session.get(url, headers=headers) as response:
        if response.status != 200:
            logging.error(f"Failed to like user {user_id}: {response.status}")

async def process_country(session, token, country_code):
    """Process users for a single country."""
    if not await update_country_filter(session, token, country_code):
        return
    await asyncio.sleep(1)  # Wait for the filter to apply
    users = await fetch_users(session, token)
    request_count = 0

    for user in users:
        if request_count >= REQUESTS_PER_COUNTRY:
            break
        await like_user(session, token, user["_id"])
        request_count += 1
        await asyncio.sleep(4)  # Wait to prevent rate limiting

async def all_countries(user_id):
    """Main function to cycle through countries and interact with users."""
    token = get_current_account(user_id)
    if not token:
        logging.error(f"No active account found for user: {user_id}")
        return
    
    async with aiohttp.ClientSession() as session:
        for country_code in countries:
            await process_country(session, token, country_code)
            await asyncio.sleep(1)  # Small delay between countries
