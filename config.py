"""Configuration constants for the bot"""

import os

# Payment card constants (defaults; overridden by DB via load_from_db())
EXP_MONTH = '04'
EXP_YEAR = '31'
ZIP_CODE = '19104'


def load_from_db():
    """Load mutable config values from the database, falling back to the defaults above."""
    global EXP_MONTH, EXP_YEAR
    import db
    EXP_MONTH = db.get_config_setting('EXP_MONTH', EXP_MONTH)
    EXP_YEAR = db.get_config_setting('EXP_YEAR', EXP_YEAR)


# --- TTSpotSlideShow OCR bridge (for the /slides command) ------------------
# Path to the ttspotslideshow repo and the Python interpreter that has its
# dependencies installed. The /slides command shells out to that repo's
# bot_ocr_entry.py so the two projects stay decoupled (they both define a `db`
# module, which would clash if imported into the same process).
TTSPOT_REPO_PATH = os.getenv(
    'TTSPOT_REPO_PATH',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ttspotslideshow'),
)
TTSPOT_PYTHON = os.getenv('TTSPOT_PYTHON', 'python')
