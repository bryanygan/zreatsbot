import types
import sys
import pathlib
from types import SimpleNamespace

class AttrStub:
    def __getattr__(self, name):
        return AttrStub()
    def __call__(self, *args, **kwargs):
        return AttrStub()

class DummyIntents(AttrStub):
    @staticmethod
    def default():
        return DummyIntents()

class DummyBotBase(AttrStub):
    def __init__(self, *args, **kwargs):
        pass

discord_stub = AttrStub()
discord_stub.Intents = DummyIntents
discord_stub.app_commands = AttrStub()
discord_stub.errors = SimpleNamespace(HTTPException=Exception)
discord_stub.ext = SimpleNamespace(commands=SimpleNamespace(Bot=DummyBotBase))
discord_stub.ui = SimpleNamespace(View=object, Button=object, button=lambda *a, **k: (lambda f: f))

dotenv_stub = SimpleNamespace(load_dotenv=lambda: None)

sys.modules.setdefault("discord", discord_stub)
sys.modules.setdefault("discord.app_commands", discord_stub.app_commands)
sys.modules.setdefault("discord.errors", discord_stub.errors)
sys.modules.setdefault("discord.ext", discord_stub.ext)
sys.modules.setdefault("discord.ext.commands", discord_stub.ext.commands)
sys.modules.setdefault("discord.ui", discord_stub.ui)
sys.modules.setdefault("dotenv", dotenv_stub)

import importlib

combinedbot_path = pathlib.Path(__file__).resolve().parents[1] / "combinedbot.py"
spec = importlib.util.spec_from_file_location("combinedbot", combinedbot_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CombinedBot = module.CombinedBot


def test_format_basic():
    bot = CombinedBot()
    assert bot.format_name_csv("john doe") == "John,Doe"


def test_format_with_comma_space():
    bot = CombinedBot()
    assert bot.format_name_csv("john, doe") == "John,Doe"


def test_format_single_word():
    bot = CombinedBot()
    assert bot.format_name_csv("alice") == "Alice,A"


def test_format_empty():
    bot = CombinedBot()
    assert bot.format_name_csv("") == ""
