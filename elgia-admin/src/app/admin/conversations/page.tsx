"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";

// APIベースURL（Flask側）
const API_BASE = "http://localhost:5000/api";

// 会話履歴型
type Conversation = {
    id: string;
    user_id: string;
    user_message: string;
    response: string;
    timestamp: string;
    hit_status: string;
};

// FAQ型
type Faq = { id: number; question: string; answer: string; lang: string };

// 会話履歴一覧とFAQ追加UI
export default function Page() {
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [search, setSearch] = useState("");
    const [selected, setSelected] = useState<Conversation | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    // FAQ追加ダイアログ
    const [faqModal, setFaqModal] = useState<{
        question: string;
        answer: string;
        lang: string;
        open: boolean;
    }>({ question: "", answer: "", lang: "ja", open: false });
    const [faqSaving, setFaqSaving] = useState(false);
    const [faqResult, setFaqResult] = useState("");

    // 会話履歴取得
    const fetchConversations = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await fetch(`${API_BASE}/conversations`);
            if (!res.ok) throw new Error("APIエラー");
            const data = await res.json();
            setConversations(Array.isArray(data) ? data : []);
        } catch {
            setError("会話履歴の取得に失敗しました");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchConversations();
    }, []);

    // FAQ追加API
    const addFaq = async () => {
        setFaqSaving(true);
        setFaqResult("");
        try {
            const res = await fetch(`${API_BASE}/faqs`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    id: 0,
                    question: faqModal.question,
                    answer: faqModal.answer,
                    lang: faqModal.lang,
                }),
            });
            if (!res.ok) throw new Error("APIエラー");
            setFaqResult("FAQを追加しました");
            setFaqModal({ question: "", answer: "", lang: "ja", open: false });
        } catch {
            setFaqResult("FAQ追加に失敗しました");
        } finally {
            setFaqSaving(false);
            // FAQ追加後に一覧をリロードしたい場合はfetchConversations();
        }
    };

    // 検索フィルタ
    const filtered = Array.isArray(conversations)
        ? conversations.filter(
            (c) =>
                (c.user_message ?? "").includes(search) ||
                (c.response ?? "").includes(search) ||
                (c.user_id ?? "").includes(search)
        )
        : [];

    // ヒット状況バッジ
    function StatusBadge({ status }: { status: string }) {
        let color = "bg-gray-200 text-gray-700";
        if (status.includes("未ヒット")) color = "bg-red-100 text-red-600";
        if (status.includes("完全一致")) color = "bg-green-100 text-green-600";
        if (status.includes("部分一致")) color = "bg-yellow-100 text-yellow-600";
        if (status.includes("AI") || status.includes("フォールバック"))
            color = "bg-blue-100 text-blue-600";
        return (
            <span className={`px-2 py-1 rounded text-xs font-bold ${color}`}>
                {status}
            </span>
        );
    }

    return (
        <div className="p-6">
            <h1 className="text-2xl font-bold mb-4">会話履歴管理</h1>
            <div className="flex gap-2 mb-4">
                <Input
                    className="w-64"
                    placeholder="検索（ユーザー・内容・応答）"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
            </div>
            {error && <div className="text-red-600 mb-2">{error}</div>}
            <div className="overflow-x-auto bg-white rounded shadow">
                {loading ? (
                    <div className="p-8 text-center text-gray-400">読込中...</div>
                ) : (
                    <table className="min-w-full">
                        <thead className="bg-gray-100">
                            <tr>
                                <th className="px-4 py-2 text-left">ユーザー</th>
                                <th className="px-4 py-2 text-left">内容</th>
                                <th className="px-4 py-2 text-left">日時</th>
                                <th className="px-4 py-2 text-left">ヒット状況</th>
                                <th className="px-4 py-2 text-center">操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((c) => (
                                <tr key={c.id} className="hover:bg-blue-50 transition">
                                    <td className="px-4 py-2">{c.user_id}</td>
                                    <td className="px-4 py-2">{c.user_message}</td>
                                    <td className="px-4 py-2">{c.timestamp}</td>
                                    <td className="px-4 py-2">
                                        <StatusBadge status={c.hit_status} />
                                    </td>
                                    <td className="px-4 py-2 flex gap-2 justify-center">
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() => setSelected(c)}
                                        >
                                            詳細
                                        </Button>
                                        {/* ▼ 「未ヒット/要対応」のみFAQ追加ボタン */}
                                        {(c.hit_status?.includes("未ヒット") ||
                                            c.hit_status?.includes("要対応")) && (
                                                <Button
                                                    size="sm"
                                                    variant="secondary"
                                                    onClick={() =>
                                                        setFaqModal({
                                                            question: c.user_message,
                                                            answer: "",
                                                            lang: "ja",
                                                            open: true,
                                                        })
                                                    }
                                                >
                                                    FAQ追加
                                                </Button>
                                            )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
                {!loading && filtered.length === 0 && (
                    <div className="text-center text-gray-400 p-8">
                        該当する会話履歴はありません
                    </div>
                )}
            </div>

            {/* 詳細ダイアログ */}
            <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
                <DialogContent>
                    <DialogTitle>会話詳細</DialogTitle>
                    {selected && (
                        <Card className="p-4 flex flex-col gap-2">
                            <div>
                                <b>ユーザー:</b> {selected.user_id}
                            </div>
                            <div>
                                <b>内容:</b> {selected.user_message}
                            </div>
                            <div>
                                <b>応答:</b> {selected.response}
                            </div>
                            <div>
                                <b>日時:</b> {selected.timestamp}
                            </div>
                            <div>
                                <b>ヒット状況:</b>{" "}
                                <StatusBadge status={selected.hit_status} />
                            </div>
                        </Card>
                    )}
                </DialogContent>
            </Dialog>

            {/* FAQ追加ダイアログ */}
            <Dialog
                open={faqModal.open}
                onOpenChange={() =>
                    setFaqModal({ ...faqModal, open: false })
                }
            >
                <DialogContent>
                    <DialogTitle>FAQ新規追加</DialogTitle>
                    <Card className="p-4 flex flex-col gap-4">
                        <Input
                            placeholder="質問"
                            value={faqModal.question}
                            onChange={(e) =>
                                setFaqModal({ ...faqModal, question: e.target.value })
                            }
                        />
                        <Input
                            placeholder="回答"
                            value={faqModal.answer}
                            onChange={(e) =>
                                setFaqModal({ ...faqModal, answer: e.target.value })
                            }
                        />
                        <Input
                            placeholder="言語"
                            value={faqModal.lang}
                            onChange={(e) =>
                                setFaqModal({ ...faqModal, lang: e.target.value })
                            }
                        />
                        {faqResult && (
                            <div className="text-green-600">{faqResult}</div>
                        )}
                        <div className="flex gap-2 justify-end">
                            <Button
                                onClick={addFaq}
                                disabled={
                                    faqSaving ||
                                    !faqModal.question.trim() ||
                                    !faqModal.answer.trim()
                                }
                            >
                                追加
                            </Button>
                            <Button
                                variant="outline"
                                onClick={() => setFaqModal({ ...faqModal, open: false })}
                            >
                                キャンセル
                            </Button>
                        </div>
                    </Card>
                </DialogContent>
            </Dialog>
        </div>
    );
}
