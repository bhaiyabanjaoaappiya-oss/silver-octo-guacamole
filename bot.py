import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pymongo import MongoClient
from datetime import datetime

# ================== CONFIG ==================

BOT_TOKEN = "7644231051:AAFswLeZkQBLIp40e1BdCNuc_XAxK_4owJY"          # <- yahan apna bot token daalo
BOT_USERNAME = "YourBotUsernameHere"       # <- @ ke bina, jaise: PyaasiAngelBot

DATABASE_URL = (
    "mongodb+srv://pefic67072:ONtkKs5MbRzEreuJ@cluster0.8py7f.mongodb.net/"
    "?retryWrites=true&w=majority"
)

# --- Channel verification config ---
PUBLIC_CHANNEL_ID = -1002438744271      # public channel ID ( -100... )
PRIVATE_CHANNEL_ID = -1002337604180     # private channel ID ( -100... )

PUBLIC_CHANNEL_URL = "https://t.me/kajal_developer"
PRIVATE_CHANNEL_URL = "https://t.me/+mfHX3OvPxKk3MWFl"

# --- Random video source channel (sirf ek) ---
SOURCE_VIDEO_CHANNEL_ID = -1003399656498  # jahan se random videos lenge

# Referral milestone rewards
REFERRAL_MILESTONES = {
    5: 50,
    10: 150,
    20: 400,
}

# ============================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ---- MongoDB setup ----
client = MongoClient(DATABASE_URL)
db = client["pyaasi_bot"]
users_col = db["users"]
videos_col = db["videos"]   # channel se aane wale videos yahan save honge


# =============== HELPER FUNCTIONS =================

def get_or_create_user(user_id: int, first_name: str = "", username: str = ""):
    user = users_col.find_one({"user_id": user_id})
    if user:
        return user

    new_user = {
        "user_id": user_id,
        "first_name": first_name,
        "username": username,
        "points": 20,
        "referrals": 0,
        "referred_by": None,
        "created_at": datetime.utcnow(),
    }
    users_col.insert_one(new_user)
    return new_user


def get_user_points(user_id: int) -> int:
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = get_or_create_user(user_id)
    return int(user.get("points", 0))


def add_points(user_id: int, amount: int):
    users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"points": amount}},
        upsert=True,
    )


def get_user_stats(user_id: int):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = get_or_create_user(user_id)

    points = int(user.get("points", 0))
    referrals = int(user.get("referrals", 0))
    return points, referrals


def is_member(chat_id: int, user_id: int) -> bool:
    """Check kare user channel ka member hai ya nahi."""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False


