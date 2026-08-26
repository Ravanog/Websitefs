import sys
import glob
import importlib
from pathlib import Path
from pyrogram import idle, filters  # ← ADDED filters here
from pyrogram.types import Message  # ← ADDED this import
from auth_check import is_user_member, check_auth_channel
from config import AUTH_CHANNEL_MODE, ADMINS, AUTH_CHANNEL, VERIFY_CHANNEL_LINK
import logging
import logging.config


# Get logging configurations
logging.config.fileConfig('logging.conf')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)


from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from config import LOG_CHANNEL, ON_HEROKU, CLONE_MODE, PORT
from typing import Union, Optional, AsyncGenerator
from pyrogram import types
from Script import script 
from datetime import date, datetime 
import pytz
from aiohttp import web
from TechVJ.server import web_server
from auth_check import check_auth_channel
import asyncio
from pyrogram import idle
from plugins.clone import restart_bots
from TechVJ.bot import StreamBot
from TechVJ.utils.keepalive import ping_server
from TechVJ.bot.clients import initialize_clients

ppath = "plugins/*.py"
files = glob.glob(ppath)
StreamBot.start()
loop = asyncio.get_event_loop()

@StreamBot.on_message(filters.private & ~filters.service, group=-1)
async def auth_middleware(client: Client, message: Message):

    if not AUTH_CHANNEL_MODE:
        return

    if message.from_user.id in ADMINS:
        return

    from auth_check import check_auth_channel
    is_verified = await check_auth_channel(client, message)

    if not is_verified:
        message.stop_propagation()
        return
        
    
    is_verified = await check_auth_channel(client, message)
    
    if not is_verified:
        # User not verified - STOP all further processing
        return  # This stops the message from reaching command handlers
    
    # User is verified - continue to command handlers
    await client.continue_propagation()    
    
async def start():
    print('\n')
    print('Initalizing Tech VJ Bot')
    bot_info = await StreamBot.get_me()
    StreamBot.username = bot_info.username
    await initialize_clients()
    for name in files:
        with open(name) as a:
            patt = Path(a.name)
            plugin_name = patt.stem.replace(".py", "")
            plugins_dir = Path(f"plugins/{plugin_name}.py")
            import_path = "plugins.{}".format(plugin_name)
            spec = importlib.util.spec_from_file_location(import_path, plugins_dir)
            load = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(load)
            sys.modules["plugins." + plugin_name] = load
            print("Tech VJ Imported => " + plugin_name)
    if ON_HEROKU:
        asyncio.create_task(ping_server())
    me = await StreamBot.get_me()
    tz = pytz.timezone('Asia/Kolkata')
    today = date.today()
    now = datetime.now(tz)
    time = now.strftime("%H:%M:%S %p")
    app = web.AppRunner(await web_server())
    await StreamBot.send_message(chat_id=LOG_CHANNEL, text=script.RESTART_TXT.format(today, time))
    await app.setup()
    bind_address = "0.0.0.0"
    await web.TCPSite(app, bind_address, PORT).start()
    if CLONE_MODE == True:
        await restart_bots()
    print("Bot Started Powered By @VJ_Bots")
    await idle()


if __name__ == '__main__':
    try:
        loop.run_until_complete(start())
    except KeyboardInterrupt:
        logging.info('Service Stopped Bye 👋')


