import asyncio
import aiohttp
import logging

# All available country ISO codes
countries = [
    "AF", "AL", "DZ", "AD", "AO", "AG", "AR", "AM", "AU", "AT", "AZ", "BS", "BH", "BD",
    "BB", "BY", "BE", "BZ", "BJ", "BT", "BO", "BA", "BW", "BR", "BN", "BG", "BF", "BI",
    "KH", "CM", "CA", "CV", "CF", "TD", "CL", "CN", "CO", "KM", "CG", "CD", "CR", "HR",
    "CU", "CY", "CZ", "DK", "DJ", "DM", "DO", "EC", "EG", "SV", "GQ", "ER", "EE", "SZ",
    "ET", "FJ", "FI", "FR", "GA", "GM", "GE", "DE", "GH", "GR", "GD", "GT", "GN", "GW",
    "GY", "HT", "HN", "HU", "IS", "IN", "ID", "IR", "IQ", "IE", "IL", "IT", "JM", "JP",
    "JO", "KZ", "KE", "KI", "KR", "KW", "KG", "LA", "LV", "LB", "LS", "LR", "LY", "LI",
    "LT", "LU", "MG", "MW", "MY", "MV", "ML", "MT", "MH", "MR", "MU", "MX", "FM", "MD",
    "MC", "MN", "ME", "MA", "MZ", "MM", "NA", "NR", "NP", "NL", "NZ", "NI", "NE", "NG",
    "MK", "NO", "OM", "PK", "PW", "PA", "PG", "PY", "PE", "PH", "PL", "PT", "QA", "RO",
    "RU", "RW", "KN", "LC", "VC", "WS", "SM", "ST", "SA", "SN", "RS", "SC", "SL", "SG",
    "SK", "SI", "SB", "SO", "ZA", "SS", "ES", "LK", "SD", "SR", "SE", "CH", "SY", "TJ",
    "TZ", "TH", "TL", "TG", "TO", "TT", "TN", "TR", "TM", "TV", "UG", "UA", "AE", "GB",
    "US", "UY", "UZ", "VU", "VA", "VE", "VN", "YE", "ZM", "ZW"
]

# Number of like requests to send per country before switching
REQUESTS_PER_COUNTRY = 2

# Base headers template; the token will be added dynamically
BASE_HEADERS = {
    "User-Agent": "okhttp/4.12.0",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8"
}

async def update_country_filter(session, headers, country_code):
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
    try:
        async with session.post(url, json=data, headers=headers) as response:
            if response.status == 200:
                logging.info(f"✅ Switched to country: {country_code}")
            else:
                logging.error(f"❌ Failed to update country: {country_code}, status: {response.status}")
    except Exception as e:
        logging.error(f"❌ Exception updating country filter for {country_code}: {e}")

async def fetch_users(session, headers):
    """Fetches users from the Meeff explore endpoint."""
    url = "https://api.meeff.com/user/explore/v2/?lat=-3.7895238&lng=-38.5327365"
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("users", [])
            else:
                logging.error(f"❌ Failed to fetch users, status: {response.status}")
                return []
    except Exception as e:
        logging.error(f"❌ Exception fetching users: {e}")
        return []

async def like_user(session, headers, user_id):
    """Sends a like request to a user."""
    url = f"https://api.meeff.com/user/undoableAnswer/v5/?userId={user_id}&isOkay=1"
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                logging.info(f"👍 Liked user: {user_id} response: {data}")
            else:
                logging.error(f"❌ Failed to like user {user_id}, status: {response.status}")
    except Exception as e:
        logging.error(f"❌ Exception liking user {user_id}: {e}")

async def run_all_countries(user_id, state, bot, get_current_account):
    """
    Runs the All Countries feature.
    
    Arguments:
    - user_id: Telegram user ID.
    - state: The user state dictionary from main.py (contains running state and counters).
    - bot: The aiogram Bot object.
    - get_current_account: A function to fetch the active account token.
    """
    token = get_current_account(user_id)
    if not token:
        await bot.send_message(chat_id=user_id, text="No active account found. Please set an account before starting All Countries feature.")
        return

    headers = dict(BASE_HEADERS)
    headers["meeff-access-token"] = token

    async with aiohttp.ClientSession() as session:
        country_index = 0
        state["total_added_friends"] = 0
        state["country_batch_index"] = 0
        status_msg = await bot.send_message(chat_id=user_id, text="Starting All Countries feature...")
        while state["running"]:
            current_country = countries[country_index]
            await update_country_filter(session, headers, current_country)
            users = await fetch_users(session, headers)
            request_count = 0
            state["country_batch_index"] += 1

            for user in users:
                if request_count >= REQUESTS_PER_COUNTRY or not state["running"]:
                    break
                await like_user(session, headers, user["_id"])
                state["total_added_friends"] += 1
                request_count += 1
                await bot.send_message(
                    chat_id=user_id, 
                    text=f"Country: {current_country} | Liked user: {user['_id']}\nTotal Liked: {state['total_added_friends']}"
                )
                await asyncio.sleep(4)
            country_index = (country_index + 1) % len(countries)
            await asyncio.sleep(1)
        await bot.send_message(
            chat_id=user_id, 
            text=f"All Countries feature stopped. Total Liked: {state['total_added_friends']}"
        )
