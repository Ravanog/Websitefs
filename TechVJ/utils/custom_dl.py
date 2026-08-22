import math
import asyncio
import logging
from config import LOG_CHANNEL
from typing import Dict, Union
from TechVJ.bot import work_loads
from pyrogram import Client, utils, raw
from .file_properties import get_file_ids
from pyrogram.session import Session, Auth
from pyrogram.errors import AuthBytesInvalid, Timeout as PyroTimeout
from TechVJ.server.exceptions import FIleNotFound
from pyrogram.file_id import FileId, FileType, ThumbnailSource


class ByteStreamer:
    def __init__(self, client: Client):
        """A custom class that holds the cache of a specific client and class functions.
        attributes:
            client: the client that the cache is for.
            cached_file_ids: a dict of cached file IDs.
            cached_file_properties: a dict of cached file properties.
        
        functions:
            generate_file_properties: returns the properties for a media of a specific message contained in Tuple.
            generate_media_session: returns the media session for the DC that contains the media file.
            yield_file: yield a file from telegram servers for streaming.
            
        This is a modified version of the <https://github.com/eyaadh/megadlbot_oss/blob/master/mega/telegram/utils/custom_download.py>
        Thanks to Eyaadh <https://github.com/eyaadh>
        """
        self.clean_timer = 30 * 60
        self.client: Client = client
        self.cached_file_ids: Dict[int, FileId] = {}
        asyncio.create_task(self.clean_cache())

    async def get_file_properties(self, id: int) -> FileId:
        """
        Returns the properties of a media of a specific message in a FIleId class.
        if the properties are cached, then it'll return the cached results.
        or it'll generate the properties from the Message ID and cache them.
        """
        if id not in self.cached_file_ids:
            await self.generate_file_properties(id)
            logging.debug(f"Cached file properties for message with ID {id}")[span_0](start_span)[span_0](end_span)
        return self.cached_file_ids[id][span_1](start_span)[span_1](end_span)
    
    async def generate_file_properties(self, id: int) -> FileId:
        """
        Generates the properties of a media file on a specific message.
        returns ths properties in a FIleId class.
        """
        file_id = await get_file_ids(self.client, LOG_CHANNEL, id)[span_2](start_span)[span_2](end_span)
        logging.debug(f"Generated file ID and Unique ID for message with ID {id}")[span_3](start_span)[span_3](end_span)
        if not file_id:
            logging.debug(f"Message with ID {id} not found")[span_4](start_span)[span_4](end_span)
            raise FIleNotFound[span_5](start_span)[span_5](end_span)
        self.cached_file_ids[id] = file_id[span_6](start_span)[span_6](end_span)
        logging.debug(f"Cached media message with ID {id}")[span_7](start_span)[span_7](end_span)
        return self.cached_file_ids[id][span_8](start_span)[span_8](end_span)

    async def generate_media_session(self, client: Client, file_id: FileId) -> Session:
        """
        Generates the media session for the DC that contains the media file.
        This is required for getting the bytes from Telegram servers.
        """

        media_session = client.media_sessions.get(file_id.dc_id, None)[span_9](start_span)[span_9](end_span)

        if media_session is None:
            if file_id.dc_id != await client.storage.dc_id():[span_10](start_span)[span_10](end_span)
                media_session = Session(
                    client,
                    file_id.dc_id,
                    await Auth(
                        client, file_id.dc_id, await client.storage.test_mode()
                    ).create(),
                    await client.storage.test_mode(),
                    is_media=True,
                )[span_11](start_span)[span_11](end_span)
                await media_session.start()[span_12](start_span)[span_12](end_span)

                for _ in range(6):
                    exported_auth = await client.invoke(
                        raw.functions.auth.ExportAuthorization(dc_id=file_id.dc_id)
                    )[span_13](start_span)[span_13](end_span)

                    try:
                        await media_session.send(
                            raw.functions.auth.ImportAuthorization(
                                id=exported_auth.id, bytes=exported_auth.bytes
                            )
                        )[span_14](start_span)[span_14](end_span)
                        break
                    except AuthBytesInvalid:
                        logging.debug(
                            f"Invalid authorization bytes for DC {file_id.dc_id}"
                        )[span_15](start_span)[span_15](end_span)
                        continue
                else:
                    await media_session.stop()[span_16](start_span)[span_16](end_span)
                    raise AuthBytesInvalid[span_17](start_span)[span_17](end_span)
            else:
                media_session = Session(
                    client,
                    file_id.dc_id,
                    await client.storage.auth_key(),
                    await client.storage.test_mode(),
                    is_media=True,
                )[span_18](start_span)[span_18](end_span)
                await media_session.start()[span_19](start_span)[span_19](end_span)
            logging.debug(f"Created media session for DC {file_id.dc_id}")[span_20](start_span)[span_20](end_span)
            client.media_sessions[file_id.dc_id] = media_session[span_21](start_span)[span_21](end_span)
        else:
            logging.debug(f"Using cached media session for DC {file_id.dc_id}")[span_22](start_span)[span_22](end_span)
        return media_session[span_23](start_span)[span_23](end_span)


    @staticmethod
    async def get_location(file_id: FileId) -> Union[raw.types.InputPhotoFileLocation,
                                                     raw.types.InputDocumentFileLocation,
                                                     raw.types.InputPeerPhotoFileLocation,]:
        """
        Returns the file location for the media file.
        """
        file_type = file_id.file_type[span_24](start_span)[span_24](end_span)

        if file_type == FileType.CHAT_PHOTO:
            if file_id.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=file_id.chat_id, access_hash=file_id.chat_access_hash
                )[span_25](start_span)[span_25](end_span)
            else:
                if file_id.chat_access_hash == 0:
                    peer = raw.types.InputPeerChat(chat_id=-file_id.chat_id)[span_26](start_span)[span_26](end_span)
                else:
                    peer = raw.types.InputPeerChannel(
                        channel_id=utils.get_channel_id(file_id.chat_id),
                        access_hash=file_id.chat_access_hash,
                    )[span_27](start_span)[span_27](end_span)

            location = raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=file_id.volume_id,
                local_id=file_id.local_id,
                big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )[span_28](start_span)[span_28](end_span)
        elif file_type == FileType.PHOTO:
            location = raw.types.InputPhotoFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size,
            )[span_29](start_span)[span_29](end_span)
        else:
            location = raw.types.InputDocumentFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size,
            )[span_30](start_span)[span_30](end_span)
        return location[span_31](start_span)[span_31](end_span)

    async def yield_file(
        self,
        file_id: FileId,
        index: int,
        offset: int,
        first_part_cut: int,
        last_part_cut: int,
        part_count: int,
        chunk_size: int,
    ) -> Union[str, None]:
        """
        Custom generator that yields the bytes of the media file with retry protection.
        Modded from <https://github.com/eyaadh/megadlbot_oss/blob/master/mega/telegram/utils/custom_download.py#L20>
        Thanks to Eyaadh <https://github.com/eyaadh>
        """
        client = self.client
        work_loads[index] += 1[span_32](start_span)[span_32](end_span)
        logging.debug(f"Starting to yielding file with client {index}.")[span_33](start_span)[span_33](end_span)
        media_session = await self.generate_media_session(client, file_id)[span_34](start_span)[span_34](end_span)

        current_part = 1
        location = await self.get_location(file_id)[span_35](start_span)[span_35](end_span)

        max_retries = 3

        try:
            r = None
            for attempt in range(max_retries):
                try:
                    r = await media_session.send(
                        raw.functions.upload.GetFile(
                            location=location, offset=offset, limit=chunk_size
                        ),
                    )
                    break
                except (TimeoutError, PyroTimeout) as e:
                    if attempt == max_retries - 1:
                        raise e
                    logging.warning(f"Telegram timeout on initial chunk fetch. Retrying ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(1.5 * (attempt + 1))

            if isinstance(r, raw.types.upload.File):
                while True:
                    chunk = r.bytes[span_36](start_span)[span_36](end_span)
                    if not chunk:
                        break[span_37](start_span)[span_37](end_span)
                    elif part_count == 1:
                        yield chunk[first_part_cut:last_part_cut][span_38](start_span)[span_38](end_span)
                    elif current_part == 1:
                        yield chunk[first_part_cut:][span_39](start_span)[span_39](end_span)
                    elif current_part == part_count:
                        yield chunk[:last_part_cut][span_40](start_span)[span_40](end_span)
                    else:
                        yield chunk[span_41](start_span)[span_41](end_span)

                    current_part += 1[span_42](start_span)[span_42](end_span)
                    offset += chunk_size[span_43](start_span)[span_43](end_span)

                    if current_part > part_count:
                        break[span_44](start_span)[span_44](end_span)

                    # Loop with retry wrapper for subsequent chunks
                    r = None
                    for attempt in range(max_retries):
                        try:
                            r = await media_session.send(
                                raw.functions.upload.GetFile(
                                    location=location, offset=offset, limit=chunk_size
                                ),
                            )
                            break
                        except (TimeoutError, PyroTimeout) as e:
                            if attempt == max_retries - 1:
                                raise e
                            logging.warning(f"Telegram timeout on part {current_part}. Retrying ({attempt + 1}/{max_retries})...")
                            await asyncio.sleep(1 * (attempt + 1))
                            
                    if not isinstance(r, raw.types.upload.File):
                        break
        except (TimeoutError, PyroTimeout, AttributeError) as err:
            logging.error(f"Stream dropped due to timeout/error: {err}")
        finally:
            logging.debug(f"Finished yielding file with {current_part} parts.")[span_45](start_span)[span_45](end_span)
            work_loads[index] -= 1[span_46](start_span)[span_46](end_span)

    
    async def clean_cache(self) -> None:
        """
        function to clean the cache to reduce memory usage
        """
        while True:
            await asyncio.sleep(self.clean_timer)[span_47](start_span)[span_47](end_span)
            self.cached_file_ids.clear()[span_48](start_span)[span_48](end_span)
            logging.debug("Cleaned the cache")[span_49](start_span)[span_49](end_span)
