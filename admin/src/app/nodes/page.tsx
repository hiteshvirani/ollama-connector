'use client';

import { useEffect, useState } from 'react';
import { api, type Node } from '@/lib/api';

export default function NodesPage() {
    const [nodes, setNodes] = useState<Node[]>([]);
    const [loading, setLoading] = useState(true);
    const adminKey = typeof window !== 'undefined' ? localStorage.getItem('adminKey') || '' : '';

    const fetchNodes = async () => {
        try {
            setLoading(true);
            const res = await api.listNodes(adminKey);
            setNodes(res);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (adminKey) fetchNodes();
        const interval = setInterval(() => {
            if (adminKey) fetchNodes();
        }, 10000); // Refresh every 10 seconds
        return () => clearInterval(interval);
    }, [adminKey]);

    const handleRemove = async (nodeId: string) => {
        if (!confirm('Remove this node?')) return;
        try {
            await api.removeNode(adminKey, nodeId);
            fetchNodes();
        } catch (err) {
            alert(err instanceof Error ? err.message : 'Failed to remove');
        }
    };

    return (
        <div>
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-2xl font-bold">Ollama Nodes</h1>
                    <p className="text-gray-400">Monitor your local LLM nodes</p>
                </div>
                <button
                    onClick={fetchNodes}
                    className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition"
                >
                    🔄 Refresh
                </button>
            </div>

            {loading ? (
                <div className="text-center py-20 text-gray-400">Loading...</div>
            ) : nodes.length === 0 ? (
                <div className="text-center py-20 text-gray-400">
                    <p className="text-4xl mb-4">🖥️</p>
                    <p className="mb-4">No nodes registered yet.</p>
                    <div className="max-w-md mx-auto text-left bg-[#111] border border-gray-800 rounded-xl p-4">
                        <p className="text-sm mb-2">To register a node, run the client agent:</p>
                        <pre className="text-xs bg-[#0a0a0a] p-2 rounded">
                            {`export SERVER_URL="http://YOUR_SERVER:7460"
export NODE_SECRET="your-node-secret"
docker compose up -d`}
                        </pre>
                    </div>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {nodes.map(node => (
                        <div
                            key={node.node_id}
                            className="bg-[#111] border border-gray-800 rounded-xl p-6"
                        >
                            <div className="flex justify-between items-start mb-4">
                                <div>
                                    <h3 className="font-semibold text-lg">{node.node_id}</h3>
                                    <span className={`px-2 py-1 rounded text-xs ${node.status === 'online' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                        {node.status}
                                    </span>
                                </div>
                                <button
                                    onClick={() => handleRemove(node.node_id)}
                                    className="text-gray-500 hover:text-red-400 text-sm"
                                >
                                    ✕
                                </button>
                            </div>

                            <div className="space-y-3 text-sm">
                                <div>
                                    <span className="text-gray-500">Connection:</span>
                                    <div className="font-mono text-xs mt-1">
                                        {node.cloudflare_url && <div className="text-blue-400">☁️ {node.cloudflare_url}</div>}
                                        {node.ipv4 && <div>IPv4: {node.ipv4}:{node.port}</div>}
                                        {node.ipv6 && <div>IPv6: [{node.ipv6}]:{node.port}</div>}
                                    </div>
                                </div>

                                <div>
                                    <span className="text-gray-500">Models ({node.models.length}):</span>
                                    <div className="flex flex-wrap gap-1 mt-1">
                                        {node.models.slice(0, 5).map(m => (
                                            <span key={m} className="px-2 py-0.5 bg-gray-800 rounded text-xs">{m}</span>
                                        ))}
                                        {node.models.length > 5 && (
                                            <span className="px-2 py-0.5 bg-gray-800 rounded text-xs">+{node.models.length - 5}</span>
                                        )}
                                    </div>
                                </div>

                                {node.load && (
                                    <div className="grid grid-cols-2 gap-2">
                                        <div>
                                            <span className="text-gray-500 text-xs">CPU</span>
                                            <div className="w-full bg-gray-800 rounded-full h-2 mt-1">
                                                <div
                                                    className="bg-primary-500 h-2 rounded-full"
                                                    style={{ width: `${(node.load.cpu || 0) * 100}%` }}
                                                />
                                            </div>
                                        </div>
                                        <div>
                                            <span className="text-gray-500 text-xs">Memory</span>
                                            <div className="w-full bg-gray-800 rounded-full h-2 mt-1">
                                                <div
                                                    className="bg-green-500 h-2 rounded-full"
                                                    style={{ width: `${(node.load.memory || 0) * 100}%` }}
                                                />
                                            </div>
                                        </div>
                                    </div>
                                )}

                                <div className="text-xs text-gray-500">
                                    Last seen: {new Date(node.last_seen).toLocaleString()}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
