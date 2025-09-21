import random
import math
import asyncio
import uuid
import logging
from datetime import datetime
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from TEAMZYRO import ZYRO as bot, user_collection

log = logging.getLogger(__name__)

# ---------------- Helpers ---------------- #

def tiny(text: str) -> str:
    """Return styled text in uppercase (tiny-caps effect)."""
    try:
        return str(text).upper()
    except:
        return text

async def mention_user(client, user_id: int) -> str:
    """Return a clickable mention for the user. Fallback to id if fetch fails."""
    try:
        u = await client.get_users(user_id)
        name = u.first_name or "User"
        # Use markdown mention
        return f"[{name}](tg://user?id={user_id})"
    except Exception:
        return f"[{user_id}](tg://user?id={user_id})"

# ---------------- In-memory state ---------------- #
# single-player games keyed by user_id (int)
active_games = {}

# multiplayer pending challenges keyed by cid (str)
pending_challenges = {}

# active multiplayer games keyed by cid (str)
active_mgames = {}

# ---------------- Utility ---------------- #

def gen_mines(total_cells: int, mines_count: int):
    """Return a list of mine indices."""
    return random.sample(range(total_cells), mines_count)

def mines_count_by_size(size: int):
    """Default mines for given sizes (customizable)."""
    if size == 5:
        return 5
    if size == 9:
        return 15
    if size == 12:
        return 25
    # fallback
    return max(5, size // 2)

# ---------------- Single-player persistence helpers ---------------- #

async def save_game(user_id: int, game: dict):
    """Save single-player to DB cache and in-memory."""
    try:
        await user_collection.update_one({"id": user_id}, {"$set": {"active_game": game}}, upsert=True)
    except Exception as e:
        log.exception("DB save_game failed: %s", e)
    active_games[user_id] = game

async def load_game(user_id: int):
    """Load single-player from memory or DB."""
    if user_id in active_games:
        return active_games[user_id]
    try:
        user = await user_collection.find_one({"id": user_id})
        if user and "active_game" in user:
            active_games[user_id] = user["active_game"]
            return active_games[user_id]
    except Exception as e:
        log.exception("DB load_game failed: %s", e)
    return None

async def delete_game(user_id: int):
    """Delete single-player game."""
    active_games.pop(user_id, None)
    try:
        await user_collection.update_one({"id": user_id}, {"$unset": {"active_game": ""}})
    except Exception as e:
        log.exception("DB delete_game failed: %s", e)

# ---------------- Single-player: /mines (5x5 board) ---------------- #

@bot.on_message(filters.command("mines"))
async def start_mines(client, message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) < 3:
        return await message.reply(tiny("USAGE: /MINES [COINS] [BOMBS]"))

    try:
        bet = int(args[1])
        bombs = int(args[2])
    except Exception:
        return await message.reply(tiny("⚠ INVALID NUMBERS"))

    if bombs < 2 or bombs > 20:
        return await message.reply(tiny("⚠ BOMBS MUST BE BETWEEN 2 AND 20"))

    try:
        user = await user_collection.find_one({"id": user_id})
    except Exception as e:
        log.exception("DB find_one failed: %s", e)
        user = None

    balance = user.get("balance", 0) if user else 0
    if balance < bet:
        return await message.reply(tiny("🚨 NOT ENOUGH COINS"))

    # Deduct bet
    try:
        await user_collection.update_one({"id": user_id}, {"$inc": {"balance": -bet}}, upsert=True)
    except Exception as e:
        log.exception("DB deduct bet failed: %s", e)
        return await message.reply(tiny("⚠ INTERNAL ERROR DEDUCTING BET"))

    size = 5
    total = size * size
    mine_positions = gen_mines(total, bombs)
    game = {
        "mode": "single",
        "bet": bet,
        "bombs": bombs,
        "size": size,
        "mine_positions": mine_positions,
        "clicked": [],
        "multiplier": 1.0,
        "started_at": datetime.utcnow().isoformat()
    }

    await save_game(user_id, game)

    keyboard = [
        [InlineKeyboardButton("❓", callback_data=f"s:{i*size+j}") for j in range(size)]
        for i in range(size)
    ]
    keyboard.append([InlineKeyboardButton("💸 CASH OUT", callback_data="s:cash")])

    try:
        await message.reply(
            tiny(f"🎮 MINES GAME STARTED!\nBET: {bet}  BOMBS: {bombs}  MULTIPLIER: 1.00X"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        log.exception("Failed to send start mines message: %s", e)
        await message.reply(tiny("⚠ FAILED TO START GAME"))

# ---------------- Core logic functions (no decorators) ---------------- #
# These are called by the universal callback handler below.

async def _single_tile_press(client, cq):
    # Always answer callback quickly so Telegram shows button as pressed
    try:
        await cq.answer()
    except:
        pass

    user_id = cq.from_user.id
    try:
        pos = int(cq.data.split(":")[1])
    except Exception:
        return await cq.answer(tiny("⚠ INVALID BUTTON"), show_alert=True)

    game = await load_game(user_id)
    if not game or game.get("mode") != "single":
        return await cq.answer(tiny("⚠ NO ACTIVE GAME"), show_alert=True)

    if pos in game["clicked"]:
        return await cq.answer(tiny("ALREADY OPENED"), show_alert=True)

    game["clicked"].append(pos)

    # if mine
    if pos in game["mine_positions"]:
        await delete_game(user_id)
        size = game["size"]
        keyboard = []
        for i in range(size):
            row = []
            for j in range(size):
                idx = i*size + j
                if idx in game["mine_positions"]:
                    row.append(InlineKeyboardButton("💣", callback_data="s:ign"))
                elif idx in game["clicked"]:
                    row.append(InlineKeyboardButton("✅", callback_data="s:ign"))
                else:
                    row.append(InlineKeyboardButton("❎", callback_data="s:ign"))
            keyboard.append(row)

        text = tiny(f"💥 BOOM! MINE HIT.\nLOST: {game['bet']} COINS")

        # Try to edit the current message; if fails, try sending a new message
        try:
            await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            log.exception("single mine hit edit_text failed: %s", e)
            try:
                await cq.message.reply(text, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                pass
        return

    # safe
    game["multiplier"] = round(game["multiplier"] + 0.05, 2)
    potential_win = math.floor(game["bet"] * game["multiplier"])
    await save_game(user_id, game)

    # update view
    size = game["size"]
    keyboard = []
    for i in range(size):
        row = []
        for j in range(size):
            idx = i*size + j
            if idx in game["clicked"]:
                row.append(InlineKeyboardButton("✅", callback_data="s:ign"))
            else:
                row.append(InlineKeyboardButton("❓", callback_data=f"s:{idx}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("💸 CASH OUT", callback_data="s:cash")])

    status = tiny(f"🎮 MINES GAME\nBET: {game['bet']}  BOMBS: {game['bombs']}  MULTIPLIER: {game['multiplier']:.2f}X  POTENTIAL: {potential_win}")

    # prefer editing only markup when possible — but we replace text+markup for consistent display
    try:
        await cq.message.edit_text(status, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        log.exception("single_tile_press edit_text failed: %s", e)
        # try send fallback so players still see updates
        try:
            await cq.message.reply(status, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            pass

async def _single_cashout(client, cq):
    try:
        await cq.answer()
    except:
        pass

    user_id = cq.from_user.id
    game = await load_game(user_id)
    if not game or game.get("mode") != "single":
        return await cq.answer(tiny("⚠ NO ACTIVE GAME"), show_alert=True)

    await delete_game(user_id)
    earned = math.floor(game["bet"] * game["multiplier"])
    try:
        await user_collection.update_one({"id": user_id}, {"$inc": {"balance": earned}}, upsert=True)
        user = await user_collection.find_one({"id": user_id})
    except Exception as e:
        log.exception("DB cashout failed: %s", e)
        user = None

    new_balance = user.get("balance", 0) if user else 0

    size = game["size"]
    keyboard = []
    for i in range(size):
        row = []
        for j in range(size):
            idx = i*size + j
            if idx in game["mine_positions"]:
                row.append(InlineKeyboardButton("💣", callback_data="s:ign"))
            elif idx in game["clicked"]:
                row.append(InlineKeyboardButton("✅", callback_data="s:ign"))
            else:
                row.append(InlineKeyboardButton("❎", callback_data="s:ign"))
        keyboard.append(row)

    msg_text = tiny(f"✅ CASHED OUT!\nWON: {earned} COINS\nMULTIPLIER: {game['multiplier']:.2f}X\nBALANCE: {new_balance}")

    try:
        msg = await cq.message.edit_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        log.exception("single_cashout edit_text failed: %s", e)
        try:
            msg = await cq.message.reply(msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            msg = None

    # remove the message after short delay to clean up UI
    if msg:
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass

async def _single_ignore(client, cq):
    # Acknowledge and ignore - this prevents the "button not responding" feeling
    try:
        await cq.answer()
    except:
        pass
    # nothing else

# ---------------- Multiplayer: /mgame challenge flow (core logic functions) ---------------- #

@bot.on_message(filters.command("mgame"))
async def mgame_command(client, message):
    """
    Usage:
        /mgame [bet] [@username]
    Or: reply to a user's message with /mgame [bet]
    """
    challenger = message.from_user
    args = message.text.split()
    if len(args) < 2 and not message.reply_to_message:
        return await message.reply(tiny("USAGE: /MGAME [BET] [@USER OR REPLY]"))

    try:
        bet = int(args[1]) if len(args) >= 2 else None
    except Exception:
        return await message.reply(tiny("⚠ INVALID BET AMOUNT"))

    # resolve opponent
    opponent_id = None
    opponent_name = None
    if len(args) >= 3:
        mention = args[2]
        try:
            u = await client.get_users(mention)
            opponent_id = u.id
            opponent_name = u.first_name
        except Exception:
            opponent_id = None
    elif message.reply_to_message:
        opponent_id = message.reply_to_message.from_user.id
        opponent_name = message.reply_to_message.from_user.first_name

    if opponent_id is None:
        return await message.reply(tiny("⚠ COULD NOT RESOLVE OPPONENT. TAG OR REPLY TO A USER."))

    # check balances
    try:
        chal_user = await user_collection.find_one({"id": challenger.id}) or {}
        opp_user = await user_collection.find_one({"id": opponent_id}) or {}
    except Exception as e:
        log.exception("DB find_one in mgame_command failed: %s", e)
        chal_user = {}
        opp_user = {}

    if (chal_user.get("balance", 0)) < bet:
        return await message.reply(tiny("🚨 YOU DONT HAVE ENOUGH COINS TO CHALLENGE"))
    if (opp_user.get("balance", 0)) < bet:
        return await message.reply(tiny("🚨 OPPONENT DOES NOT HAVE ENOUGH COINS"))

    # create challenge id
    cid = uuid.uuid4().hex[:8]
    pending_challenges[cid] = {
        "cid": cid,
        "challenger": challenger.id,
        "opponent": opponent_id,
        "bet": bet,
        "created_at": datetime.utcnow().isoformat()
    }

    kb = [
        [InlineKeyboardButton("✅ ACCEPT", callback_data=f"mg:acc:{cid}"),
         InlineKeyboardButton("❌ DECLINE", callback_data=f"mg:rej:{cid}")]
    ]

    # send challenge to opponent (private) - best-effort
    try:
        await client.send_message(
            opponent_id,
            tiny(f"🎮 YOU HAVE BEEN CHALLENGED BY {challenger.first_name}\nBET: {bet} COINS EACH\nCLICK TO ACCEPT OR DECLINE"),
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except Exception as e:
        log.exception("Failed to send challenge: %s", e)
        pending_challenges.pop(cid, None)
        return await message.reply(tiny("⚠ COULD NOT SEND CHALLENGE TO OPPONENT (PRIVATE MESSAGES MAY BE CLOSED)."))

    await message.reply(tiny(f"CHALLENGE SENT TO {opponent_name} (ID {cid})"))

async def _mg_reject_handler(client, cq):
    try:
        await cq.answer()
    except:
        pass

    cid = cq.data.split(":")[2]
    chal = pending_challenges.get(cid)
    if not chal:
        return await cq.answer(tiny("⚠ CHALLENGE NOT FOUND"), show_alert=True)
    if cq.from_user.id != chal["opponent"]:
        return await cq.answer(tiny("THIS IS NOT FOR YOU"), show_alert=True)

    pending_challenges.pop(cid, None)
    try:
        await cq.message.edit_text(tiny("CHALLENGE DECLINED"))
    except Exception:
        pass
    try:
        await client.send_message(chal["challenger"], tiny(f"YOUR CHALLENGE {cid} WAS DECLINED"))
    except:
        pass

async def _mg_accept_handler(client, cq):
    try:
        await cq.answer()
    except:
        pass

    cid = cq.data.split(":")[2]
    chal = pending_challenges.get(cid)
    if not chal:
        return await cq.answer(tiny("⚠ CHALLENGE NOT FOUND"), show_alert=True)
    if cq.from_user.id != chal["opponent"]:
        return await cq.answer(tiny("THIS IS NOT FOR YOU"), show_alert=True)

    # show size selection
    kb = [
        [InlineKeyboardButton("5 x 5", callback_data=f"mg:size:{cid}:5")],
        [InlineKeyboardButton("9 x 9", callback_data=f"mg:size:{cid}:9")],
        [InlineKeyboardButton("12 x 12", callback_data=f"mg:size:{cid}:12")],
    ]
    try:
        # prefer editing markup only when possible
        try:
            await cq.message.edit_text(tiny("SELECT BOARD SIZE"), reply_markup=InlineKeyboardMarkup(kb))
        except Exception:
            await cq.message.reply(tiny("SELECT BOARD SIZE"), reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        log.exception("mg_accept_handler failed: %s", e)

async def _mg_size_selected(client, cq):
    try:
        await cq.answer()
    except:
        pass

    parts = cq.data.split(":")
    try:
        cid = parts[2]
        size = int(parts[3])
    except Exception:
        return await cq.answer(tiny("⚠ INVALID SELECTION"), show_alert=True)

    chal = pending_challenges.get(cid)
    if not chal:
        return await cq.answer(tiny("⚠ CHALLENGE EXPIRED"), show_alert=True)

    challenger_id = chal["challenger"]
    opponent_id = chal["opponent"]
    bet = chal["bet"]

    # re-check balances
    try:
        chal_user = await user_collection.find_one({"id": challenger_id}) or {}
        opp_user = await user_collection.find_one({"id": opponent_id}) or {}
    except Exception as e:
        log.exception("DB find_one in mg_size_selected failed: %s", e)
        chal_user = {}
        opp_user = {}

    if (chal_user.get("balance", 0)) < bet:
        pending_challenges.pop(cid, None)
        return await cq.answer(tiny("CHALLENGER INSUFFICIENT FUNDS"), show_alert=True)
    if (opp_user.get("balance", 0)) < bet:
        pending_challenges.pop(cid, None)
        return await cq.answer(tiny("OPPONENT INSUFFICIENT FUNDS"), show_alert=True)

    # deduct bets
    try:
        await user_collection.update_one({"id": challenger_id}, {"$inc": {"balance": -bet}}, upsert=True)
        await user_collection.update_one({"id": opponent_id}, {"$inc": {"balance": -bet}}, upsert=True)
    except Exception as e:
        log.exception("DB deduct in mg_size_selected failed: %s", e)
        return await cq.answer(tiny("⚠ INTERNAL ERROR PROCESSING BETS"), show_alert=True)

    # create game
    total_cells = size * size
    mines_count = mines_count_by_size(size)
    mine_positions = gen_mines(total_cells, mines_count)

    game = {
        "cid": cid,
        "mode": "multi",
        "players": [challenger_id, opponent_id],
        "bet": bet,
        "size": size,
        "bombs": mines_count,
        "mine_positions": mine_positions,
        "clicked": [],
        "turn": challenger_id,  # challenger starts
        "started_at": datetime.utcnow().isoformat()
    }

    active_mgames[cid] = game
    pending_challenges.pop(cid, None)

    # build keyboard
    def build_board_kb(g):
        sz = g["size"]
        kb = []
        for i in range(sz):
            row = []
            for j in range(sz):
                idx = i*sz + j
                row.append(InlineKeyboardButton("❓", callback_data=f"mp:{g['cid']}:{idx}"))
            kb.append(row)
        kb.append([InlineKeyboardButton("🔁 REFRESH", callback_data=f"mp:refresh:{g['cid']}")])
        return kb

    kb = build_board_kb(game)

    # Compose status showing mentions for turn
    try:
        turn_mention = await mention_user(client, game["turn"])
    except Exception:
        turn_mention = str(game["turn"])

    status_text = tiny(f"🎮 MINES DUEL STARTED!\nBET: {bet} EACH  POOL: {bet*2}\nSIZE: {size}x{size}  BOMBS: {mines_count}\nTURN: {turn_mention}")

    # Try to edit opponent message and notify challenger
    try:
        await cq.message.edit_text(status_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="markdown")
    except Exception:
        try:
            await cq.message.reply(status_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="markdown")
        except Exception:
            pass

    # send a message to challenger too (private)
    try:
        await client.send_message(game["players"][0], status_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="markdown")
    except Exception:
        pass

async def _mp_refresh_handler(client, cq):
    """Refresh the board view for the player who pressed refresh."""
    try:
        await cq.answer()
    except:
        pass
    cid = cq.data.split(":")[2]
    game = active_mgames.get(cid)
    if not game:
        return await cq.answer(tiny("⚠ NO ACTIVE MULTIPLAYER GAME"), show_alert=True)

    # rebuild keyboard showing opened tiles
    sz = game["size"]
    keyboard = []
    for i in range(sz):
        row = []
        for j in range(sz):
            idx = i*sz + j
            if idx in game["clicked"]:
                row.append(InlineKeyboardButton("✅", callback_data=f"mpx:{cid}:ign"))
            else:
                row.append(InlineKeyboardButton("❓", callback_data=f"mp:{cid}:{idx}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔁 REFRESH", callback_data=f"mp:refresh:{cid}")])

    try:
        turn_mention = await mention_user(client, game["turn"])
    except:
        turn_mention = str(game["turn"])

    status = tiny(f"🎮 MINES DUEL\nBET: {game['bet']} EACH  POOL: {game['bet']*2}\nSIZE: {sz}x{sz}  BOMBS: {game['bombs']}\nTURN: {turn_mention}")

    # edit current message
    try:
        await cq.message.edit_text(status, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="markdown")
    except Exception as e:
        log.exception("mp_tile_handler update edit_text failed: %s", e)
        # best-effort: send direct messages to players so they see the updated board
        for p in game["players"]:
            try:
                await client.send_message(p, status, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="markdown")
            except:
                pass

async def _mp_ignore_buttons(client, cq):
    # Acknowledge and ignore revealed/disabled presses
    try:
        await cq.answer()
    except:
        pass
    # nothing else

# ---------------- Universal callback handler (single place to catch all callback_data) ---------------- #

@bot.on_callback_query()
async def universal_callback_router(client, cq):
    """
    Single callback entrypoint. Routes callback_data to the right internal handler.
    This avoids issues with multiple regex-based handlers not registering properly.
    """
    data = cq.data or ""
    # quick debug log (comment out or use logging in production)
    try:
        log.info("Callback received: %s from %s", data, cq.from_user.id)
    except:
        pass

    # SINGLE PLAYER: s:
    if data.startswith("s:"):
        # exact matches first
        if data == "s:cash":
            return await _single_cashout(client, cq)
        if data == "s:ign":
            return await _single_ignore(client, cq)
        # tile press like s:12
        return await _single_tile_press(client, cq)

    # MGAME (challenge) handlers: mg:rej:, mg:acc:, mg:size:
    if data.startswith("mg:rej:"):
        return await _mg_reject_handler(client, cq)
    if data.startswith("mg:acc:"):
        return await _mg_accept_handler(client, cq)
    if data.startswith("mg:size:"):
        return await _mg_size_selected(client, cq)

    # MULTIPLAYER: mp:refresh:, mp:..., mpx:...
    if data.startswith("mp:refresh:"):
        return await _mp_refresh_handler(client, cq)
    if data.startswith("mpx:"):
        # ignored/disabled tile presses
        return await _mp_ignore_buttons(client, cq)
    if data.startswith("mp:"):
        # multiplayer tile press - currently refresh covers view, individual tile presses
        # can be implemented here if you want turn-based tile press logic.
        # For now, we respond with a helpful message.
        try:
            await cq.answer("Use REFRESH to update board or wait for opponent.", show_alert=False)
        except:
            pass
        return

    # fallback for unknown buttons
    try:
        await cq.answer("⚠ Unknown or expired button.", show_alert=True)
    except:
        pass

# ---------------- End of file ---------------- #