def ensure_joined_channels(message) -> bool:
    """User ne dono channels join kiye hain ya nahi, check karo."""
    user_id = message.from_user.id

    joined_public = is_member(PUBLIC_CHANNEL_ID, user_id)
    joined_private = is_member(PRIVATE_CHANNEL_ID, user_id)

    if joined_public and joined_private:
        return True

    text = (
        "🚨 You must join <b>both</b> channels to access content.\n\n"
        "1️⃣ Join the public updates channel.\n"
        "2️⃣ Join the private content channel.\n\n"
        "Then try again by pressing VIDEO or PHOTO 😊"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔔 Join Public Channel", url=PUBLIC_CHANNEL_URL))
    markup.add(InlineKeyboardButton("🛡 Join Private Channel", url=PRIVATE_CHANNEL_URL))

    bot.send_message(message.chat.id, text, reply_markup=markup)
    return False


def get_random_video_doc():
    """MongoDB se ek random video document lao."""
    try:
        cursor = videos_col.aggregate([{"$sample": {"size": 1}}])
        return next(cursor, None)
    except Exception:
        return None


# =============== REFERRAL SYSTEM =================

def set_referrer(new_user_id: int, ref_user_id: int):
    """Referral system: new user ko referrer set karo (agar pehle se nahi hai)."""
    user = users_col.find_one({"user_id": new_user_id})
    if user and user.get("referred_by"):
        return

    users_col.update_one(
        {"user_id": new_user_id},
        {
            "$set": {"referred_by": ref_user_id},
            "$inc": {"points": 10},   # new user bonus
        },
        upsert=True,
    )

    result = users_col.find_one_and_update(
        {"user_id": ref_user_id},
        {"$inc": {"points": 20, "referrals": 1}},
        return_document=True,
        upsert=True,
    )

    new_referral_count = int(result.get("referrals", 0))

    # milestone check
    if new_referral_count in REFERRAL_MILESTONES:
        bonus = REFERRAL_MILESTONES[new_referral_count]
        add_points(ref_user_id, bonus)

        try:
            bot.send_message(
                ref_user_id,
                (
                    "🎉 <b>Referral Milestone Unlocked!</b>\n\n"
                    f"✅ You reached <b>{new_referral_count}</b> referrals.\n"
                    f"🎁 Bonus rewarded: <b>{bonus} points</b> added.\n\n"
                    "Keep sharing your /refer link to unlock more rewards! 🚀"
                ),
            )
        except Exception:
            pass


# =============== CHANNEL VIDEO LOGGER =================

@bot.channel_post_handler(content_types=["video"])
def save_channel_video(message):
    """Source channel par post hua video MongoDB me save karo."""
    if message.chat.id != SOURCE_VIDEO_CHANNEL_ID:
        return

    videos_col.update_one(
        {
            "chat_id": message.chat.id,
            "message_id": message.message_id,
        },
        {
            "$set": {
                "chat_id": message.chat.id,
                "message_id": message.message_id,
                "date": message.date,
            }
        },
        upsert=True,
    )


# =============== COMMAND HANDLERS =================

@bot.message_handler(commands=["start"])
def send_welcome(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "there"
    username = message.from_user.username or ""

    # deep-link referral: /start ref_123456
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            ref_id = int(parts[1].replace("ref_", ""))
            if ref_id != user_id:
                set_referrer(user_id, ref_id)
        except ValueError:
            pass

    get_or_create_user(user_id, first_name, username)

    text = (
        f"Hey 👋, {first_name}! 🥂\n"
        f"Welcome to Pyaasi Angel Bot 💋🆓\n\n"
        "I'm here to share exclusive private video content from a variety of styles:\n\n"
        "• Fan Content 🎥\n"
        "• Casual Clips 📸\n"
        "• Trending Media 🌐\n"
        "• Vault Finds 🔐\n\n"
        "⚠️ <b>Disclaimer:</b>\n"
        "This service is 18+ only. By using this bot you confirm you're an adult.\n\n"
        "Check /privacy for full policy."
    )

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    row1 = [KeyboardButton("VIDEO 🎬"), KeyboardButton("PHOTO 📸")]
    row2 = [KeyboardButton("POINTS 🏅")]
    row3 = [KeyboardButton("/refer 🔗")]
    row4 = [KeyboardButton("/privacy 🔒"), KeyboardButton("/buy 💰")]

    markup.row(*row1)
    markup.row(*row2)
    markup.row(*row3)
    markup.row(*row4)

    bot.send_message(chat_id, text, reply_markup=markup)


@bot.message_handler(commands=["privacy"])
def send_privacy(message):
    text = (
        "🔒 <b>Privacy Policy & Disclaimer</b>\n\n"
        "📌 We collect only:\n"
        "• Telegram User ID\n"
        "• Username & Name\n"
        "• Points & referral stats\n"
        "• Interaction timestamps\n\n"
        "❌ We NEVER collect:\n"
        "• Private messages\n"
        "• Contacts / Phone number\n"
        "• Location\n\n"
        "⚠️ This bot may share adult-themed content.\n"
        "You must be 18+ to use this bot.\n\n"
        "📬 Owner: @Evil_AngeI\n"
        "🕒 Last updated: June 2025"
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["points"])
def show_points(message):
    user_id = message.from_user.id
    points, referrals = get_user_stats(user_id)

    text = (
        f"⭐ You have <b>{points}</b> points.\n"
        f"🤝 Total referrals: <b>{referrals}</b>\n\n"
        "Earn more through your /refer link 🚀"
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["refer"])
def send_refer(message):
    user_id = message.from_user.id
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

    text = (
        "📢 <b>Invite & Earn Points!</b>\n\n"
        "🔁 Base Reward:\n"
        "• 1 referral = +20 points 🏅\n\n"
        "🎯 Milestones:\n"
        "• 5 referrals = +50 bonus 🎉\n"
        "• 10 referrals = +150 bonus 🏆\n"
        "• 20 referrals = +400 bonus 👑\n\n"
        f"{ref_link}\n\n"
        "🔞 18+ Only"
    )

    markup = InlineKeyboardMarkup()
    share_url = (
        "https://t.me/share/url"
        f"?url={ref_link}"
        "&text=Join%20this%2018%2B%20private%20content%20bot%20and%20earn%20points"
    )
    markup.add(InlineKeyboardButton("🚀 Share Now 🚀", url=share_url))

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=markup,
        disable_web_page_preview=False,
    )


@bot.message_handler(commands=["buy"])
def buy_points(message):
    text = (
        "💰 <b>Purchase Points Now!</b>\n\n"
        "Check prices & contact the owner for instant top-ups 💫"
    )

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("💳 Point Prices", callback_data="prices"),
        InlineKeyboardButton("💬 Contact owner", url="https://t.me/Evil_AngeI"),
    )

    bot.send_message(message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "prices")
