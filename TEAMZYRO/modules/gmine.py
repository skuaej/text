from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from TEAMZYRO import ZYRO as bot
import random, math

# in-memory state
active_games = {}

def tiny(text: str) -> str:
    return str(text).upper()

def gen_mines(total_cells: int, mines_count: int):
    return random.sample(range(total_cells), mines_count)

@bot.on_message(filters.command("gmines"))
async def start_mines(client, message):
    user_id = message.from_user.id
    bet = 10
    bombs = 5
    size = 5
    total = size * size
    mine_positions = gen_mines(total, bombs)

    game = {
        "bet": bet,
        "bombs": bombs,
        "size": size,
        "mine_positions": mine_positions,
        "clicked": [],
        "multiplier": 1.0,
    }
    active_games[user_id] = game

    keyboard = [
        [InlineKeyboardButton("❓", callback_data=f"s:{i*size+j}") for j in range(size)]
        for i in range(size)
    ]
    keyboard.append([InlineKeyboardButton("💸 CASH OUT", callback_data="s:cash")])

    await message.reply(
        tiny(f"🎮 MINES GAME STARTED!\nBET: {bet}  BOMBS: {bombs}"),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

@bot.on_callback_query(filters.regex(r"^s:\d+$"))
async def single_tile_press(client, cq):
    user_id = cq.from_user.id
    pos = int(cq.data.split(":")[1])

    if user_id not in active_games:
        return await cq.answer(tiny("⚠ NO GAME"), show_alert=True)

    game = active_games[user_id]
    if pos in game["clicked"]:
        return await cq.answer(tiny("ALREADY OPENED"), show_alert=True)

    game["clicked"].append(pos)

    if pos in game["mine_positions"]:
        active_games.pop(user_id, None)
        return await cq.message.edit_text(tiny("💥 BOOM! MINE HIT."))

    game["multiplier"] = round(game["multiplier"] + 0.1, 2)
    potential_win = math.floor(game["bet"] * game["multiplier"])

    size = game["size"]
    keyboard = []
    for i in range(size):
        row = []
        for j in range(size):
            idx = i*size + j
            if idx in game["clicked"]:
                row.append(InlineKeyboardButton("✅", callback_data="s:ignore"))
            else:
                row.append(InlineKeyboardButton("❓", callback_data=f"s:{idx}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("💸 CASH OUT", callback_data="s:cash")])

    await cq.message.edit_text(
        tiny(f"SAFE!\nMULTIPLIER: {game['multiplier']}X  POTENTIAL: {potential_win}"),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

@bot.on_callback_query(filters.regex(r"^s:cash$"))
async def single_cashout(client, cq):
    user_id = cq.from_user.id
    if user_id not in active_games:
        return await cq.answer(tiny("⚠ NO GAME"), show_alert=True)

    game = active_games.pop(user_id)
    earned = math.floor(game["bet"] * game["multiplier"])
    await cq.message.edit_text(tiny(f"✅ CASHED OUT! WON {earned} COINS"))

@bot.on_callback_query(filters.regex(r"^s:ignore$"))
async def ignore_button(client, cq):
    await cq.answer()
