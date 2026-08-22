import re
import time
import math
import logging
import secrets
import mimetypes
import json
import random
import os
import subprocess
import tempfile
import asyncio
from datetime import datetime
from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine
from TechVJ.bot import multi_clients, work_loads, StreamBot
from TechVJ.server.exceptions import FIleNotFound, InvalidHash
from TechVJ import StartTime, __version__
from ..utils.time_format import get_readable_time
from ..utils.custom_dl import ByteStreamer
from TechVJ.utils.render_template import render_page
from config import MULTI_CLIENT

routes = web.RouteTableDef()

VOTES_FILE = 'votes.json'
REPORTS_FILE = 'reports.json'
AUDIO_CACHE_DIR = 'audio_cache'
AUDIO_CACHE = {}
AUDIO_CACHE_LOCK = asyncio.Lock()

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

if not os.path.exists(VOTES_FILE):
    with open(VOTES_FILE, 'w') as f:
        json.dump({}, f)

if not os.path.exists(REPORTS_FILE):
    with open(REPORTS_FILE, 'w') as f:
        json.dump([], f)

LANG_MAP = {
    'hin': 'Hindi', 'tam': 'Tamil', 'tel': 'Telugu',
    'mal': 'Malayalam', 'kan': 'Kannada', 'eng': 'English',
    'ben': 'Bengali', 'pan': 'Punjabi', 'mar': 'Marathi',
    'jpn': 'Japanese', 'kor': 'Korean', 'zho': 'Chinese',
    'rus': 'Russian', 'fra': 'French', 'spa': 'Spanish',
    'deu': 'German', 'ita': 'Italian', 'por': 'Portuguese',
    'ara': 'Arabic', 'tur': 'Turkish', 'und': 'Unknown'
}

class_cache = {}

@routes.get("/favicon.ico")
async def favicon_handler(_):
    raise web.HTTPNotFound()

@routes.get("/", allow_head=True)
async def root_route_handler(_):
    return web.json_response(
        {
            "server_status": "running",
            "uptime": get_readable_time(time.time() - StartTime),
            "telegram_bot": "@" + StreamBot.username,
            "connected_bots": len(multi_clients),
            "loads": dict(
                ("bot" + str(c + 1), l)
                for c, (_, l) in enumerate(
                    sorted(work_loads.items(), key=lambda x: x[1], reverse=True)
                )
            ),
            "version": __version__,
        }
    )

@routes.get(r"/watch/{path:\S+}", allow_head=True)
async def watch_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")
        return web.Response(text=await render_page(id, secure_hash), content_type='text/html')
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))

@routes.get(r"/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")
        return await media_streamer(request, id, secure_hash)
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))

