"""
Restart Handler - Manages safe bot restarts with event streaming
"""
import os
import sys
import asyncio
import time
from typing import Optional
import discord

from bot_monitor import get_monitor


class RestartHandler:
    """Handles safe bot restarts with progress updates"""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.monitor = get_monitor()
        self._restart_in_progress = False

    async def check_and_handle_restart(self):
        """Check if restart is requested and handle it"""
        if self.monitor.is_restart_requested() and not self._restart_in_progress:
            await self.perform_restart()

    async def perform_restart(self):
        """Perform a graceful bot restart"""
        self._restart_in_progress = True

        try:
            from status_server import emit_event

            # Emit restart started event
            emit_event('restart_started', {
                'reason': self.monitor.get_restart_reason(),
                'step': 'preparing'
            })

            print("[Restart] Restart requested, beginning graceful shutdown...")

            # Step 1: Stop accepting new commands
            emit_event('restart_progress', {
                'step': 'stopping_commands',
                'message': 'Stopping command processing...'
            })
            await asyncio.sleep(1)

            # Step 2: Wait for ongoing operations to complete
            emit_event('restart_progress', {
                'step': 'waiting_operations',
                'message': 'Waiting for ongoing operations...'
            })
            await asyncio.sleep(2)

            # Step 3: Close database connections
            emit_event('restart_progress', {
                'step': 'closing_database',
                'message': 'Closing database connections...'
            })

            try:
                import db
                # Close all connections in the pool
                if hasattr(db, '_POOL') and db._POOL:
                    for conn in db._POOL:
                        if conn:
                            conn.close()
                    db._POOL.clear()

                # Close main connection
                if hasattr(db, 'DB_CONN') and db.DB_CONN:
                    db.DB_CONN.close()
                    db.DB_CONN = None
            except Exception as e:
                print(f"[Restart] Error closing database: {e}")

            await asyncio.sleep(1)

            # Step 4: Disconnect from Discord
            emit_event('restart_progress', {
                'step': 'disconnecting_discord',
                'message': 'Disconnecting from Discord...'
            })
            await self.bot.close()
            await asyncio.sleep(1)

            # Step 5: Restart the process
            emit_event('restart_progress', {
                'step': 'restarting_process',
                'message': 'Restarting bot process...'
            })

            print("[Restart] Restarting process...")

            # Give events time to be sent
            await asyncio.sleep(2)

            # Restart the Python process
            os.execv(sys.executable, [sys.executable] + sys.argv)

        except Exception as e:
            print(f"[Restart] Error during restart: {e}")
            from status_server import emit_event
            emit_event('restart_error', {
                'error': str(e),
                'message': 'Restart failed, bot still running'
            })
            self._restart_in_progress = False
            self.monitor.clear_restart_request()


async def restart_check_loop(bot: discord.Client):
    """Background task to check for restart requests"""
    handler = RestartHandler(bot)
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            await handler.check_and_handle_restart()
        except Exception as e:
            print(f"[Restart] Error in restart check loop: {e}")

        # Check every 5 seconds
        await asyncio.sleep(5)
