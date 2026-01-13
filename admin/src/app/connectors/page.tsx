'use client';

import { useEffect, useState } from 'react';
import { api, type Connector } from '@/lib/api';

export default function ConnectorsPage() {
    const [connectors, setConnectors] = useState<Connector[]>([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [newApiKey, setNewApiKey] = useState<string | null>(null);
    const adminKey = typeof window !== 'undefined' ? localStorage.getItem('adminKey') || '' : '';

    const [form, setForm] = useState({
        name: '',
        description: '',
        priority: 5,
        rate_limit_per_minute: 60,
    });

    const fetchConnectors = async () => {
        try {
            setLoading(true);
            const res = await api.listConnectors(adminKey);
            setConnectors(res.items);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (adminKey) fetchConnectors();
    }, [adminKey]);

    const handleCreate = async () => {
        try {
            const result = await api.createConnector(adminKey, {
                name: form.name,
                description: form.description,
                priority: form.priority,
                routing: { prefer: 'ollama', fallback: 'openrouter' },
                rate_limits: { per_minute: form.rate_limit_per_minute, per_hour: 1000, burst: 20 },
                quotas: {},
                allowed_models: ['*'],
                blocked_models: [],
                tags: [],
                config_info: {},
            });
            setNewApiKey(result.api_key);
            setShowCreate(false);
            setForm({ name: '', description: '', priority: 5, rate_limit_per_minute: 60 });
            fetchConnectors();
        } catch (err) {
            alert(err instanceof Error ? err.message : 'Failed to create');
        }
    };

    const handleDelete = async (id: string) => {
        if (!confirm('Delete this connector?')) return;
        try {
            await api.deleteConnector(adminKey, id);
            fetchConnectors();
        } catch (err) {
            alert(err instanceof Error ? err.message : 'Failed to delete');
        }
    };

    return (
        <div>
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-2xl font-bold">Connectors</h1>
                    <p className="text-gray-400">Manage API credentials and access controls</p>
                </div>
                <button
                    onClick={() => setShowCreate(true)}
                    className="px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm transition"
                >
                    ➕ New Connector
                </button>
            </div>

            {/* New API Key Modal */}
            {newApiKey && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-[#111] border border-gray-800 rounded-xl p-6 max-w-lg w-full mx-4">
                        <h3 className="text-lg font-semibold mb-4 text-green-400">✅ Connector Created!</h3>
                        <p className="text-gray-400 text-sm mb-4">
                            Copy your API key now. It won't be shown again.
                        </p>
                        <div className="bg-[#0a0a0a] p-4 rounded-lg font-mono text-sm break-all mb-4">
                            {newApiKey}
                        </div>
                        <button
                            onClick={() => {
                                navigator.clipboard.writeText(newApiKey);
                                alert('Copied!');
                            }}
                            className="w-full px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition mb-2"
                        >
                            📋 Copy to Clipboard
                        </button>
                        <button
                            onClick={() => setNewApiKey(null)}
                            className="w-full px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm transition"
                        >
                            Done
                        </button>
                    </div>
                </div>
            )}

            {/* Create Modal */}
            {showCreate && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-[#111] border border-gray-800 rounded-xl p-6 max-w-lg w-full mx-4">
                        <h3 className="text-lg font-semibold mb-4">Create Connector</h3>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm text-gray-400 mb-1">Name</label>
                                <input
                                    value={form.name}
                                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                                    className="w-full px-4 py-2 bg-[#0a0a0a] border border-gray-700 rounded-lg text-white focus:border-primary-500 focus:outline-none"
                                    placeholder="My App Connector"
                                />
                            </div>
                            <div>
                                <label className="block text-sm text-gray-400 mb-1">Description</label>
                                <input
                                    value={form.description}
                                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                                    className="w-full px-4 py-2 bg-[#0a0a0a] border border-gray-700 rounded-lg text-white focus:border-primary-500 focus:outline-none"
                                    placeholder="Optional description"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">Priority (1-10)</label>
                                    <input
                                        type="number"
                                        min={1}
                                        max={10}
                                        value={form.priority}
                                        onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value) || 5 })}
                                        className="w-full px-4 py-2 bg-[#0a0a0a] border border-gray-700 rounded-lg text-white focus:border-primary-500 focus:outline-none"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">Rate Limit/min</label>
                                    <input
                                        type="number"
                                        min={1}
                                        value={form.rate_limit_per_minute}
                                        onChange={(e) => setForm({ ...form, rate_limit_per_minute: parseInt(e.target.value) || 60 })}
                                        className="w-full px-4 py-2 bg-[#0a0a0a] border border-gray-700 rounded-lg text-white focus:border-primary-500 focus:outline-none"
                                    />
                                </div>
                            </div>
                        </div>
                        <div className="flex gap-2 mt-6">
                            <button
                                onClick={() => setShowCreate(false)}
                                className="flex-1 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleCreate}
                                className="flex-1 px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm transition"
                            >
                                Create
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Connectors List */}
            {loading ? (
                <div className="text-center py-20 text-gray-400">Loading...</div>
            ) : connectors.length === 0 ? (
                <div className="text-center py-20 text-gray-400">
                    <p className="text-4xl mb-4">🔑</p>
                    <p>No connectors yet. Create one to get started!</p>
                </div>
            ) : (
                <div className="bg-[#111] border border-gray-800 rounded-xl overflow-hidden">
                    <table className="w-full">
                        <thead className="bg-[#0a0a0a] border-b border-gray-800">
                            <tr>
                                <th className="px-4 py-3 text-left text-sm text-gray-400">Name</th>
                                <th className="px-4 py-3 text-left text-sm text-gray-400">ID</th>
                                <th className="px-4 py-3 text-left text-sm text-gray-400">Priority</th>
                                <th className="px-4 py-3 text-left text-sm text-gray-400">Rate Limit</th>
                                <th className="px-4 py-3 text-left text-sm text-gray-400">Status</th>
                                <th className="px-4 py-3 text-left text-sm text-gray-400">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {connectors.map(c => (
                                <tr key={c.id} className="border-b border-gray-800 hover:bg-[#0a0a0a]/50">
                                    <td className="px-4 py-3">
                                        <div className="font-medium">{c.name}</div>
                                        {c.description && <div className="text-xs text-gray-500">{c.description}</div>}
                                    </td>
                                    <td className="px-4 py-3 font-mono text-xs text-gray-400">{c.id}</td>
                                    <td className="px-4 py-3">
                                        <span className={`px-2 py-1 rounded text-xs ${c.priority >= 7 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-gray-500/20 text-gray-400'}`}>
                                            {c.priority}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-sm">{c.rate_limit_per_minute}/min</td>
                                    <td className="px-4 py-3">
                                        <span className={`px-2 py-1 rounded text-xs ${c.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                            {c.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <button
                                            onClick={() => handleDelete(c.id)}
                                            className="text-red-400 hover:text-red-300 text-sm"
                                        >
                                            Delete
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
