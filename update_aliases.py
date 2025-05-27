import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("C:\\Users\\KOZUE\\Downloads\\a1\\kasutama-f026a-firebase-adminsdk-fbsvc-58aec87c32.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

doc_ref = db.collection('faq').document('値下がり時期')

doc = doc_ref.get()
if doc.exists:
    data = doc.to_dict()
    aliases = set(data.get('aliases', []))
    new_aliases = {
        "こめの値段いつさがりますか",
        "お米の値段いつ下がる",
        "お米価格はいつ下がる",
        "お米の値段下がり時期",
        "米価格下落時期"
    }
    aliases.update(new_aliases)
    doc_ref.update({"aliases": list(aliases)})
    print("aliasesを更新しました")
else:
    print("値下がり時期のドキュメントが見つかりません")
