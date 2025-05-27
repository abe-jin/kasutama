from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from faq_firestore import load_faqs, save_faq, delete_faq, import_faq_list, export_faq_list
import io
import csv
import json

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin', methods=['GET'])
def admin_top():
    faqs = load_faqs()
    return render_template('admin.html', faqs=faqs, messages=[])

@admin_bp.route('/admin/faq_save', methods=['POST'])
def admin_faq_save():
    faq_id = request.form.get("faq_id")
    question = request.form.get("question", "").strip()
    answer = request.form.get("answer", "").strip()
    aliases = request.form.get("aliases", "")
    if not question or not answer:
        flash("質問・回答は必須です。")
        return redirect(url_for('admin.admin_top'))
    save_faq(faq_id, question, answer, aliases)
    return redirect(url_for('admin.admin_top'))

@admin_bp.route('/admin/faq_delete', methods=['POST'])
def admin_faq_delete():
    faq_id = request.form.get("faq_id")
    delete_faq(faq_id)
    return redirect(url_for('admin.admin_top'))

@admin_bp.route('/admin/faq_import', methods=['POST'])
def admin_faq_import():
    file = request.files.get("faq_file")
    if file and file.filename.endswith('.csv'):
        stream = io.StringIO(file.stream.read().decode("utf-8"))
        reader = csv.DictReader(stream)
        faq_list = []
        for row in reader:
            faq_list.append({
                "question": row["質問"],
                "answer": row["回答"],
                "aliases": [a.strip() for a in row["別名"].split(",") if a.strip()]
            })
        import_faq_list(faq_list)
    elif file and file.filename.endswith('.json'):
        faq_list = json.load(file.stream)
        import_faq_list(faq_list)
    return redirect(url_for('admin.admin_top'))

@admin_bp.route('/admin/faq_export')
def admin_faq_export():
    faqs = export_faq_list()
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(["質問", "回答", "別名"])
    for faq in faqs:
        writer.writerow([
            faq.get("question", ""),
            faq.get("answer", ""),
            ",".join(faq.get("aliases", []))
        ])
    output = io.BytesIO()
    output.write(si.getvalue().encode("utf-8"))
    output.seek(0)
    return send_file(output, mimetype="text/csv", as_attachment=True, download_name="faq_export.csv")
