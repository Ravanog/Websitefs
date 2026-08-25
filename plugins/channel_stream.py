from urllib.parse import quote_plus
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from TechVJ.utils.file_properties import get_hash, get_name
from config import STREAM_MODE, URL, LOG_CHANNEL

# Put your private channel ID here (Private channel IDs always start with -100)
ALLOWED_CHANNELS = [-1002578416876]  

# Your Vercel frontend URL
VERCEL_URL = "https://harimoviezstreampage.vercel.app/?token="

@Client.on_message(filters.chat(ALLOWED_CHANNELS) & (filters.document | filters.video) & ~filters.forwarded, group=-1)
async def private_channel_receive_handler(bot: Client, broadcast: Message):
    if STREAM_MODE == False:
        return
    
    try:
        file = broadcast.document or broadcast.video
        file_name = file.file_name if file else "Unknown File"
        
        # For private channels, forwarding to log channel is mandatory to generate valid stream tokens
        msg = await broadcast.forward(chat_id=LOG_CHANNEL)
        
        # Direct Koyeb stream/download links for backup and logs
        stream = f"{URL}watch/{msg.id}/{quote_plus(get_name(msg))}?hash={get_hash(msg)}"
        download = f"{URL}{msg.id}/{quote_plus(get_name(msg))}?hash={get_hash(msg)}"
        
        # Create unique token for your Vercel page
        file_token = f"{msg.id}_{get_hash(msg)}"
        ver_link = f"{VERCEL_URL}{quote_plus(file_token)}"
        
        # Admin log message buttons
        log_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖥 Wᴀᴛᴄʜ Nᴏᴡ!", url=stream),
             InlineKeyboardButton("📥 Dᴏᴡɴʟᴏᴀᴅ", url=download)],
            [InlineKeyboardButton("❌ REMOVE BUTTONS", callback_data=f"remove_btn_{broadcast.chat.id}_{broadcast.id}")]
        ])
        
        await msg.reply_text(
            text=f"**Private Channel:** {broadcast.chat.title}\n**File:** `{file_name}`\n**Message ID:** `{broadcast.id}`",
            quote=True,
            reply_markup=log_buttons
        )
        
        # Buttons attached to the message inside your private channel
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
        await private_channel_receive_handler(bot, broadcast)
    except Exception as e:
        print(f"Private Channel Error: {e}")
