import os
import logging
import random
import asyncio
import re
import json
import base64
from validators import domain
from urllib.parse import quote_plus
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import *
from Script import script
from plugins.dbusers import db
from plugins.users_api import get_user, update_user_info
from utils import verify_user, check_token, check_verification, get_token
from TechVJ.utils.file_properties import get_name, get_hash, get_media_file_size
from config import *
from auth_check import is_user_member
import config

logger = logging.getLogger(__name__)

BATCH_FILES = {}

def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

def formate_file_name(file_name):
    chars = ["[", "]", "(", ")"]
    for c in chars:
        file_name = file_name.replace(c, "")
    file_name = ' '.join(filter(lambda x: not x.startswith('http') and not x.startswith('@') and not x.startswith('www.'), file_name.split()))
    return file_name

@Client.on_message(filters.command("start") & filters.incoming, group=1)
async def start(client, message):
    username = client.me.username
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(LOG_CHANNEL, script.LOG_TEXT.format(message.from_user.id, message.from_user.mention))
    if len(message.command) != 2:
        buttons = [[
            InlineKeyboardButton('ᴠɪꜱɪᴛ ᴡᴇʙꜱɪᴛᴇ', url='https://hkmoviez.netlify.app'),
            InlineKeyboardButton('ʙᴀᴄᴋᴜᴘ', url='https://t.me/Hari_Moviez')
        ]]
        if CLONE_MODE:
            buttons.append([InlineKeyboardButton('Create Your Own Clone Bot', callback_data='clone')])
        reply_markup = InlineKeyboardMarkup(buttons)
        me = client.me
        await message.reply_text(
            text=script.START_TXT.format(message.from_user.mention, me.mention),
            reply_markup=reply_markup
        )
        return

    data = message.command[1]
    try:
        pre, file_id = data.split('_', 1)
    except:
        file_id = data
        pre = ""
    
    if data.split("-", 1)[0] == "verify":
        userid = data.split("-", 2)[1]
        token = data.split("-", 3)[2]
        if str(message.from_user.id) != str(userid):
            return await message.reply_text(
                text="<b>Invalid link or Expired link !</b>",
                protect_content=True
            )
        is_valid = await check_token(client, userid, token)
        if is_valid:
            await message.reply_text(
                text=f"<b>Hey {message.from_user.mention}, You are successfully verified !\nNow you have unlimited access for all files till today midnight.</b>",
                protect_content=True
            )
            await verify_user(client, userid, token)
        else:
            return await message.reply_text(
                text="<b>Invalid link or Expired link !</b>",
                protect_content=True
            )
    
    elif data.split("-", 1)[0] == "BATCH":
        try:
            if not await check_verification(client, message.from_user.id) and VERIFY_MODE:
                btn = [[
                    InlineKeyboardButton("Verify", url=await get_token(client, message.from_user.id, f"https://telegram.me/{username}?start="))
                ],[
                    InlineKeyboardButton("How To Open Link & Verify", url=VERIFY_TUTORIAL)
                ]]
                await message.reply_text(
                    text="<b>You are not verified !\nKindly verify to continue !</b>",
                    protect_content=True,
                    reply_markup=InlineKeyboardMarkup(btn)
                )
                return
        except Exception as e:
            return await message.reply_text(f"**Error - {e}**")
        
        sts = await message.reply("**Please Wait**")
        file_id = data.split("-", 1)[1]
        msgs = BATCH_FILES.get(file_id)
        if not msgs:
            decode_file_id = base64.urlsafe_b64decode(file_id + "=" * (-len(file_id) % 4)).decode("ascii")
            msg = await client.get_messages(LOG_CHANNEL, int(decode_file_id))
            media = getattr(msg, msg.media.value)
            file_id = media.file_id
            file = await client.download_media(file_id)
            try:
                with open(file) as file_data:
                    msgs = json.loads(file_data.read())
            except:
                await sts.edit("FAILED")
                return await client.send_message(LOG_CHANNEL, "UNABLE TO OPEN FILE.")
            os.remove(file)
            BATCH_FILES[file_id] = msgs
        
        filesarr = []
        for msg_data in msgs:
            channel_id = int(msg_data.get("channel_id"))
            msgid = msg_data.get("msg_id")
            info = await client.get_messages(channel_id, int(msgid))
            if info.media:
                file_type = info.media
                file = getattr(info, file_type.value)
                f_caption = getattr(info, 'caption', '')
                if f_caption:
                    f_caption = f"{f_caption.html}"
                old_title = getattr(file, "file_name", "")
                title = formate_file_name(old_title)
                size = get_size(int(file.file_size))
                if BATCH_FILE_CAPTION:
                    try:
                        f_caption = BATCH_FILE_CAPTION.format(file_name='' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption)
                    except:
                        f_caption = f_caption
                if f_caption is None:
                    f_caption = f"<code>{title}</code>"
                
                reply_markup = None
                if msg_data.get("buttons"):
                    btn_rows = []
                    for row in msg_data.get("buttons"):
                        btn_row = []
                        for btn in row:
                            if btn.get("url"):
                                btn_row.append(InlineKeyboardButton(btn["text"], url=btn["url"]))
                            elif btn.get("callback_data"):
                                btn_row.append(InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"]))
                        if btn_row:
                            btn_rows.append(btn_row)
                    if btn_rows:
                        reply_markup = InlineKeyboardMarkup(btn_rows)
                
                
                try:
                    msg = await info.copy(chat_id=message.from_user.id, caption=f_caption, protect_content=False, reply_markup=reply_markup)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    msg = await info.copy(chat_id=message.from_user.id, caption=f_caption, protect_content=False, reply_markup=reply_markup)
                except:
                    continue
            else:
                try:
                    msg = await info.copy(chat_id=message.from_user.id, protect_content=False)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    msg = await info.copy(chat_id=message.from_user.id, protect_content=False)
                except:
                    continue
            filesarr.append(msg)
            await asyncio.sleep(1)
        await sts.delete()
        if AUTO_DELETE_MODE:
            k = await client.send_message(chat_id=message.from_user.id, text=f"<b><u>⚠️ ᴛʜɪꜱ ᴍᴏᴠɪᴇ ғɪʟᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ {AUTO_DELETE} ᴍɪɴᴜᴛᴇꜱ. ⏳ (ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪɴᴛᴇɢʀᴀᴛɪᴏɴ) 🚫🎬 \n\n 📥 ᴘʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴏʀ ғᴏʀᴡᴀʀᴅ ɪᴛ ᴛᴏ ʏᴏᴜʀ ꜱᴀᴠᴇᴅ ᴍᴇꜱꜱᴀɢᴇꜱ 💬 \n ʙᴇғᴏʀᴇ ɪᴛ ɢᴇᴛꜱ ᴅᴇʟᴇᴛᴇᴅ. 💾</b>")
            await asyncio.sleep(AUTO_DELETE_TIME)
            for x in filesarr:
                try:
                    await x.delete()
                except:
                    pass
            await k.edit_text("<b>ғɪʟᴇꜱ ʜᴀᴠᴇ ʙᴇᴇɴ ᴅᴇʟᴇᴛᴇᴅ 🗑️</b>")
        return

    pre, decode_file_id = ((base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))).decode("ascii")).split("_", 1)
    if not await check_verification(client, message.from_user.id) and VERIFY_MODE:
        btn = [[
            InlineKeyboardButton("Verify", url=await get_token(client, message.from_user.id, f"https://telegram.me/{username}?start="))
        ],[
            InlineKeyboardButton("How To Open Link & Verify", url=VERIFY_TUTORIAL)
        ]]
        await message.reply_text(
            text="<b>You are not verified !\nKindly verify to continue !</b>",
            protect_content=True,
            reply_markup=InlineKeyboardMarkup(btn)
        )
        return
    
    try:
        msg = await client.get_messages(LOG_CHANNEL, int(decode_file_id))
        if msg.media:
            media = getattr(msg, msg.media.value)
            title = formate_file_name(media.file_name)
            size = get_size(media.file_size)
            f_caption = f"<code>{title}</code>"
            if CUSTOM_FILE_CAPTION:
                try:
                    f_caption = CUSTOM_FILE_CAPTION.format(file_name='' if title is None else title, file_size='' if size is None else size, file_caption='')
                except:
                    pass
            
            if STREAM_MODE and (msg.video or msg.document):
                stream = f"{URL}watch/{str(msg.id)}/{quote_plus(get_name(msg))}?hash={get_hash(msg)}"
                download = f"{URL}{str(msg.id)}/{quote_plus(get_name(msg))}?hash={get_hash(msg)}"
                button = [[
                    InlineKeyboardButton("Download", url=download),
                    InlineKeyboardButton('Watch', url=stream)
                ]]
                reply_markup = InlineKeyboardMarkup(button)
            else:
                reply_markup = None
            
            del_msg = await msg.copy(chat_id=message.from_user.id, caption=f_caption, reply_markup=reply_markup, protect_content=False)
        else:
            del_msg = await msg.copy(chat_id=message.from_user.id, protect_content=False)
        
        if AUTO_DELETE_MODE:
            k = await client.send_message(chat_id=message.from_user.id, text=f"<b>⚠️ ᴛʜɪꜱ ᴍᴏᴠɪᴇ ғɪʟᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ {AUTO_DELETE} ᴍɪɴᴜᴛᴇꜱ. ⏳ (ᴅᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ɪɴᴛᴇɢʀᴀᴛɪᴏɴ) 🚫🎬  \n\n 📥 ᴘʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴏʀ ғᴏʀᴡᴀʀᴅ ɪᴛ ᴛᴏ ʏᴏᴜʀ ꜱᴀᴠᴇᴅ ᴍᴇꜱꜱᴀɢᴇꜱ 💬 \n ʙᴇғᴏʀᴇ ɪᴛ ɢᴇᴛꜱ ᴅᴇʟᴇᴛᴇᴅ. 💾</b>")
            await asyncio.sleep(AUTO_DELETE_TIME)
            try:
                await del_msg.delete()
            except:
                pass
            await k.edit_text("<b>ғɪʟᴇꜱ ʜᴀᴠᴇ ʙᴇᴇɴ ᴅᴇʟᴇᴛᴇᴅ 🗑️</b>")
        return
    except:
        pass

