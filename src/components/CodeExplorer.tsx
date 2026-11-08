import React, { useState } from 'react';
import { Copy, Check, Download, FileCode, FolderTree } from 'lucide-react';
import { PROJECT_FILES, PROJECT_TREE, ProjectFile } from '../data/projectFiles';

export const CodeExplorer: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<ProjectFile>(
    PROJECT_FILES[0]
  );
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  const handleCopy = async (file: ProjectFile) => {
    await navigator.clipboard.writeText(file.content);
    setCopiedPath(file.path);
    setTimeout(() => setCopiedPath(null), 2000);
  };

  const handleDownloadSingle = (file: ProjectFile) => {
    const blob = new Blob([file.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = file.path.replace(/\//g, '_');
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Architecture & Project Structure Banner */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        <div className="lg:col-span-5 bg-white border border-slate-200 rounded-xl p-5 flex flex-col justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-slate-900 font-bold text-base">
              <FolderTree className="w-4 h-4 text-sky-700" />
              <h2>Project Directory Structure</h2>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Clean modular architecture for Python 3.11+ using{' '}
              <code>aiogram 3.x</code> routers, finite state machines (FSM),
              outer whitelist middleware, and <code>aiosqlite</code> storage.
            </p>
            <pre className="p-3.5 bg-slate-900 text-slate-100 rounded-lg text-xs font-mono leading-relaxed overflow-x-auto">
              {PROJECT_TREE}
            </pre>
          </div>
        </div>

        {/* File Viewer */}
        <div className="lg:col-span-7 bg-white border border-slate-200 rounded-xl overflow-hidden flex flex-col">
          {/* File Selector Tabs */}
          <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex flex-wrap gap-1.5">
            {PROJECT_FILES.map((file) => (
              <button
                key={file.path}
                type="button"
                onClick={() => setSelectedFile(file)}
                className={`px-2.5 py-1.5 text-xs font-mono rounded-md transition-colors whitespace-nowrap shrink-0 ${
                  selectedFile.path === file.path
                    ? 'bg-sky-700 text-white font-semibold'
                    : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                }`}
              >
                {file.path}
              </button>
            ))}
          </div>

          {/* Active File Toolbar */}
          <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between gap-4 bg-white">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <FileCode className="w-4 h-4 text-sky-700 shrink-0" />
                <span className="text-sm font-bold font-mono text-slate-900 truncate">
                  {selectedFile.path}
                </span>
              </div>
              <p className="text-xs text-slate-500 truncate mt-0.5">
                {selectedFile.summary}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => handleCopy(selectedFile)}
                className="px-3 py-1.5 text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg flex items-center gap-1.5 transition-colors whitespace-nowrap shrink-0"
              >
                {copiedPath === selectedFile.path ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy Code</span>
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={() => handleDownloadSingle(selectedFile)}
                className="px-3 py-1.5 text-xs font-medium bg-slate-900 hover:bg-slate-800 text-white rounded-lg flex items-center gap-1.5 transition-colors whitespace-nowrap shrink-0"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download</span>
              </button>
            </div>
          </div>

          {/* Source Code Body */}
          <pre className="p-5 bg-slate-950 text-slate-100 text-xs font-mono leading-relaxed overflow-x-auto max-h-[540px] flex-1">
            <code>{selectedFile.content}</code>
          </pre>
        </div>
      </div>
    </div>
  );
};
