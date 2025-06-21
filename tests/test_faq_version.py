import pytest
import faq_firestore
from faq_firestore import save_faq_version, get_faq_versions, rollback_faq, COL, VERSION_COL

class FakeDoc:
    def __init__(self, id, data):
        self.id = id
        self._data = data

    def to_dict(self):
        return self._data

    @property
    def exists(self):
        return bool(self._data)

class FakeCollection:
    def __init__(self):
        self.add_calls = []
        self.set_call = None
        self._doc_id = None

    def add(self, data):
        self.add_calls.append(data)

    def where(self, field, op, value):
        return self

    def order_by(self, field, direction):
        return self

    def stream(self):
        return [
            FakeDoc("v1", {"faq_id": "f1", "data": {"question": "Q1"}, "editor": "E1", "timestamp": None}),
            FakeDoc("v2", {"faq_id": "f1", "data": {"question": "Q2"}, "editor": "E2", "timestamp": None}),
        ]

    def document(self, doc_id):
        self._doc_id = doc_id
        return self

    def get(self):
        if self._doc_id == "v1":
            return FakeDoc("v1", {"data": {"question": "ORIG"}})
        return FakeDoc(self._doc_id, {})

    def set(self, data):
        self.set_call = data

class FakeDB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]

@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(faq_firestore, 'db', fake)
    return fake

def test_save_faq_version(fake_db):
    save_faq_version("f1", {"q": "質問"}, "editor@example.com")
    col = fake_db.collections[VERSION_COL]
    assert len(col.add_calls) == 1
    data = col.add_calls[0]
    assert data["faq_id"] == "f1"
    assert data["data"] == {"q": "質問"}
    assert data["editor"] == "editor@example.com"
    assert "timestamp" in data

def test_get_faq_versions(fake_db):
    versions = get_faq_versions("f1")
    assert isinstance(versions, list) and len(versions) == 2
    assert versions[0]["id"] == "v1" and versions[0]["data"]["question"] == "Q1"
    assert versions[1]["id"] == "v2" and versions[1]["data"]["question"] == "Q2"

def test_rollback_faq_success(fake_db):
    rollback_faq("f1", "v1")
    col = fake_db.collections[COL]
    assert col.set_call == {"question": "ORIG"}

def test_rollback_faq_invalid_version(fake_db):
    with pytest.raises(ValueError):
        rollback_faq("f1", "nonexistent_version")
