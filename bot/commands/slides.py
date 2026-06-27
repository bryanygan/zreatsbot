"""/slides command — turn a Spotify/Apple Music queue screenshot into TikTok slides.

This is the Discord side of the ttspotslideshow OCR pipeline ("remote control"
idea): send a screenshot to the bot, it runs OCR + slideshow rendering on the
host PC and replies with the rendered PNG slides.

To stay decoupled from this bot's own modules (notably a same-named ``db``), the
heavy lifting runs in a subprocess against the ttspotslideshow repo via its
``bot_ocr_entry.py``, which prints a single JSON result line.
"""

import asyncio
import json
import os
import subprocess
import tempfile

import discord
from discord import app_commands
from discord.ext import commands

from ..utils.helpers import owner_only
from config import TTSPOT_REPO_PATH, TTSPOT_PYTHON

# Discord allows at most 10 file attachments per message.
_MAX_FILES_PER_MSG = 10
# Generous ceiling: OCR + rendering a full recap can take a while.
_SUBPROCESS_TIMEOUT = 300


def _run_pipeline(image_path: str, min_tracks: int) -> dict:
    """Invoke ttspotslideshow's OCR entry script and return its parsed JSON.

    Runs synchronously (call from an executor). Returns a dict that always has an
    ``ok`` key; on any failure it returns ``{"ok": False, "error": ...}``.
    """
    entry = os.path.join(TTSPOT_REPO_PATH, "bot_ocr_entry.py")
    if not os.path.isfile(entry):
        return {"ok": False, "error": f"OCR entry script not found at {entry}. "
                "Set TTSPOT_REPO_PATH to your ttspotslideshow checkout."}

    try:
        proc = subprocess.run(
            [TTSPOT_PYTHON, entry, image_path, "--min-tracks", str(min_tracks)],
            cwd=TTSPOT_REPO_PATH,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "OCR/render timed out."}
    except FileNotFoundError:
        return {"ok": False, "error": f"Python interpreter '{TTSPOT_PYTHON}' not found. "
                "Set TTSPOT_PYTHON to the ttspotslideshow environment's python."}

    # The entry script prints exactly one JSON line on stdout. Parse the last
    # non-empty line so any stray prints upstream don't break us.
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        err = proc.stderr.strip() or "No output from OCR pipeline."
        return {"ok": False, "error": err[:1500]}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": (proc.stderr.strip() or lines[-1])[:1500]}


def setup(bot: commands.Bot):
    @bot.tree.command(
        name="slides",
        description="Turn a music-app queue screenshot into TikTok slideshow images.",
    )
    @app_commands.describe(
        screenshot="A screenshot of your Spotify/Apple Music queue or playlist.",
        min_tracks="Minimum tracks to require before rendering (default 4).",
    )
    async def slides(
        interaction: discord.Interaction,
        screenshot: discord.Attachment,
        min_tracks: int = 4,
    ):
        if not owner_only(interaction):
            return await interaction.response.send_message(
                "❌ You are not authorized.", ephemeral=True
            )

        if not (screenshot.content_type or "").startswith("image/"):
            return await interaction.response.send_message(
                "❌ Please attach an image file.", ephemeral=True
            )

        await interaction.response.defer(thinking=True)

        tmp_dir = tempfile.mkdtemp(prefix="ttspot_ocr_")
        image_path = os.path.join(tmp_dir, screenshot.filename or "screenshot.png")
        try:
            await screenshot.save(image_path)

            # Run the (blocking) subprocess off the event loop.
            result = await asyncio.get_event_loop().run_in_executor(
                None, _run_pipeline, image_path, min_tracks
            )

            if not result.get("ok"):
                return await interaction.followup.send(
                    f"❌ {result.get('error', 'Slide generation failed.')}"
                )

            slide_paths = result.get("slides", [])
            if not slide_paths:
                return await interaction.followup.send("❌ No slides were produced.")

            caption = result.get("caption", "")
            header = (
                f"✅ Generated **{result.get('slide_count', len(slide_paths))}** "
                f"slide(s) from **{result.get('track_count', '?')}** track(s)."
            )
            if caption:
                header += f"\n\n{caption}"

            # First message carries the header + first batch of files; the rest
            # follow in batches of 10 (Discord's per-message attachment cap).
            first = True
            for i in range(0, len(slide_paths), _MAX_FILES_PER_MSG):
                batch = slide_paths[i:i + _MAX_FILES_PER_MSG]
                files = [discord.File(p) for p in batch if os.path.isfile(p)]
                if not files:
                    continue
                if first:
                    await interaction.followup.send(content=header, files=files)
                    first = False
                else:
                    await interaction.followup.send(files=files)
        except Exception as e:
            await interaction.followup.send(f"❌ Unexpected error: {e}")
        finally:
            # Clean up the downloaded screenshot + temp dir.
            try:
                if os.path.isfile(image_path):
                    os.remove(image_path)
                os.rmdir(tmp_dir)
            except OSError:
                pass
