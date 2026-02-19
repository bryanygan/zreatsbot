import types
import sys
import pathlib
from types import SimpleNamespace


# ---- Stub out discord / dotenv so the bot modules can be imported ----

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
discord_stub.ui = SimpleNamespace(
    View=object, Button=object,
    Modal=object, TextInput=object,
    button=lambda *a, **k: (lambda f: f),
)

dotenv_stub = SimpleNamespace(load_dotenv=lambda: None)

sys.modules.setdefault("discord", discord_stub)
sys.modules.setdefault("discord.app_commands", discord_stub.app_commands)
sys.modules.setdefault("discord.errors", discord_stub.errors)
sys.modules.setdefault("discord.ext", discord_stub.ext)
sys.modules.setdefault("discord.ext.commands", discord_stub.ext.commands)
sys.modules.setdefault("discord.ui", discord_stub.ui)
sys.modules.setdefault("dotenv", dotenv_stub)

# ---- Import the module under test ----

import importlib

parser_path = pathlib.Path(__file__).resolve().parents[1] / "bot" / "utils" / "address_parser.py"
spec = importlib.util.spec_from_file_location("address_parser", parser_path)
address_parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(address_parser)

parse_address = address_parser.parse_address
format_address_csv = address_parser.format_address_csv


# ---- Tests: parse_address ----

def test_standard_multiline():
    result = parse_address("Elijah Martir\n1863 Corner Meadow Circle\nOrlando, FL 32820")
    assert result["name"] == "Elijah Martir"
    assert result["street"] == "1863 Corner Meadow Circle"
    assert result["street2"] == ""
    assert result["city"] == "Orlando"
    assert result["state"] == "FL"
    assert result["zip"] == "32820"


def test_comma_separated():
    result = parse_address("Joey Cusic\n334 American Avenue, Lexington, KY, 40503")
    assert result["name"] == "Joey Cusic"
    assert result["street"] == "334 American Avenue"
    assert result["street2"] == ""
    assert result["city"] == "Lexington"
    assert result["state"] == "KY"
    assert result["zip"] == "40503"


def test_with_apartment():
    result = parse_address("Rowan Klein\n728 E 18th Aly\napt 1\nEugene, OR, 97401")
    assert result["name"] == "Rowan Klein"
    assert result["street"] == "728 E 18th Aly"
    assert result["street2"] == "Apt 1"
    assert result["city"] == "Eugene"
    assert result["state"] == "OR"
    assert result["zip"] == "97401"


def test_lowercase_name():
    result = parse_address("marcelo torres\n13804 Trull Way\nHudson, Fl, 34669")
    assert result["name"] == "Marcelo Torres"
    assert result["street"] == "13804 Trull Way"
    assert result["city"] == "Hudson"
    assert result["state"] == "FL"
    assert result["zip"] == "34669"


def test_single_line_full_state():
    result = parse_address("2211 7th street south Moorhead Minnesota 56560")
    assert result["name"] == ""
    assert result["street"] == "2211 7th Street South"
    assert result["city"] == "Moorhead"
    assert result["state"] == "MN"
    assert result["zip"] == "56560"


def test_with_united_states():
    result = parse_address("Pavel Hernandez\n17 Pecan blvd\nPittsburg, TX  75686\nUnited States")
    assert result["name"] == "Pavel Hernandez"
    assert result["street"] == "17 Pecan Blvd"
    assert result["street2"] == ""
    assert result["city"] == "Pittsburg"
    assert result["state"] == "TX"
    assert result["zip"] == "75686"


def test_inline_city_state_zip():
    result = parse_address("Carlos Alas\n83 Jefferson St Inwood, NY 11096")
    assert result["name"] == "Carlos Alas"
    assert result["street"] == "83 Jefferson St"
    assert result["street2"] == ""
    assert result["city"] == "Inwood"
    assert result["state"] == "NY"
    assert result["zip"] == "11096"


# ---- Tests: format_address_csv ----

def test_format_address_csv():
    parsed = {
        "name": "John Doe",
        "street": "123 Main St",
        "street2": "Apt 2B",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
    }
    result = format_address_csv(parsed)
    assert result == "John Doe,123 Main St,Apt 2B,New York,NY,10001"


def test_format_address_csv_with_comma_in_field():
    parsed = {
        "name": "John Doe, Jr",
        "street": "123 Main St",
        "street2": "",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
    }
    result = format_address_csv(parsed)
    assert result == '"John Doe, Jr",123 Main St,,New York,NY,10001'
