# Channel Help Bot (Python 3.11+ · aiogram 3.x · SQLite)

A Telegram channel publishing and post management bot built with **Python 3.11+**, **aiogram 3.x** (async, FSM), and **SQLite** (`aiosqlite`). Posts with buttons are published as **Bot API 10.3 Rich Messages with Rich Buttons** (`sendRichMessage`, buttons inside the message body instead of the normal inline keyboard). Posts without buttons, or with *Rich Buttons: OFF*, use the classic methods (`copyMessage`, `sendMessage`, `sendPhoto`, `sendVideo`, `sendDocument`, `sendAnimation`, `InlineKeyboardMarkup` with URL buttons, `editMessageReplyMarkup`, `editMessageText`, `editMessageCaption`, `deleteMessage`, and `pinChatMessage`).

---

## Project Structure

```text
channel-help-bot/
├── .env.example
├── README.md
├── requirements.txt
├── bot/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── keyboards.py
│   ├── main.py
│   ├── states.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── channels.py
│   │   ├── my_posts.py
│   │   ├── posts.py
│   │   ├── start.py
│   │   └── votes.py          # vote button presses + live counters
│   ├── middlewares/
│   │   ├── __init__.py
│   │   └── access.py
│   └── utils/
│       ├── __init__.py
│       ├── bot_api_103.py    # optional Bot API 10.3 rich buttons / ephemeral card
│       ├── button_parser.py
│       ├── post_render.py    # edit buttons of published posts (rich or classic)
│       ├── rich_post.py      # message -> Rich Message blocks + Rich Buttons
│       └── telegram_helpers.py
└── tests/
    └── test_button_parser.py
```

---

## 1. BotFather Setup

1. Open Telegram and start a chat with **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot` and follow the prompts:
   - Choose a display name (e.g., `Channel Help Publisher`).
   - Choose a unique username ending in `bot` (e.g., `my_channel_publisher_bot`).
3. Copy the HTTP API token provided by `@BotFather` (e.g., `1234567890:AAH...`).
4. *(Optional)* Configure the bot's commands list in `@BotFather` via `/setcommands`:
   ```text
   start - Open main menu
   help - Show usage instructions and button syntax
   ```

---

## 2. How to Add the Bot as a Channel Administrator

Before the bot can verify or publish to your Telegram channel, you must grant it administrator rights:

1. Open your Telegram **Channel** and tap the channel header at the top.
2. Tap **Edit** (pencil icon) → **Administrators** → **Add Admin**.
3. Search for your bot's `@username` and select it.
4. Ensure at least the following permissions are **enabled**:
   - ✅ **Post Messages** (`can_post_messages`) — required for publishing posts.
   - ✅ **Edit Messages of Others** (`can_edit_messages`) — required for editing inline URL buttons on published posts.
   - ✅ **Delete Messages of Others** (`can_delete_messages`) — required if you want to delete published posts from **My Posts**.
   - ✅ **Pin Messages** (`can_pin_messages`) — required if you use the **Pin After Publish** toggle.
5. Tap **Done** (checkmark) to save administrator settings.
6. In your private chat with the bot:
   - Tap **📢 My Channels** → **➕ Connect Channel**.
   - Either **forward any message** from your channel to the bot, or send the channel's `@username` (e.g., `@my_channel`).
   - The bot calls `getChatMember` to verify both its own post/edit permissions and that your account is the channel's `creator` or `administrator`.

---

## 3. Installation & Running

### Prerequisites
- Python **3.11** or newer

### Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
```

Edit `.env`:
```ini
BOT_TOKEN="1234567890:AAH_your_bot_token_here"
ADMIN_IDS="123456789"
WHITELIST_ENABLED="true"
DB_PATH="channel_help_bot.db"
LOG_LEVEL="INFO"
```

### Start the Bot (Long Polling)

```bash
python3 -m bot.main
```

### Run Unit Tests

```bash
pytest -v
# or using standard library unittest:
python3 -m unittest discover -s tests -v
```


---

## 4. Vote Buttons (unique vote per user)

In the button builder, write `vote` instead of a URL:

```text
👍 Like - vote | 👎 Dislike - vote
Website - https://example.com
```

- **One vote per user per post** (database PRIMARY KEY on `post token + user_id`).
  Tap another option to **change** the vote, tap the same option again to **withdraw** it.
- The counter is shown live on the button (`👍 Like · 12`). Counter edits are coalesced
  (many votes in a second → one `editMessageReplyMarkup`) to stay inside Telegram rate limits.
- **Every voter sees their own choice privately** (`✅ Your vote: 👍 Like`) through the
  `answerCallbackQuery` toast, so nobody else sees it.
- Subscribers are not on `ADMIN_IDS`; vote presses (`v:<token>:<option>`) bypass the whitelist
  automatically, all other callbacks stay protected.
- Editing buttons of a published post keeps existing votes (option ids are stable and never reused).
- Existing databases are migrated automatically (`posts.vote_token` + `votes` table).

### Optional: Bot API 10.3 personal rich-button card (experimental)

Bot API 10.3 (Aug 24, 2026) added `RichMessageButton` / `RichBlockButtons` and ephemeral
messages (`EphemeralMessageParameters`). With `VOTE_EPHEMERAL_CARD="true"` the bot also sends each
voter a card that only they can see, where their own choice is highlighted green.
aiogram 3.x has no models for these yet, so `bot/utils/bot_api_103.py` sends them as raw API calls.
Ephemeral messages are documented for groups; if Telegram rejects the call for a channel the bot
silently falls back to the normal private toast. Default is `false`.


---

## 5. Rich Buttons (Bot API 10.3, Aug 24 2026)

When you publish a post that has buttons, the bot no longer attaches a normal inline keyboard.
It re-creates your message as a **Rich Message** and puts the buttons inside it as
`RichMessageButton` blocks (`{"type":"buttons","buttons":[...],"align":"center"}`):

```text
[ media block (photo / video / GIF / audio / voice / document) ]
[ paragraph block: your text/caption with bold, italic, links, spoilers, code, custom emoji ]
[ buttons block per row: URL buttons and 🗳 vote buttons ]
```

- Same button syntax as before (`Text - https://url`, `Text - vote`); each row = one buttons block (max 8).
- In the preview screen use **🟢 Rich Buttons (API 10.3): ON/OFF** to switch per post.
  Default comes from `RICH_BUTTONS` in `.env`. The bot re-sends the preview after toggling.
- Editing buttons of a published post and live vote counters use
  `editMessageText(rich_message=...)` automatically (the post content is stored in the DB).
- If Telegram rejects the rich message, the bot shows the error and keeps the preview screen so you can
  switch Rich Buttons OFF and publish with normal inline buttons.

Known limits of the conversion: `pre`/blockquote entities become inline code / plain text,
forwarded stickers and polls are not supported as rich posts. Posts with only a media file and no
text work; posts longer than 32 768 characters are truncated.
