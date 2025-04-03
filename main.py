import asyncio
import aiohttp
import logging
import html
from collections import defaultdict
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, Router, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.filters import Command
from aiogram.types.callback_query import CallbackQuery
from db import set_token, get_tokens, set_current_account, get_current_account, delete_token
from lounge import send_lounge
from chatroom import send_message_to_everyone
from unsubscribe import unsubscribe_everyone
from filters import filter_command, set_filter
from aio import aio_markup, aio_callback_handler, run_requests, user_states
from allcountry import run_all_countries

API_TOKEN = "7682628861:AAEEXyWLUiP2jOtsghWqt0bw4L65H6mwsyY"
ADMIN_USER_IDS = [6387028671, 6816341239, 6204011131]
TEMP_PASSWORD = "11223344"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
bot = Bot(token=API_TOKEN)
router = Router()
dp = Dispatcher()

# Global state variables
user_states = defaultdict(lambda: {
    "running": False,
    "status_message_id": None,
    "pinned_message_id": None,
    "total_added_friends": 0
})

# Inline keyboards
start_markup = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Start Requests", callback_data="start")],
    [InlineKeyboardButton(text="Manage Accounts", callback_data="manage_accounts")],
    [InlineKeyboardButton(text="All Countries", callback_data="all_countries")]
])
stop_markup = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Stop Requests", callback_data="stop")]
])
back_markup = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Back", callback_data="back_to_menu")]
])

def is_admin(user_id):
    return user_id in ADMIN_USER_IDS

def has_valid_access(user_id):
    return is_admin(user_id) or (user_id in password_access and password_access[user_id] > datetime.now())

password_access = {}

async def fetch_users(session, token):
    url = "https://api.meeff.com/user/explore/v2/?lat=33.589510&lng=-117.860909"
    headers = {"meeff-access-token": token, "Connection": "keep-alive"}
    async with session.get(url, headers=headers) as response:
        if response.status != 200:
            logging.error(f"Failed to fetch users: {response.status}")
            return []
        return (await response.json()).get("users", [])

def format_user_details(user):
    return (
        f"<b>Name:</b> {html.escape(user.get('name', 'N/A'))}\n"
        f"<b>Description:</b> {html.escape(user.get('description', 'N/A'))}\n"
        f"<b>Birth Year:</b> {html.escape(str(user.get('birthYear', 'N/A')))}\n"
        f"<b>Distance:</b> {html.escape(str(user.get('distance', 'N/A')))} km\n"
        f"<b>Language Codes:</b> {html.escape(', '.join(user.get('languageCodes', [])))}\n"
        "Photos: " + ' '.join([f"<a href='{html.escape(url)}'>Photo</a>" for url in user.get('photoUrls', [])])
    )

async def process_users(session, users, token, user_id):
    state = user_states[user_id]
    batch_added = 0
    for user in users:
        if not state["running"]:
            break
        url = f"https://api.meeff.com/user/undoableAnswer/v5/?userId={user['_id']}&isOkay=1"
        headers = {"meeff-access-token": token, "Connection": "keep-alive"}
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            if data.get("errorCode") == "LikeExceeded":
                logging.info("Daily like limit reached.")
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=state["status_message_id"],
                    text=f"You've reached the daily limit. Total Added: {state['total_added_friends']}. Try again tomorrow.",
                    reply_markup=None
                )
                return True
            # send user info and update counts
            await bot.send_message(chat_id=user_id, text=format_user_details(user), parse_mode="HTML")
            batch_added += 1
            state["total_added_friends"] += 1
            if state["running"]:
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=state["status_message_id"],
                    text=(f"Batch: {state['batch_index']} | Users Fetched: {len(users)}\n"
                          f"Batch Added: {batch_added}\nTotal Added: {state['total_added_friends']}"),
                    reply_markup=stop_markup
                )
            await asyncio.sleep(1)
    return False

async def run_requests(user_id):
    state = user_states[user_id]
    state["total_added_friends"] = state["batch_index"] = 0
    async with aiohttp.ClientSession() as session:
        while state["running"]:
            token = get_current_account(user_id)
            if not token:
                await bot.edit_message_text(chat_id=user_id, message_id=state["status_message_id"],
                                              text="No active account found. Set an account to start requests.", reply_markup=None)
                state["running"] = False
                if state["pinned_message_id"]:
                    await bot.unpin_chat_message(chat_id=user_id, message_id=state["pinned_message_id"])
                break
            users = await fetch_users(session, token)
            state["batch_index"] += 1
            if not users:
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=state["status_message_id"],
                    text=f"Batch: {state['batch_index']} | Users Fetched: 0\nTotal Added: {state['total_added_friends']}",
                    reply_markup=stop_markup
                )
            elif await process_users(session, users, token, user_id):
                state["running"] = False
                if state["pinned_message_id"]:
                    await bot.unpin_chat_message(chat_id=user_id, message_id=state["pinned_message_id"])
                break
            await asyncio.sleep(1)

