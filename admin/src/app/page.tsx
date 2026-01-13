'use client';

import { useEffect, useState } from 'react';
import { api, type Connector, type Node } from '@/lib/api';

export default function Dashboard() {
    const [connectors, setConnectors] = useState<Connector[]>([]);
    const [nodes, setNodes] = useState<Node[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [adminKey, setAdminKey] = useState('');
    const [isAuthenticated, setIsAuthenticated] = useState(false);

    const fetchData = async () => {
        if (!adminKey) return;

        try {
            setLoading(true);
            const [connectorsRes, nodesRes] = await Promise.all([
                api.listConnectors(adminKey),
                api.listNodes(adminKey),
            ]);
            setConnectors(connectorsRes.items);
            setNodes(nodesRes);
            setIsAuthenticated(true);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to fetch data');
            setIsAuthenticated(false);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        // Try to load admin key from localStorage
        const savedKey = localStorage.getItem('adminKey');
        if (savedKey) {
            setAdminKey(savedKey);
        }
    }, []);

    useEffect(() => {
        if (adminKey) {
            localStorage.setItem('adminKey', adminKey);
            fetchData();
        }
    }, [adminKey]);

    if (!isAuthenticated) {
        return (
            <div className="max-w-md mx-auto mt-20">
                <div className="bg-[#111] border border-gray-800 rounded-xl p-6">
                    <h2 className="text-xl font-bold mb-4">🔐 Admin Login</h2>
                    <p className="text-gray-400 text-sm mb-4">
                        Enter your admin API key to access the dashboard.
                    </p>
                    <input
                        type="password"
                        value={adminKey}
                        onChange={(e) => setAdminKey(e.target.value)}
                        placeholder="Enter Admin API Key"
                        className="w-full px-4 py-2 bg-[#0a0a0a] border border-gray-700 rounded-lg text-white focus:border-primary-500 focus:outline-none"
                    />
                    {error && (
                        <p className="mt-2 text-red-400 text-sm">{error}</p>
                    )}
                    <button
                        onClick={fetchData}
                        className="mt-4 w-full px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition"
                    >
                        Login
                    </button>
                </div>
            </div>
        );
    }

    const activeConnectors = connectors.filter(c => c.is_active).length;
    const onlineNodes = nodes.filter(n => n.status === 'online').length;
    const totalModels = [...new Set(nodes.flatMap(n => n.models))].length;

    return (
        <div>
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-2xl font-bold">Dashboard</h1>
                    <p className="text-gray-400">Overview of your LLM Gateway</p>
                </div>
                <button
                    onClick={fetchData}
                    className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition"
                >
                    🔄 Refresh
                </button>
            </div>

            {loading ? (
                <div className="text-center py-20 text-gray-400">Loading...</div>
            ) : (
                <>
                    {/* Stats Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                        <div className="bg-[#111] border border-gray-800 rounded-xl p-6">
                            <div className="text-3xl mb-2">🔑</div>
                            <div className="text-3xl font-bold">{activeConnectors}</div>
                            <div className="text-gray-400 text-sm">Active Connectors</div>
                        </div>
                        <div className="bg-[#111] border border-gray-800 rounded-xl p-6">
                            <div className="text-3xl mb-2">🖥️</div>
                            <div className="text-3xl font-bold text-green-400">{onlineNodes}</div>
                            <div className="text-gray-400 text-sm">Online Nodes</div>
                        </div>
                        <div className="bg-[#111] border border-gray-800 rounded-xl p-6">
                            <div className="text-3xl mb-2">🤖</div>
                            <div className="text-3xl font-bold">{totalModels}</div>
                            <div className="text-gray-400 text-sm">Available Models</div>
                        </div>
                        <div className="bg-[#111] border border-gray-800 rounded-xl p-6">
                            <div className="text-3xl mb-2">📡</div>
                            <div className="text-3xl font-bold text-primary-400">:7460</div>
                            <div className="text-gray-400 text-sm">API Port</div>
                        </div>
                    </div>

                    {/* Recent Connectors */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div className="bg-[#111] border border-gray-800 rounded-xl p-6">
                            <h3 className="text-lg font-semibold mb-4">Recent Connectors</h3>
                            {connectors.length === 0 ? (
                                <p className="text-gray-500">No connectors yet</p>
                            ) : (
                                <div className="space-y-3">
                                    {connectors.slice(0, 5).map(c => (
                                        <div key={c.id} className="flex justify-between items-center p-3 bg-[#0a0a0a] rounded-lg">
                                            <div>
                                                <div className="font-medium">{c.name}</div>
                                                <div className="text-xs text-gray-500">{c.id}</div>
                                            </div>
                                            <span className={`px-2 py-1 rounded text-xs ${c.is_active ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
                                                {c.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="bg-[#111] border border-gray-800 rounded-xl p-6">
                            <h3 className="text-lg font-semibold mb-4">Ollama Nodes</h3>
                            {nodes.length === 0 ? (
                                <p className="text-gray-500">No nodes registered</p>
                            ) : (
                                <div className="space-y-3">
                                    {nodes.map(n => (
                                        <div key={n.node_id} className="flex justify-between items-center p-3 bg-[#0a0a0a] rounded-lg">
                                            <div>
                                                <div className="font-medium">{n.node_id}</div>
                                                <div className="text-xs text-gray-500">{n.models.length} models</div>
                                            </div>
                                            <span className={`px-2 py-1 rounded text-xs ${n.status === 'online' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                                {n.status}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Quick Start */}
                    <div className="mt-6 bg-gradient-to-r from-primary-900/20 to-transparent border border-primary-800/30 rounded-xl p-6">
                        <h3 className="text-lg font-semibold mb-2">🚀 Quick Start</h3>
                        <p className="text-gray-400 text-sm mb-4">Use the OpenAI-compatible API with your connector's API key:</p>
                        <pre className="bg-[#0a0a0a] p-4 rounded-lg text-sm overflow-x-auto">
                            {`curl -X POST http://localhost:7460/v1/chat/completions \\
  -H "Authorization: Bearer YOUR_CONNECTOR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "qwen2.5:7b",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`}
                        </pre>
                    </div>
                </>
            )}
        </div>
    );
}