@Client.on_message(filters.command('api') & filters.private)
async def shortener_api_handler(client, m: Message):
    user_id = m.from_user.id
    user = await get_user(user_id)
    cmd = m.command
    if len(cmd) == 1:
        s = script.SHORTENER_API_MESSAGE.format(base_site=user["base_site"], shortener_api=user["shortener_api"])
        return await m.reply(s)
    elif len(cmd) == 2:
        api = cmd[1].strip()
        await update_user_info(user_id, {"shortener_api": api})
        await m.reply("<b>Shortener API updated successfully to</b> " + api)

@Client.on_message(filters.command("base_site") & filters.private)
async def base_site_handler(client, m: Message):
    user_id = m.from_user.id
    user = await get_user(user_id)
    cmd = m.command
    text = f"`/base_site (base_site)`\n\n<b>Current base site: None\n\n EX:</b> `/base_site shortnerdomain.com`\n\nIf You Want To Remove Base Site Then Copy This And Send To Bot - `/base_site None`"
    if len(cmd) == 1:
        return await m.reply(text=text, disable_web_page_preview=True)
    elif len(cmd) == 2:
        base_site = cmd[1].strip()
        if base_site == "None":
            await update_user_info(user_id, {"base_site": None})
            return await m.reply("<b>Base Site updated successfully</b>")
        if not domain(base_site):
            return await m.reply(text=text, disable_web_page_preview=True)
        await update_user_info(user_id, {"base_site": base_site})
        await m.reply("<b>Base Site updated successfully</b>")

