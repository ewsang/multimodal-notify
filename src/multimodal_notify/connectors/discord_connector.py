import asyncio
import logging
import re
import threading
import time
import discord
from .base_connector import BaseConnector
from multimodal_notify.core.events.message_event import MessageEvent
from multimodal_notify.core.message_filter import evaluate_reaction_emojis, should_send_notification

log = logging.getLogger(__name__)


class DiscordConnector(BaseConnector):
    """Handles connection management, event filtering, and message routing for a background Discord bot."""

    def __init__(self, token: str, channel_id: int, role_map: dict[str, int], profile_config: dict = None):
        """Initializes connector parameters, validates configuration, and starts background thread."""
        self.token = token
        self.channel_id = channel_id
        self.role_map = role_map
        self.profile_config = profile_config or {}

        # Validate message filter configuration
        schema = self.profile_config.get("parser_schema", {})
        matrix = self.profile_config.get("message_filter_rules", {}).get("matrix", {})
        if not schema or not matrix:
            log.warning("Message filter rule configuration missing. All messages will bypass filtering.")

        # Validate message reaction configuration
        try:
            evaluate_reaction_emojis({}, self.profile_config)
        except Exception as e:
            log.warning("Message reaction rule configuration invalid or missing: %s", e)

        self._bot = self._create_bot()
        self._ready = asyncio.Event()
        self._start_background_bot()

    def _create_bot(self) -> discord.Client:
        """Creates the Discord client, configures intents, and registers the on_ready event hook."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        bot = discord.Client(intents=intents)

        @bot.event
        async def on_ready():
            """Triggers when the bot connects, flags readiness, and broadcasts a reconnection message."""
            log.info("Discord bot connected successfully as %s", bot.user)
            self._ready.set()

            try:
                channel = self._get_channel()
                if not channel:
                    log.error("Could not send reconnect message; channel %s not found", self.channel_id)
                    return

                base_text = f":wireless: {bot.user.mention} reconnected to server"
                reconnect_msg = self._apply_timestamp(base_text, time.time())
                await channel.send(reconnect_msg)
            except Exception as e:
                log.error(f"Failed to dispatch reconnection alert: {e}", exc_info=True)

        return bot

    def _start_background_bot(self):
        """Spawns the blocking Discord event loop inside a dedicated background daemon thread."""
        thread = threading.Thread(target=lambda: self._bot.run(self.token), daemon=True)
        thread.start()

    def _get_channel(self) -> discord.abc.GuildChannel | None:
        """Fetches the target Discord channel entity using the configured channel ID."""
        return self._bot.get_channel(self.channel_id)

    def _apply_role_pings(self, text: str, metadata: dict) -> str:
        """Scans text for role map keywords and converts them into functional Discord role mentions."""
        if not self.role_map:
            return text

        formatted_text = text
        for role_keyword_upper, role_id in self.role_map.items():
            discord_mention = f"<@&{role_id}>"
            pattern = re.compile(rf"\b{re.escape(role_keyword_upper)}\b", re.IGNORECASE)
            formatted_text = pattern.sub(discord_mention, formatted_text)

        return formatted_text

    def _apply_timestamp(self, text: str, ts: float | None) -> str:
        """Prepends a formatted relative Discord markdown timestamp to the provided text payload."""
        if not ts:
            return text
        discord_ts = f"<t:{int(ts)}:R>"
        return f"⏱️ {discord_ts}\n{text}"

    def _to_discord_embed(self, event: MessageEvent) -> discord.Embed:
        """Maps an internal generic MessageEvent into a visually formatted discord.Embed object."""
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

    def shutdown(self):
        """Gracefully alerts Discord and closes the bot client connection during a shutdown event."""
        log.info("Initiating Discord connector graceful shutdown...")

        if not self._ready.is_set():
            log.warning("Bot was never fully ready; skipping disconnect broadcast.")
            return

        async def _send_disconnect_and_close():
            try:
                channel = self._get_channel()
                if channel:
                    base_text = f"🛑 {self._bot.user.mention} disconnected from server"
                    disconnect_msg = self._apply_timestamp(base_text, time.time())
                    await channel.send(disconnect_msg)
                else:
                    log.error("Could not send disconnect message; channel not found.")
            except Exception as e:
                log.error(f"Failed to send disconnection message: {e}", exc_info=True)
            finally:
                await self._bot.close()

        future = asyncio.run_coroutine_threadsafe(_send_disconnect_and_close(), self._bot.loop)

        try:
            future.result(timeout=10)
            log.info("Discord background thread cleanup complete.")
        except Exception as e:
            log.error(f"Timed out or failed waiting for Discord shutdown: {e}")

    def handle(self, event: MessageEvent):
        """Processes incoming notification events, filtering out messages that do not meet criteria."""
        if not isinstance(event, MessageEvent):
            return

        # Check general message visibility rules before sending anything
        if not should_send_notification(event.description, self.profile_config):
            log.info("Notification dropped: Event description failed message filter criteria mapping.")
            return

        if event.message_type != "discord_embed":
            content = self._apply_role_pings(event.description, event.metadata)
            content = self._apply_timestamp(content, event.timestamp)

            active_reactions = evaluate_reaction_emojis(event.metadata, self.profile_config)
            self._schedule_async(self._send_async(content, reactions=active_reactions))
        else:
            embed = self._to_discord_embed(event)
            self._schedule_async(self._send_embed_async(embed))

    def _schedule_async(self, coro):
        """Schedules thread-safe execution of an async coroutine onto the active Discord event loop."""
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
        """Asynchronously dispatches raw text payloads to the channel and appends reaction emojis."""
        channel = self._get_channel()
        if not channel:
            log.error("Discord channel %s not found", self.channel_id)
            return

        message = await channel.send(content)
        log.info(f"Successfully sent message {message.id} to channel {self.channel_id}")

        if reactions:
            for emoji in reactions:
                try:
                    await message.add_reaction(emoji)
                except Exception as e:
                    log.error(f"Failed to append emoji reaction {emoji}: {e}")

    async def _send_embed_async(self, embed: discord.Embed):
        """Asynchronously dispatches formatted Embed objects to the target Discord channel."""
        channel = self._get_channel()
        if channel:
            await channel.send(embed=embed)
            log.info(f"Successfully sent embed message to channel {self.channel_id}")