@router.message(Command("password"))
async def password_command(message: types.Message):
    user_id = message.chat.id
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.reply("Usage: /password <password>")
        return
    if parts[1] == TEMP_PASSWORD:
        password_access[user_id] = datetime.now() + timedelta(hours=1)
        await message.reply("Access granted for one hour.")
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    else:
        await message.reply("Incorrect password.")

@router.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("You are not authorized.")
        return
    state = user_states[user_id]
    status = await message.answer("Welcome! Use the menu to start requests.", reply_markup=start_markup)
    state["status_message_id"] = status.message_id
    state["pinned_message_id"] = None

async def token_verification(token):
    url = "https://api.meeff.com/facetalk/vibemeet/history/count/v1"
    params = {'locale': "en"}
    headers = {
        'User-Agent': "okhttp/5.0.0-alpha.14",
        'Accept-Encoding': "gzip",
        'meeff-access-token': token
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as resp:
            return await resp.json(content_type=None)

@router.message()
async def handle_new_token(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return
    user_id = message.from_user.id
    if message.from_user.is_bot or not has_valid_access(user_id):
        await message.reply("Not authorized.")
        return
    token = message.text.strip()
    if len(token) < 10:
        await message.reply("Invalid token. Try again.")
        return
    result = await token_verification(token)
    if "errorCode" in result and result["errorCode"] == "AuthRequired":
        await message.reply("The provided token is invalid or disabled. Try a different token.")
        return
    tokens = get_tokens(user_id)
    account_name = f"Account {len(tokens) + 1}"
    set_token(user_id, token, account_name)
    await message.reply(f"Token verified and saved as {account_name}.")

@router.message(Command("chatroom"))
async def send_to_all_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("Not authorized.")
        return
    token = get_current_account(user_id)
    if not token:
        await message.reply("Set an active account first.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.reply("Usage: /send_to_all <message>")
        return
    custom_message = " ".join(parts[1:])
    status_message = await message.reply("Sending messages...")
    await send_message_to_everyone(token, custom_message, status_message=status_message, bot=bot, chat_id=user_id)
    await status_message.edit_text("Messages sent to chatrooms.")

@router.message(Command("skip"))
async def unsubscribe_all_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("Not authorized.")
        return
    token = get_current_account(user_id)
    if not token:
        await message.reply("Set an active account first.")
        return
    status_msg = await message.reply("Unsubscribing...")
    await unsubscribe_everyone(token, status_message=status_msg, bot=bot, chat_id=user_id)
    await status_msg.edit_text("Unsubscribed from chatrooms.")

@router.message(Command("lounge"))
async def lounge_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("Not authorized.")
        return
    token = get_current_account(user_id)
    if not token:
        await message.reply("Set an active account first.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.reply("Usage: /lounge <message>")
        return
    custom_message = " ".join(parts[1:])
    status_msg = await message.reply("Sending lounge messages...")
    await send_lounge(token, custom_message, status_message=status_msg, bot=bot, chat_id=user_id)
    await status_msg.edit_text("Messages sent to lounge users.")

@router.message(Command("filter"))
async def filter_handler(message: types.Message):
    if not has_valid_access(message.chat.id):
        await message.reply("Not authorized.")
        return
    await filter_command(message)

@router.message(Command("invoke"))
async def invoke_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("Not authorized.")
        return
    tokens = get_tokens(user_id)
    if not tokens:
        await message.reply("No tokens found.")
        return
    disabled = []
    url = "https://api.meeff.com/facetalk/vibemeet/history/count/v1"
    params = {'locale': "en"}
    async with aiohttp.ClientSession() as session:
        for t in tokens:
            headers = {
                'User-Agent': "okhttp/5.0.0-alpha.14",
                'Accept-Encoding': "gzip",
                'meeff-access-token': t["token"]
            }
            try:
                async with session.get(url, params=params, headers=headers) as resp:
                    result = await resp.json(content_type=None)
                    if result.get("errorCode") == "AuthRequired":
                        disabled.append(t)
            except Exception as e:
                logging.error(f"Error checking token {t.get('name')}: {e}")
                disabled.append(t)
    if disabled:
        for t in disabled:
            delete_token(user_id, t["token"])
            await message.reply(f"Deleted disabled token for account: {t['name']}")
    else:
        await message.reply("All accounts are working.")

@router.message(Command("aio"))
async def aio_command(message: types.Message):
    if not has_valid_access(message.chat.id):
        await message.reply("Not authorized.")
        return
    await message.answer("Choose an action:", reply_markup=aio_markup)

@router.callback_query()
async def callback_handler(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    state = user_states[user_id]
    if not has_valid_access(user_id):
        await callback_query.answer("Not authorized.")
        return
    if callback_query.data.startswith("aio_"):
        await aio_callback_handler(callback_query)
        return

    # Manage Accounts
    if callback_query.data == "manage_accounts":
        tokens = get_tokens(user_id)
        current = get_current_account(user_id)
        if not tokens:
            await callback_query.message.edit_text("No accounts saved. Send a token to add one.", reply_markup=back_markup)
            return
        buttons = [[
            InlineKeyboardButton(text=f"{t['name']} {'(Current)' if t['token'] == current else ''}",
                                   callback_data=f"set_account_{i}"),
            InlineKeyboardButton(text="Delete", callback_data=f"delete_account_{i}")
        ] for i, t in enumerate(tokens)]
        buttons.append([InlineKeyboardButton(text="Back", callback_data="back_to_menu")])
        await callback_query.message.edit_text("Manage your accounts:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    elif callback_query.data.startswith("set_account_"):
        index = int(callback_query.data.split("_")[-1])
        tokens = get_tokens(user_id)
        if index < len(tokens):
            set_current_account(user_id, tokens[index]["token"])
            await callback_query.message.edit_text("Account set as active. You can now start requests.")
        else:
            await callback_query.answer("Invalid account selected.")
    elif callback_query.data.startswith("delete_account_"):
        index = int(callback_query.data.split("_")[-1])
        tokens = get_tokens(user_id)
        if index < len(tokens):
            delete_token(user_id, tokens[index]["token"])
            await callback_query.message.edit_text("Account deleted.", reply_markup=back_markup)
        else:
            await callback_query.answer("Invalid account selected.")
    elif callback_query.data == "start":
        if state["running"]:
            await callback_query.answer("Requests already running!")
        else:
            state["running"] = True
            try:
                status_msg = await callback_query.message.edit_text("Initializing requests...", reply_markup=stop_markup)
                state["status_message_id"] = status_msg.message_id
                state["pinned_message_id"] = status_msg.message_id
                await bot.pin_chat_message(chat_id=user_id, message_id=state["status_message_id"])
                asyncio.create_task(run_requests(user_id))
                await callback_query.answer("Requests started!")
            except Exception as e:
                logging.error(f"Error starting requests: {e}")
                await callback_query.message.edit_text("Error starting requests.", reply_markup=start_markup)
                state["running"] = False
    elif callback_query.data == "stop":
        if not state["running"]:
            await callback_query.answer("Requests not running!")
        else:
            state["running"] = False
            await callback_query.message.edit_text(
                f"Requests stopped. Total Added: {state['total_added_friends']}",
                reply_markup=start_markup
            )
            await callback_query.answer("Requests stopped.")
            if state["pinned_message_id"]:
                await bot.unpin_chat_message(chat_id=user_id, message_id=state["pinned_message_id"])
    elif callback_query.data == "all_countries":
        if state["running"]:
            await callback_query.answer("Another process running!")
        else:
            state["running"] = True
            try:
                status_msg = await callback_query.message.edit_text("Starting All Countries feature...", reply_markup=stop_markup)
                state["status_message_id"] = status_msg.message_id
                state["pinned_message_id"] = status_msg.message_id
                state["stop_markup"] = stop_markup
                await bot.pin_chat_message(chat_id=user_id, message_id=status_msg.message_id)
                asyncio.create_task(run_all_countries(user_id, state, bot, get_current_account))
                await callback_query.answer("All Countries feature started!")
            except Exception as e:
                logging.error(f"Error starting All Countries feature: {e}")
                await callback_query.message.edit_text("Error starting All Countries feature.", reply_markup=start_markup)
                state["running"] = False
    elif callback_query.data == "back_to_menu":
        await callback_query.message.edit_text("Welcome! Use the menu below to navigate.", reply_markup=start_markup)
    elif callback_query.data.startswith("filter_"):
        await set_filter(callback_query)

async def set_bot_commands():
    cmds = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="lounge", description="Send lounge message"),
        BotCommand(command="chatroom", description="Send chatroom message"),
        BotCommand(command="aio", description="Show aio commands"),
        BotCommand(command="filter", description="Set filter preferences"),
        BotCommand(command="invoke", description="Verify and remove disabled accounts"),
        BotCommand(command="skip", description="Skip chatroom users"),
        BotCommand(command="password", description="Enter temporary access password")
    ]
    await bot.set_my_commands(cmds)

async def main():
    await set_bot_commands()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
