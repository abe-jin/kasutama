import sys
import os

# この2行で絶対に親ディレクトリをsys.pathに追加
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app import app
import base64
import pytest

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "password")
basic_auth = base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASS}".encode()).decode()

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def auth_headers():
    return {"Authorization": "Basic " + basic_auth}

def test_faq_crud(client):
    # 追加
    data = {"question": "Q1?", "answer": "A1", "lang": "ja"}
    res = client.post("/api/faq", json=data, headers=auth_headers())
    assert res.status_code == 200
    faq_id = res.get_json().get("id")
    assert faq_id

    # 取得
    res = client.get("/api/faq", headers=auth_headers())
    assert res.status_code == 200
    faqs = res.get_json()
    assert any(f.get("question") == "Q1?" for f in faqs)

    # 更新
    update = {"question": "Q1?", "answer": "A2", "lang": "ja"}
    res = client.put(f"/api/faq/{faq_id}", json=update, headers=auth_headers())
    assert res.status_code == 200

    # 確認
    res = client.get("/api/faq", headers=auth_headers())
    faqs = res.get_json()
    assert any(f.get("answer") == "A2" for f in faqs)

    # 削除
    res = client.delete(f"/api/faq/{faq_id}", headers=auth_headers())
    assert res.status_code == 200

    # 完全削除確認
    res = client.get("/api/faq", headers=auth_headers())
    faqs = res.get_json()
    assert not any(f.get("question") == "Q1?" for f in faqs)

def test_auth_required(client):
    # 未認証だと401
    res = client.get('/api/faq')
    assert res.status_code == 401
