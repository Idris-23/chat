
import tkinter as tk
from tkinter import messagebox

import database
from theme import T, FONT, make_button, make_field, theme_toggle
from register import RegisterFrame
from main import DashboardFrame
from profile_page import ProfileFrame


class LoginFrame(tk.Frame):
    def __init__(self, parent, on_success=None, on_go_register=None, on_toggle_theme=None):
        super().__init__(parent, bg=T.BG)
        self.on_success = on_success          # called with (user_id, username)
        self.on_go_register = on_go_register  # shows the register page

        card = tk.Frame(self, bg=T.CARD, padx=40, pady=35)
        card.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(card, text="💬", font=(FONT, 34), bg=T.CARD, fg=T.TEXT).pack()
        tk.Label(card, text="Welcome back", font=(FONT, 20, "bold"),
                 bg=T.CARD, fg=T.TEXT).pack(pady=(5, 0))
        tk.Label(card, text="Log in to continue chatting", font=(FONT, 10),
                 bg=T.CARD, fg=T.MUTED).pack(pady=(0, 20))

        self.username = make_field(card, "Username", width=30)
        self.password = make_field(card, "Password", show="*", width=30)

        self.show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            card, text="Show password", variable=self.show_var,
            command=self.toggle_password, bg=T.CARD, fg=T.MUTED,
            activebackground=T.CARD, activeforeground=T.TEXT,
            selectcolor=T.INPUT, bd=0, highlightthickness=0, font=(FONT, 9),
        ).pack(anchor="w", pady=(0, 15))

        make_button(card, "Log in", self.login).pack(fill="x")

        row = tk.Frame(card, bg=T.CARD)
        row.pack(pady=(18, 0))
        tk.Label(row, text="Don't have an account?", font=(FONT, 9),
                 bg=T.CARD, fg=T.MUTED).pack(side="left")
        link = tk.Label(row, text=" Register", font=(FONT, 9, "bold"),
                        bg=T.CARD, fg=T.ACCENT_HOVER, cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda e: self.go_register())

        if on_toggle_theme:
            theme_toggle(self, on_toggle_theme, bg=T.BG).place(
                relx=1.0, x=-16, y=12, anchor="ne")

        self.password.bind("<Return>", lambda e: self.login())
        self.username.focus_set()

    def toggle_password(self):
        self.password.config(show="" if self.show_var.get() else "*")

    def login(self):
        username = self.username.get().strip()
        password = self.password.get()

        if not username or not password:
            messagebox.showwarning("Missing info", "Enter your username and password.")
            return

        user_id = database.login_user(username, password)
        if user_id is None:
            messagebox.showerror("Login failed", "Wrong username or password.")
            self.password.delete(0, tk.END)
            return

        if self.on_success:
            self.on_success(user_id, username)

    def go_register(self):
        if self.on_go_register:
            self.on_go_register()


class App(tk.Tk):
    """The window. It shows one page at a time and swaps them."""

    def __init__(self):
        super().__init__()
        self.title("Mini ChatGPT")
        database.init_db()  # creates / upgrades the tables
        T.set_mode(database.get_setting("theme", "dark"))  # remembers dark/light mode
        self.current = None   # the page on screen
        self.page = None      # its name: "login", "register", "dashboard" or "profile"
        self.user_id = None
        self.username = None
        self.show_login()

    def show_page(self, page, size, min_size):
        if self.current is not None:
            self.current.destroy()
        self.current = page
        self.configure(bg=T.BG)
        self.minsize(*min_size)
        self.geometry(size)
        self.current.pack(fill="both", expand=True)

    def toggle_theme(self, open_id=None):
        """Switch dark/light, remember it, and rebuild the page with the new colors."""
        T.toggle()
        database.set_setting("theme", T.mode)
        if self.page == "dashboard":
            self.show_dashboard(self.user_id, self.username, open_id)
        elif self.page == "register":
            self.show_register()
        else:
            self.show_login()

    def show_login(self):
        self.page = "login"
        self.user_id = None
        self.username = None
        page = LoginFrame(self, on_success=self.show_dashboard,
                          on_go_register=self.show_register,
                          on_toggle_theme=self.toggle_theme)
        self.show_page(page, "460x600", (460, 600))

    def show_register(self):
        self.page = "register"
        page = RegisterFrame(self, on_success=self.show_login,
                             on_go_login=self.show_login,
                             on_toggle_theme=self.toggle_theme)
        self.show_page(page, "460x680", (460, 680))

    def show_dashboard(self, user_id, username, open_id=None):
        self.page = "dashboard"
        self.user_id = user_id
        self.username = username
        page = DashboardFrame(self, user_id, username, on_logout=self.show_login,
                              on_profile=self.show_profile,
                              on_toggle_theme=self.toggle_theme, open_id=open_id)
        self.show_page(page, "980x680", (720, 480))

    def show_profile(self, open_id=None):
        self.page = "profile"
        page = ProfileFrame(
            self, self.user_id, self.username,
            on_back=lambda: self.show_dashboard(self.user_id, self.username, open_id))
        self.show_page(page, "520x700", (520, 660))


if __name__ == "__main__":
    App().mainloop()