import React, { useState } from 'react';
import {
  Send,
  Plus,
  Trash2,
  ExternalLink,
  VolumeX,
  Lock,
  Pin,
  Image as ImageIcon,
  Film,
  FileText,
  Music,
  Mic,
  Sparkles,
  Check,
  AlertTriangle,
  CornerUpRight,
} from 'lucide-react';
import {
  ParsedButton,
  parseButtonsText,
  removeButtonByPosition,
  formatButtonsDsl,
} from '../utils/buttonParser';

export type ContentType =
  | 'text'
  | 'photo'
  | 'video'
  | 'document'
  | 'animation'
  | 'audio'
  | 'voice';

export interface ConnectedChannel {
  channelId: number;
  title: string;
  username: string;
  botIsAdmin: boolean;
  botCanPost: boolean;
  botCanEdit: boolean;
  userIsAdmin: boolean;
}

export interface PublishedPost {
  id: number;
  channelId: number;
  channelTitle: string;
  channelUsername: string;
  sourceChatId: number;
  sourceMessageId: number;
  channelMessageId: number;
  contentType: ContentType;
  text: string;
  mediaLabel?: string;
  buttons: ParsedButton[][];
  silent: boolean;
  protectContent: boolean;
  pinned: boolean;
  createdAt: string;
}

type FsmState =
  | 'IDLE'
  | 'WAITING_FOR_CHANNEL'
  | 'CHOOSING_CHANNEL'
  | 'WAITING_FOR_CONTENT'
  | 'MANAGING_BUTTONS'
  | 'WAITING_FOR_BUTTONS_INPUT'
  | 'PREVIEWING'
  | 'VIEWING_MY_POSTS'
  | 'VIEWING_SINGLE_POST'
  | 'EDITING_PUBLISHED_BUTTONS'
  | 'CONFIRM_DELETE_POST';

type SimulatedErrorMode =
  | 'none'
  | 'retry_after_429'
  | 'bot_not_admin'
  | 'chat_not_found'
  | 'bot_kicked';

interface ChatLogEntry {
  id: number;
  sender: 'user' | 'bot';
  text: string;
  contentType?: ContentType;
  mediaLabel?: string;
  urlButtons?: ParsedButton[][];
  timestamp: string;
  apiMethodTag?: string;
}

const INITIAL_CHANNELS: ConnectedChannel[] = [
  {
    channelId: -1001948271042,
    title: 'Python Engineering Dispatch',
    username: 'py_eng_dispatch',
    botIsAdmin: true,
    botCanPost: true,
    botCanEdit: true,
    userIsAdmin: true,
  },
  {
    channelId: -1002084719205,
    title: 'Product Release Notes',
    username: 'product_releases_hq',
    botIsAdmin: true,
    botCanPost: true,
    botCanEdit: true,
    userIsAdmin: true,
  },
];

const INITIAL_POSTS: PublishedPost[] = [
  {
    id: 1,
    channelId: -1001948271042,
    channelTitle: 'Python Engineering Dispatch',
    channelUsername: 'py_eng_dispatch',
    sourceChatId: 74920184,
    sourceMessageId: 102,
    channelMessageId: 4018,
    contentType: 'photo',
    text: '<b>aiogram 3.x + SQLite Publisher Released</b>\n\nAll posts are published using classic <code>copyMessage</code> with full formatting entity preservation and inline URL keyboards.',
    mediaLabel: 'release_architecture_diagram.png (1280×720)',
    buttons: [
      [
        { text: 'Read Documentation', url: 'https://docs.aiogram.dev' },
        { text: 'GitHub Repository', url: 'https://github.com/aiogram/aiogram' },
      ],
      [{ text: 'Open Discussion', url: 'tg://resolve?domain=aiogram_ru' }],
    ],
    silent: false,
    protectContent: false,
    pinned: true,
    createdAt: '14:20 UTC',
  },
];

function renderFormattedTelegramHtml(raw: string): React.ReactNode {
  // Safe lightweight renderer for <b>, <i>, <code>, <pre> in simulator preview
  const lines = raw.split('\n');
  return lines.map((line, idx) => (
    <React.Fragment key={idx}>
      {idx > 0 && <br />}
      <span
        dangerouslySetInnerHTML={{
          __html: line
            .replace(/&(?!amp;|lt;|gt;|quot;)/g, '&amp;')
            .replace(/<(?!\/?(b|i|u|s|code|pre)\b)/gi, '&lt;'),
        }}
      />
    </React.Fragment>
  ));
}

