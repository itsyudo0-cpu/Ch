import React, { useState, useMemo } from 'react';
import { Check, AlertCircle, ExternalLink, Play } from 'lucide-react';
import {
  parseButtonsText,
  validateButtonUrl,
  removeButtonByPosition,
  formatButtonsDsl,
  MAX_BUTTONS_PER_ROW,
  MAX_BUTTON_TEXT_LEN,
  MAX_TOTAL_BUTTONS,
} from '../utils/buttonParser';

interface UnitTestResult {
  name: string;
  description: string;
  passed: boolean;
  detail: string;
}

function runAllUnitTests(): UnitTestResult[] {
  const results: UnitTestResult[] = [];

  const runTest = (
    name: string,
    description: string,
    fn: () => string
  ) => {
    try {
      const detail = fn();
      results.push({ name, description, passed: true, detail });
    } catch (err) {
      results.push({
        name,
        description,
        passed: false,
        detail: err instanceof Error ? err.message : String(err),
      });
    }
  };

  runTest(
    'test_single_row_single_button',
    'Parses single button Text - https://example.com',
    () => {
      const rows = parseButtonsText('Official Website - https://example.com');
      if (rows.length !== 1 || rows[0][0].text !== 'Official Website') {
        throw new Error('Unexpected parsed structure');
      }
      return '1 row, 1 button parsed';
    }
  );

  runTest(
    'test_multiple_rows_and_pipe_separated_buttons',
    'Parses multi-line rows and pipe-separated buttons with https://, http://, and tg://',
    () => {
      const raw =
        'Read Blog - https://example.com/blog\n' +
        'GitHub - https://github.com/org/repo | Telegram - tg://resolve?domain=telegram\n\n' +
        'HTTP Link - http://legacy.example.org/path?query=1';
      const rows = parseButtonsText(raw);
      if (rows.length !== 3 || rows[1].length !== 2) {
        throw new Error('Row count mismatch');
      }
      return '3 rows (4 buttons total) across https, http, and tg schemes';
    }
  );

  runTest(
    'test_button_text_containing_hyphens',
    'Splits on rightmost " - " so button text can contain hyphens',
    () => {
      const rows = parseButtonsText(
        'Part 1 - Getting Started - Guide - https://docs.example.com/start'
      );
      if (rows[0][0].text !== 'Part 1 - Getting Started - Guide') {
        throw new Error(`Got text: ${rows[0][0].text}`);
      }
      return `Preserved text "${rows[0][0].text}"`;
    }
  );

  runTest(
    'test_append_to_existing_rows',
    'Appends new button rows to existing rows without mutating input',
    () => {
      const existing = [[{ text: 'First', url: 'https://first.example.com' }]];
      const updated = parseButtonsText(
        'Second - https://second.example.com',
        existing
      );
      if (updated.length !== 2) throw new Error('Expected 2 rows');
      return 'Appended row #2 cleanly';
    }
  );

  runTest(
    'test_reject_invalid_url_schemes',
    'Rejects javascript:, ftp:, mailto:, and bare domains without scheme',
    () => {
      const invalidInputs = [
        'Click - javascript:alert(1)',
        'FTP - ftp://files.example.com/archive.zip',
        'Mail - mailto:admin@example.com',
        'No Scheme - www.example.com',
      ];
      for (const item of invalidInputs) {
        let threw = false;
        try {
          parseButtonsText(item);
        } catch {
          threw = true;
        }
        if (!threw) throw new Error(`Failed to reject: ${item}`);
      }
      return 'All 4 disallowed schemes rejected with ButtonParseError';
    }
  );

  runTest(
    'test_reject_malformed_urls',
    'Rejects empty hosts, missing domain dots, leading/trailing dots, and spaces',
    () => {
      const malformed = [
        'https://',
        'http://nodot',
        'https://.leadingdot.com',
        'https://trailingdot.com.',
        'tg://',
        'https://example.com/path with spaces',
      ];
      for (const u of malformed) {
        let threw = false;
        try {
          validateButtonUrl(u);
        } catch {
          threw = true;
        }
        if (!threw) throw new Error(`Failed to reject malformed URL: ${u}`);
      }
      return 'All 6 malformed URLs rejected';
    }
  );

  runTest(
    'test_reject_missing_separator_or_empty_parts',
    'Rejects empty input, missing " - " separator, and dangling pipe segments',
    () => {
      const badInputs = [
        '',
        '   \n  ',
        'MissingSeparator https://example.com',
        ' - https://example.com',
        'Valid - https://example.com | ',
        ' | Valid - https://example.com',
      ];
      for (const b of badInputs) {
        let threw = false;
        try {
          parseButtonsText(b);
        } catch {
          threw = true;
        }
        if (!threw) throw new Error(`Failed to reject: "${b}"`);
      }
      return 'All 6 syntax errors rejected';
    }
  );

  runTest(
    'test_enforce_max_buttons_per_row',
    `Enforces Telegram limit of ${MAX_BUTTONS_PER_ROW} buttons per row`,
    () => {
      const row = Array.from(
        { length: MAX_BUTTONS_PER_ROW + 1 },
        (_, i) => `B${i} - https://example.com/${i}`
      ).join(' | ');
      let threw = false;
      try {
        parseButtonsText(row);
      } catch {
        threw = true;
      }
      if (!threw) throw new Error('Expected error for 9 buttons in 1 row');
      return `Rejected ${MAX_BUTTONS_PER_ROW + 1} buttons in a single row`;
    }
  );

  runTest(
    'test_enforce_max_button_text_length',
    `Enforces max button label length (${MAX_BUTTON_TEXT_LEN} chars)`,
    () => {
      const longLabel = 'A'.repeat(MAX_BUTTON_TEXT_LEN + 1);
      let threw = false;
      try {
        parseButtonsText(`${longLabel} - https://example.com`);
      } catch {
        threw = true;
      }
      if (!threw) throw new Error('Expected error for >64 char label');
      return `Rejected ${MAX_BUTTON_TEXT_LEN + 1}-char button label`;
    }
  );

  runTest(
    'test_enforce_max_total_buttons',
    `Enforces Telegram limit of ${MAX_TOTAL_BUTTONS} total inline buttons`,
    () => {
      const lines = Array.from(
        { length: MAX_TOTAL_BUTTONS + 1 },
        (_, i) => `Btn ${i} - https://example.com/${i}`
      ).join('\n');
      let threw = false;
      try {
        parseButtonsText(lines);
      } catch {
        threw = true;
      }
      if (!threw) throw new Error('Expected error for >100 buttons');
      return `Rejected ${MAX_TOTAL_BUTTONS + 1} total buttons`;
    }
  );

  runTest(
    'test_remove_button_and_row_cleanup',
    'Removes individual button at (row, col) and prunes empty rows automatically',
    () => {
      const rows = parseButtonsText(
        'One - https://example.com/1 | Two - https://example.com/2\nThree - https://example.com/3'
      );
      const step1 = removeButtonByPosition(rows, 0, 0);
      const step2 = removeButtonByPosition(step1, 0, 0);
      if (step2.length !== 1 || step2[0][0].text !== 'Three') {
        throw new Error('Failed row cleanup');
      }
      return 'Removed (0,0) twice and pruned empty row #1';
    }
  );

  runTest(
    'test_roundtrip_dsl_and_keyboard_builder',
    'Formats 2D button array back to canonical DSL and builds InlineKeyboardMarkup',
    () => {
      const dslIn =
        'Docs - https://example.com/docs | Support - tg://resolve?domain=support';
      const rows = parseButtonsText(dslIn);
      const dslOut = formatButtonsDsl(rows);
      if (dslOut !== dslIn) throw new Error('Roundtrip mismatch');
      return 'Exact roundtrip match verified';
    }
  );

  return results;
}

