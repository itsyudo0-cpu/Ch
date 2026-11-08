import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

export const SetupGuide: React.FC = () => {
  const [botTokenInput, setBotTokenInput] = useState<string>(
    '1234567890:AAH_your_bot_token_from_botfather'
  );
  const [adminIdsInput, setAdminIdsInput] = useState<string>('123456789,987654321');
  const [whitelistEnabled, setWhitelistEnabled] = useState<boolean>(true);
  const [dbPathInput, setDbPathInput] = useState<string>('channel_help_bot.db');
  const [copiedEnv, setCopiedEnv] = useState<boolean>(false);

  const generatedEnv = `# Telegram Bot Token from @BotFather
BOT_TOKEN="${botTokenInput.trim()}"

# Comma-separated Telegram user IDs of bot admins / whitelisted owners
ADMIN_IDS="${adminIdsInput.trim()}"

# Restrict bot access strictly to ADMIN_IDS
WHITELIST_ENABLED="${whitelistEnabled ? 'true' : 'false'}"

# SQLite database path
DB_PATH="${dbPathInput.trim()}"

# Logging verbosity (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL="INFO"`;

  const handleCopyEnv = async () => {
    await navigator.clipboard.writeText(generatedEnv);
    setCopiedEnv(true);
    setTimeout(() => setCopiedEnv(false), 2000);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
      {/* Left Column: Step-by-Step BotFather & Channel Admin Walkthrough */}
      <div className="lg:col-span-7 bg-white border border-slate-200 rounded-xl p-6 space-y-6">
        <div className="space-y-1">
          <h2 className="text-lg font-bold text-slate-900">
            BotFather &amp; Channel Administrator Setup Guide
          </h2>
          <p className="text-xs text-slate-500">
            Complete instructions to register your bot, grant required channel
            permissions, and start long polling.
          </p>
        </div>

        <div className="space-y-5 divide-y divide-slate-200">
          <div className="space-y-2 pt-2">
            <h3 className="text-sm font-semibold text-slate-900">
              01. Create Bot in @BotFather
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Open <b>@BotFather</b> in Telegram and send <code>/newbot</code>.
              Provide a display name (e.g. <i>Channel Help Publisher</i>) and a
              username ending in <code>bot</code>. Copy the HTTP API token and
              optionally register commands with <code>/setcommands</code>:
            </p>
            <pre className="p-3 bg-slate-900 text-slate-100 rounded-lg text-xs font-mono">
              {`start - Open main menu\nhelp - Show usage instructions and button syntax`}
            </pre>
          </div>

          <div className="space-y-2 pt-4">
            <h3 className="text-sm font-semibold text-slate-900">
              02. Add Bot as Channel Administrator
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Open your Telegram Broadcast Channel → <b>Channel Info</b> →{' '}
              <b>Administrators</b> → <b>Add Admin</b>. Search for your bot&apos;s{' '}
              <code>@username</code> and enable these classic permissions:
            </p>
            <ul className="text-xs text-slate-700 space-y-1.5 font-mono bg-slate-50 p-3.5 rounded-lg border border-slate-200">
              <li>✅ Post Messages (can_post_messages = True)</li>
              <li>✅ Edit Messages of Others (can_edit_messages = True)</li>
              <li>✅ Delete Messages of Others (can_delete_messages = True)</li>
              <li>✅ Pin Messages (can_pin_messages = True)</li>
            </ul>
          </div>

          <div className="space-y-2 pt-4">
            <h3 className="text-sm font-semibold text-slate-900">
              03. Install Dependencies &amp; Run Long Polling
            </h3>
            <pre className="p-3.5 bg-slate-900 text-slate-100 rounded-lg text-xs font-mono leading-relaxed overflow-x-auto">
              {`python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m bot.main`}
            </pre>
          </div>
        </div>
      </div>

      {/* Right Column: Interactive .env Configuration Builder */}
      <div className="lg:col-span-5 bg-white border border-slate-200 rounded-xl p-6 flex flex-col justify-between space-y-5">
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              Interactive .env Generator
            </h2>
            <p className="text-xs text-slate-500">
              Customize your environment configuration and copy directly to{' '}
              <code>.env</code>.
            </p>
          </div>

          <div className="space-y-3">
            <div>
              <label
                htmlFor="env-bot-token"
                className="block text-xs font-semibold text-slate-700 mb-1"
              >
                BOT_TOKEN
              </label>
              <input
                id="env-bot-token"
                type="text"
                value={botTokenInput}
                onChange={(e) => setBotTokenInput(e.target.value)}
                className="w-full text-xs font-mono bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-600"
              />
            </div>

            <div>
              <label
                htmlFor="env-admin-ids"
                className="block text-xs font-semibold text-slate-700 mb-1"
              >
                ADMIN_IDS (Comma-separated Telegram User IDs)
              </label>
              <input
                id="env-admin-ids"
                type="text"
                value={adminIdsInput}
                onChange={(e) => setAdminIdsInput(e.target.value)}
                className="w-full text-xs font-mono bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-600"
              />
            </div>

            <div>
              <label
                htmlFor="env-db-path"
                className="block text-xs font-semibold text-slate-700 mb-1"
              >
                DB_PATH (SQLite File)
              </label>
              <input
                id="env-db-path"
                type="text"
                value={dbPathInput}
                onChange={(e) => setDbPathInput(e.target.value)}
                className="w-full text-xs font-mono bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-600"
              />
            </div>

            <div className="flex items-center justify-between pt-1">
              <span className="text-xs font-semibold text-slate-700">
                Enforce User Whitelist (WHITELIST_ENABLED)
              </span>
              <button
                type="button"
                onClick={() => setWhitelistEnabled((v) => !v)}
                className={`px-3 py-1 text-xs font-mono font-semibold rounded-md transition-colors ${
                  whitelistEnabled
                    ? 'bg-sky-700 text-white'
                    : 'bg-slate-200 text-slate-700'
                }`}
              >
                {whitelistEnabled ? 'true' : 'false'}
              </button>
            </div>
          </div>

          <div className="space-y-1.5 pt-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-700">
                Generated .env File
              </span>
              <button
                type="button"
                onClick={handleCopyEnv}
                className="px-3 py-1 text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-md flex items-center gap-1.5 transition-colors"
              >
                {copiedEnv ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy .env</span>
                  </>
                )}
              </button>
            </div>
            <pre className="p-3.5 bg-slate-900 text-slate-100 rounded-lg text-xs font-mono leading-relaxed overflow-x-auto">
              {generatedEnv}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};