@Client.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    # ADD THIS BLOCK AT THE VERY TOP ↓
    if query.data.startswith("remove_btn_"):
        data = query.data.split("_")
        chat_id = int(data[2])
        msg_id = int(data[3])
        
        try:
            await client.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=None
            )
            await query.answer("Buttons removed successfully!", show_alert=True)
            await query.message.edit_text(
                text=query.message.text + "\n\n✅ Buttons removed from original message"
            )
        except Exception as e:
            await query.answer(f"Error: {e}", show_alert=True)
        return
    # REST OF YOUR CALLBACKS BELOW...
    if query.data == "check_membership":
        user_id = query.from_user.id
        is_member = await is_user_member(client, user_id)
        if is_member:
            await query.message.edit_text(
                "✅ **Verification Successful!**\n\nYou have joined the channel. You can now use the bot.\n\nSend /start to continue."
            )
            await query.answer("Verified! You can now use the bot.", show_alert=True)
        else:
            auth_channel = config.AUTH_CHANNEL
            if auth_channel.startswith('@'):
                auth_channel = auth_channel[1:]
            channel_link = config.VERIFY_CHANNEL_LINK or f"https://t.me/{auth_channel}"
            await query.answer("❌ You haven't joined the channel yet!\nPlease join first.", show_alert=True)
            await query.message.edit_reply_markup(
                InlineKeyboardMarkup([[
                    InlineKeyboardButton("📢 Join Channel", url=channel_link),
                    InlineKeyboardButton("✅ Verify Membership", callback_data="check_membership")
                ]])
            )
        return
        
    elif query.data == "close_data":
        await query.message.delete()
    
    elif query.data == "about":
        buttons = [[
            InlineKeyboardButton('Home', callback_data='start'),
            InlineKeyboardButton('Close', callback_data='close_data')
        ]]
        await client.edit_message_media(
            query.message.chat.id,
            query.message.id,
            InputMediaPhoto(random.choice(PICS))
        )
        reply_markup = InlineKeyboardMarkup(buttons)
        me2 = (await client.get_me()).mention
        await query.message.edit_text(
            text=script.ABOUT_TXT.format(me2),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
    
    elif query.data == "start":
        buttons = [[
            InlineKeyboardButton('Subscribe My YouTube Channel', url='https://youtube.com/@Tech_VJ')
        ],[
            InlineKeyboardButton('Support Group', url='https://t.me/vj_bot_disscussion'),
            InlineKeyboardButton('Update Channel', url='https://t.me/vj_bots')
        ],[
            InlineKeyboardButton('Help', callback_data='help'),
            InlineKeyboardButton('About', callback_data='about')
        ]]
        if CLONE_MODE:
            buttons.append([InlineKeyboardButton('Create Your Own Clone Bot', callback_data='clone')])
        reply_markup = InlineKeyboardMarkup(buttons)
        await client.edit_message_media(
            query.message.chat.id,
            query.message.id,
            InputMediaPhoto(random.choice(PICS))
        )
        me2 = (await client.get_me()).mention
        await query.message.edit_text(
            text=script.START_TXT.format(query.from_user.mention, me2),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
    
    elif query.data == "clone":
        buttons = [[
            InlineKeyboardButton('Home', callback_data='start'),
            InlineKeyboardButton('Close', callback_data='close_data')
        ]]
        await client.edit_message_media(
            query.message.chat.id,
            query.message.id,
            InputMediaPhoto(random.choice(PICS))
        )
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
            text=script.CLONE_TXT.format(query.from_user.mention),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
    
    elif query.data == "help":
        buttons = [[
            InlineKeyboardButton('Home', callback_data='start'),
            InlineKeyboardButton('Close', callback_data='close_data')
        ]]
        await client.edit_message_media(
            query.message.chat.id,
            query.message.id,
            InputMediaPhoto(random.choice(PICS))
        )
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
            text=script.HELP_TXT,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
