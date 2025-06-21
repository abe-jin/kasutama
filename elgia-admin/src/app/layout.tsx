// src/app/layout.tsx
import './globals.css';

function NavButton({ icon, label, href }: { icon: string, label: string, href: string }) {
  return (
    <a
      href={href}
      className="flex items-center gap-2 text-gray-800 hover:bg-gray-100 rounded-lg px-3 py-2 transition"
    >
      <span className="text-2xl">{icon}</span>
      <span className="font-semibold">{label}</span>
    </a>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="flex min-h-screen bg-gray-50">
        <aside className="w-64 bg-white shadow-lg flex flex-col gap-4 p-6">
          <div className="font-bold text-xl mb-8">管理画面</div>
          <NavButton icon="💬" label="FAQ管理" href="/admin/faqs" />
          <NavButton icon="📜" label="会話履歴" href="/admin/conversations" />
          <NavButton icon="⚙️" label="設定" href="/admin/settings" />
        </aside>
        <main className="flex-1 p-8">{children}</main>
      </body>
    </html>
  );
}
