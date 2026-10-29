import tkinter as tk
from tkinter import messagebox

import database
from theme import T, FONT, make_button, make_field, theme_toggle


class RegisterFrame(tk.Frame):
    def __init__(self, parent, on_success=None, on_go_login=None, on_toggle_theme=None):
        super().__init__(parent, bg=T.BG)
        self.on_success = on_success    # called after the account is created
        self.on_go_login = on_go_login  # shows the login page

        card = tk.Frame(self, bg=T.CARD, padx=40, pady=30)
        card.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(card, text="✨", font=(FONT, 34), bg=T.CARD, fg=T.TEXT).pack()
        tk.Label(card, text="Create account", font=(FONT, 20, "bold"),
                 bg=T.CARD, fg=T.TEXT).pack(pady=(5, 0))
        tk.Label(card, text="Sign up to start chatting", font=(FONT, 10),
                 bg=T.CARD, fg=T.MUTED).pack(pady=(0, 18))

        self.username = make_field(card, "Username", width=30)
        self.password = make_field(card, "Password", show="*", width=30)
        self.confirm = make_field(card, "Confirm password", show="*", width=30)

        self.show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            card, text="Show passwords", variable=self.show_var,
            command=self.toggle_password, bg=T.CARD, fg=T.MUTED,
            activebackground=T.CARD, activeforeground=T.TEXT,
            selectcolor=T.INPUT, bd=0, highlightthickness=0, font=(FONT, 9),
        ).pack(anchor="w", pady=(0, 15))

        make_button(card, "Create account", self.register).pack(fill="x")

        row = tk.Frame(card, bg=T.CARD)
        row.pack(pady=(18, 0))
        tk.Label(row, text="Already have an account?", font=(FONT, 9),
                 bg=T.CARD, fg=T.MUTED).pack(side="left")
        link = tk.Label(row, text=" Log in", font=(FONT, 9, "bold"),
                        bg=T.CARD, fg=T.ACCENT_HOVER, cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda e: self.go_login())

        if on_toggle_theme:
            theme_toggle(self, on_toggle_theme, bg=T.BG).place(
                relx=1.0, x=-16, y=12, anchor="ne")

        self.confirm.bind("<Return>", lambda e: self.register())
        self.username.focus_set()

    def toggle_password(self):
        show = "" if self.show_var.get() else "*"
        self.password.config(show=show)
        self.confirm.config(show=show)

    def register(self):
        username = self.username.get().strip()
        password = self.password.get()
        confirm = self.confirm.get()

        if len(username) < 3:
            messagebox.showwarning("Invalid username", "Username must be at least 3 characters.")
            return
        if len(password) < 6:
            messagebox.showwarning("Weak password", "Password must be at least 6 characters.")
            return
        if password != confirm:
            messagebox.showwarning("Mismatch", "The two passwords don't match.")
            self.confirm.delete(0, tk.END)
            return

        ok, message = database.register_user(username, password)
        if not ok:
            messagebox.showerror("Registration failed", message)
            return

        messagebox.showinfo("Success", "Account created! You can log in now.")
        if self.on_success:
            self.on_success()

    def go_login(self):
        if self.on_go_login:
            self.on_go_login()