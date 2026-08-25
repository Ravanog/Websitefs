from urllib.parse import quote_plus
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from TechVJ.utils.file_properties import get_hash, get_name
from config import STREAM_MODE, URL, LOG_CHANNEL

ALLOWED_CHANNELS = [-1002578416876]  # Add your channel IDs here

# 1. Define your Vercel frontend URL at the top of your file (replace with your actual Vercel link)
VERCEL_URL = "https://streampage-liard.vercel.app"

# Inside your channel_receive_handler function:
@Client.on_message(filters.channel & (filters.document | filters.video) & ~filters.forwarded, group=-1)
async def channel_receive_handler(bot: Client, broadcast: Message):
    if STREAM_MODE == False:
        return
    
    if broadcast.chat.id not in ALLOWED_CHANNELS:
        return
    
    try:
        file = broadcast.document or broadcast.video
        file_name = file.file_name if file else "Unknown File"
        
        msg = await broadcast.forward(chat_id=LOG_CHANNEL)
        
        # Keep direct links ONLY for the log channel if you want admin backups
        stream = f"{URL}watch/{msg.id}/{quote_plus(get_name(msg))}?hash={get_hash(msg)}"
        download = f"{URL}{msg.id}/{quote_plus(get_name(msg))}?hash={get_hash(msg)}"
        
        # Create a unique token combining the message ID and hash for Vercel
        file_token = f"{msg.id}_{get_hash(msg)}"
        ver_link = f"{VERCEL_URL}{quote_plus(file_token)}"
        
        # Admin log message buttons (keeps direct Koyeb links)
        log_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖥 Wᴀᴛᴄʜ Nᴏᴡ!", url=stream),
             InlineKeyboardButton("📥 Dᴏᴡɴʟᴏᴀᴅ", url=download)],
            [InlineKeyboardButton("❌ REMOVE BUTTONS", callback_data=f"remove_btn_{broadcast.chat.id}_{broadcast.id}")]
        ])
        
        await msg.reply_text(
            text=f"**Channel:** {broadcast.chat.title}\n**File:** `{file_name}`\n**Message ID:** `{broadcast.id}`",
            quote=True,
            reply_markup=log_buttons
        )
        
        # IMPORTANT: Public channel buttons MUST use 'ver_link' (Vercel) instead of 'stream'/'download'
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖥 Wᴀᴛᴄʜ Nᴏᴡ!", url=ver_link),
             InlineKeyboardButton("📥 Dᴏᴡɴʟᴏᴀᴅ", url=ver_link)]
        ])
        
        await bot.edit_message_reply_markup(
            chat_id=broadcast.chat.id,
            message_id=broadcast.id,
            reply_markup=buttons
        )

    except FloodWait as w:
        await asyncio.sleep(w.value)
        await channel_receive_handler(bot, broadcast)
    except Exception as e:
        print(f"Error: {e}")
        
