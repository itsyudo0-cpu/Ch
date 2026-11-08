import React, { useState } from 'react';
import { BotSimulator } from './components/BotSimulator';
import { ButtonParserWorkbench } from './components/ButtonParserWorkbench';
import { CodeExplorer } from './components/CodeExplorer';
import { SetupGuide } from './components/SetupGuide';
import { PROJECT_FILES, PROJECT_TREE } from './data/projectFiles';

type ActiveTab = 'simulator' | 'parser' | 'code' | 'setup';

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('simulator');

  const handleDownloadBundle = () => {
    // Generate a self-contained POSIX shell installer script containing all project files
    const sections: string[] = [
      '#!/usr/bin/env bash',
      '# Self-extracting archive for Channel Help Bot (Python 3.11+ / aiogram 3.x / SQLite)',
      'set -e',
      'mkdir -p bot/handlers bot/middlewares bot/utils tests',
      '',
    ];

    for (const file of PROJECT_FILES) {
      sections.push(`cat << 'EOF_FILE_CONTENT' > "${file.path}"`);
      sections.push(file.content.replace(/\r\n/g, '\n'));
      sections.push('EOF_FILE_CONTENT');
      sections.push('');
    }

    sections.push('echo "✅ Extracted all Channel Help Bot files successfully!"');
    sections.push(
      'echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"'
    );

    const blob = new Blob([sections.join('\n')], {
      type: 'text/x-shellscript;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'install_channel_help_bot.sh';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      {/* Top Bar Contract: 3 Zones separated by gap-8 */}
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-[1360px] mx-auto flex items-center justify-between gap-8">
          {/* Zone 1: Single text element wordmark */}
          <a
            href="#top"
            onClick={(e) => {
              e.preventDefault();
              setActiveTab('simulator');
            }}
            className="text-lg font-bold tracking-tight text-slate-900 whitespace-nowrap shrink-0 font-display"
          >
            Channel Help Bot
          </a>

          {/* Zone 2: 4 concise single-line text navigation links */}
          <nav className="flex items-center gap-6 text-sm font-medium text-slate-600 overflow-x-auto">
            <button
              type="button"
              onClick={() => setActiveTab('simulator')}
              className={`hover:text-slate-900 transition-colors whitespace-nowrap shrink-0 pb-0.5 ${
                activeTab === 'simulator'
                  ? 'text-slate-900 underline underline-offset-8 decoration-2 decoration-sky-700 font-semibold'
                  : ''
              }`}
            >
              Bot Simulator
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('parser')}
              className={`hover:text-slate-900 transition-colors whitespace-nowrap shrink-0 pb-0.5 ${
                activeTab === 'parser'
                  ? 'text-slate-900 underline underline-offset-8 decoration-2 decoration-sky-700 font-semibold'
                  : ''
              }`}
            >
              Button Parser
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('code')}
              className={`hover:text-slate-900 transition-colors whitespace-nowrap shrink-0 pb-0.5 ${
                activeTab === 'code'
                  ? 'text-slate-900 underline underline-offset-8 decoration-2 decoration-sky-700 font-semibold'
                  : ''
              }`}
            >
              Source Code
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('setup')}
              className={`hover:text-slate-900 transition-colors whitespace-nowrap shrink-0 pb-0.5 ${
                activeTab === 'setup'
                  ? 'text-slate-900 underline underline-offset-8 decoration-2 decoration-sky-700 font-semibold'
                  : ''
              }`}
            >
              Setup Guide
            </button>
          </nav>

          {/* Zone 3: 1 primary action */}
          <div className="shrink-0">
            <button
              type="button"
              onClick={handleDownloadBundle}
              className="px-4 py-2 text-xs font-semibold text-white bg-slate-900 rounded-lg hover:bg-slate-800 transition-colors whitespace-nowrap shrink-0"
            >
              Download Project Bundle
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Container */}
      <main className="flex-1 max-w-[1360px] w-full mx-auto px-6 py-8 space-y-6">
        {/* Contextual Workspace Header with Clean Unboxed Metadata */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-5 border-b border-slate-200">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 font-mono">
              <span>Python 3.11+</span>
              <span aria-hidden="true">·</span>
              <span>aiogram 3.x (Async FSM)</span>
              <span aria-hidden="true">·</span>
              <span>SQLite (aiosqlite)</span>
              <span aria-hidden="true">·</span>
              <span>Classic Telegram Bot API</span>
              <span aria-hidden="true">·</span>
              <span>{PROJECT_FILES.length} Project Files</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight font-display">
              {activeTab === 'simulator' &&
                'Interactive Bot & Channel Publishing Simulator'}
              {activeTab === 'parser' &&
                'URL Button Builder Parser & Unit Test Suite'}
              {activeTab === 'code' &&
                'Complete Python 3.11+ Codebase & Project Structure'}
              {activeTab === 'setup' &&
                'BotFather Registration & Channel Admin Configuration'}
            </h1>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-500 font-mono">
            <span>copyMessage</span>
            <span aria-hidden="true">·</span>
            <span>getChatMember</span>
            <span aria-hidden="true">·</span>
            <span>editMessageReplyMarkup</span>
            <span aria-hidden="true">·</span>
            <span>deleteMessage</span>
          </div>
        </div>

        {/* Active Workspace View */}
        {activeTab === 'simulator' && <BotSimulator />}
        {activeTab === 'parser' && <ButtonParserWorkbench />}
        {activeTab === 'code' && <CodeExplorer />}
        {activeTab === 'setup' && <SetupGuide />}
      </main>

      {/* Quiet Footer */}
      <footer className="bg-white border-t border-slate-200 px-6 py-4 mt-12">
        <div className="max-w-[1360px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <div>
            Channel Help Bot — Built with Python 3.11+, aiogram 3.x, and SQLite
            using stable classic Telegram Bot API methods.
          </div>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => setActiveTab('code')}
              className="hover:text-slate-900 transition-colors"
            >
              Browse {PROJECT_FILES.length} Files ({PROJECT_TREE.split('\n').length}{' '}
              entries)
            </button>
            <span aria-hidden="true">·</span>
            <button
              type="button"
              onClick={handleDownloadBundle}
              className="hover:text-slate-900 transition-colors"
            >
              Export Installer Script
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
