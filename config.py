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
