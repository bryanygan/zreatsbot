import importlib.util
import sqlite3
import pathlib

db_path = pathlib.Path(__file__).resolve().parents[1] / "db.py"
spec = importlib.util.spec_from_file_location("db", db_path)
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)


def test_connection_pool_acquire_release():
    conn1 = db.acquire_connection()
    conn2 = db.acquire_connection()
    assert isinstance(conn1, sqlite3.Connection)
    assert isinstance(conn2, sqlite3.Connection)
    assert conn1 is not conn2
    db.release_connection(conn1)
    db.release_connection(conn2)


def test_get_connection_singleton():
    conn1 = db.get_connection()
    conn2 = db.get_connection()
    assert conn1 is conn2
    assert isinstance(conn1, sqlite3.Connection)