async def media_streamer(request: web.Request, id: int, secure_hash: str):
    range_header = request.headers.get("Range", 0)
    
    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]
    
    if MULTI_CLIENT:
        logging.info(f"Client {index} is now serving {request.remote}")

    if faster_client in class_cache:
        tg_connect = class_cache[faster_client]
        logging.debug(f"Using cached ByteStreamer object for client {index}")
    else:
        logging.debug(f"Creating new ByteStreamer object for client {index}")
        tg_connect = ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect

    file_id = await tg_connect.get_file_properties(id)
    
    if file_id.unique_id[:6] != secure_hash:
        raise InvalidHash
    
    file_size = file_id.file_size

    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = request.http_range.start or 0
        until_bytes = (request.http_range.stop or file_size) - 1

    if (until_bytes > file_size) or (from_bytes < 0) or (until_bytes < from_bytes):
        return web.Response(
            status=416,
            body="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_size = 1024 * 1024
    until_bytes = min(until_bytes, file_size - 1)

    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = until_bytes % chunk_size + 1

    req_length = until_bytes - from_bytes + 1
    part_count = math.ceil(until_bytes / chunk_size) - math.floor(offset / chunk_size)
    body = tg_connect.yield_file(
        file_id, index, offset, first_part_cut, last_part_cut, part_count, chunk_size
    )

    mime_type = file_id.mime_type
    file_name = file_id.file_name
    disposition = "attachment"

    if mime_type:
        if not file_name:
            try:
                file_name = f"{secrets.token_hex(2)}.{mime_type.split('/')[1]}"
            except (IndexError, AttributeError):
                file_name = f"{secrets.token_hex(2)}.unknown"
    else:
        if file_name:
            mime_type = mimetypes.guess_type(file_id.file_name)
        else:
            mime_type = "application/octet-stream"
            file_name = f"{secrets.token_hex(2)}.unknown"

    return web.Response(
        status=206 if range_header else 200,
        body=body,
        headers={
            "Content-Type": f"{mime_type}",
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(req_length),
            "Content-Disposition": f'{disposition}; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        },
    )

@routes.get("/api/tracks/{file_id}", allow_head=True)
async def get_audio_tracks(request: web.Request):
    file_id = request.match_info["file_id"]
    
    try:
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", file_id)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)", file_id).group(1))
            secure_hash = request.rel_url.query.get("hash")
        
        index = min(work_loads, key=work_loads.get)
        faster_client = multi_clients[index]
        tg_connect = ByteStreamer(faster_client)
        file_props = await tg_connect.get_file_properties(id)
        
        cache_key = f"tracks_{file_id}"
        if cache_key in AUDIO_CACHE:
            return web.json_response(AUDIO_CACHE[cache_key])
        
        file_size = file_props.file_size
        sample_size = min(5 * 1024 * 1024, file_size)
        
        chunk_size = 1024 * 1024
        offset = 0
        first_part_cut = 0
        last_part_cut = sample_size
        
        sample_data = b''
        async for chunk in tg_connect.yield_file(
            file_props, index, offset, first_part_cut, last_part_cut, 
            math.ceil(sample_size / chunk_size), chunk_size
        ):
            sample_data += chunk
            if len(sample_data) >= sample_size:
                break
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
            tmp.write(sample_data)
            tmp_path = tmp.name
        
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_streams', '-select_streams', 'a', tmp_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            os.unlink(tmp_path)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                streams = data.get('streams', [])
                
                tracks = []
                for i, stream in enumerate(streams):
                    tags = stream.get('tags', {})
                    language = tags.get('language', 'und')
                    title = tags.get('title', f'Track {i+1}')
                    
                    display_lang = LANG_MAP.get(language.lower(), language)
                    
                    tracks.append({
                        'index': i,
                        'codec_name': stream.get('codec_name', 'aac'),
                        'tags': {
                            'language': display_lang,
                            'title': title,
                            'codec': stream.get('codec_name', 'aac')
                        }
                    })
                
                async with AUDIO_CACHE_LOCK:
                    AUDIO_CACHE[cache_key] = tracks
                
                return web.json_response(tracks)
            else:
                return web.json_response([])
                
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logging.error(f"FFprobe error: {e}")
            os.unlink(tmp_path)
            return web.json_response([])
            
    except Exception as e:
        logging.error(f"Audio tracks error: {e}")
        return web.json_response([])

@routes.get("/audio/{stream_index}/{file_id}", allow_head=True)
async def audio_stream_handler(request: web.Request):
    stream_index = int(request.match_info["stream_index"])
    file_id = request.match_info["file_id"]
    
    try:
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", file_id)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)", file_id).group(1))
            secure_hash = request.rel_url.query.get("hash")
        
        index = min(work_loads, key=work_loads.get)
        faster_client = multi_clients[index]
        tg_connect = ByteStreamer(faster_client)
        file_props = await tg_connect.get_file_properties(id)
        
        cache_key = f"audio_{stream_index}_{file_id}"
        cache_file = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.mp3")
        
        if not os.path.exists(cache_file):
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            temp_path = temp_file.name
            temp_file.close()
            
            try:
                file_size = file_props.file_size
                chunk_size = 1024 * 1024
                offset = 0
                
                with open(temp_path, 'wb') as f:
                    while offset < file_size:
                        remaining = file_size - offset
                        current_chunk = min(chunk_size, remaining)
                        part_count = math.ceil(current_chunk / chunk_size)
                        
                        async for chunk in tg_connect.yield_file(
                            file_props, index, offset, 0, current_chunk, part_count, chunk_size
                        ):
                            f.write(chunk)
                            offset += len(chunk)
                            if offset >= file_size:
                                break
                
                extract_cmd = [
                    'ffmpeg', '-i', temp_path,
                    '-map', f'0:a:{stream_index}',
                    '-c:a', 'libmp3lame',
                    '-b:a', '128k',
                    '-vn',
                    '-y', cache_file
                ]
                
                result = subprocess.run(extract_cmd, capture_output=True, timeout=300)
                
                if result.returncode != 0:
                    logging.error(f"FFmpeg error: {result.stderr.decode()}")
                    return web.Response(status=500, text="Audio extraction failed")
                
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                
            except Exception as e:
                logging.error(f"Audio extraction error: {e}")
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                return web.Response(status=500, text=str(e))
        
        if os.path.exists(cache_file):
            audio_size = os.path.getsize(cache_file)
            
            range_header = request.headers.get("Range", 0)
            
            if range_header:
                from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
                from_bytes = int(from_bytes)
                until_bytes = int(until_bytes) if until_bytes else audio_size - 1
            else:
                from_bytes = 0
                until_bytes = audio_size - 1
            
            if from_bytes < 0 or until_bytes >= audio_size or from_bytes > until_bytes:
                from_bytes = 0
                until_bytes = audio_size - 1
            
            async def file_generator():
                with open(cache_file, 'rb') as f:
                    f.seek(from_bytes)
                    remaining = until_bytes - from_bytes + 1
                    while remaining > 0:
                        chunk = f.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            
            return web.Response(
                status=206 if range_header else 200,
                body=file_generator(),
                headers={
                    "Content-Type": "audio/mpeg",
                    "Content-Range": f"bytes {from_bytes}-{until_bytes}/{audio_size}",
                    "Content-Length": str(until_bytes - from_bytes + 1),
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=31536000"
                }
            )
        else:
            return web.Response(status=404, text="Audio track not found")
        
    except Exception as e:
        logging.error(f"Audio stream error: {e}")
        return web.Response(status=500, text=str(e))

