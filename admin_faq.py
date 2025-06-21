# admin_faq.py

from flask import (Blueprint, Response, abort, flash, redirect, render_template,
                   request, send_file, url_for)
from flask_login import current_user, login_required
import io
import csv
import json
from functools import wraps

# --- 自作モジュールから関数をインポート ---
from faq_firestore import (db, delete_faq, get_faq_versions, load_faqs,
                             rollback_faq, save_faq)

# --- Blueprintの定義 ---
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# --- 権限チェックのデコレータ ---
def role_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user_role = getattr(current_user, 'role', 'viewer')
            if not current_user.is_authenticated or user_role not in roles:
                abort(403, "この操作を行う権限がありません。")
            return func(*args, **kwargs)
        return wrapper
    return decorator

# --- ビュー関数 ---

@admin_bp.route('/')
@login_required
def top():
    """管理画面トップページ"""
    try:
        faqs = load_faqs()
    except Exception as e:
        flash(f"FAQリストの読み込みに失敗しました: {e}", "danger")
        faqs = []
    return render_template('admin.html', faqs=faqs)


@admin_bp.route('/faq/save', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def faq_save():
    """FAQの保存（新規・更新）"""
    try:
        faq_id = request.form.get('faq_id') or None
        question = request.form.get('question', '').strip()
        answer = request.form.get('answer', '').strip()
        aliases = request.form.get('aliases', '')
        editor_id = getattr(current_user, 'id', 'unknown')
        
        save_faq(question=question, answer=answer, aliases_str=aliases, editor_id=editor_id, faq_id=faq_id)
        flash('FAQを保存しました', 'success')
    except Exception as e:
        flash(f"保存に失敗しました: {e}", 'danger')
    return redirect(url_for('admin.top'))


@admin_bp.route('/faq/delete', methods=['POST'])
@login_required
@role_required('admin')
def faq_delete():
    """FAQの削除"""
    try:
        faq_id = request.form.get('faq_id')
        if not faq_id: raise ValueError("削除対象のIDが指定されていません。")
        delete_faq(faq_id)
        flash('FAQを削除しました', 'info')
    except Exception as e:
        flash(f"削除に失敗しました: {e}", 'danger')
    return redirect(url_for('admin.top'))


@admin_bp.route('/faq/import', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def faq_import():
    """CSV/JSONファイルからFAQを一括インポート"""
    file = request.files.get('faq_file')
    if not file or not file.filename:
        flash('ファイルが選択されていません。', 'warning')
        return redirect(url_for('admin.top'))

    try:
        editor_id = getattr(current_user, 'id', 'unknown')
        filename = file.filename.lower()
        
        if filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode('utf-8'))
            reader = csv.DictReader(stream)
            for row in reader:
                save_faq(
                    question=row.get('question', row.get('質問', '')),
                    answer=row.get('answer', row.get('回答', '')),
                    aliases_str=row.get('aliases', row.get('別名', '')),
                    editor_id=editor_id
                )
            flash(f'CSV「{file.filename}」からFAQをインポートしました', 'success')

        elif filename.endswith('.json'):
            faq_list = json.load(file.stream)
            for faq in faq_list:
                 save_faq(
                    question=faq.get('question', ''),
                    answer=faq.get('answer', ''),
                    aliases_str=",".join(faq.get('aliases', [])),
                    editor_id=editor_id
                )
            flash(f'JSON「{file.filename}」からFAQをインポートしました', 'success')
        else:
            flash('CSV または JSON ファイルを選択してください', 'warning')
            
    except Exception as e:
        flash(f"インポート処理中にエラーが発生しました: {e}", "danger")
        
    return redirect(url_for('admin.top'))


@admin_bp.route('/faq/export')
@login_required
def faq_export():
    """FAQリストをCSV形式でエクスポート"""
    try:
        faqs = load_faqs()
        string_io = io.StringIO()
        writer = csv.writer(string_io)
        writer.writerow(['question', 'answer', 'aliases'])
        for faq in faqs:
            writer.writerow([
                faq.get('question', ''),
                faq.get('answer', ''),
                ','.join(faq.get('aliases', []))
            ])
        
        mem = io.BytesIO()
        mem.write(string_io.getvalue().encode('utf-8'))
        mem.seek(0)
        string_io.close()
        
        return send_file(
            mem,
            as_attachment=True,
            download_name='faq_export.csv',
            mimetype='text/csv'
        )
    except Exception as e:
        flash(f"エクスポート処理中にエラーが発生しました: {e}", 'danger')
        return redirect(url_for('admin.top'))


@admin_bp.route('/faq/versions/<faq_id>')
@login_required
def faq_versions(faq_id):
    """FAQのバージョン履歴ページ"""
    versions = get_faq_versions(faq_id)
    return render_template('faq_versions.html', faq_id=faq_id, versions=versions)


@admin_bp.route('/faq/rollback', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def faq_rollback():
    """FAQのロールバック実行"""
    faq_id = request.form.get('faq_id')
    try:
        version_id = request.form.get('version_id')
        editor_id = getattr(current_user, 'id', 'unknown')
        rollback_faq(faq_id, version_id, editor_id)
        flash('指定のバージョンにロールバックしました', 'success')
    except Exception as e:
        flash(f"ロールバックに失敗しました: {e}", 'danger')
    return redirect(url_for('admin.faq_versions', faq_id=faq_id))


@admin_bp.route('/audit')
@login_required
@role_required('admin')
def audit_log():
    """監査ログページ"""
    try:
        logs_query = (
            db.collection('audit_logs')
              .order_by('timestamp', direction=db.Query.DESCENDING)
              .limit(100)
              .stream()
        )
        logs = [doc.to_dict() for doc in logs_query]
    except Exception as e:
        flash(f"監査ログの読み込みに失敗しました: {e}", 'danger')
        logs = []
    return render_template('audit_log.html', logs=logs)