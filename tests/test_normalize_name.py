import sys
import types
import pathlib

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

# Prepare stub modules to satisfy imports
discord_stub = AttrStub()
discord_stub.Intents = DummyIntents
discord_stub.app_commands = AttrStub()
discord_stub.errors = types.SimpleNamespace(HTTPException=Exception)
discord_stub.ext = types.SimpleNamespace(commands=types.SimpleNamespace(Bot=DummyBotBase))

dotenv_stub = types.SimpleNamespace(load_dotenv=lambda: None)

sys.modules.setdefault("discord", discord_stub)
sys.modules.setdefault("discord.app_commands", discord_stub.app_commands)
sys.modules.setdefault("discord.errors", discord_stub.errors)
sys.modules.setdefault("discord.ext", discord_stub.ext)
sys.modules.setdefault("discord.ext.commands", discord_stub.ext.commands)
sys.modules.setdefault("dotenv", dotenv_stub)

# Load CombinedBot class without executing the whole script
source_lines = []
combinedbot_path = pathlib.Path(__file__).resolve().parents[1] / "combinedbot.py"
with open(combinedbot_path, "r") as f:
    for line in f:
        if line.startswith("bot = CombinedBot()"):
            break
        source_lines.append(line)
module = types.ModuleType("combinedbot_partial")
module.__file__ = str(combinedbot_path)
exec("".join(source_lines), module.__dict__)
CombinedBot = module.CombinedBot


def test_normalize_two_words():
    bot = CombinedBot()
    assert bot.normalize_name("john doe") == "John Doe"


def test_normalize_single_word():
    bot = CombinedBot()
    assert bot.normalize_name("alice") == "Alice A"


def test_normalize_empty():
    bot = CombinedBot()
    assert bot.normalize_name("") == ""


def test_normalize_multi_word():
    bot = CombinedBot()
    assert bot.normalize_name("charlie brown jr") == "Charlie Brown"