@routes.get("/votes/{file_name}", allow_head=True)
async def get_votes(request):
    file_name = request.match_info["file_name"]
    try:
        with open(VOTES_FILE, 'r') as f:
            data = json.load(f)
    except:
        data = {}
    
    if file_name not in data:
        data[file_name] = {
            'likes': random.randint(400, 500),
            'dislikes': random.randint(5, 50),
            'users': {}
        }
        with open(VOTES_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    return web.json_response({
        'likes': data[file_name]['likes'],
        'dislikes': data[file_name]['dislikes'],
        'user_vote': None
    })

@routes.post("/vote")
async def vote(request):
    data = await request.json()
    file_name = data['file_name']
    vote_type = data['vote']
    user_ip = request.remote
    
    try:
        with open(VOTES_FILE, 'r') as f:
            votes = json.load(f)
    except:
        votes = {}
    
    if file_name not in votes:
        votes[file_name] = {
            'likes': random.randint(400, 500),
            'dislikes': random.randint(5, 50),
            'users': {}
        }
    
    if user_ip in votes[file_name]['users']:
        existing = votes[file_name]['users'][user_ip]
        if existing == vote_type:
            if vote_type == 'like':
                votes[file_name]['likes'] -= 1
            else:
                votes[file_name]['dislikes'] -= 1
            del votes[file_name]['users'][user_ip]
            user_vote = None
        else:
            if existing == 'like':
                votes[file_name]['likes'] -= 1
                votes[file_name]['dislikes'] += 1
            else:
                votes[file_name]['dislikes'] -= 1
                votes[file_name]['likes'] += 1
            votes[file_name]['users'][user_ip] = vote_type
            user_vote = vote_type
    else:
        if vote_type == 'like':
            votes[file_name]['likes'] += 1
        else:
            votes[file_name]['dislikes'] += 1
        votes[file_name]['users'][user_ip] = vote_type
        user_vote = vote_type
    
    with open(VOTES_FILE, 'w') as f:
        json.dump(votes, f, indent=2)
    
    return web.json_response({
        'likes': votes[file_name]['likes'],
        'dislikes': votes[file_name]['dislikes'],
        'user_vote': user_Here is the fully rewritten and cleaned-up version of your `aiohttp` route file for the Telegram streaming bot, optimized for readability, organization, and error-handling.

```python
import re
import time
import math
import logging
import secrets
import mimetypes
import json
import random
import os
import subprocess
import tempfile
import asyncio
from datetime import datetime
from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine
from TechVJ.bot import multi_clients, work_loads, StreamBot
from TechVJ.server.exceptions import FIleNotFound, InvalidHash
from TechVJ import StartTime, __version__
from ..utils.time_format import get_readable_time
from ..utils.custom_dl import ByteStreamer
from TechVJ.utils.render_template import render_page
from config import MULTI_CLIENT

# Initialize Route Table
routes = web.RouteTableDef()

# File paths and caching configurations
VOTES_FILE = 'votes.json'
REPORTS_FILE = 'reports.json'
AUDIO_CACHE_DIR = 'audio_cache'
AUDIO_CACHE = {}
AUDIO_CACHE_LOCK = asyncio.Lock()

# Ensure necessary directories and storage files exist
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

if not os.path.exists(VOTES_FILE):
    with open(VOTES_FILE, 'w') as f:
        json.dump({}, f)

if not os.path.exists(REPORTS_FILE):
    with open(REPORTS_FILE, 'w') as f:
        json.dump([], f)

# Language code mapping dictionary
LANG_MAP = {
    'hin': 'Hindi', 'tam': 'Tamil', 'tel': 'Telugu',
    'mal': 'Malayalam', 'kan': 'Kannada', 'eng': 'English',
    'ben': 'Bengali', 'pan': 'Punjabi', 'mar': 'Marathi',
    'jpn': 'Japanese', 'kor': 'Korean', 'zho': 'Chinese',
    'rus': 'Russian', 'fra': 'French', 'spa': 'Spanish',
    'deu': 'German', 'ita': 'Italian', 'por': 'Portuguese',
    'ara': 'Arabic', 'tur': 'Turkish', 'und': 'Unknown'
}

class_cache = {}


def parse_file_path(path: str, query_hash: str = None):
    """Helper utility to extract secure hash and file ID from request path."""
    match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
    if match:
        return match.group(1), int(match.group(2))
    
    file_id_match = re.search(r"(\d+)(?:\/\S+)?", path)
    if not file_id_match:
        file_id_match = re.search(r"(\d+)", path)
    
    file_id = int(file_id_match.group(1)) if file_id_match else 0
    return query_hash, file_id


@routes.get("/", allow_head=True)
async def root_route_handler(_):
    """Server status endpoint[span_1](start_span)[span_1](end_span)."""
    return web.json_response({
        "server_status": "running",
        "uptime": get_readable_time(time.time() - StartTime),
        "telegram_bot": "@" + StreamBot.username,
        "connected_bots": len(multi_clients),
        "loads": dict(
            ("bot" + str(c + 1), l)
            for c, (_, l) in enumerate(
                sorted(work_loads.items(), key=lambda x: x[1], reverse=True)
            )
        ),
        "version": __version__,
    })


@routes.get(r"/watch/{path:\S+}", allow_head=True)
async def watch_handler(request: web.Request):
    """Renders the HTML streaming watch page[span_2](start_span)[span_2](end_span)."""
    try:
        path = request.match_info["path"]
        secure_hash, file_id = parse_file_path(path, request.rel_url.query.get("hash"))
        return web.Response(text=await render_page(file_id, secure_hash), content_type='text/html')
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))


@routes.get(r"/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    """Main media stream router[span_3](start_span)[span_3](end_span)."""
    try:
        path = request.match_info["path"]
        secure_hash, file_id = parse_file_path(path, request.rel_url.query.get("hash"))
        return await media_streamer(request, file_id, secure_hash)
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))


async def media_streamer(request: web.Request, id: int, secure_hash: str):
    """Handles partial content video/file byte streaming[span_4](start_span)[span_4](end_span)."""
    range_header = request.headers.get("Range", 0)
    
    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]
    
    if MULTI_CLIENT:
        logging.info(f"Client {index} is now serving {request.remote}")

    if faster_client in class_cache:
        tg_connect = class_cache[faster_client]
        logging.debug(f"Using cached ByteStreamer object for client {index}")
    else:
        logging.debug(f"Creating new ByteStreamer object for client {index}")
        tg_connect = ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect

    file_id = await tg_connect.get_file_properties(id)
    
    if file_id.unique_id[:6] != secure_hash:
        raise InvalidHash
    
    file_size = file_id.file_size

    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = request.http_range.start or 0
        until_bytes = (request.http_range.stop or file_size) - 1

    if (until_bytes > file_size) or (from_bytes < 0) or (until_bytes < from_bytes):
        return web.Response(
            status=416,
            body="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_size = 1024 * 1024
    until_bytes = min(until_bytes, file_size - 1)

    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = until_bytes % chunk_size + 1

    req_length = until_bytes - from_bytes + 1
    part_count = math.ceil(until_bytes / chunk_size) - math.floor(offset / chunk_size)
    body = tg_connect.yield_file(
        file_id, index, offset, first_part_cut, last_part_cut, part_count, chunk_size
    )

    mime_type = file_id.mime_type
    file_name = file_id.file_name
    disposition = "attachment"

    if mime_type:
        if not file_name:
            try:
                file_name = f"{secrets.token_hex(2)}.{mime_type.split('/')[1]}"
            except (IndexError, AttributeError):
                file_name = f"{secrets.token_hex(2)}.unknown"
    else:
        if file_name:
            mime_type = mimetypes.guess_type(file_id.file_name)[0] or "application/octet-stream"
        else:
            mime_type = "application/octet-stream"
            file_name = f"{secrets.token_hex(2)}.unknown"

    return web.Response(
        status=206 if range_header else 200,
        body=body,
        headers={
            "Content-Type": f"{mime_type}",
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(req_length),
            "Content-Disposition": f'{disposition}; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        },
    )


@routes.get("/api/tracks/{file_id}", allow_head=True)
async def get_audio_tracks(request: web.Request):
    """Analyzes media file tracks using ffprobe[span_5](start_span)[span_5](end_span)."""
    raw_file_id = request.match_info["file_id"]
    
    try:
        secure_hash, id = parse_file_path(raw_file_id, request.rel_url.query.get("hash"))
        
        index = min(work_loads, key=work_loads.get)
        faster_client = multi_clients[index]
        tg_connect = ByteStreamer(faster_client)
        file_props = await tg_connect.get_file_properties(id)
        
        cache_key = f"tracks_{raw_file_id}"
        if cache_key in AUDIO_CACHE:
            return web.json_response(AUDIO_CACHE[cache_key])
        
        file_size = file_props.file_size
        sample_size = min(5 * 1024 * 1024, file_size)
        
        chunk_size = 1024 * 1024
        sample_data = b''
        async for chunk in tg_connect.yield_file(
            file_props, index, 0, 0, sample_size, 
            math.ceil(sample_size / chunk_size), chunk_size
        ):
            sample_data += chunk
            if len(sample_data) >= sample_size:
                break
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
            tmp.write(sample_data)
            tmp_path = tmp.name
        
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_streams', '-select_streams', 'a', tmp_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            os.unlink(tmp_path)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                streams = data.get('streams', [])
                
                tracks = []
                for i, stream in enumerate(streams):
                    tags = stream.get('tags', {})
                    language = tags.get('language', 'und')
                    title = tags.get('title', f'Track {i+1}')
                    display_lang = LANG_MAP.get(language.lower(), language)
                    
                    tracks.append({
                        'index': i,
                        'codec_name': stream.get('codec_name', 'aac'),
                        'tags': {
                            'language': display_lang,
                            'title': title,
                            'codec': stream.get('codec_name', 'aac')
                        }
                    })
                
                async with AUDIO_CACHE_LOCK:
                    AUDIO_CACHE[cache_key] = tracks
                
                return web.json_response(tracks)
            else:
                return web.json_response([])
                
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logging.error(f"FFprobe error: {e}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return web.json_response([])
            
    except Exception as e:
        logging.error(f"Audio tracks error: {e}")
        return web.json_response([])


@routes.get("/audio/{stream_index}/{file_id}", allow_head=True)
async def audio_stream_handler(request: web.Request):
    """Extracts and streams individual audio tracks via ffmpeg[span_6](start_span)[span_6](end_span)."""
    stream_index = int(request.match_info["stream_index"])
    raw_file_id = request.match_info["file_id"]
    
    try:
        secure_hash, id = parse_file_path(raw_file_id, request.rel_url.query.get("hash"))
        
        index = min(work_loads, key=work_loads.get)
        faster_client = multi_clients[index]
        tg_connect = ByteStreamer(faster_client)
        file_props = await tg_connect.get_file_properties(id)
        
        cache_key = f"audio_{stream_index}_{raw_file_id}"
        cache_file = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.mp3")
        temp_path = None
        
        if not os.path.exists(cache_file):
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            temp_path = temp_file.name
            temp_file.close()
            
            try:
                file_size = file_props.file_size
                chunk_size = 1024 * 1024
                offset = 0
                
                with open(temp_path, 'wb') as f:
                    while offset < file_size:
                        remaining = file_size - offset
                        current_chunk = min(chunk_size, remaining)
                        part_count = math.ceil(current_chunk / chunk_size)
                        
                        async for chunk in tg_connect.yield_file(
                            file_props, index, offset, 0, current_chunk, part_count, chunk_size
                        ):
                            f.write(chunk)
                            offset += len(chunk)
                            if offset >= file_size:
                                break
                
                extract_cmd = [
                    'ffmpeg', '-i', temp_path,
                    '-map', f'0:a:{stream_index}',
                    '-c:a', 'libmp3lame',
                    '-b:a', '128k',
                    '-vn', '-y', cache_file
                ]
                
                result = subprocess.run(extract_cmd, capture_output=True, timeout=300)
                
                if result.returncode != 0:
                    logging.error(f"FFmpeg error: {result.stderr.decode()}")
                    return web.Response(status=500, text="Audio extraction failed")
                
            except Exception as e:
                logging.error(f"Audio extraction error: {e}")
                return web.Response(status=500, text=str(e))
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        if os.path.exists(cache_file):
            audio_size = os.path.getsize(cache_file)
            range_header = request.headers.get("Range", 0)
            
            if range_header:
                from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
                from_bytes = int(from_bytes)
                until_bytes = int(until_bytes) if until_bytes else audio_size - 1
            else:
                from_bytes = 0
                until_bytes = audio_size - 1
            
            if from_bytes < 0 or until_bytes >= audio_size or from_bytes > until_bytes:
                from_bytes = 0
                until_bytes = audio_size - 1
            
            async def file_generator():
                with open(cache_file, 'rb') as f:
                    f.seek(from_bytes)
                    remaining = until_bytes - from_bytes + 1
                    while remaining > 0:
                        chunk = f.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            
            return web.Response(
                status=206 if range_header else 200,
                body=file_generator(),
                headers={
                    "Content-Type": "audio/mpeg",
                    "Content-Range": f"bytes {from_bytes}-{until_bytes}/{audio_size}",
                    "Content-Length": str(until_bytes - from_bytes + 1),
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=31536000"
                }
            )
        else:
            return web.Response(status=404, text="Audio track not found")
        
    except Exception as e:
        logging.error(f"Audio stream error: {e}")
        return web.Response(status=500, text=str(e))


@routes.get("/votes/{file_name}", allow_head=True)
async def get_votes(request: web.Request):
    """Retrieves like/dislike counts for a file[span_7](start_span)[span_7](end_span)."""
    file_name = request.match_info["file_name"]
    try:
        with open(VOTES_FILE, 'r') as f:
            data = json.load(f)
    except Exception:
        data = {}
    
    if file_name not in data:
        data[file_name] = {
            'likes': random.randint(400, 500),
            'dislikes': random.randint(5, 50),
            'users': {}
        }
        with open(VOTES_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    return web.json_response({
        'likes': data[file_name]['likes'],
        'dislikes': data[file_name]['dislikes'],
        'user_vote': None
    })


@routes.post("/vote")
async def vote(request: web.Request):
    """Handles updating like/dislike votes per user IP[span_8](start_span)[span_8](end_span)."""
    data = await request.json()
    file_name = data['file_name']
    vote_type = data['vote']
    user_ip = request.remote
    
    try:
        with open(VOTES_FILE, 'r') as f:
            votes = json.load(f)
    except Exception:
        votes = {}
    
    if file_name not in votes:
        votes[file_name] = {
            'likes': random.randint(400, 500),
            'dislikes': random.randint(5, 50),
            'users': {}
        }
    
    if user_ip in votes[file_name]['users']:
        existing = votes[file_name]['users'][user_ip]
        if existing == vote_type:
            if vote_type == 'like':
                votes[file_name]['likes'] -= 1
            else:
                votes[file_name]['dislikes'] -= 1
            del votes[file_name]['users'][user_ip]
            user_vote = None
        else:
            if existing == 'like':
                votes[file_name]['likes'] -= 1
                votes[file_name]['dislikes'] += 1
            else:
                votes[file_name]['dislikes'] -= 1
                votes[file_name]['likes'] += 1
            votes[file_name]['users'][user_ip] = vote_type
            user_vote = vote_type
    else:
        if vote_type == 'like':
            votes[file_name]['likes'] += 1
        else:
            votes[file_name]['dislikes'] += 1
        votes[file_name]['users'][user_ip] = vote_type
        user_vote = vote_type
    
    with open(VOTES_FILE, 'w') as f:
        json.dump(votes, f, indent=2)
    
    return web.json_response({
        'likes': votes[file_name]['likes'],
        'dislikes': votes[file_name]['dislikes'],
        'user_vote': user_vote
    })


@routes.post("/report")
async def report(request: web.Request):
    """Logs media report submissions to storage[span_9](start_span)[span_9](end_span)."""
    data = await request.json()
    try:
        with open(REPORTS_FILE, 'r') as f:
            reports = json.load(f)
    except Exception:
        reports = []
    
    reports.append({
        **data,
        'timestamp': str(datetime.now())
    })
    
    with open(REPORTS_FILE, 'w') as f:
        json.dump(reports, f, indent=2)
    
    return web.json_response({'success': True})