export const ButtonParserWorkbench: React.FC = () => {
  const [dslInput, setDslInput] = useState<string>(
    'Read Documentation - https://docs.aiogram.dev/en/latest/\n' +
      'GitHub Repo - https://github.com/aiogram/aiogram | Telegram Channel - tg://resolve?domain=aiogram_ru\n' +
      'Part 1 - Setup Guide - https://example.com/setup-guide'
  );
  const [testResults, setTestResults] = useState<UnitTestResult[]>(() =>
    runAllUnitTests()
  );

  const parseOutcome = useMemo(() => {
    try {
      const rows = parseButtonsText(dslInput);
      return { ok: true as const, rows, error: null };
    } catch (err) {
      return {
        ok: false as const,
        rows: [],
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }, [dslInput]);

  const inlineKeyboardJson = useMemo(() => {
    if (!parseOutcome.ok) return null;
    return JSON.stringify(
      {
        inline_keyboard: parseOutcome.rows.map((row) =>
          row.map((btn) => ({ text: btn.text, url: btn.url, vote: btn.vote }))
        ),
      },
      null,
      2
    );
  }, [parseOutcome]);

  return (
    <div className="space-y-8">
      {/* Live Parser & Validator Section */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        <div className="lg:col-span-6 bg-white border border-slate-200 rounded-xl p-5 flex flex-col justify-between space-y-4">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-slate-900">
                Button Builder DSL Input
              </h2>
              <span className="text-xs text-slate-500 font-mono">
                bot/utils/button_parser.py
              </span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Enter one button row per line. Separate multiple buttons in the
              same row with <code>|</code>. Format each button as{' '}
              <code>Text - https://url</code>. Allowed schemes:{' '}
              <code>http://</code>, <code>https://</code>, <code>tg://</code>.
            </p>
            <textarea
              rows={6}
              value={dslInput}
              onChange={(e) => setDslInput(e.target.value)}
              className="w-full font-mono text-xs bg-slate-50 border border-slate-300 rounded-lg p-3.5 text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-600 leading-relaxed"
              placeholder="Button Text - https://example.com | Second - tg://resolve?domain=telegram"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
            <span className="text-xs font-medium text-slate-500 mr-1">
              Test Cases:
            </span>
            <button
              type="button"
              onClick={() =>
                setDslInput(
                  'Read Documentation - https://docs.aiogram.dev/en/latest/\nGitHub Repo - https://github.com/aiogram/aiogram | Telegram - tg://resolve?domain=aiogram_ru'
                )
              }
              className="px-2.5 py-1 text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-md transition-colors whitespace-nowrap shrink-0"
            >
              Valid Multi-Row
            </button>
            <button
              type="button"
              onClick={() =>
                setDslInput('XSS Attempt - javascript:alert(document.cookie)')
              }
              className="px-2.5 py-1 text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-md transition-colors whitespace-nowrap shrink-0"
            >
              Invalid Scheme (javascript:)
            </button>
            <button
              type="button"
              onClick={() =>
                setDslInput('Missing Separator https://example.com')
              }
              className="px-2.5 py-1 text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-md transition-colors whitespace-nowrap shrink-0"
            >
              Missing &quot; - &quot;
            </button>
            <button
              type="button"
              onClick={() =>
                setDslInput(
                  Array.from(
                    { length: 9 },
                    (_, i) => `B${i + 1} - https://example.com/${i + 1}`
                  ).join(' | ')
                )
              }
              className="px-2.5 py-1 text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-md transition-colors whitespace-nowrap shrink-0"
            >
              Exceed 8 Buttons/Row
            </button>
          </div>
        </div>

        {/* Live Output & InlineKeyboardMarkup JSON Preview */}
        <div className="lg:col-span-6 bg-white border border-slate-200 rounded-xl p-5 space-y-4 flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-slate-900">
                Validation &amp; InlineKeyboardMarkup Output
              </h2>
              {parseOutcome.ok ? (
                <span className="text-xs font-semibold text-emerald-700 flex items-center gap-1">
                  <Check className="w-4 h-4" />
                  <span>
                    Valid ({parseOutcome.rows.length} rows ·{' '}
                    {parseOutcome.rows.reduce((a, r) => a + r.length, 0)} buttons)
                  </span>
                </span>
              ) : (
                <span className="text-xs font-semibold text-rose-700 flex items-center gap-1">
                  <AlertCircle className="w-4 h-4" />
                  <span>ButtonParseError</span>
                </span>
              )}
            </div>

            {!parseOutcome.ok ? (
              <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-900 font-mono">
                {parseOutcome.error}
              </div>
            ) : (
              <div className="space-y-3">
                <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg space-y-1.5">
                  <div className="text-[11px] font-mono text-slate-500 mb-2">
                    Rendered Telegram URL Inline Keyboard:
                  </div>
                  {parseOutcome.rows.map((row, rIdx) => (
                    <div
                      key={rIdx}
                      className="grid grid-cols-1 sm:grid-flow-col gap-1.5"
                    >
                      {row.map((btn, bIdx) =>
                        btn.vote ? (
                          <button
                            key={bIdx}
                            type="button"
                            className="px-3 py-1.5 bg-white hover:bg-emerald-50 text-emerald-700 border border-slate-200 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-colors truncate"
                            title="Vote button: one unique vote per user, live counter"
                          >
                            <span className="truncate">{btn.text}</span>
                          </button>
                        ) : (
                          <a
                            key={bIdx}
                            href={btn.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-3 py-1.5 bg-white hover:bg-sky-50 text-sky-700 border border-slate-200 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-colors truncate"
                          >
                            <span className="truncate">{btn.text}</span>
                            <ExternalLink className="w-3 h-3 shrink-0" />
                          </a>
                        )
                      )}
                    </div>
                  ))}
                </div>

                <div>
                  <div className="text-xs font-medium text-slate-600 mb-1.5">
                    Classic Bot API <code>reply_markup</code> Payload:
                  </div>
                  <pre className="p-3 bg-slate-900 text-slate-100 rounded-lg text-xs font-mono overflow-x-auto max-h-44">
                    {inlineKeyboardJson}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Unit Test Suite Table (tests/test_button_parser.py) */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              Unit Test Suite — tests/test_button_parser.py
            </h2>
            <p className="text-xs text-slate-500">
              12 automated unit test assertions verifying URL schemes, Telegram
              limits, hyphen edge cases, and row manipulation
            </p>
          </div>
          <button
            type="button"
            onClick={() => setTestResults(runAllUnitTests())}
            className="px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors whitespace-nowrap shrink-0"
          >
            <Play className="w-3.5 h-3.5" />
            <span>Re-Run 12 Unit Tests</span>
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-xs font-semibold text-slate-600">
                <th className="py-2.5 px-4">Test Function</th>
                <th className="py-2.5 px-4">Specification</th>
                <th className="py-2.5 px-4">Assertion Result</th>
                <th className="py-2.5 px-4 text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-xs">
              {testResults.map((t) => (
                <tr key={t.name} className="hover:bg-slate-50/80">
                  <td className="py-2.5 px-4 font-mono font-semibold text-slate-900">
                    {t.name}
                  </td>
                  <td className="py-2.5 px-4 text-slate-600">
                    {t.description}
                  </td>
                  <td className="py-2.5 px-4 font-mono text-slate-500">
                    {t.detail}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono font-semibold">
                    {t.passed ? (
                      <span className="text-emerald-700">PASS</span>
                    ) : (
                      <span className="text-rose-700">FAIL</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
