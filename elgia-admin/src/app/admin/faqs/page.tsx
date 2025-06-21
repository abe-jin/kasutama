"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";

const API_BASE = "http://localhost:5000/api"; // FlaskのAPIベースURL

type Faq = { id: number; question: string; answer: string; lang: string };

export default function FaqPage() {
    const [faqs, setFaqs] = useState<Faq[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [editFaq, setEditFaq] = useState<Faq | null>(null);
    const [error, setError] = useState("");

    // FAQ一覧をAPIから取得
    const fetchFaqs = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await fetch(`${API_BASE}/faqs`);
            if (!res.ok) throw new Error("APIエラー");
            const data = await res.json();
            setFaqs(data);
        } catch (e) {
            setError("FAQ一覧の取得に失敗しました");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetch(`${API_BASE}/faqs`)
            .then(res => res.json())
            .then(data => {
            console.log("API data:", data); // ←追加
            setFaqs(data);
            setLoading(false);
            })
            .catch(() => setLoading(false));
        }, []);

    // 新規・編集の保存
    const handleSave = async (faq: Faq) => {
        setError("");
        if (faq.question.trim() === "" || faq.answer.trim() === "") {
            setError("質問と回答は必須です");
            return;
        }
        try {
            if (faq.id === 0) {
                // 新規追加
                const res = await fetch(`${API_BASE}/faqs`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(faq),
                });
                if (!res.ok) throw new Error("APIエラー");
            } else {
                // 編集
                const res = await fetch(`${API_BASE}/faqs/${faq.id}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(faq),
                });
                if (!res.ok) throw new Error("APIエラー");
            }
            await fetchFaqs(); // 更新
            setEditFaq(null);
        } catch (e) {
            setError("保存に失敗しました");
        }
    };

    // 削除
    const handleDelete = async (id: number) => {
        if (!window.confirm("本当に削除しますか？")) return;
        setError("");
        try {
            const res = await fetch(`${API_BASE}/faqs/${id}`, { method: "DELETE" });
            if (!res.ok) throw new Error("APIエラー");
            setFaqs(faqs.filter(f => f.id !== id));
        } catch (e) {
            setError("削除に失敗しました");
        }
    };

    const filteredFaqs = Array.isArray(faqs)
        ? faqs.filter(
            f =>
                (f?.question ?? "").includes(search) ||
                (f?.answer ?? "").includes(search)
            )
        : [];
    return (
        <div>
            <div className="flex justify-between items-center mb-4">
                <h1 className="text-2xl font-bold">FAQ管理</h1>
                <Button onClick={() => setEditFaq({ id: 0, question: "", answer: "", lang: "ja" })}>
                    ＋新規FAQ
                </Button>
            </div>
            <Input
                placeholder="質問や回答で検索"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="mb-4 w-64"
            />
            {error && <div className="text-red-600 mb-2">{error}</div>}
            <div className="overflow-x-auto bg-white rounded shadow">
                {loading ? (
                    <div className="p-8 text-center text-gray-400">読込中...</div>
                ) : (
                    <table className="min-w-full">
                        <thead className="bg-gray-100">
                            <tr>
                                <th className="px-4 py-2 text-left">質問</th>
                                <th className="px-4 py-2 text-left">回答</th>
                                <th className="px-4 py-2 text-left">言語</th>
                                <th className="px-4 py-2 text-center">操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredFaqs.map(faq => (
                                <tr key={faq.id} className="hover:bg-blue-50 transition">
                                    <td className="px-4 py-2">{faq.question}</td>
                                    <td className="px-4 py-2">{faq.answer}</td>
                                    <td className="px-4 py-2">{faq.lang}</td>
                                    <td className="px-4 py-2 flex gap-2 justify-center">
                                        <Button size="sm" variant="outline" onClick={() => setEditFaq(faq)}>
                                            編集
                                        </Button>
                                        <Button size="sm" variant="destructive" onClick={() => handleDelete(faq.id)}>
                                            削除
                                        </Button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
                {!loading && filteredFaqs.length === 0 && (
                    <div className="text-center text-gray-400 p-8">該当するFAQはありません</div>
                )}
            </div>
            {/* 編集/新規FAQモーダル */}
            <Dialog open={!!editFaq} onOpenChange={() => setEditFaq(null)}>
                <DialogContent>
                    <DialogTitle>FAQ {editFaq?.id ? "編集" : "新規作成"}</DialogTitle>
                    {editFaq && (
                        <Card className="p-4 flex flex-col gap-4">
                            <Input
                                placeholder="質問"
                                value={editFaq.question}
                                onChange={e => setEditFaq({ ...editFaq, question: e.target.value })}
                            />
                            <Input
                                placeholder="回答"
                                value={editFaq.answer}
                                onChange={e => setEditFaq({ ...editFaq, answer: e.target.value })}
                            />
                            <Input
                                placeholder="言語"
                                value={editFaq.lang}
                                onChange={e => setEditFaq({ ...editFaq, lang: e.target.value })}
                            />
                            <div className="flex gap-2 justify-end">
                                <Button onClick={() => handleSave(editFaq)}>保存</Button>
                                <Button variant="outline" onClick={() => setEditFaq(null)}>
                                    キャンセル
                                </Button>
                            </div>
                        </Card>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
}
