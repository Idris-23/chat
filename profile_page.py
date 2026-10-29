
import io
import tkinter as tk
from tkinter import filedialog, messagebox

import database
from theme import T, FONT, make_button, make_field

try:
    from PIL import Image, ImageDraw, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False


# ---------------------------------------------------------------- pictures
def process_image(path):
    """Opens any image, crops it to a centered square, shrinks it, returns PNG bytes."""
    image = Image.open(path).convert("RGB")
    width, height = image.size
    side = min(width, height)
    left, top = (width - side) // 2, (height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((256, 256), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def circle_image(image_bytes, size):
    """Turns saved PNG bytes into a round picture of the given size."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    # Draw the circle 4x bigger then shrink it, so the edge is smooth
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    image.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))
    return image


def make_avatar(parent, size, avatar_bytes, name, bg):
    """A round profile picture. Without a picture it shows the first letter of the name."""
    canvas = tk.Canvas(parent, width=size, height=size, bg=bg,
                       highlightthickness=0, bd=0)
    photo = None
    if avatar_bytes and PIL_OK:
        try:
            photo = ImageTk.PhotoImage(circle_image(avatar_bytes, size))
        except Exception:
            photo = None

    if photo:
        canvas.create_image(size // 2, size // 2, image=photo)
        canvas.photo = photo  # keep a reference, or Tk throws the image away
    else:
        canvas.create_oval(1, 1, size - 1, size - 1, fill=T.ACCENT, outline="")
        initial = (name or "?")[0].upper()
        canvas.create_text(size // 2, size // 2, text=initial, fill="white",
                           font=(FONT, max(8, int(size * 0.42)), "bold"))
    return canvas


# ---------------------------------------------------------------- the page
class ProfileFrame(tk.Frame):
    def __init__(self, parent, user_id, username, on_back):
        super().__init__(parent, bg=T.BG)
        self.user_id = user_id
        self.username = username
        self.on_back = on_back

        profile = database.get_profile(user_id)
        self.avatar = profile["avatar"]   # PNG bytes or None
        self.avatar_changed = False       # only save the picture if it was changed

        card = tk.Frame(self, bg=T.CARD, padx=40, pady=26)
        card.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(card, text="Your profile", font=(FONT, 20, "bold"),
                 bg=T.CARD, fg=T.TEXT).pack()
        tk.Label(card, text=f"@{username}", font=(FONT, 10),
                 bg=T.CARD, fg=T.MUTED).pack(pady=(0, 14))

        # picture on the left, its buttons on the right
        top = tk.Frame(card, bg=T.CARD)
        top.pack(fill="x", pady=(0, 14))
        self.avatar_holder = tk.Frame(top, bg=T.CARD)
        self.avatar_holder.pack(side="left")
        buttons = tk.Frame(top, bg=T.CARD)
        buttons.pack(side="left", padx=20)
        make_button(buttons, "Change picture", self.choose_picture,
                    size=10, padx=16, pady=7).pack(fill="x")
        make_button(buttons, "Remove picture", self.remove_picture,
                    primary=False, size=10, padx=16, pady=7).pack(fill="x", pady=(8, 0))

        self.display_name = make_field(card, "Display name", gap=8)
        self.display_name.insert(0, profile["display_name"])
        self.email = make_field(card, "Email", gap=8)
        self.email.insert(0, profile["email"])

        tk.Label(card, text="About me", font=(FONT, 10), bg=T.CARD,
                 fg=T.MUTED).pack(anchor="w", pady=(0, 4))
        self.bio = tk.Text(
            card, width=32, height=3, font=(FONT, 11), bg=T.INPUT, fg=T.TEXT,
            insertbackground=T.TEXT, relief="flat", wrap="word", padx=6, pady=6,
            highlightthickness=2, highlightbackground=T.INPUT, highlightcolor=T.ACCENT,
        )
        self.bio.pack(pady=(0, 16))
        self.bio.insert("1.0", profile["bio"])

        row = tk.Frame(card, bg=T.CARD)
        row.pack(fill="x")
        make_button(row, "Save changes", self.save).pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        make_button(row, "Back", self.on_back, primary=False).pack(
            side="left", fill="x", expand=True)

        self.show_avatar()

    def show_avatar(self):
        for child in self.avatar_holder.winfo_children():
            child.destroy()
        name = self.display_name.get().strip() or self.username
        make_avatar(self.avatar_holder, 96, self.avatar, name, T.CARD).pack()

    def choose_picture(self):
        if not PIL_OK:
            messagebox.showinfo(
                "Pillow needed",
                "To use profile pictures, install Pillow:\n\n"
                "    pip install pillow\n\nThen restart the app.")
            return
        path = filedialog.askopenfilename(
            title="Choose a profile picture",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            self.avatar = process_image(path)
        except Exception:
            messagebox.showerror("Error", "That file couldn't be opened as an image.")
            return
        self.avatar_changed = True
        self.show_avatar()

    def remove_picture(self):
        self.avatar = None
        self.avatar_changed = True
        self.show_avatar()

    def save(self):
        display_name = self.display_name.get().strip()
        email = self.email.get().strip()
        bio = self.bio.get("1.0", "end").strip()

        if len(display_name) > 40:
            messagebox.showwarning("Too long", "Display name can be at most 40 characters.")
            return
        if email and ("@" not in email or "." not in email.split("@")[-1]):
            messagebox.showwarning("Invalid email", "That email address doesn't look right.")
            return
        if len(bio) > 200:
            messagebox.showwarning("Too long", "About me can be at most 200 characters.")
            return

        database.update_profile(self.user_id, display_name, email, bio)
        if self.avatar_changed:
            database.set_avatar(self.user_id, self.avatar)
        messagebox.showinfo("Saved", "Your profile has been updated.")
        self.on_back()