"""OverLoad - Téléchargeur YouTube (application de bureau)."""
import io
import os
import threading
import urllib.request
from tkinter import filedialog

import customtkinter as ctk
import yt_dlp
from PIL import Image

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = None

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VIOLET = "#7c3aed"
ROSE = "#db2777"
BG = "#0f0a1f"
CARD = "#1a1333"


class OverLoad(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("OverLoad — Téléchargeur YouTube")
        self.geometry("620x640")
        self.minsize(560, 600)
        self.configure(fg_color=BG)
        self.format = ctk.StringVar(value="video")
        self.dossier = os.path.join(os.path.expanduser("~"), "Downloads")
        self._build()

    # ---------- Interface ----------
    def _build(self):
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=24)
        card.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(card, text="⚡ OverLoad", font=("Segoe UI", 34, "bold"),
                     text_color="#c084fc").pack(pady=(28, 0))
        ctk.CTkLabel(card, text="Télécharge tes vidéos YouTube en vidéo ou en MP3",
                     text_color="#c4b5fd").pack(pady=(0, 20))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=28)
        self.url = ctk.CTkEntry(row, placeholder_text="Colle le lien de la vidéo YouTube…",
                                height=44, corner_radius=14, border_color="#4c1d95")
        self.url.pack(side="left", fill="x", expand=True)
        self.url.bind("<Return>", lambda e: self.chercher())
        ctk.CTkButton(row, text="🔍", width=50, height=44, corner_radius=14,
                      fg_color=VIOLET, hover_color="#6d28d9",
                      command=self.chercher).pack(side="left", padx=(8, 0))

        # Infos vidéo
        self.info = ctk.CTkFrame(card, fg_color="#120c26", corner_radius=14, height=100)
        self.info.pack(fill="x", padx=28, pady=16)
        self.thumb = ctk.CTkLabel(self.info, text="🎞️", width=140, height=80, font=("", 30))
        self.thumb.pack(side="left", padx=10, pady=10)
        txt = ctk.CTkFrame(self.info, fg_color="transparent")
        txt.pack(side="left", fill="both", expand=True)
        self.titre = ctk.CTkLabel(txt, text="Aucune vidéo", font=("Segoe UI", 14, "bold"),
                                  anchor="w", justify="left", wraplength=320)
        self.titre.pack(fill="x", pady=(16, 2))
        self.meta = ctk.CTkLabel(txt, text="", anchor="w", text_color="#a5a0c0")
        self.meta.pack(fill="x")

        # Format
        fmt = ctk.CTkSegmentedButton(card, values=["🎬  Vidéo (meilleure qualité)", "🎵  Audio (MP3)"],
                                     height=44, corner_radius=14, selected_color=ROSE,
                                     selected_hover_color="#be185d", command=self._set_fmt)
        fmt.set("🎬  Vidéo (meilleure qualité)")
        fmt.pack(fill="x", padx=28)

        # Dossier
        drow = ctk.CTkFrame(card, fg_color="transparent")
        drow.pack(fill="x", padx=28, pady=14)
        self.lbl_dossier = ctk.CTkLabel(drow, text=f"📁 {self.dossier}", anchor="w", text_color="#a5a0c0")
        self.lbl_dossier.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(drow, text="Changer", width=80, fg_color="#2e1f5e", hover_color="#3b2a75",
                      command=self.choisir_dossier).pack(side="right")

        self.btn = ctk.CTkButton(card, text="Télécharger", height=50, corner_radius=14,
                                 font=("Segoe UI", 16, "bold"), fg_color=ROSE,
                                 hover_color="#be185d", command=self.telecharger)
        self.btn.pack(fill="x", padx=28)

        self.bar = ctk.CTkProgressBar(card, height=12, corner_radius=8, progress_color="#c084fc")
        self.bar.set(0)
        self.bar.pack(fill="x", padx=28, pady=(18, 6))
        self.status = ctk.CTkLabel(card, text="", text_color="#ddd6fe")
        self.status.pack()

        self.btn_ouvrir = ctk.CTkButton(card, text="📂 Ouvrir le dossier", fg_color="#2e1f5e",
                                        hover_color="#3b2a75", command=self.ouvrir_dossier)

    def _set_fmt(self, v):
        self.format.set("audio" if "Audio" in v else "video")

    def choisir_dossier(self):
        d = filedialog.askdirectory(initialdir=self.dossier)
        if d:
            self.dossier = d
            self.lbl_dossier.configure(text=f"📁 {d}")

    def ouvrir_dossier(self):
        if os.name == "nt":
            os.startfile(self.dossier)
        else:
            os.system(f'xdg-open "{self.dossier}" || open "{self.dossier}"')

    def set_status(self, t, color="#ddd6fe"):
        self.after(0, lambda: self.status.configure(text=t, text_color=color))

    # ---------- Infos ----------
    def chercher(self):
        url = self.url.get().strip()
        if not url:
            return self.set_status("❌ Lien invalide.", "#fca5a5")
        self.set_status("Recherche…")
        threading.Thread(target=self._chercher, args=(url,), daemon=True).start()

    def _chercher(self, url):
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
                i = ydl.extract_info(url, download=False)
            img = None
            if i.get("thumbnail"):
                data = urllib.request.urlopen(i["thumbnail"], timeout=10).read()
                pil = Image.open(io.BytesIO(data))
                img = ctk.CTkImage(pil, size=(140, 80))
            self.after(0, self._show_info, i, img)
            self.set_status("")
        except Exception as e:
            self.set_status(f"❌ {str(e)[:90]}", "#fca5a5")

    def _show_info(self, i, img):
        self.titre.configure(text=i.get("title", "Inconnu"))
        self.meta.configure(text=f"{i.get('uploader', '')}  •  ⏱ {i.get('duration_string', 'N/A')}")
        if img:
            self.thumb.configure(image=img, text="")

    # ---------- Téléchargement ----------
    def telecharger(self):
        url = self.url.get().strip()
        if not url:
            return self.set_status("❌ Lien invalide.", "#fca5a5")
        self.btn.configure(state="disabled", text="Téléchargement…")
        self.btn_ouvrir.pack_forget()
        self.bar.set(0)
        if self.titre.cget("text") == "Aucune vidéo":
            self.chercher()
        threading.Thread(target=self._telecharger, args=(url,), daemon=True).start()

    def _hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            p = d.get("downloaded_bytes", 0) / total if total else 0
            self.after(0, self.bar.set, p)
            self.set_status(f"Téléchargement : {p*100:.1f}%  |  Vitesse : {(d.get('_speed_str') or 'N/A').strip()}")
        elif d["status"] == "finished":
            self.set_status("Conversion en cours…")

    def _telecharger(self, url):
        opts = {
            "progress_hooks": [self._hook],
            "outtmpl": os.path.join(self.dossier, "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "noprogress": True,
        }
        if FFMPEG:
            opts["ffmpeg_location"] = FFMPEG
        if self.format.get() == "audio":
            opts.update({"format": "bestaudio/best", "postprocessors": [{
                "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]})
        else:
            opts.update({"format": "bestvideo+bestaudio/best", "merge_output_format": "mp4"})
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self.after(0, self.bar.set, 1)
            self.set_status("✅ Téléchargement terminé !", "#86efac")
            self.after(0, lambda: self.btn_ouvrir.pack(pady=8))
        except Exception as e:
            self.set_status(f"❌ {str(e)[:90]}", "#fca5a5")
        self.after(0, lambda: self.btn.configure(state="normal", text="Télécharger"))


if __name__ == "__main__":
    OverLoad().mainloop()