export const BotSimulator: React.FC = () => {
  const [channels, setChannels] = useState<ConnectedChannel[]>(INITIAL_CHANNELS);
  const [posts, setPosts] = useState<PublishedPost[]>(INITIAL_POSTS);
  const [activeChannelViewId, setActiveChannelViewId] = useState<number>(
    INITIAL_CHANNELS[0].channelId
  );

  const [fsmState, setFsmState] = useState<FsmState>('IDLE');
  const [simulatedError, setSimulatedError] = useState<SimulatedErrorMode>('none');

  // Draft state (mirrors aiogram FSMContext data)
  const [draftChannel, setDraftChannel] = useState<ConnectedChannel | null>(null);
  const [draftContentType, setDraftContentType] = useState<ContentType>('text');
  const [draftText, setDraftText] = useState<string>('');
  const [draftMediaLabel, setDraftMediaLabel] = useState<string>('');
  const [draftSourceMsgId, setDraftSourceMsgId] = useState<number>(105);
  const [draftButtons, setDraftButtons] = useState<ParsedButton[][]>([]);
  const [draftSilent, setDraftSilent] = useState<boolean>(false);
  const [draftProtect, setDraftProtect] = useState<boolean>(false);
  const [draftPin, setDraftPin] = useState<boolean>(false);

  // Selected post in My Posts
  const [selectedPostId, setSelectedPostId] = useState<number | null>(null);
  const [editingPostButtons, setEditingPostButtons] = useState<ParsedButton[][]>([]);

  // Input box state
  const [inputText, setInputText] = useState<string>('');
  const [selectedMediaInput, setSelectedMediaInput] = useState<ContentType>('text');

  // Chat history
  const [chatLog, setChatLog] = useState<ChatLogEntry[]>([
    {
      id: 1,
      sender: 'user',
      text: '/start',
      timestamp: '14:22:01',
    },
    {
      id: 2,
      sender: 'bot',
      text: '👋 <b>Welcome to Channel Help Bot!</b>\n\nCreate formatted posts with URL inline buttons, preview them accurately, and publish or manage them in your Telegram channels.\n\nChoose an option from the menu below:',
      timestamp: '14:22:01',
      apiMethodTag: 'sendMessage',
    },
  ]);

  const nowTime = () => {
    const d = new Date();
    return d.toTimeString().slice(0, 8);
  };

  const appendLog = (entry: Omit<ChatLogEntry, 'id' | 'timestamp'>) => {
    setChatLog((prev) => [
      ...prev,
      {
        ...entry,
        id: prev.length + 1,
        timestamp: nowTime(),
      },
    ]);
  };

  const checkSimulatedError = (): string | null => {
    if (simulatedError === 'retry_after_429') {
      return 'Telegram rate limit hit (HTTP 429). Please wait 14 seconds before trying again.';
    }
    if (simulatedError === 'bot_not_admin') {
      return 'The bot does not have enough administrator rights in the channel. Please enable "Post Messages" and "Edit Messages of Others".';
    }
    if (simulatedError === 'chat_not_found') {
      return 'Channel not found. Make sure the @username is correct and the bot has been added to the channel as an administrator.';
    }
    if (simulatedError === 'bot_kicked') {
      return 'The bot was kicked from the channel. Please re-add the bot as an administrator.';
    }
    return null;
  };

  // Menu triggers
  const triggerMainMenu = () => {
    setFsmState('IDLE');
    appendLog({
      sender: 'bot',
      text: '👋 <b>Channel Help Bot — Main Menu</b>\n\nSelect an action below:',
      apiMethodTag: 'editMessageText',
    });
  };

  const triggerNewPost = () => {
    if (channels.length === 0) {
      setFsmState('IDLE');
      appendLog({
        sender: 'bot',
        text: '⚠️ <b>No Channels Connected</b>\n\nBefore creating a post, connect at least one Telegram channel where the bot is an Administrator.',
        apiMethodTag: 'sendMessage',
      });
      return;
    }
    setFsmState('CHOOSING_CHANNEL');
    appendLog({
      sender: 'bot',
      text: '📝 <b>New Post — Step 1 of 3</b>\n\nSelect the channel you want to publish to:',
      apiMethodTag: 'sendMessage',
    });
  };

  const triggerMyChannels = () => {
    setFsmState('IDLE');
    appendLog({
      sender: 'bot',
      text: `📢 <b>My Channels</b> (${channels.length} connected)\n\nSelect a channel below to verify its <code>getChatMember</code> permissions, or connect a new channel:`,
      apiMethodTag: 'sendMessage',
    });
  };

  const triggerMyPosts = () => {
    setFsmState('VIEWING_MY_POSTS');
    appendLog({
      sender: 'bot',
      text:
        posts.length > 0
          ? `🗂 <b>My Published Posts</b> (${posts.length} active)\n\nSelect a post below to edit its URL buttons or delete it from the channel:`
          : '🗂 <b>My Published Posts</b>\n\nYou have no published posts yet.',
      apiMethodTag: 'sendMessage',
    });
  };

  const triggerHelp = () => {
    setFsmState('IDLE');
    appendLog({
      sender: 'bot',
      text: 'ℹ️ <b>How to Use Channel Help Bot</b>\n\n1. Connect a channel via <b>My Channels</b> (forward a post or send <code>@username</code>).\n2. Tap <b>New Post</b> and send text, photo, video, GIF, document, audio, or voice with formatting.\n3. Add URL buttons using <code>Text - https://url | Second - https://url2</code>.\n4. Preview with <code>copyMessage</code> and publish with Silent, Protected, or Pin options.',
      apiMethodTag: 'sendMessage',
    });
  };

  const handleSelectChannelForPost = (ch: ConnectedChannel) => {
    setDraftChannel(ch);
    setDraftButtons([]);
    setDraftSilent(false);
    setDraftProtect(false);
    setDraftPin(false);
    setFsmState('WAITING_FOR_CONTENT');
    appendLog({
      sender: 'bot',
      text: `📝 <b>New Post for ${ch.title} — Step 2 of 3</b>\n\nSend the post content now. Supported formats:\n• Text message (all formatting entities preserved)\n• Photo, Video, Document, or GIF (Animation) with caption\n• Audio or Voice message with caption`,
      apiMethodTag: 'editMessageText',
    });
  };

  const handleSendInput = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputText.trim();
    if (!trimmed && selectedMediaInput === 'text') return;

    if (trimmed === '/start') {
      appendLog({ sender: 'user', text: '/start' });
      setInputText('');
      triggerMainMenu();
      return;
    }
    if (trimmed === '/help') {
      appendLog({ sender: 'user', text: '/help' });
      setInputText('');
      triggerHelp();
      return;
    }

    // State 1: Connecting a channel
    if (fsmState === 'WAITING_FOR_CHANNEL') {
      appendLog({ sender: 'user', text: trimmed });
      setInputText('');

      const simErr = checkSimulatedError();
      if (simErr) {
        appendLog({
          sender: 'bot',
          text: `❌ <b>Could not connect channel:</b>\n${simErr}`,
          apiMethodTag: 'getChatMember',
        });
        return;
      }

      const cleanHandle = trimmed
        .replace(/^https?:\/\/t\.me\//i, '@')
        .replace(/^@?/, '')
        .split('/')[0];

      if (!cleanHandle || cleanHandle.length < 3) {
        appendLog({
          sender: 'bot',
          text: '⚠️ Please forward a message from your channel or send its public <code>@username</code> (e.g. <code>@my_channel</code>).',
          apiMethodTag: 'sendMessage',
        });
        return;
      }

      const newChan: ConnectedChannel = {
        channelId: -1000000000000 - Math.floor(Math.random() * 8999999999),
        title: cleanHandle
          .split('_')
          .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
          .join(' '),
        username: cleanHandle,
        botIsAdmin: true,
        botCanPost: true,
        botCanEdit: true,
        userIsAdmin: true,
      };

      setChannels((prev) => [
        newChan,
        ...prev.filter((c) => c.username !== newChan.username),
      ]);
      setActiveChannelViewId(newChan.channelId);
      setFsmState('IDLE');
      appendLog({
        sender: 'bot',
        text: `✅ <b>Channel connected!</b>\nChannel: <b>${newChan.title}</b> (@${newChan.username})\nID: <code>${newChan.channelId}</code>\n\nVerified via <code>getChatMember</code>: Bot has <code>can_post_messages</code> &amp; <code>can_edit_messages</code>, and you are <code>administrator</code>.`,
        apiMethodTag: 'getChatMember',
      });
      return;
    }

    // State 2: Waiting for post content
    if (fsmState === 'WAITING_FOR_CONTENT' && draftChannel) {
      const mediaDescriptions: Record<ContentType, string> = {
        text: '',
        photo: 'attached_photo_hd.jpg (1920×1080)',
        video: 'demo_walkthrough.mp4 (01:14 · 1080p)',
        document: 'technical_whitepaper_v2.pdf (2.4 MB)',
        animation: 'feature_preview_loop.gif (GIF Animation)',
        audio: 'episode_42_podcast.mp3 (24:10 · Audio)',
        voice: 'founder_voice_note.ogg (00:48 · Voice)',
      };
      const mediaLabel = mediaDescriptions[selectedMediaInput];
      const msgText = trimmed || `New ${selectedMediaInput} post for ${draftChannel.title}`;
      const nextMsgId = draftSourceMsgId + 1;

      appendLog({
        sender: 'user',
        text: msgText,
        contentType: selectedMediaInput,
        mediaLabel: mediaLabel || undefined,
      });

      setDraftContentType(selectedMediaInput);
      setDraftText(msgText);
      setDraftMediaLabel(mediaLabel);
      setDraftSourceMsgId(nextMsgId);
      setInputText('');
      setFsmState('MANAGING_BUTTONS');

      appendLog({
        sender: 'bot',
        text: `🔗 <b>Button Builder — ${draftChannel.title}</b>\nPost type: <code>${selectedMediaInput}</code> · Stored <code>chat_id=74920184, message_id=${nextMsgId}</code>\n\nSend URL buttons in text format (one row per line, multiple buttons in a row separated by <code>|</code>):\n<pre>Read Guide - https://example.com/guide\nWebsite - https://example.com | Community - tg://resolve?domain=telegram</pre>`,
        apiMethodTag: 'sendMessage',
      });
      return;
    }

    // State 3: Adding buttons in draft Button Builder
    if (
      fsmState === 'MANAGING_BUTTONS' ||
      fsmState === 'WAITING_FOR_BUTTONS_INPUT'
    ) {
      appendLog({ sender: 'user', text: trimmed });
      setInputText('');
      try {
        const updated = parseButtonsText(trimmed, draftButtons);
        setDraftButtons(updated);
        setFsmState('MANAGING_BUTTONS');
        const totalBtns = updated.reduce((acc, r) => acc + r.length, 0);
        appendLog({
          sender: 'bot',
          text: `✅ <b>Added URL buttons!</b>\nTotal: <b>${totalBtns}</b> button(s) across <b>${updated.length}</b> row(s).\n<pre>${formatButtonsDsl(updated)}</pre>`,
          apiMethodTag: 'sendMessage',
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        appendLog({
          sender: 'bot',
          text: `❌ <b>Invalid button format:</b>\n${msg}\n\nPlease fix and send again:`,
          apiMethodTag: 'sendMessage',
        });
      }
      return;
    }

    // State 4: Adding buttons to an already published post
    if (fsmState === 'EDITING_PUBLISHED_BUTTONS' && selectedPostId !== null) {
      appendLog({ sender: 'user', text: trimmed });
      setInputText('');
      try {
        const updated = parseButtonsText(trimmed, editingPostButtons);
        setEditingPostButtons(updated);
        const totalBtns = updated.reduce((acc, r) => acc + r.length, 0);
        appendLog({
          sender: 'bot',
          text: `🔗 <b>Updated Draft Buttons for Post #${selectedPostId}</b> (${totalBtns} buttons):\n<pre>${formatButtonsDsl(updated)}</pre>\nTap <b>Save Buttons to Channel Post</b> below to commit via <code>editMessageReplyMarkup</code>.`,
          apiMethodTag: 'sendMessage',
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        appendLog({
          sender: 'bot',
          text: `❌ <b>Invalid button format:</b>\n${msg}`,
          apiMethodTag: 'sendMessage',
        });
      }
      return;
    }

    // Default fallback
    appendLog({ sender: 'user', text: trimmed });
    setInputText('');
    appendLog({
      sender: 'bot',
      text: 'Choose an action from the menu below (`New Post`, `My Channels`, `My Posts`, or `Help`).',
      apiMethodTag: 'sendMessage',
    });
  };

  const handleShowPreview = () => {
    if (!draftChannel) return;
    setFsmState('PREVIEWING');
    appendLog({
      sender: 'bot',
      text: draftText,
      contentType: draftContentType,
      mediaLabel: draftMediaLabel || undefined,
      urlButtons: draftButtons,
      apiMethodTag: 'copyMessage',
    });
    appendLog({
      sender: 'bot',
      text: `👁 <b>Post Preview for ${draftChannel.title}</b>\nThe message above was generated via <code>copyMessage</code> with your <code>InlineKeyboardMarkup</code> URL buttons.`,
      apiMethodTag: 'sendMessage',
    });
  };

  const handlePublishPost = () => {
    if (!draftChannel) return;
    const simErr = checkSimulatedError();
    if (simErr) {
      appendLog({
        sender: 'bot',
        text: `❌ <b>Publishing failed:</b>\n${simErr}`,
        apiMethodTag: 'copyMessage',
      });
      return;
    }

    const newChannelMsgId = 4020 + posts.length * 3;
    const newPost: PublishedPost = {
      id: posts.length > 0 ? Math.max(...posts.map((p) => p.id)) + 1 : 1,
      channelId: draftChannel.channelId,
      channelTitle: draftChannel.title,
      channelUsername: draftChannel.username,
      sourceChatId: 74920184,
      sourceMessageId: draftSourceMsgId,
      channelMessageId: newChannelMsgId,
      contentType: draftContentType,
      text: draftText,
      mediaLabel: draftMediaLabel || undefined,
      buttons: draftButtons,
      silent: draftSilent,
      protectContent: draftProtect,
      pinned: draftPin,
      createdAt: `${nowTime().slice(0, 5)} UTC`,
    };

    setPosts((prev) => [newPost, ...prev]);
    setActiveChannelViewId(draftChannel.channelId);
    setFsmState('IDLE');

    appendLog({
      sender: 'bot',
      text: `✅ <b>Post #${newPost.id} Published Successfully!</b>\n\nChannel: <b>${draftChannel.title}</b> (@${draftChannel.username})\nChannel Message ID: <code>${newChannelMsgId}</code>${draftPin ? '\n📌 Pinned in channel via <code>pinChatMessage</code>' : ''}`,
      apiMethodTag: draftPin ? 'copyMessage + pinChatMessage' : 'copyMessage',
    });
  };

  const handleSaveEditedPublishedButtons = () => {
    if (selectedPostId === null) return;
    const simErr = checkSimulatedError();
    if (simErr) {
      appendLog({
        sender: 'bot',
        text: `❌ <b>Failed to update buttons:</b>\n${simErr}`,
        apiMethodTag: 'editMessageReplyMarkup',
      });
      return;
    }

    setPosts((prev) =>
      prev.map((p) =>
        p.id === selectedPostId ? { ...p, buttons: editingPostButtons } : p
      )
    );
    setFsmState('VIEWING_SINGLE_POST');
    appendLog({
      sender: 'bot',
      text: `✅ <b>Buttons updated on channel post #${selectedPostId}!</b>\nApplied live via <code>editMessageReplyMarkup</code>.`,
      apiMethodTag: 'editMessageReplyMarkup',
    });
  };

  const handleDeletePublishedPost = (postId: number) => {
    const target = posts.find((p) => p.id === postId);
    if (!target) return;

    const simErr = checkSimulatedError();
    if (simErr) {
      appendLog({
        sender: 'bot',
        text: `❌ <b>Failed to delete post:</b>\n${simErr}`,
        apiMethodTag: 'deleteMessage',
      });
      return;
    }

    setPosts((prev) => prev.filter((p) => p.id !== postId));
    setSelectedPostId(null);
    setFsmState('VIEWING_MY_POSTS');
    appendLog({
      sender: 'bot',
      text: `🗑 <b>Post #${postId} deleted from ${target.channelTitle}</b> (channel message <code>${target.channelMessageId}</code> removed via <code>deleteMessage</code>).`,
      apiMethodTag: 'deleteMessage',
    });
  };

  const selectedPost = posts.find((p) => p.id === selectedPostId) || null;
  const activeChannel =
    channels.find((c) => c.channelId === activeChannelViewId) || channels[0];
  const channelPosts = posts.filter(
    (p) => activeChannel && p.channelId === activeChannel.channelId
  );

  return (
    <div className="space-y-6">
      {/* Simulator Toolbar: Scenario Quick-Actions & Error Handling Injection */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white border border-slate-200 rounded-xl p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs font-semibold text-slate-700">
            Quick Demo Presets:
          </span>
          <button
            type="button"
            onClick={() => {
              const ch = channels[0];
              if (!ch) return;
              setDraftChannel(ch);
              setDraftContentType('photo');
              setDraftText(
                '<b>Python 3.12 Maintenance Update</b>\n\nSecurity and performance patches are now available across all production images. Read the full changelog below.'
              );
              setDraftMediaLabel('python_312_benchmark.png (1600×900)');
              setDraftButtons([
                [
                  { text: 'Release Notes', url: 'https://www.python.org/downloads/' },
                  { text: 'Docker Hub', url: 'https://hub.docker.com/_/python' },
                ],
                [{ text: 'Telegram Dev Chat', url: 'tg://resolve?domain=python' }],
              ]);
              setDraftSilent(false);
              setDraftProtect(false);
              setDraftPin(true);
              setFsmState('PREVIEWING');
              appendLog({
                sender: 'bot',
                text: '<b>Python 3.12 Maintenance Update</b>\n\nSecurity and performance patches are now available across all production images. Read the full changelog below.',
                contentType: 'photo',
                mediaLabel: 'python_312_benchmark.png (1600×900)',
                urlButtons: [
                  [
                    { text: 'Release Notes', url: 'https://www.python.org/downloads/' },
                    { text: 'Docker Hub', url: 'https://hub.docker.com/_/python' },
                  ],
                  [{ text: 'Telegram Dev Chat', url: 'tg://resolve?domain=python' }],
                ],
                apiMethodTag: 'copyMessage',
              });
            }}
            className="px-3 py-1.5 text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition-colors whitespace-nowrap shrink-0"
          >
            Load Sample Post Preview
          </button>
          <button
            type="button"
            onClick={() => {
              setFsmState('WAITING_FOR_CHANNEL');
              appendLog({
                sender: 'bot',
                text: '➕ <b>Connect a Telegram Channel</b>\nForward a message from your channel or send its <code>@username</code>:',
                apiMethodTag: 'sendMessage',
              });
            }}
            className="px-3 py-1.5 text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition-colors whitespace-nowrap shrink-0"
          >
            Test Channel Connection
          </button>
        </div>

        {/* Error Simulation Selector (Requirement 8: 429 retry_after, bot not admin, chat not found, bot kicked) */}
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <label
            htmlFor="error-sim-select"
            className="text-xs font-medium text-slate-600 whitespace-nowrap"
          >
            Simulate Bot API Error:
          </label>
          <select
            id="error-sim-select"
            value={simulatedError}
            onChange={(e) =>
              setSimulatedError(e.target.value as SimulatedErrorMode)
            }
            className="text-xs font-mono bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-600"
          >
            <option value="none">Nominal (200 OK)</option>
            <option value="retry_after_429">429 Too Many Requests (retry_after)</option>
            <option value="bot_not_admin">400 Bad Request: Bot Not Admin</option>
            <option value="chat_not_found">400 Bad Request: Chat Not Found</option>
            <option value="bot_kicked">403 Forbidden: Bot Kicked from Channel</option>
          </select>
        </div>
      </div>

      {/* Main Split View: Bot Private Chat (Left) & Live Telegram Channel Feed (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* Left Column: @channel_help_bot Interactive Private Chat */}
        <div className="lg:col-span-7 flex flex-col bg-white border border-slate-200 rounded-xl overflow-hidden">
          {/* Chat Header */}
          <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
            <div>
              <h2 className="text-sm font-bold text-slate-900">
                @channel_help_bot
              </h2>
              <p className="text-xs text-slate-500 font-mono">
                FSM State: {fsmState} · Classic Bot API Mode
              </p>
            </div>
            <button
              type="button"
              onClick={triggerMainMenu}
              className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-100 transition-colors whitespace-nowrap shrink-0"
            >
              /start
            </button>
          </div>

          {/* Chat Message Stream */}
          <div className="p-5 space-y-4 max-h-[460px] overflow-y-auto bg-slate-50/50 flex-1">
            {chatLog.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${
                  msg.sender === 'user' ? 'items-end' : 'items-start'
                }`}
              >
                <div
                  className={`max-w-[88%] rounded-xl px-4 py-3 text-sm ${
                    msg.sender === 'user'
                      ? 'bg-sky-700 text-white'
                      : 'bg-white border border-slate-200 text-slate-800'
                  }`}
                >
                  {msg.mediaLabel && (
                    <div
                      className={`mb-2 px-3 py-2 rounded-lg text-xs font-mono flex items-center gap-2 ${
                        msg.sender === 'user'
                          ? 'bg-sky-800 text-sky-100'
                          : 'bg-slate-100 text-slate-700'
                      }`}
                    >
                      <Sparkles className="w-3.5 h-3.5 shrink-0" />
                      <span>
                        [{msg.contentType?.toUpperCase()}] {msg.mediaLabel}
                      </span>
                    </div>
                  )}
                  <div className="leading-relaxed break-words">
                    {renderFormattedTelegramHtml(msg.text)}
                  </div>

                  {/* Classic URL InlineKeyboardMarkup rendered directly under the message */}
                  {msg.urlButtons && msg.urlButtons.length > 0 && (
                    <div className="mt-3 pt-2.5 border-t border-slate-200 space-y-1.5">
                      {msg.urlButtons.map((row, rIdx) => (
                        <div key={rIdx} className="grid grid-cols-1 sm:grid-flow-col gap-1.5">
                          {row.map((btn, bIdx) => (
                            <a
                              key={bIdx}
                              href={btn.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-3 py-1.5 bg-slate-100 hover:bg-sky-50 text-sky-700 border border-slate-200 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-colors truncate"
                            >
                              <span className="truncate">{btn.text}</span>
                              <ExternalLink className="w-3 h-3 shrink-0" />
                            </a>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-400 font-mono">
                  <span>{msg.timestamp}</span>
                  {msg.apiMethodTag && (
                    <>
                      <span aria-hidden="true">·</span>
                      <span>API: {msg.apiMethodTag}</span>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Interactive Contextual Inline Keyboard Panel (Depends on FSM State) */}
          <div className="px-5 py-3.5 bg-slate-100/80 border-t border-slate-200">
            <div className="text-xs font-medium text-slate-500 mb-2">
              Active Bot Inline KeyboardMarkup Controls:
            </div>

            {fsmState === 'CHOOSING_CHANNEL' && (
              <div className="flex flex-wrap gap-2">
                {channels.map((ch) => (
                  <button
                    key={ch.channelId}
                    type="button"
                    onClick={() => handleSelectChannelForPost(ch)}
                    className="px-3 py-1.5 text-xs font-semibold bg-white border border-slate-300 hover:border-sky-600 text-slate-800 rounded-lg transition-colors whitespace-nowrap shrink-0"
                  >
                    📢 {ch.title} (@{ch.username})
                  </button>
                ))}
                <button
                  type="button"
                  onClick={triggerMainMenu}
                  className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 text-slate-600 rounded-lg hover:bg-slate-50 whitespace-nowrap shrink-0"
                >
                  ✖️ Cancel
                </button>
              </div>
            )}

            {fsmState === 'WAITING_FOR_CHANNEL' && (
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const forwardedChan: ConnectedChannel = {
                      channelId: -1001889922110,
                      title: 'AI Systems Architecture',
                      username: 'ai_systems_arch',
                      botIsAdmin: true,
                      botCanPost: true,
                      botCanEdit: true,
                      userIsAdmin: true,
                    };
                    const simErr = checkSimulatedError();
                    if (simErr) {
                      appendLog({
                        sender: 'bot',
                        text: `❌ <b>Could not connect channel:</b>\n${simErr}`,
                        apiMethodTag: 'getChatMember',
                      });
                      return;
                    }
                    setChannels((prev) => [
                      forwardedChan,
                      ...prev.filter((c) => c.channelId !== forwardedChan.channelId),
                    ]);
                    setActiveChannelViewId(forwardedChan.channelId);
                    setFsmState('IDLE');
                    appendLog({
                      sender: 'user',
                      text: '[Forwarded from AI Systems Architecture (@ai_systems_arch)]',
                    });
                    appendLog({
                      sender: 'bot',
                      text: `✅ <b>Channel connected via Forwarded Message!</b>\nChannel: <b>${forwardedChan.title}</b> (@${forwardedChan.username})\nVerified via <code>getChatMember</code>: bot has post/edit rights &amp; user is admin.`,
                      apiMethodTag: 'getChatMember',
                    });
                  }}
                  className="px-3 py-1.5 text-xs font-semibold bg-sky-700 hover:bg-sky-800 text-white rounded-lg transition-colors flex items-center gap-1.5 whitespace-nowrap shrink-0"
                >
                  <CornerUpRight className="w-3.5 h-3.5" />
                  <span>Simulate Forwarding Channel Post</span>
                </button>
                <button
                  type="button"
                  onClick={triggerMainMenu}
                  className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 text-slate-600 rounded-lg hover:bg-slate-50 whitespace-nowrap shrink-0"
                >
                  ✖️ Cancel
                </button>
              </div>
            )}

            {(fsmState === 'MANAGING_BUTTONS' ||
              fsmState === 'WAITING_FOR_BUTTONS_INPUT') && (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const sample =
                        'Documentation - https://docs.aiogram.dev | PyPI - https://pypi.org/project/aiogram/';
                      const updated = parseButtonsText(sample, draftButtons);
                      setDraftButtons(updated);
                      appendLog({
                        sender: 'bot',
                        text: `Added sample row:\n<pre>${formatButtonsDsl(updated)}</pre>`,
                        apiMethodTag: 'editMessageText',
                      });
                    }}
                    className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 hover:border-sky-600 text-slate-800 rounded-lg transition-colors flex items-center gap-1 whitespace-nowrap shrink-0"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Quick Add Sample Row</span>
                  </button>

                  {draftButtons.length > 0 && (
                    <button
                      type="button"
                      onClick={() => {
                        setDraftButtons([]);
                        appendLog({
                          sender: 'bot',
                          text: '🧹 All URL buttons cleared.',
                          apiMethodTag: 'editMessageText',
                        });
                      }}
                      className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 hover:border-rose-500 text-rose-700 rounded-lg transition-colors whitespace-nowrap shrink-0"
                    >
                      🧹 Clear All Buttons
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={handleShowPreview}
                    className="px-3 py-1.5 text-xs font-semibold bg-sky-700 hover:bg-sky-800 text-white rounded-lg transition-colors whitespace-nowrap shrink-0"
                  >
                    👁 Preview Post
                  </button>

                  <button
                    type="button"
                    onClick={triggerMainMenu}
                    className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 text-slate-600 rounded-lg hover:bg-slate-50 whitespace-nowrap shrink-0"
                  >
                    ✖️ Cancel
                  </button>
                </div>

                {/* Individual button removal controls */}
                {draftButtons.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {draftButtons.map((row, rIdx) =>
                      row.map((btn, cIdx) => (
                        <button
                          key={`${rIdx}-${cIdx}`}
                          type="button"
                          onClick={() => {
                            const updated = removeButtonByPosition(
                              draftButtons,
                              rIdx,
                              cIdx
                            );
                            setDraftButtons(updated);
                          }}
                          className="px-2.5 py-1 text-xs font-mono bg-white border border-slate-300 hover:border-rose-400 text-slate-700 rounded-md transition-colors whitespace-nowrap shrink-0"
                        >
                          ❌ Remove [{rIdx + 1}.{cIdx + 1}] {btn.text.slice(0, 14)}
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            )}

            {fsmState === 'PREVIEWING' && (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={handlePublishPost}
                    className="px-4 py-1.5 text-xs font-semibold bg-emerald-700 hover:bg-emerald-800 text-white rounded-lg transition-colors whitespace-nowrap shrink-0"
                  >
                    🚀 Publish Now (copyMessage)
                  </button>
                  <button
                    type="button"
                    onClick={() => setFsmState('MANAGING_BUTTONS')}
                    className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 hover:bg-slate-50 text-slate-800 rounded-lg transition-colors whitespace-nowrap shrink-0"
                  >
                    🔗 Edit URL Buttons (
                    {draftButtons.reduce((a, r) => a + r.length, 0)})
                  </button>
                  <button
                    type="button"
                    onClick={triggerMainMenu}
                    className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 text-slate-600 rounded-lg hover:bg-slate-50 whitespace-nowrap shrink-0"
                  >
                    ✖️ Cancel
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setDraftSilent((v) => !v)}
                    className={`px-3 py-1 text-xs font-medium rounded-lg border transition-colors whitespace-nowrap shrink-0 ${
                      draftSilent
                        ? 'bg-sky-50 border-sky-600 text-sky-900'
                        : 'bg-white border-slate-300 text-slate-700'
                    }`}
                  >
                    {draftSilent ? '✅' : '⬜'} Silent Notification
                  </button>
                  <button
                    type="button"
                    onClick={() => setDraftProtect((v) => !v)}
                    className={`px-3 py-1 text-xs font-medium rounded-lg border transition-colors whitespace-nowrap shrink-0 ${
                      draftProtect
                        ? 'bg-sky-50 border-sky-600 text-sky-900'
                        : 'bg-white border-slate-300 text-slate-700'
                    }`}
                  >
                    {draftProtect ? '✅' : '⬜'} Protect Content
                  </button>
                  <button
                    type="button"
                    onClick={() => setDraftPin((v) => !v)}
                    className={`px-3 py-1 text-xs font-medium rounded-lg border transition-colors whitespace-nowrap shrink-0 ${
                      draftPin
                        ? 'bg-sky-50 border-sky-600 text-sky-900'
                        : 'bg-white border-slate-300 text-slate-700'
                    }`}
                  >
                    {draftPin ? '✅' : '⬜'} Pin After Publish
                  </button>
                </div>
              </div>
            )}

            {fsmState === 'VIEWING_MY_POSTS' && (
              <div className="flex flex-wrap gap-2">
                {posts.map((post) => (
                  <button
                    key={post.id}
                    type="button"
                    onClick={() => {
                      setSelectedPostId(post.id);
                      setFsmState('VIEWING_SINGLE_POST');
                      appendLog({
                        sender: 'bot',
                        text: `🗂 <b>Published Post #${post.id}</b>\nChannel: <b>${post.channelTitle}</b> · Msg ID: <code>${post.channelMessageId}</code>\nButtons: <b>${post.buttons.reduce((a, r) => a + r.length, 0)}</b>`,
                        apiMethodTag: 'editMessageText',
                      });
                    }}
                    className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 hover:border-sky-600 text-slate-800 rounded-lg transition-colors whitespace-nowrap shrink-0"
                  >
                    #{post.id} [{post.channelTitle.slice(0, 16)}] (
                    {post.buttons.reduce((a, r) => a + r.length, 0)}🔗)
                  </button>
                ))}
                <button
                  type="button"
                  onClick={triggerMainMenu}
                  className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 text-slate-600 rounded-lg hover:bg-slate-50 whitespace-nowrap shrink-0"
                >
                  ⬅️ Back to Menu
                </button>
              </div>
            )}

            {fsmState === 'VIEWING_SINGLE_POST' && selectedPost && (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setEditingPostButtons(selectedPost.buttons);
                    setFsmState('EDITING_PUBLISHED_BUTTONS');
                    appendLog({
                      sender: 'bot',
                      text: `🔗 <b>Editing Buttons for Post #${selectedPost.id}</b>\nSend new button lines to append, or remove buttons below, then tap <b>Save Buttons to Channel Post</b>.`,
                      apiMethodTag: 'editMessageText',
                    });
                  }}
                  className="px-3 py-1.5 text-xs font-semibold bg-sky-700 hover:bg-sky-800 text-white rounded-lg transition-colors whitespace-nowrap shrink-0"
                >
                  🔗 Edit URL Buttons
                </button>
                <button
                  type="button"
                  onClick={() => handleDeletePublishedPost(selectedPost.id)}
                  className="px-3 py-1.5 text-xs font-semibold bg-rose-700 hover:bg-rose-800 text-white rounded-lg transition-colors whitespace-nowrap shrink-0"
                >
                  🗑 Delete from Channel (deleteMessage)
                </button>
                <button
                  type="button"
                  onClick={triggerMyPosts}
                  className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 whitespace-nowrap shrink-0"
                >
                  ⬅️ Back to My Posts
                </button>
              </div>
            )}

            {fsmState === 'EDITING_PUBLISHED_BUTTONS' && selectedPost && (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={handleSaveEditedPublishedButtons}
                    className="px-3 py-1.5 text-xs font-semibold bg-emerald-700 hover:bg-emerald-800 text-white rounded-lg transition-colors whitespace-nowrap shrink-0"
                  >
                    💾 Save Buttons to Channel Post (editMessageReplyMarkup)
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingPostButtons([])}
                    className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 text-rose-700 rounded-lg hover:bg-rose-50 whitespace-nowrap shrink-0"
                  >
                    🧹 Clear All
                  </button>
                  <button
                    type="button"
                    onClick={() => setFsmState('VIEWING_SINGLE_POST')}
                    className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 whitespace-nowrap shrink-0"
                  >
                    ⬅️ Cancel
                  </button>
                </div>
                {editingPostButtons.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {editingPostButtons.map((row, rIdx) =>
                      row.map((btn, cIdx) => (
                        <button
                          key={`${rIdx}-${cIdx}`}
                          type="button"
                          onClick={() =>
                            setEditingPostButtons(
                              removeButtonByPosition(editingPostButtons, rIdx, cIdx)
                            )
                          }
                          className="px-2.5 py-1 text-xs font-mono bg-white border border-slate-300 hover:border-rose-400 text-slate-700 rounded-md whitespace-nowrap shrink-0"
                        >
                          ❌ Remove [{rIdx + 1}.{cIdx + 1}] {btn.text.slice(0, 14)}
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            )}

            {fsmState === 'IDLE' && (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setFsmState('WAITING_FOR_CHANNEL');
                    appendLog({
                      sender: 'bot',
                      text: '➕ <b>Connect a Telegram Channel</b>\nForward any message from your channel or send its <code>@username</code>:',
                      apiMethodTag: 'editMessageText',
                    });
                  }}
                  className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 hover:border-sky-600 text-slate-800 rounded-lg transition-colors whitespace-nowrap shrink-0"
                >
                  ➕ Connect Channel
                </button>
                {channels.map((ch) => (
                  <button
                    key={ch.channelId}
                    type="button"
                    onClick={() => {
                      const simErr = checkSimulatedError();
                      appendLog({
                        sender: 'bot',
                        text: simErr
                          ? `❌ <b>Permission check failed for ${ch.title}:</b>\n${simErr}`
                          : `✅ <b>${ch.title} (@${ch.username})</b>\n<code>getChatMember</code> verified: Bot has <code>can_post_messages=True, can_edit_messages=True</code> · User is <code>administrator</code>.`,
                        apiMethodTag: 'getChatMember',
                      });
                    }}
                    className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 hover:border-sky-600 text-slate-700 rounded-lg transition-colors whitespace-nowrap shrink-0"
                  >
                    🔍 Verify @{ch.username}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Message Input Bar + Media Content Type Selector */}
          <form
            onSubmit={handleSendInput}
            className="p-3.5 bg-white border-t border-slate-200 space-y-2.5"
          >
            {fsmState === 'WAITING_FOR_CONTENT' && (
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
                <span className="text-xs text-slate-500 mr-1 shrink-0">
                  Attachment:
                </span>
                {(
                  [
                    { id: 'text', label: 'Text', icon: FileText },
                    { id: 'photo', label: 'Photo', icon: ImageIcon },
                    { id: 'video', label: 'Video', icon: Film },
                    { id: 'animation', label: 'GIF', icon: Sparkles },
                    { id: 'document', label: 'Doc', icon: FileText },
                    { id: 'audio', label: 'Audio', icon: Music },
                    { id: 'voice', label: 'Voice', icon: Mic },
                  ] as const
                ).map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setSelectedMediaInput(item.id)}
                      className={`px-2.5 py-1 text-xs font-medium rounded-md flex items-center gap-1 transition-colors whitespace-nowrap shrink-0 ${
                        selectedMediaInput === item.id
                          ? 'bg-sky-700 text-white'
                          : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                      }`}
                    >
                      <Icon className="w-3 h-3" />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </div>
            )}

            <div className="flex items-center gap-2">
              <input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder={
                  fsmState === 'WAITING_FOR_CHANNEL'
                    ? 'Enter @channel_username (e.g. @devops_daily)...'
                    : fsmState === 'WAITING_FOR_CONTENT'
                    ? 'Write post text or HTML caption (<b>bold</b>, <code>code</code>)...'
                    : fsmState === 'MANAGING_BUTTONS' ||
                      fsmState === 'WAITING_FOR_BUTTONS_INPUT' ||
                      fsmState === 'EDITING_PUBLISHED_BUTTONS'
                    ? 'Text - https://example.com | Second - tg://resolve?domain=telegram'
                    : 'Type a command (/start, /help) or use the ReplyKeyboard below...'
                }
                className="flex-1 text-sm bg-slate-50 border border-slate-300 rounded-lg px-3.5 py-2 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-600"
              />
              <button
                type="submit"
                className="px-4 py-2 bg-sky-700 hover:bg-sky-800 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors whitespace-nowrap shrink-0"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Send</span>
              </button>
            </div>

            {/* Persistent Telegram ReplyKeyboardMarkup */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
              <button
                type="button"
                onClick={triggerNewPost}
                className="py-2 px-3 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition-colors text-center whitespace-nowrap truncate"
              >
                📝 New Post
              </button>
              <button
                type="button"
                onClick={triggerMyChannels}
                className="py-2 px-3 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition-colors text-center whitespace-nowrap truncate"
              >
                📢 My Channels
              </button>
              <button
                type="button"
                onClick={triggerMyPosts}
                className="py-2 px-3 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition-colors text-center whitespace-nowrap truncate"
              >
                🗂 My Posts
              </button>
              <button
                type="button"
                onClick={triggerHelp}
                className="py-2 px-3 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition-colors text-center whitespace-nowrap truncate"
              >
                ℹ️ Help
              </button>
            </div>
          </form>
        </div>

        {/* Right Column: Live Broadcast Channel Output Feed */}
        <div className="lg:col-span-5 flex flex-col bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-slate-200 bg-slate-50 flex items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-bold text-slate-900">
                Live Channel Broadcast View
              </h2>
              <p className="text-xs text-slate-500 font-mono">
                {activeChannel
                  ? `@${activeChannel.username} (${activeChannel.channelId})`
                  : 'Select a channel'}
              </p>
            </div>
            <select
              aria-label="Select broadcast channel view"
              value={activeChannelViewId}
              onChange={(e) => setActiveChannelViewId(Number(e.target.value))}
              className="text-xs font-medium bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-600"
            >
              {channels.map((ch) => (
                <option key={ch.channelId} value={ch.channelId}>
                  {ch.title}
                </option>
              ))}
            </select>
          </div>

          {/* Pinned Message Banner (if any post in this channel is pinned) */}
          {channelPosts.some((p) => p.pinned) && (
            <div className="px-5 py-2 bg-sky-50/70 border-b border-slate-200 flex items-center justify-between text-xs text-slate-700">
              <div className="flex items-center gap-2 truncate">
                <Pin className="w-3.5 h-3.5 text-sky-700 shrink-0" />
                <span className="font-semibold text-sky-900 shrink-0">
                  Pinned Message:
                </span>
                <span className="truncate text-slate-600">
                  {channelPosts
                    .find((p) => p.pinned)
                    ?.text.replace(/<[^>]+>/g, '')}
                </span>
              </div>
              <span className="font-mono text-[11px] text-slate-500 shrink-0 ml-2">
                #{channelPosts.find((p) => p.pinned)?.channelMessageId}
              </span>
            </div>
          )}

          {/* Published Posts Feed */}
          <div className="p-5 space-y-4 flex-1 overflow-y-auto bg-slate-50/30">
            {channelPosts.length === 0 ? (
              <div className="py-12 text-center space-y-3">
                <p className="text-sm font-medium text-slate-700">
                  No posts published to {activeChannel?.title} yet.
                </p>
                <p className="text-xs text-slate-500 max-w-xs mx-auto">
                  Use <b>New Post</b> in the bot chat or click{' '}
                  <b>Load Sample Post Preview</b> above to publish your first
                  post with URL buttons.
                </p>
                <button
                  type="button"
                  onClick={triggerNewPost}
                  className="px-4 py-2 text-xs font-semibold bg-sky-700 hover:bg-sky-800 text-white rounded-lg transition-colors"
                >
                  Create First Channel Post
                </button>
              </div>
            ) : (
              channelPosts.map((post) => (
                <article
                  key={post.id}
                  className="bg-white border border-slate-200 rounded-xl p-4 space-y-3"
                >
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <div className="flex items-center gap-1.5 font-medium text-slate-800">
                      <span>{post.channelTitle}</span>
                      <span aria-hidden="true">·</span>
                      <span className="font-mono text-slate-500">
                        Msg #{post.channelMessageId}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 font-mono text-[11px]">
                      {post.silent && (
                        <span
                          title="Published silently (disable_notification=True)"
                          className="flex items-center gap-0.5 text-slate-500"
                        >
                          <VolumeX className="w-3 h-3" />
                          <span>Silent</span>
                        </span>
                      )}
                      {post.protectContent && (
                        <span
                          title="Protected content (protect_content=True)"
                          className="flex items-center gap-0.5 text-amber-700"
                        >
                          <Lock className="w-3 h-3" />
                          <span>Protected</span>
                        </span>
                      )}
                      {post.pinned && (
                        <span
                          title="Pinned via pinChatMessage"
                          className="flex items-center gap-0.5 text-sky-700"
                        >
                          <Pin className="w-3 h-3" />
                          <span>Pinned</span>
                        </span>
                      )}
                      <span>{post.createdAt}</span>
                    </div>
                  </div>

                  {post.mediaLabel && (
                    <div className="px-3 py-2.5 bg-slate-100 rounded-lg text-xs font-mono text-slate-700 flex items-center justify-between">
                      <span>
                        [{post.contentType.toUpperCase()}] {post.mediaLabel}
                      </span>
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                    </div>
                  )}

                  <div className="text-sm text-slate-800 leading-relaxed break-words">
                    {renderFormattedTelegramHtml(post.text)}
                  </div>

                  {/* InlineKeyboardMarkup URL Buttons */}
                  {post.buttons.length > 0 && (
                    <div className="pt-2 border-t border-slate-100 space-y-1.5">
                      {post.buttons.map((row, rIdx) => (
                        <div
                          key={rIdx}
                          className="grid grid-cols-1 sm:grid-flow-col gap-1.5"
                        >
                          {row.map((btn, bIdx) => (
                            <a
                              key={bIdx}
                              href={btn.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-3 py-1.5 bg-slate-50 hover:bg-sky-50 text-sky-700 border border-slate-200 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-colors truncate"
                            >
                              <span className="truncate">{btn.text}</span>
                              <ExternalLink className="w-3 h-3 shrink-0" />
                            </a>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Direct Shortcut Controls for My Posts actions */}
                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                    <span className="font-mono text-[11px]">
                      SQLite Post ID: #{post.id}
                    </span>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedPostId(post.id);
                          setEditingPostButtons(post.buttons);
                          setFsmState('EDITING_PUBLISHED_BUTTONS');
                          appendLog({
                            sender: 'bot',
                            text: `🔗 <b>Editing Buttons for Post #${post.id}</b>\nSend new button rows in the chat input or remove existing ones, then tap <b>Save Buttons to Channel Post</b>.`,
                            apiMethodTag: 'editMessageText',
                          });
                        }}
                        className="text-sky-700 hover:underline font-medium"
                      >
                        Edit Buttons
                      </button>
                      <span aria-hidden="true">·</span>
                      <button
                        type="button"
                        onClick={() => handleDeletePublishedPost(post.id)}
                        className="text-rose-700 hover:underline font-medium flex items-center gap-1"
                      >
                        <Trash2 className="w-3 h-3" />
                        <span>Delete</span>
                      </button>
                    </div>
                  </div>
                </article>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
