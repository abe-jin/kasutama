import sys
import os

# この2行で絶対に親ディレクトリをsys.pathに追加
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app import app
import pytest

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "pass1234")

@pytest.fixture
def unauth_client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        resp = client.post(
            "/login",
            data={"username": ADMIN_USER, "password": ADMIN_PASS},
            follow_redirects=True
        )
        assert resp.status_code in (200, 302)
        yield client

def test_faq_crud_and_lang_filter(client):
    # --- 1. 2言語FAQ登録 ---
    data_ja = {"question": "Q日本語?", "answer": "A日本語", "lang": "ja", "aliases": []}
    data_en = {"question": "QEnglish?", "answer": "AEnglish", "lang": "en", "aliases": []}

    res_ja = client.post("/api/faq", json=data_ja)
    res_en = client.post("/api/faq", json=data_en)
    assert res_ja.status_code == 200
    assert res_en.status_code == 200

    id_ja = res_ja.get_json().get("id")
    id_en = res_en.get_json().get("id")
    assert id_ja and id_en

    # --- 2. 多言語フィルタ取得 ---
    res = client.get("/api/faq?lang=ja")
    faqs_ja = res.get_json()
    assert all(f["lang"] == "ja" for f in faqs_ja)
    assert any(f["question"] == "Q日本語?" for f in faqs_ja)

    res = client.get("/api/faq?lang=en")
    faqs_en = res.get_json()
    assert all(f["lang"] == "en" for f in faqs_en)
    assert any(f["question"] == "QEnglish?" for f in faqs_en)

    # --- 3. CRUD（更新：日本語FAQのみ） ---
    update = {"question": "Q日本語?", "answer": "A日本語 改", "lang": "ja", "aliases": []}
    res = client.put(f"/api/faq/{id_ja}", json=update)
    assert res.status_code == 200

    # --- 4. 更新内容反映確認 ---
    res = client.get("/api/faq?lang=ja")
    faqs_ja = res.get_json()
    assert any(f["answer"] == "A日本語 改" for f in faqs_ja)

    # --- 5. 削除（両言語） ---
    res = client.delete(f"/api/faq/{id_ja}")
    assert res.status_code == 200
    res = client.delete(f"/api/faq/{id_en}")
    assert res.status_code == 200

    # --- 6. 完全削除確認 ---
    res = client.get("/api/faq?lang=ja")
    assert not any(f.get("id") == id_ja for f in res.get_json())
    res = client.get("/api/faq?lang=en")
    assert not any(f.get("id") == id_en for f in res.get_json())

def test_auth_required(unauth_client):
    # 未認証だと401
    res = unauth_client.get('/api/faq')
    assert res.status_code == 401
