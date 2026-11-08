import envExampleRaw from '../../.env.example?raw';
import requirementsRaw from '../../requirements.txt?raw';
import readmeRaw from '../../README.md?raw';
import botInitRaw from '../../bot/__init__.py?raw';
import botConfigRaw from '../../bot/config.py?raw';
import botDbRaw from '../../bot/db.py?raw';
import botStatesRaw from '../../bot/states.py?raw';
import botKeyboardsRaw from '../../bot/keyboards.py?raw';
import botMainRaw from '../../bot/main.py?raw';
import buttonParserRaw from '../../bot/utils/button_parser.py?raw';
import telegramHelpersRaw from '../../bot/utils/telegram_helpers.py?raw';
import accessMiddlewareRaw from '../../bot/middlewares/access.py?raw';
import startHandlerRaw from '../../bot/handlers/start.py?raw';
import channelsHandlerRaw from '../../bot/handlers/channels.py?raw';
import postsHandlerRaw from '../../bot/handlers/posts.py?raw';
import myPostsHandlerRaw from '../../bot/handlers/my_posts.py?raw';
import votesHandlerRaw from '../../bot/handlers/votes.py?raw';
import botApi103Raw from '../../bot/utils/bot_api_103.py?raw';
import richPostRaw from '../../bot/utils/rich_post.py?raw';
import postRenderRaw from '../../bot/utils/post_render.py?raw';
import testButtonParserRaw from '../../tests/test_button_parser.py?raw';

export interface ProjectFile {
  path: string;
  language: 'python' | 'markdown' | 'ini' | 'text';
  summary: string;
  content: string;
}

export const PROJECT_TREE = `channel-help-bot/
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
│   │   └── votes.py
│   ├── middlewares/
│   │   ├── __init__.py
│   │   └── access.py
│   └── utils/
│       ├── __init__.py
│       ├── bot_api_103.py
│       ├── post_render.py
│       ├── rich_post.py
│       ├── button_parser.py
│       └── telegram_helpers.py
└── tests/
    └── test_button_parser.py`;

export const PROJECT_FILES: ProjectFile[] = [
  {
    path: 'requirements.txt',
    language: 'text',
    summary: 'Python 3.11+ dependencies: aiogram 3.x, aiosqlite, python-dotenv, pytest',
    content: requirementsRaw,
  },
  {
    path: '.env.example',
    language: 'ini',
    summary: 'Environment variables template (BOT_TOKEN, ADMIN_IDS, WHITELIST_ENABLED, DB_PATH, LOG_LEVEL)',
    content: envExampleRaw,
  },
  {
    path: 'README.md',
    language: 'markdown',
    summary: 'Complete documentation with BotFather setup, channel admin permissions guide, and CLI usage',
    content: readmeRaw,
  },
  {
    path: 'bot/__init__.py',
    language: 'python',
    summary: 'Root package initializer',
    content: botInitRaw,
  },
  {
    path: 'bot/config.py',
    language: 'python',
    summary: 'Typed configuration loader reading .env variables and admin whitelist IDs',
    content: botConfigRaw,
  },
  {
    path: 'bot/db.py',
    language: 'python',
    summary: 'Async SQLite (aiosqlite) persistence layer for connected channels and published posts',
    content: botDbRaw,
  },
  {
    path: 'bot/states.py',
    language: 'python',
    summary: 'aiogram 3.x FSM StatesGroup definitions for channel connection, post creation, and editing',
    content: botStatesRaw,
  },
  {
    path: 'bot/utils/button_parser.py',
    language: 'python',
    summary: 'URL button DSL parser, scheme/limit validator, row manipulator, and InlineKeyboardMarkup builder',
    content: buttonParserRaw,
  },
  {
    path: 'bot/utils/telegram_helpers.py',
    language: 'python',
    summary: 'getChatMember channel & admin verification, 429 retry_after handler, and error translator',
    content: telegramHelpersRaw,
  },
  {
    path: 'bot/keyboards.py',
    language: 'python',
    summary: 'Classic ReplyKeyboardMarkup and InlineKeyboardMarkup builders for all menus and workflows',
    content: botKeyboardsRaw,
  },
  {
    path: 'bot/middlewares/access.py',
    language: 'python',
    summary: 'Outer middleware injecting SQLite database handle and enforcing optional user ID whitelist',
    content: accessMiddlewareRaw,
  },
  {
    path: 'bot/handlers/start.py',
    language: 'python',
    summary: '/start, /help, main menu navigation, and global cancel callback handler',
    content: startHandlerRaw,
  },
  {
    path: 'bot/handlers/channels.py',
    language: 'python',
    summary: 'Connect channel via forwarded message or @username with getChatMember admin rights verification',
    content: channelsHandlerRaw,
  },
  {
    path: 'bot/handlers/posts.py',
    language: 'python',
    summary: 'New Post FSM flow: media/entity capture, button builder, copyMessage preview, and channel publish',
    content: postsHandlerRaw,
  },
  {
    path: 'bot/handlers/my_posts.py',
    language: 'python',
    summary: 'My Posts manager: edit live channel post URL buttons (editMessageReplyMarkup) or delete post (deleteMessage)',
    content: myPostsHandlerRaw,
  },
  {
    path: 'bot/handlers/votes.py',
    language: 'python',
    summary: 'Vote button presses: one unique vote per user, private toast, coalesced live counters',
    content: votesHandlerRaw,
  },
  {
    path: 'bot/utils/bot_api_103.py',
    language: 'python',
    summary: 'Optional Bot API 10.3 helpers: RichMessageButton blocks and ephemeral personal card',
    content: botApi103Raw,
  },  {
    path: 'bot/utils/rich_post.py',
    language: 'python',
    summary: 'Converts a message into Bot API 10.3 Rich Message blocks with Rich Buttons',
    content: richPostRaw,
  },
  {
    path: 'bot/utils/post_render.py',
    language: 'python',
    summary: 'Updates buttons of published posts (rich edit or classic reply markup)',
    content: postRenderRaw,
  },

  {
    path: 'bot/main.py',
    language: 'python',
    summary: 'Async entry point configuring logging, SQLite WAL mode, routers, and long polling',
    content: botMainRaw,
  },
  {
    path: 'tests/test_button_parser.py',
    language: 'python',
    summary: '12 unit tests covering single/multi-row parsing, URL validation, Telegram limits, and button removal',
    content: testButtonParserRaw,
  },
];
