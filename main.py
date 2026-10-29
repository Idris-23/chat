
import json
import os
import queue
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from tkinter import messagebox, simpledialog

import database
from profile_page import make_avatar
from theme import T, FONT, make_button, theme_toggle

# ---------------------------------------------------------------- .env file
def load_env_file():
    """Reads KEY=value lines from a file called .env next to this script,
    so you don't have to set your API keys in the terminal every time.
    A key already set in the terminal wins over the .env file."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            name, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            if value:
                os.environ.setdefault(name.strip(), value)


load_env_file()


# ---------------------------------------------------------------- AI settings
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
GPT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")        # change if OpenAI renames it
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")  # change if Google renames it
HISTORY_LIMIT = 20  # how many past messages the AI gets as context

KEYS = {"claude": ANTHROPIC_KEY, "openai": OPENAI_KEY, "gemini": GEMINI_KEY}
MODELS = {"claude": CLAUDE_MODEL, "openai": GPT_MODEL, "gemini": GEMINI_MODEL}
NAMES = {"claude": "Claude", "openai": "GPT", "gemini": "Gemini"}

# Which AI do we use?
#  1. The one named in AI_PROVIDER (claude / openai / gemini), if its key is set
#  2. Otherwise the first key found, in the order: Claude, GPT, Gemini
#  3. Otherwise offline mode
wanted = os.environ.get("AI_PROVIDER", "").strip().lower()
if wanted in KEYS and KEYS[wanted]:
    PROVIDER = wanted
else:
    PROVIDER = next((name for name, key in KEYS.items() if key), None)
PROVIDER_LABEL = f"{NAMES[PROVIDER]} · {MODELS[PROVIDER]}" if PROVIDER else "Offline mode"

OFFLINE_TEXT = ("I'm in offline mode because no API key is set, so I can't "
                "really answer yet.\n\nSet ANTHROPIC_API_KEY, OPENAI_API_KEY or "
                "GEMINI_API_KEY, restart the app, and I'll reply for real.")


# ---------------------------------------------------------------- AI (streaming)
def sse_events(request):
    """Sends the request and yields each streamed event (both APIs stream this way).

    The server sends lines like:   data: {"some": "json"}
    """
    with urllib.request.urlopen(request, timeout=180) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload:
                continue
            if payload == "[DONE]":  # OpenAI's way of saying "finished"
                return
            yield json.loads(payload)


def stream_claude(history):
    # Claude wants the conversation to start with a user message
    history = list(history)
    while history and history[0][0] != "user":
        history.pop(0)

    body = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": 1024,
        "stream": True,  # <- this turns streaming on
        "messages": [{"role": r, "content": c} for r, c in history],
    }).encode()
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    for event in sse_events(request):
        kind = event.get("type")
        if kind == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                yield delta.get("text", "")
        elif kind == "error":
            raise RuntimeError(event.get("error", {}).get("message", "Unknown API error"))
        elif kind == "message_stop":
            return


def stream_openai(history):
    body = json.dumps({
        "model": GPT_MODEL,
        "stream": True,  # <- this turns streaming on
        "messages": [{"role": r, "content": c} for r, c in history],
    }).encode()
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {OPENAI_KEY}",
        },
    )
    for event in sse_events(request):
        if "error" in event:
            raise RuntimeError(event["error"].get("message", "Unknown API error"))
        for choice in event.get("choices", []):
            text = choice.get("delta", {}).get("content")
            if text:
                yield text


def stream_gemini(history):
    # Gemini calls the AI's side "model" (not "assistant"), the chat must start with
    # a user turn, and it prefers turns that alternate, so neighbours of the same
    # role are merged into one.
    contents = []
    for role, text in history:
        role = "user" if role == "user" else "model"
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n\n" + text
        elif contents or role == "user":
            contents.append({"role": role, "parts": [{"text": text}]})

    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
        ":streamGenerateContent?alt=sse",  # alt=sse turns streaming on
        data=json.dumps({"contents": contents}).encode(),
        headers={
            "content-type": "application/json",
            "x-goog-api-key": GEMINI_KEY,
        },
    )
    for event in sse_events(request):
        if "error" in event:
            raise RuntimeError(event["error"].get("message", "Unknown API error"))
        reason = event.get("promptFeedback", {}).get("blockReason")
        if reason:
            raise RuntimeError(f"Gemini blocked this message ({reason}).")
        for candidate in event.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if part.get("text") and not part.get("thought"):  # skip "thinking" notes
                    yield part["text"]


def stream_reply(history):
    """Yields the AI's reply a few words at a time, using whichever AI is set up."""
    if PROVIDER == "claude":
        yield from stream_claude(history)
    elif PROVIDER == "openai":
        yield from stream_openai(history)
    elif PROVIDER == "gemini":
        yield from stream_gemini(history)
    else:
        for word in OFFLINE_TEXT.split(" "):  # fake streaming so you can see the effect
            time.sleep(0.03)
            yield word + " "


