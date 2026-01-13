import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
    title: 'Ollama Connector Admin',
    description: 'Admin panel for Ollama Connector LLM Gateway',
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en">
            <body className="min-h-screen bg-[#0a0a0a]">
                <div className="flex min-h-screen">
                    {/* Sidebar */}
                    <aside className="w-64 bg-[#111] border-r border-gray-800 p-4 fixed h-full">
                        <div className="mb-8">
                            <h1 className="text-xl font-bold text-white flex items-center gap-2">
                                <span className="text-2xl">🔌</span>
                                Ollama Connector
                            </h1>
                            <p className="text-xs text-gray-500 mt-1">Admin Panel</p>
                        </div>

                        <nav className="space-y-1">
                            <a
                                href="/"
                                className="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-300 hover:bg-gray-800 hover:text-white transition"
                            >
                                <span>📊</span>
                                Dashboard
                            </a>
                            <a
                                href="/connectors"
                                className="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-300 hover:bg-gray-800 hover:text-white transition"
                            >
                                <span>🔑</span>
                                Connectors
                            </a>
                            <a
                                href="/nodes"
                                className="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-300 hover:bg-gray-800 hover:text-white transition"
                            >
                                <span>🖥️</span>
                                Nodes
                            </a>
                            <a
                                href="/analytics"
                                className="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-300 hover:bg-gray-800 hover:text-white transition"
                            >
                                <span>📈</span>
                                Analytics
                            </a>
                        </nav>

                        <div className="absolute bottom-4 left-4 right-4">
                            <div className="p-3 bg-gray-800/50 rounded-lg text-xs text-gray-400">
                                <p>API: <code className="text-primary-400">:7460</code></p>
                                <p>Admin: <code className="text-primary-400">:7463</code></p>
                            </div>
                        </div>
                    </aside>

                    {/* Main content */}
                    <main className="flex-1 ml-64 p-8">
                        {children}
                    </main>
                </div>
            </body>
        </html>
    );
}