def show_prices(call):
    text = (
        "💳 <b>Point Price List</b>\n\n"
        "• 50 points = ₹39\n"
        "• 100 points = ₹69\n"
        "• 250 points = ₹149\n"
        "• 500 points = ₹249\n\n"
        "Payment: UPI / Paytm / GPay\n"
        "Send payment screenshot to the owner."
    )
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, text)


@bot.message_handler(commands=["video"])
def cmd_video(message):
    handle_video(message)


# =============== BUTTON HANDLERS =================

@bot.message_handler(func=lambda m: m.text == "POINTS 🏅")
def handle_points_button(message):
    show_points(message)


@bot.message_handler(func=lambda m: m.text == "/refer 🔗")
def handle_refer_button(message):
    send_refer(message)


@bot.message_handler(func=lambda m: m.text == "/privacy 🔒")
def handle_privacy_button(message):
    send_privacy(message)


@bot.message_handler(func=lambda m: m.text == "/buy 💰")
def handle_buy_button(message):
    buy_points(message)


# =============== CONTENT BUTTONS =================

@bot.message_handler(func=lambda m: m.text == "VIDEO 🎬")
def handle_video(message):
    # 1) channel join verification
    if not ensure_joined_channels(message):
        return

    # 2) random video from source channel
    doc = get_random_video_doc()
    if not doc:
        bot.send_message(
            message.chat.id,
            "😕 No videos available yet.\nPlease try again later.",
        )
        return

    try:
        bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=doc["chat_id"],
            message_id=doc["message_id"],
        )
    except Exception:
        bot.send_message(
            message.chat.id,
            "⚠️ Error sending video. Please try again.",
        )


@bot.message_handler(func=lambda m: m.text == "PHOTO 📸")
def handle_photo(message):
    # abhi sirf verification + placeholder
    if not ensure_joined_channels(message):
        return

    bot.send_message(
        message.chat.id,
        "📸 Access granted!\nPhoto gallery coming soon… 🔐",
    )


# =============== FALLBACK =================

@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.send_message(
        message.chat.id,
        "Use menu buttons or commands like /start /points /refer /buy /privacy 🙂"
    )


# =============== RUN BOT =================

print("Bot running... 🚀")
bot.infinity_polling()
