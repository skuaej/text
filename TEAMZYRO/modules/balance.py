from TEAMZYRO import *

from pyrogram import Client, filters

from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

import html, random



# ---------------- BALANCE HELPER ---------------- #

async def get_balance(user_id):

    user_data = await user_collection.find_one({'id': user_id}, {'balance': 1})

    if user_data:

        return user_data.get('balance', 0)

    return 0



# ---------------- BALANCE IMAGES ---------------- #

BALANCE_IMAGES = [

    "https://files.catbox.moe/uvvkah.jpg"

]



# ---------------- BALANCE COMMAND ---------------- #

@app.on_message(filters.command("balance"))

async def balance(client: Client, message: Message):

    user_id = message.from_user.id

    user_balance = await get_balance(user_id)



    caption = (

        f"👤 {html.escape(message.from_user.first_name)}\n"

        f"💰 Balance: ||{user_balance} coins||"

    )



    photo_url = random.choice(BALANCE_IMAGES)



    await message.reply_photo(

        photo=photo_url,

        caption=caption,

        has_spoiler=True   # photo bhi spoiler me hoga

    )



# ---------------- PAY COMMAND ---------------- #

@app.on_message(filters.command("pay"))

async def pay(client: Client, message: Message):

    sender_id = message.from_user.id

    args = message.command



    if len(args) < 3:

        await message.reply_text("Usage: /pay <amount> [@username/user_id] or reply to a user.")

        return



    # --- Amount check ---

    try:

        amount = int(args[1])

        if amount <= 0:

            raise ValueError

    except ValueError:

        await message.reply_text("❌ Invalid amount. Please enter a positive number.")

        return



    recipient_id = None

    recipient_name = None



    # If replied to user

    if message.reply_to_message:

        recipient_id = message.reply_to_message.from_user.id

        recipient_name = message.reply_to_message.from_user.first_name



    # If username or ID given

    elif len(args) > 2:

        try:

            recipient_id = int(args[2])

        except ValueError:

            recipient_username = args[2].lstrip('@')

            user_data = await user_collection.find_one({'username': recipient_username}, {'id': 1, 'first_name': 1})

            if user_data:

                recipient_id = user_data['id']

                recipient_name = user_data.get('first_name', recipient_username)

            else:

                await message.reply_text("❌ Recipient not found.")

                return



    if not recipient_id:

        await message.reply_text("❌ Recipient not found. Reply to a user or provide a valid user ID/username.")

        return



    sender_balance = await get_balance(sender_id)

    if sender_balance < amount:

        await message.reply_text("❌ Insufficient balance.")

        return



    # --- Confirm/Cancel Buttons ---

    buttons = InlineKeyboardMarkup(

        [

            [

                InlineKeyboardButton("✅ Confirm", callback_data=f"pay_confirm:{sender_id}:{recipient_id}:{amount}"),

                InlineKeyboardButton("❌ Cancel", callback_data=f"pay_cancel:{sender_id}:{recipient_id}:{amount}")

            ]

        ]

    )



    recipient_display = html.escape(recipient_name or str(recipient_id))

    await message.reply_text(

        f"⚠️ Are you sure you want to pay {amount} coins to {recipient_display}?",

        reply_markup=buttons

    )



# ---------------- CALLBACK HANDLER ---------------- #

@app.on_callback_query(filters.regex(r"^pay_"))

async def pay_callback(client: Client, callback_query):

    try:

        parts = callback_query.data.split(":")

        action = parts[0]              # pay_confirm / pay_cancel

        sender_id = int(parts[1])

        recipient_id = int(parts[2])

        amount = int(parts[3])



        await callback_query.answer()



        # Only sender can confirm/cancel

        if callback_query.from_user.id != sender_id:

            await callback_query.answer("⚠️ You are not allowed to confirm this transaction!", show_alert=True)

            return



        # Cancel

        if action == "pay_cancel":

            await callback_query.message.edit_text("❌ Payment cancelled.")

            return



        # Confirm

        if action == "pay_confirm":

            sender_balance = await get_balance(sender_id)

            if sender_balance < amount:

                await callback_query.message.edit_text("❌ Transaction failed. Insufficient balance.")

                return



            # Update balances

            await user_collection.update_one({'id': sender_id}, {'$inc': {'balance': -amount}})

            await user_collection.update_one({'id': recipient_id}, {'$inc': {'balance': amount}}, upsert=True)



            updated_sender_balance = await get_balance(sender_id)

            updated_recipient_balance = await get_balance(recipient_id)



            recipient_data = await user_collection.find_one({'id': recipient_id}, {'first_name': 1})

            recipient_name = recipient_data.get('first_name', str(recipient_id)) if recipient_data else str(recipient_id)



            sender_display = html.escape(callback_query.from_user.first_name or str(sender_id))

            recipient_display = html.escape(recipient_name)



            # Notify sender

            await callback_query.message.edit_text(

                f"✅ You paid {amount} coins to {recipient_display}.\n"

                f"💰 Your New Balance: {updated_sender_balance} coins"

            )



            # Notify recipient

            try:

                await client.send_message(

                    chat_id=recipient_id,

                    text=f"🎉 You received {amount} coins from {sender_display}!\n"

                         f"💰 Your New Balance: {updated_recipient_balance} coins"

                )

            except:

                pass



    except Exception as e:

        await callback_query.answer("⚠️ Error in processing payment!", show_alert=True)

        print(f"PAY CALLBACK ERROR: {e}")
