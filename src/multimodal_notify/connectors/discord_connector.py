import asyncio
import discord
import logging
import re
import time
import threading
from .base_connector import BaseConnector
from multimodal_notify.core.events.message_event import MessageEvent
from multimodal_notify.core.message_filter import evaluate_reaction_emojis

log = logging.getLogger(__name__)


class DiscordConnector(BaseConnector):

    def __init__(self, token: str, channel_id: int, role_map: dict[str, int], profile_config: dict = None):
        self.token = token
        self.channel_id = channel_id
        self.role_map = role_map
        self.profile_config = profile_config or {}

        try:
            log.info("Initializing filtering schema configurations...")
            evaluate_reaction_emojis({}, self.profile_config)
        except Exception as e:
            log.debug("Schema warm-up complete or safely skipped: %s", e)

        self._bot = self._create_bot()
        self._ready = asyncio.Event()
        self._start_background_bot()

    def _create_bot(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        bot = discord.Client(intents=intents)

        @bot.event
        async def on_ready():
            log.info("Discord bot connected as %s", bot.user)
            self._ready.set()

            try:
                channel = self._get_channel()
                if not channel:
                    log.error("Could not send reconnect message; channel %s not found", self.channel_id)
                    return

                base_text = f":wireless: {bot.user.mention} reconnected to server"
                reconnect_msg = self._apply_timestamp(base_text, time.time())

                log.debug("📡 Posting automatic system reconnection message...")
                await channel.send(reconnect_msg)
                log.info("✅ Reconnection message dispatched successfully.")
            except Exception as e:
                log.error(f"💥 Failed to dispatch reconnection alert: {e}", exc_info=True)

        return bot

    def _start_background_bot(self):
        thread = threading.Thread(target=lambda: self._bot.run(self.token), daemon=True)
        thread.start()

    def _get_channel(self):
        return self._bot.get_channel(self.channel_id)

    def _apply_role_pings(self, text: str, metadata: dict) -> str:
        if not self.role_map:
            return text

        formatted_text = text
        for role_keyword_upper, role_id in self.role_map.items():
            discord_mention = f"<@&{role_id}>"
            pattern = re.compile(rf"\b{re.escape(role_keyword_upper)}\b", re.IGNORECASE)
            formatted_text = pattern.sub(discord_mention, formatted_text)

        return formatted_text

    def _apply_timestamp(self, text, ts):
        if not ts:
            return text
        discord_ts = f"<t:{int(ts)}:R>"
        return f"⏱️ {discord_ts}\n{text}"

    def _to_discord_embed(self, event: MessageEvent) -> discord.Embed:
        description = self._apply_role_pings(event.description, event.metadata)
        embed = discord.Embed(
            description=description,
            color=event.color or 0x3498db,
        )
        if event.title:
            embed.title = event.title
        if event.title_url:
            embed.url = event.title_url
        if event.author:
            embed.set_author(
                name=event.author,
                url=event.author_url or discord.Embed.Empty,
                icon_url=event.author_icon_url or discord.Embed.Empty,
            )
        if event.thumbnail_url:
            embed.set_thumbnail(url=event.thumbnail_url)
        for field in event.fields:
            embed.add_field(name=field.name, value=field.value, inline=field.inline)
        if event.footer:
            embed.set_footer(text=event.footer)
        if event.timestamp:
            embed.timestamp = discord.utils.utcnow()
        return embed

    def handle(self, event):
        if not isinstance(event, MessageEvent):
            return

        if event.message_type != "discord_embed":
            log.debug(f"🚨 RAW EVENT METADATA IS: {event.metadata}")
            content = self._apply_role_pings(event.description, event.metadata)
            content = self._apply_timestamp(content, event.timestamp)

            active_reactions = evaluate_reaction_emojis(event.metadata, self.profile_config)
            self._schedule_async(self._send_async(content, reactions=active_reactions))
        else:
            embed = self._to_discord_embed(event)
            self._schedule_async(self._send_embed_async(embed))

    def _schedule_async(self, coro):
        if not self._ready.is_set():
            log.warning("Discord bot not ready yet; dropping or delayed message task.")

        future = asyncio.run_coroutine_threadsafe(coro, self._bot.loop)

        def check_result(f):
            try:
                f.result()
            except Exception as e:
                log.error(f"Error executing async discord task: {e}", exc_info=True)

        future.add_done_callback(check_result)

    async def _send_async(self, content: str, reactions: list[str] = None):
        channel = self._get_channel()
        if not channel:
            log.error("Discord channel %s not found", self.channel_id)
            return

        log.debug("📡 Sending raw content to target Discord channel...")
        message = await channel.send(content)
        log.debug(f"✉️ Message posted successfully. ID: {message.id}. Reactions: {reactions}")

        if reactions:
            for emoji in reactions:
                try:
                    log.debug(f"Attempting to add reaction: {emoji}")
                    await message.add_reaction(emoji)
                    log.info(f"✅ Successfully attached reaction {emoji} to message.")
                except Exception as e:
                    log.error(f"💥 Failed to append emoji reaction {emoji}: {e}")

    async def _send_embed_async(self, embed: discord.Embed):
        channel = self._get_channel()
        if channel:
            await channel.send(embed=embed)
