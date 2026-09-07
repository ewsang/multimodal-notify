"""Handles connection management, event filtering, and message routing for a background Discord bot."""

import asyncio
import importlib.metadata
import logging
import re
import threading
import time

import discord

from multimodal_notify.connectors.base_connector import BaseConnector
from multimodal_notify.core.events import MessageEvent

log = logging.getLogger(__name__)


class DiscordConnector(BaseConnector):
    """Manage connection and message routing for a background Discord bot."""

    def __init__(
        self, 
        token: str, 
        channel_id: int, 
        role_map: dict[str, int], 
        profile_config: dict = None
    ):
        """Configure connection parameters, validate rules, and boot client."""
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

    def is_connected(self) -> bool:
        """Check if the underlying Discord gateway connection is live."""
        return self._bot is not None and self._bot.is_ready()

    def handle(self, event: MessageEvent) -> None:
        """Process messages, assign active reactions, and trigger transmission."""
        if not isinstance(event, MessageEvent):
            return
        
        source = event.metadata.get("source", "OCR")

        if source == "OCR":
            active_reactions = self._evaluate_reaction_emojis(
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

    def shutdown(self) -> None:
        """Broadcast disconnection notice and sever network socket client safely."""
        log.info("Initiating graceful shutdown...")
        if not self.is_connected():
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

    def _create_bot(self) -> discord.Client:
        """Configure client event hooks and login callbacks."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        bot = discord.Client(intents=intents)

        @bot.event
        async def on_ready():
            log.info(f"Bot connected successfully as {bot.user}")
            
            channel = self._get_channel()
            if not channel:
                log.error(
                    f"Could not send reconnect message; channel "
                    f"{self.channel_id} not found"
                )
                return
                
            try:
                try:
                    pkg_version = importlib.metadata.version("multimodal-notify")
                except importlib.metadata.PackageNotFoundError:
                    pkg_version = "0.2.0-dev"

                base_text = (
                    f"📡 {bot.user.mention} reconnected to server"
                    f", running `multimodal-notify v{pkg_version}`"
                )
                reconnect_msg = self._apply_timestamp(base_text, time.time())
                await channel.send(reconnect_msg)
            except Exception as e:
                log.error(
                    f"Failed to dispatch reconnection alert: {e}", 
                    exc_info=True
                )
                
        return bot

    def _start_background_bot(self) -> None:
        """Spawn blocking client runner in a dedicated background daemon thread."""
        thread = threading.Thread(
            target=lambda: self._bot.run(self.token),
            name=self.name,
            daemon=True
        )
        thread.start()

    def _get_channel(self) -> discord.abc.GuildChannel | None:
        """Query active session for the target destination channel ID."""
        return self._bot.get_channel(self.channel_id)

    def _schedule_async(self, coro) -> None:
        """Inject async tasks thread-safely onto the active client loop layer."""
        if not self.is_connected():
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
        """Asynchronously submit text contents to channel and attach emojis."""
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
        """Asynchronously dispatch rich graphic embed objects to target channels."""
        channel = self._get_channel()
        if channel:
            await channel.send(embed=embed)
            log.info("Successfully sent rich embed layout message.")

    def _apply_role_pings(self, text: str) -> str:
        """Translate registered raw keywords into Discord role mention tags."""
        formatted_text = text
        for pattern, mention_string in self.compiled_roles:
            formatted_text = pattern.sub(mention_string, formatted_text)
        return formatted_text

    def _apply_timestamp(self, text: str, ts: float) -> str:
        """Generate relative dynamic markdown timestamps for chat headers."""
        return f"⏱️ <t:{int(ts)}:R>\n{text}"

    def _evaluate_reaction_emojis(self, metadata: dict, profile_config: dict) -> list[str]:
        """Evaluate metadata properties against profile criteria to yield matching emojis."""
        rules = profile_config.get("reaction_rules", [])
        if not metadata or not rules:
            return []

        matched_emojis = []
        normalized_meta = {
            str(k).upper().strip(): str(v).upper().strip() 
            for k, v in metadata.items()
        }

        for rule in rules:
            emoji = rule.get("emoji")
            criteria = rule.get("criteria", {})
            if not emoji or not criteria:
                continue

            is_match = True
            for criterion_key, criterion_val in criteria.items():
                meta_key = str(criterion_key).upper().strip()
                expected_val = str(criterion_val).upper().strip()
                if normalized_meta.get(meta_key) != expected_val:
                    is_match = False
                    break

            if is_match:
                matched_emojis.append(emoji)

        return matched_emojis

    def _to_discord_embed(self, event: MessageEvent) -> discord.Embed:
        """Convert abstract MessageEvents into rich graphical layouts."""
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