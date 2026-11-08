export interface ParsedButton {
  text: string;
  url: string;
  /** Stable option id for vote buttons (`Text - vote`); url is '' for these. */
  vote?: string;
}

export const VOTE_KEYWORD = 'vote';

function nextVoteId(rows: ParsedButton[][]): number {
  const ids = rows.flat().map((b) => Number(b.vote)).filter((n) => Number.isInteger(n) && n > 0);
  return ids.length ? Math.max(...ids) + 1 : 1;
}

export const MAX_BUTTONS_PER_ROW = 8;
export const MAX_TOTAL_BUTTONS = 100;
export const MAX_ROWS = 100;
export const MAX_BUTTON_TEXT_LEN = 64;
export const MAX_URL_LEN = 2048;
export const ALLOWED_SCHEMES = new Set(['http:', 'https:', 'tg:']);

export class ButtonParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ButtonParseError';
  }
}

export function validateButtonUrl(url: string): string {
  const cleaned = url.trim();
  if (!cleaned) {
    throw new ButtonParseError('URL cannot be empty.');
  }
  if (cleaned.length > MAX_URL_LEN) {
    throw new ButtonParseError(
      `URL exceeds Telegram limit of ${MAX_URL_LEN} characters.`
    );
  }
  if (/\s/.test(cleaned)) {
    throw new ButtonParseError(`URL '${cleaned}' must not contain whitespace.`);
  }

  let parsed: URL;
  try {
    parsed = new URL(cleaned);
  } catch {
    throw new ButtonParseError(
      `Invalid URL scheme in '${cleaned}'. Only http://, https://, and tg:// are allowed.`
    );
  }

  const protocol = parsed.protocol.toLowerCase();
  if (!ALLOWED_SCHEMES.has(protocol)) {
    throw new ButtonParseError(
      `Invalid URL scheme in '${cleaned}'. Only http://, https://, and tg:// are allowed.`
    );
  }

  if (protocol === 'http:' || protocol === 'https:') {
    const host = parsed.hostname;
    if (!host || !host.includes('.')) {
      throw new ButtonParseError(
        `Invalid HTTP/HTTPS URL '${cleaned}': missing a valid domain name.`
      );
    }
    if (host.startsWith('.') || host.endsWith('.')) {
      throw new ButtonParseError(
        `Invalid HTTP/HTTPS URL '${cleaned}': malformed domain name.`
      );
    }
  } else if (protocol === 'tg:') {
    const afterScheme = cleaned.slice(5);
    if (!afterScheme || afterScheme === '//') {
      throw new ButtonParseError(
        `Invalid tg:// link '${cleaned}': missing target path or domain.`
      );
    }
  }

  return cleaned;
}

export function parseButtonsText(
  rawText: string,
  existingRows: ParsedButton[][] = []
): ParsedButton[][] {
  if (!rawText || !rawText.trim()) {
    throw new ButtonParseError('Button input cannot be empty.');
  }

  const baseRows: ParsedButton[][] = existingRows.map((row) =>
    row.map((btn) => ({ ...btn }))
  );
  let totalButtons = baseRows.reduce((acc, r) => acc + r.length, 0);
  const newRows: ParsedButton[][] = [];

  const lines = rawText.trim().split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const lineIdx = i + 1;
    const line = lines[i].trim();
    if (!line) continue;

    const segments = line.split('|').map((s) => s.trim());
    if (segments.some((s) => !s)) {
      throw new ButtonParseError(
        `Line ${lineIdx}: Empty button segment near '|'. Format each button as 'Text - https://url'.`
      );
    }

    if (segments.length > MAX_BUTTONS_PER_ROW) {
      throw new ButtonParseError(
        `Line ${lineIdx}: Too many buttons in one row (${segments.length}). Telegram allows at most ${MAX_BUTTONS_PER_ROW} buttons per row.`
      );
    }

    const rowButtons: ParsedButton[] = [];
    for (let j = 0; j < segments.length; j++) {
      const btnIdx = j + 1;
      const segment = segments[j];
      const sepIndex = segment.lastIndexOf(' - ');
      if (sepIndex === -1) {
        throw new ButtonParseError(
          `Line ${lineIdx}, button ${btnIdx} ('${segment}'): Missing ' - ' separator. Expected format: Text - https://url`
        );
      }

      const btnText = segment.slice(0, sepIndex).trim();
      const btnUrlRaw = segment.slice(sepIndex + 3).trim();

      if (!btnText) {
        throw new ButtonParseError(
          `Line ${lineIdx}, button ${btnIdx}: Button text cannot be empty.`
        );
      }
      if (btnText.length > MAX_BUTTON_TEXT_LEN) {
        throw new ButtonParseError(
          `Line ${lineIdx}, button ${btnIdx}: Button text exceeds ${MAX_BUTTON_TEXT_LEN} characters (${btnText.length} chars).`
        );
      }

      const isVote = btnUrlRaw.toLowerCase() === VOTE_KEYWORD;
      const validatedUrl = isVote ? '' : validateButtonUrl(btnUrlRaw);
      totalButtons += 1;
      if (totalButtons > MAX_TOTAL_BUTTONS) {
        throw new ButtonParseError(
          `Total buttons exceed Telegram limit of ${MAX_TOTAL_BUTTONS} buttons.`
        );
      }

      if (isVote) {
        const voteId = nextVoteId([...baseRows, ...newRows, rowButtons]);
        rowButtons.push({ text: btnText, url: '', vote: String(voteId) });
      } else {
        rowButtons.push({ text: btnText, url: validatedUrl });
      }
    }

    newRows.push(rowButtons);
  }

  if (newRows.length === 0) {
    throw new ButtonParseError('No valid buttons found in input.');
  }

  const combined = [...baseRows, ...newRows];
  if (combined.length > MAX_ROWS) {
    throw new ButtonParseError(
      `Total button rows (${combined.length}) exceed limit of ${MAX_ROWS} rows.`
    );
  }

  return combined;
}

export function removeButtonByPosition(
  rows: ParsedButton[][],
  rowIndex: number,
  colIndex?: number
): ParsedButton[][] {
  if (rowIndex < 0 || rowIndex >= rows.length) {
    throw new RangeError(`Row index ${rowIndex + 1} is out of range.`);
  }
  const updated = rows.map((r) => r.map((b) => ({ ...b })));
  if (colIndex === undefined) {
    updated.splice(rowIndex, 1);
  } else {
    const targetRow = updated[rowIndex];
    if (colIndex < 0 || colIndex >= targetRow.length) {
      throw new RangeError(
        `Button index ${colIndex + 1} in row ${rowIndex + 1} is out of range.`
      );
    }
    targetRow.splice(colIndex, 1);
    if (targetRow.length === 0) {
      updated.splice(rowIndex, 1);
    }
  }
  return updated;
}

export function formatButtonsDsl(rows: ParsedButton[][]): string {
  if (!rows.length) return '';
  return rows
    .map((row) => row.map((b) => `${b.text} - ${b.vote ? VOTE_KEYWORD : b.url}`).join(' | '))
    .join('\n');
}
