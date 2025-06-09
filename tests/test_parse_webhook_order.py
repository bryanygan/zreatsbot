import types
import sys
import pathlib
from types import SimpleNamespace

class AttrStub:
    def __getattr__(self, name):
        return AttrStub()
    def __call__(self, *args, **kwargs):
        return AttrStub()

class DummyEmbed:
    def __init__(self, url=""):
        self.url = url
        self.author = SimpleNamespace(url=url)
        self.fields = []
    def add_field(self, name, value, inline=False):
        self.fields.append(SimpleNamespace(name=name, value=value))

discord_stub = AttrStub()
discord_stub.Embed = DummyEmbed
discord_stub.app_commands = AttrStub()
discord_stub.errors = SimpleNamespace(HTTPException=Exception)
discord_stub.ext = SimpleNamespace(commands=SimpleNamespace(Bot=AttrStub()))
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

helpers_path = pathlib.Path(__file__).resolve().parents[1] / "bot" / "utils" / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

parse_webhook_order = helpers.parse_webhook_order
Embed = DummyEmbed


def test_parse_webhook_order_basic():
    embed = Embed(url="https://track.example.com")
    embed.add_field(name="Store", value="Pizza Place")
    embed.add_field(name="Estimated Arrival", value="5 PM")
    embed.add_field(name="Name", value="John Doe")
    embed.add_field(name="Delivery Address", value="123 Street")
    embed.add_field(name="Order Items", value="Pizza")

    result = parse_webhook_order(embed)

    assert result == {
        "store": "Pizza Place",
        "eta": "5 PM",
        "name": "John Doe",
        "address": "123 Street",
        "items": "Pizza",
        "tracking": "https://track.example.com",
    }
