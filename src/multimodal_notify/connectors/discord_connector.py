"""Handles connection management, event filtering, and message routing for a background Discord bot."""

import asyncio
import logging
import re
import threading
import time

import discord

from multimodal_notify.core.events.message_event import MessageEvent
from multimodal_notify.core.message_filter import evaluate_reaction_emojis
from .base_connector import BaseConnector

log = logging.getLogger(__name__)


class DiscordConnector(BaseConnector):
    """Broadcaster connection node providing message routing to a specified Discord server channel."""

    def __init__(
        self, 
        token: str, 
        channel_id: int, 
        role_map: dict[str, int], 
        profile_config: dict = None
    ):
        """Initializes the connection parameters, validates configurations, and boots the client."""
        super().__init__(connector_name="DiscordConnector")
        self.token = token
        self.channel_id = channel_id
        self.profile_config = profile_config or {}

        strategies = self.profile_config.get("strategies", {})
        self.ocr_cfg = strategies.get("ocr", {}).get("strategy_config", {})
        self.cv_cfg = strategies.get("cv", {}).get("strategy_config", {})

        self.compiled_roles = []
        if role_map:
            for role_keyword, role_id in role_map.items():
                pattern = re.compile(
                    rf"\b{re.escape(role_keyword)}\b", re.IGNORECASE
                )
                self.compiled_roles.append((pattern, f"<@&{role_id}>"))

        self._bot = self._create_bot()
        self._ready = asyncio.Event()
        self._start_background_bot()

    def _create_bot(self) -> discord.Client:
        """Configures individual client hooks and tracks gateway initialization callbacks."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        bot = discord.Client(intents=intents)

        @bot.event
        async def on_ready():
            log.info(f"Bot connected successfully as {bot.user}")
            self._ready.set()
            
            channel = self._get_channel()
            if not channel:
                log.error(
                    f"Could not send reconnect message; channel "
                    f"{self.channel_id} not found"
                )
                return
                
            try:
                base_text = f"📡 {bot.user.mention} reconnected to server"
                reconnect_msg = self._apply_timestamp(base_text, time.time())
                await channel.send(reconnect_msg)
            except Exception as e:
                log.error(
                    f"Failed to dispatch reconnection alert: {e}", 
                    exc_info=True
                )
                
        return bot

    def _start_background_bot(self) -> None:
        """Spawns the blocking client login runner routine inside a dedicated background daemon thread."""
        thread = threading.Thread(
            target=lambda: self._bot.run(self.token),
            name=self.name,
            daemon=True
        )
        thread.start()

    def _get_channel(self) -> discord.abc.GuildChannel | None:
        """Queries the active client session for the matched destination target channel identification."""
        return self._bot.get_channel(self.channel_id)

    def _apply_role_pings(self, text: str) -> str:
        """Parses description targets to translate registered raw keywords into operational mention highlights."""
        formatted_text = text
        for pattern, mention_string in self.compiled_roles:
            formatted_text = pattern.sub(mention_string, formatted_text)
        return formatted_text

    def _apply_timestamp(self, text: str, ts: float) -> str:
        """Generates dynamic markdown timestamps for human-readable relative timing inside chats."""
        return f"⏱️ <t:{int(ts)}:R>\n{text}"

    def _to_discord_embed(self, event: MessageEvent) -> discord.Embed:
        """Converts intermediate abstract MessageEvents into rich graphical layout embed interfaces."""
        description = self._apply_role_pings(event.description)
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
            embed.add_field(
                name=field.name, value=field.value, inline=field.inline
            )
            
        if event.footer:
            embed.set_footer(text=event.footer)
            
        embed.timestamp = discord.utils.utcnow()
        return embed

    def shutdown(self) -> None:
        """Broadcasts disconnection notices and securely severs network client socket sockets on teardown."""
        log.info("Initiating graceful shutdown...")
        if not self._ready.is_set():
            log.warning(
                "Bot was never fully ready; skipping disconnect broadcast."
            )
            return

        async def _send_disconnect_and_close():
            try:
                channel = self._get_channel()
                if channel:
                    base_text = (
                        f"🛑 {self._bot.user.mention} disconnected from server"
                    )
                    disconnect_msg = self._apply_timestamp(
                        base_text, time.time()
                    )
                    await channel.send(disconnect_msg)
                else:
                    log.error(
                        "Could not send disconnect message; channel not found."
                    )
            except Exception as e:
                log.error(
                    f"Failed to send disconnection message: {e}", 
                    exc_info=True
                )
            finally:
                await self._bot.close()

        future = asyncio.run_coroutine_threadsafe(
            _send_disconnect_and_close(), self._bot.loop
        )
        try:
            future.result(timeout=10)
            log.info("Background thread cleanup complete.")
        except Exception as e:
            log.error(f"Timed out or failed waiting for shutdown: {e}")

    def handle(self, event: MessageEvent) -> None:
        """Processes message records, selects filtration engines based on source origin, and handles transmissions."""
        if not isinstance(event, MessageEvent):
            return
        
        source = event.metadata.get("source", "OCR")

        if source == "OCR":
            active_reactions = evaluate_reaction_emojis(
                event.metadata, self.ocr_cfg
            )
        elif source == "CV":
            reaction_rules = event.metadata.get(
                "reaction_rules", self.cv_cfg.get("reaction_rules", [])
            )
            active_reactions = [
                rule["emoji"] for rule in reaction_rules if "emoji" in rule
            ]
        else:
            active_reactions = []

        if event.message_type != "discord_embed":
            content = self._apply_role_pings(event.description)
            content = self._apply_timestamp(content, event.timestamp)
            self._schedule_async(
                self._send_async(content, reactions=active_reactions)
            )
        else:
            embed = self._to_discord_embed(event)
            self._schedule_async(self._send_embed_async(embed))

    def _schedule_async(self, coro) -> None:
        """Thread-safe injection of async task expressions straight onto the active client loop layer."""
        if not self._ready.is_set():
            log.warning("Bot not ready yet; dropping or delaying message task.")
            return

        future = asyncio.run_coroutine_threadsafe(coro, self._bot.loop)

        def check_result(f):
            try:
                f.result()
            except Exception as e:
                log.error(
                    f"Error executing async task: {e}", exc_info=True
                )
                
        future.add_done_callback(check_result)

    async def _send_async(
        self, content: str, reactions: list[str] = None
    ) -> None:
        """Asynchronously submits string contents to chat channels and iterates emoji reaction bindings."""
        channel = self._get_channel()
        if not channel:
            log.error(f"Discord channel {self.channel_id} not found")
            return
            
        message = await channel.send(content)
        log.info(f"Successfully sent message {message.id}")
        
        if reactions:
            for emoji in reactions:
                try:
                    await message.add_reaction(emoji)
                except Exception as e:
                    log.error(f"Failed to append emoji reaction {emoji}: {e}")

    async def _send_embed_async(self, embed: discord.Embed) -> None:
        """Asynchronously dispatches rich graphics embed records to target Discord server channels."""
        channel = self._get_channel()
        if channel:
            await channel.send(embed=embed)
            log.info("Successfully sent rich embed layout message.")