def describe_http_error(error):
    raw = error.read().decode(errors="ignore")
    try:
        message = json.loads(raw)["error"]["message"]
    except Exception:
        message = raw[:300]
    return f"API error {error.code}: {message}"


# ---------------------------------------------------------------- dashboard
class DashboardFrame(tk.Frame):
    def __init__(self, parent, user_id, username, on_logout, on_profile,
                 on_toggle_theme, open_id=None):
        super().__init__(parent, bg=T.BG)
        self.user_id = user_id
        self.username = username
        self.on_logout = on_logout
        self.on_profile = on_profile
        self.on_toggle_theme = on_toggle_theme

        self.events = queue.Queue()   # the background thread drops stream events here
        self.poll_id = None
        self.waiting = False          # True while the AI is replying
        self.current_id = None        # id of the conversation on screen
        self.conversations = []       # list of (id, title) shown in the sidebar
        self.stream_conv = None       # conversation the AI is replying in
        self.stream_text = ""         # the reply written so far
        self.stream_visible = False   # is the reply being drawn on screen?

        profile = database.get_profile(user_id)
        self.display_name = profile["display_name"] or username

        # ----- header (top, full width) -----
        header = tk.Frame(self, bg=T.CARD, padx=20, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="💬 Mini ChatGPT", font=(FONT, 14, "bold"),
                 bg=T.CARD, fg=T.TEXT).pack(side="left")
        tk.Label(header, text=PROVIDER_LABEL, font=(FONT, 9), bg=T.CARD,
                 fg=T.MUTED).pack(side="left", padx=12)
        make_button(header, "Log out", lambda: self.guard(self.on_logout),
                    primary=False, size=10, padx=14, pady=6).pack(side="right")
        make_button(header, "Delete chat", self.delete_chat,
                    primary=False, size=10, padx=14, pady=6).pack(side="right", padx=8)
        theme_toggle(header, lambda: self.guard(lambda: self.on_toggle_theme(self.current_id)),
                     bg=T.CARD).pack(side="right", padx=8)

        # picture + name: click to open your profile
        user_box = tk.Frame(header, bg=T.CARD, cursor="hand2")
        user_box.pack(side="right", padx=12)
        avatar = make_avatar(user_box, 34, profile["avatar"], self.display_name, T.CARD)
        avatar.pack(side="left")
        name_label = tk.Label(user_box, text=self.display_name, font=(FONT, 10, "bold"),
                              bg=T.CARD, fg=T.TEXT, cursor="hand2")
        name_label.pack(side="left", padx=8)
        for widget in (user_box, avatar, name_label):
            widget.bind("<Button-1>",
                        lambda e: self.guard(lambda: self.on_profile(self.current_id)))

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True)

        # ----- sidebar (left) -----
        sidebar = tk.Frame(body, bg=T.SIDEBAR, width=250)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)  # keep the width fixed

        make_button(sidebar, "+  New chat", self.new_chat, size=10, pady=10).pack(
            fill="x", padx=12, pady=12)

        tk.Label(sidebar, text="Double-click a chat to rename it", font=(FONT, 8),
                 bg=T.SIDEBAR, fg=T.MUTED).pack(side="bottom", pady=8)

        self.listbox = tk.Listbox(
            sidebar, bg=T.SIDEBAR, fg=T.TEXT, font=(FONT, 11), borderwidth=0,
            highlightthickness=0, activestyle="none", selectbackground=T.ACCENT,
            selectforeground="white", exportselection=False,
        )
        self.listbox.pack(fill="both", expand=True, padx=(8, 0))
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.listbox.bind("<Double-Button-1>", self.rename_chat)

        # ----- main area (right) -----
        main = tk.Frame(body, bg=T.BG)
        main.pack(side="left", fill="both", expand=True)

        # bottom parts are packed first so they always stay visible
        input_bar = tk.Frame(main, bg=T.CARD, padx=20, pady=14)
        input_bar.pack(side="bottom", fill="x")
        self.entry = tk.Entry(
            input_bar, font=(FONT, 12), bg=T.INPUT, fg=T.TEXT, insertbackground=T.TEXT,
            relief="flat", highlightthickness=2, highlightbackground=T.INPUT,
            highlightcolor=T.ACCENT,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=9)
        self.entry.bind("<Return>", lambda e: self.send())
        make_button(input_bar, "Send", self.send, size=10, padx=22, pady=9).pack(
            side="left", padx=(10, 0))

        self.status = tk.Label(main, text="", font=(FONT, 9, "italic"), bg=T.BG, fg=T.MUTED)
        self.status.pack(side="bottom", anchor="w", padx=22, pady=(0, 4))

        area = tk.Frame(main, bg=T.BG)
        area.pack(fill="both", expand=True)
        scrollbar = tk.Scrollbar(area)
        scrollbar.pack(side="right", fill="y")
        self.chat = tk.Text(
            area, bg=T.BG, fg=T.TEXT, wrap="word", relief="flat", font=(FONT, 11),
            padx=20, pady=15, highlightthickness=0, state="disabled",
            yscrollcommand=scrollbar.set, spacing3=2,
        )
        self.chat.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.chat.yview)

        # Styles: your messages on the right, the AI's on the left
        self.chat.tag_config("user_name", justify="right", foreground=T.ACCENT_HOVER,
                             font=(FONT, 9, "bold"), lmargin1=120, lmargin2=120, rmargin=10)
        self.chat.tag_config("user_body", justify="right", foreground=T.TEXT,
                             lmargin1=120, lmargin2=120, rmargin=10)
        self.chat.tag_config("bot_name", foreground=T.GREEN, font=(FONT, 9, "bold"),
                             lmargin1=10, lmargin2=10, rmargin=120)
        self.chat.tag_config("bot_body", foreground=T.TEXT,
                             lmargin1=10, lmargin2=10, rmargin=120)
        self.chat.tag_config("notice", foreground=T.ERROR, font=(FONT, 10, "italic"),
                             lmargin1=10, lmargin2=10, rmargin=120)

        # Open the chat we came from, else the most recent one, else a fresh one
        conversations = database.get_conversations(self.user_id)
        ids = [c[0] for c in conversations]
        if open_id in ids:
            self.open_conversation(open_id)
        elif conversations:
            self.open_conversation(conversations[0][0])
        else:
            self.start_new_conversation()

        self.poll_id = self.after(40, self.process_events)

    def destroy(self):
        if self.poll_id:
            self.after_cancel(self.poll_id)  # stop the timer so it doesn't fire on a dead page
        super().destroy()

    # ---------- small helpers ----------
    def guard(self, action):
        """Run action, unless the AI is in the middle of a reply."""
        if self.waiting:
            messagebox.showinfo("Please wait", "The AI is still replying. Try again in a moment.")
            return
        action()

    def append_text(self, text, tag):
        self.chat.config(state="normal")
        self.chat.insert(tk.END, text, tag)
        self.chat.config(state="disabled")
        self.chat.see(tk.END)

    def show_message(self, role, text):
        """Draws one finished message in the chat area (does not save it)."""
        side = "user" if role == "user" else "bot"
        name = "You" if role == "user" else "AI"
        self.append_text(name + "\n", side + "_name")
        self.append_text(text + "\n\n", side + "_body")

    def clear_view(self):
        self.chat.config(state="normal")
        self.chat.delete("1.0", tk.END)
        self.chat.config(state="disabled")

    def greet(self):
        text = f"Hi {self.display_name}! How can I help you today?"
        if PROVIDER is None:
            text += "\n\n(Offline mode: no API key found. Set ANTHROPIC_API_KEY, OPENAI_API_KEY or GEMINI_API_KEY.)"
        self.show_message("assistant", text)

    def set_waiting(self, waiting):
        self.waiting = waiting
        self.status.config(text="AI is thinking..." if waiting else "")

    # ---------- sidebar ----------
    def refresh_sidebar(self):
        """Reloads the list of chats and highlights the one on screen."""
        self.conversations = database.get_conversations(self.user_id)
        self.listbox.delete(0, tk.END)
        for conversation_id, title in self.conversations:
            self.listbox.insert(tk.END, f"   {title}")
            if conversation_id == self.current_id:
                index = self.listbox.size() - 1
                self.listbox.selection_set(index)
                self.listbox.see(index)

    def on_select(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        conversation_id = self.conversations[selection[0]][0]
        if conversation_id != self.current_id:
            self.open_conversation(conversation_id)

    def open_conversation(self, conversation_id):
        """Shows a saved conversation in the chat area."""
        self.current_id = conversation_id
        self.clear_view()
        self.stream_visible = False
        messages = database.get_messages(conversation_id)
        if not messages:
            self.greet()
        for role, content in messages:
            self.show_message(role, content)

        # Came back to a chat the AI is still writing in: show what it has so far
        if self.waiting and self.stream_conv == conversation_id and self.stream_text:
            self.append_text("AI\n", "bot_name")
            self.append_text(self.stream_text, "bot_body")
            self.stream_visible = True

        self.refresh_sidebar()
        self.entry.focus_set()

    def start_new_conversation(self):
        conversation_id = database.create_conversation(self.user_id)
        self.open_conversation(conversation_id)

    def new_chat(self):
        # If the current chat is still empty, there's no need for another one
        if self.current_id and not database.get_messages(self.current_id):
            self.entry.focus_set()
            return
        self.start_new_conversation()

    def rename_chat(self, event):
        index = self.listbox.nearest(event.y)
        box = self.listbox.bbox(index)
        if index >= len(self.conversations) or not box or event.y > box[1] + box[3]:
            return  # the double-click was on empty space
        conversation_id, title = self.conversations[index]
        name = simpledialog.askstring("Rename chat", "New name:",
                                      initialvalue=title, parent=self)
        if name and name.strip():
            database.rename_conversation(conversation_id, name.strip()[:40])
            self.refresh_sidebar()

    def delete_chat(self):
        if not messagebox.askyesno("Delete chat", "Delete this conversation?"):
            return
        database.delete_conversation(self.current_id)
        self.current_id = None
        remaining = database.get_conversations(self.user_id)
        if remaining:
            self.open_conversation(remaining[0][0])
        else:
            self.start_new_conversation()

    def auto_title(self, text):
        """Names a brand-new chat after the first thing the user types."""
        for conversation_id, title in self.conversations:
            if conversation_id == self.current_id and title == database.DEFAULT_TITLE:
                short = text if len(text) <= 30 else text[:30].rstrip() + "…"
                database.rename_conversation(conversation_id, short)

    # ---------- sending + streaming ----------
    def send(self):
        text = self.entry.get().strip()
        if not text or self.waiting:
            return
        self.entry.delete(0, tk.END)

        conversation_id = self.current_id
        database.add_message(self.user_id, conversation_id, "user", text)
        self.show_message("user", text)
        self.auto_title(text)
        self.refresh_sidebar()

        self.set_waiting(True)
        self.stream_conv = conversation_id
        self.stream_text = ""
        self.stream_visible = False

        history = database.get_messages(conversation_id, HISTORY_LIMIT)
        threading.Thread(target=self.worker, args=(conversation_id, history),
                         daemon=True).start()

    def worker(self, conversation_id, history):
        """Runs in the background: collects the streamed reply and reports back."""
        parts = []
        try:
            for chunk in stream_reply(history):
                parts.append(chunk)
                self.events.put(("chunk", conversation_id, chunk))
            self.events.put(("done", conversation_id, "".join(parts)))
        except urllib.error.HTTPError as e:
            self.events.put(("error", conversation_id, ("".join(parts), describe_http_error(e))))
        except Exception as e:
            self.events.put(("error", conversation_id, ("".join(parts), f"Error: {e}")))

    def process_events(self):
        """Runs every 40 ms on the main thread and draws whatever the worker sent."""
        try:
            while True:
                kind, conversation_id, payload = self.events.get_nowait()
                if kind == "chunk":
                    self.on_chunk(conversation_id, payload)
                else:
                    self.on_finished(kind, conversation_id, payload)
        except queue.Empty:
            pass
        self.poll_id = self.after(40, self.process_events)

    def on_chunk(self, conversation_id, text):
        self.stream_text += text
        if conversation_id != self.current_id:
            return  # the user is looking at another chat; the text is kept for later
        if not self.stream_visible:
            self.append_text("AI\n", "bot_name")
            self.stream_visible = True
            self.status.config(text="AI is typing...")
        self.append_text(text, "bot_body")

    def on_finished(self, kind, conversation_id, payload):
        self.set_waiting(False)
        if kind == "done":
            reply, error = payload, None
        else:
            reply, error = payload

        # The chat might have been deleted while the AI was replying
        exists = any(c[0] == conversation_id for c in self.conversations)
        if exists and reply.strip():
            database.add_message(self.user_id, conversation_id, "assistant", reply)

        if exists and conversation_id == self.current_id:
            if self.stream_visible:
                self.append_text("\n\n", "bot_body")
            elif reply.strip():
                self.show_message("assistant", reply)
            if error:
                self.append_text(f"⚠ {error}\n\n", "notice")

        self.stream_conv = None
        self.stream_text = ""
        self.stream_visible = False
        self.refresh_sidebar()