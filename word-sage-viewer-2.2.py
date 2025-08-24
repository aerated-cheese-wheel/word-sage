import os
import threading
import time
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageTk
import io
import urllib.parse
import datetime
import tkinter as tk
from tkinter import ttk
import ttkbootstrap as tb
from ttkbootstrap.constants import *

BASE_ARCHIVE = "wiki_archive"
USER_AGENT = "WordSageBot/1.0"
SUBLINK_LIMIT = 5
IMAGE_LIMIT = 5  # per page

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

# ----------------------------
# WIKI CRAWLER
# ----------------------------
class WikiCrawler:
    def __init__(self, base_dir=BASE_ARCHIVE):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self.visited = set()
        self.lock = threading.Lock()

    def safe_folder_name(self, title):
        return "".join(c if c.isalnum() or c in "_-" else "_" for c in title)

    def clean_html(self, html):
        soup = BeautifulSoup(html, "html.parser")
        # Remove MediaWiki cruft
        for div in soup.select(".navbox, .metadata, .mw-references-wrap, script, style, .toc, .infobox, header, footer, .mw-editsection, .sistersitebox"):
            div.decompose()
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, type(soup.Comment))):
            comment.extract()
        return soup

    def save_page(self, title, soup):
        folder = os.path.join(self.base_dir, self.safe_folder_name(title))
        os.makedirs(folder, exist_ok=True)
        html_file = os.path.join(folder, "page.html")
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(str(soup))
        log(f"Saved HTML for page: {title}")

        img_folder = os.path.join(folder, "images")
        os.makedirs(img_folder, exist_ok=True)
        images = soup.find_all("img")
        img_count = 0
        for i, img in enumerate(images):
            if img_count >= IMAGE_LIMIT:
                break
            src = img.get("src")
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = "https://en.wikipedia.org" + src
            try:
                r = requests.get(src, headers={"User-Agent": USER_AGENT})
                if r.status_code == 200:
                    ext = os.path.splitext(src)[1].split("?")[0]
                    fname = f"img_{i}{ext}"
                    with open(os.path.join(img_folder, fname), "wb") as f:
                        f.write(r.content)
                    img_count += 1
                    log(f"Downloaded image: {fname} for page: {title}")
            except Exception as e:
                log(f"Failed to download image {src}: {e}")
        return folder

    def crawl_page(self, url, depth=0):
        url = urllib.parse.urljoin("https://en.wikipedia.org/", url)
        with self.lock:
            if url in self.visited:
                log(f"Skipping already visited page: {url}")
                return
            self.visited.add(url)
        try:
            log(f"Crawling page: {url}")
            r = requests.get(url, headers={"User-Agent": USER_AGENT})
            if r.status_code != 200:
                log(f"Failed to fetch page {url}, status: {r.status_code}")
                return
            soup = self.clean_html(r.text)
            title = url.split("/")[-1]
            folder = self.save_page(title, soup)

            # Crawl sublinks
            count = 0
            links = soup.find_all("a", href=True)
            for link in links:
                href = link['href']
                if href.startswith("/wiki/") and ":" not in href:
                    if count >= SUBLINK_LIMIT:
                        break
                    count += 1
                    self.crawl_page(href, depth=depth+1)
            return folder
        except Exception as e:
            log(f"Error crawling page {url}: {e}")
            return

# ----------------------------
# GUI APP
# ----------------------------
class WikiApp(tb.Window):
    def __init__(self):
        super().__init__(themename="sandstone")
        self.title("Word Sage Wiki Browser")
        self.geometry("1200x700")

        self.crawler = WikiCrawler()
        self.auto_archive = tk.BooleanVar(value=False)
        self.dark_mode = tk.BooleanVar(value=False)

        self.pages_archived = 0
        self.current_page = ""
        self.images_downloaded = 0

        self.create_controls()
        self.create_search()
        self.create_stats()
        self.create_progress()
        self.create_viewer()

        self.archive_thread = None

    # ------------------ CONTROLS ------------------
    def create_controls(self):
        ctrl = tb.Frame(self)
        ctrl.pack(side="top", fill="x", pady=5)
        tb.Checkbutton(ctrl, text="Dark Mode", variable=self.dark_mode,
                       bootstyle=SUCCESS, command=self.toggle_dark).pack(side="left", padx=5)
        tb.Checkbutton(ctrl, text="Auto-Archive", variable=self.auto_archive,
                       bootstyle=INFO, command=self.toggle_auto_archive).pack(side="left", padx=5)

    def toggle_dark(self):
        self.style.theme_use("darkly" if self.dark_mode.get() else "sandstone")
        self.update_viewer_colors()
        log(f"Dark mode set to: {self.dark_mode.get()}")

    def toggle_auto_archive(self):
        if self.auto_archive.get() and self.archive_thread is None:
            self.archive_thread = threading.Thread(target=self.run_auto_archive, daemon=True)
            self.archive_thread.start()
            log("Auto-archive started.")

    # ------------------ SEARCH ------------------
    def create_search(self):
        frame = tb.Frame(self)
        frame.pack(side="top", fill="x", padx=5, pady=5)

        self.search_var = tk.StringVar()
        entry = tb.Entry(frame, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", self.search)

        tb.Button(frame, text="Search", bootstyle=PRIMARY, command=self.search).pack(side="left", padx=5)

        # Scrollable results
        result_container = tk.Frame(self)
        result_container.pack(side="top", fill="x", padx=5, pady=5)
        self.canvas = tk.Canvas(result_container, height=150)
        scrollbar = ttk.Scrollbar(result_container, orient="vertical", command=self.canvas.yview)
        self.result_frame = tk.Frame(self.canvas)

        self.result_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.result_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def search(self, event=None):
        for widget in self.result_frame.winfo_children():
            widget.destroy()
        query = self.search_var.get().lower()
        results = []
        for folder in os.listdir(BASE_ARCHIVE):
            fpath = os.path.join(BASE_ARCHIVE, folder)
            if os.path.isdir(fpath) and query in folder.lower():
                results.append(fpath)
        log(f"Search for '{query}' returned {len(results)} results.")
        for folder in results:
            fr = tb.Frame(self.result_frame)
            fr.pack(fill="x", pady=1)
            tb.Label(fr, text=os.path.basename(folder), bootstyle=INFO).pack(side="left", padx=5)
            tb.Button(fr, text="Default", bootstyle="link",
                      command=lambda f=folder: self.load_page(f, mode="default")).pack(side="left")
            tb.Button(fr, text="*text", bootstyle="link",
                      command=lambda f=folder: self.load_page(f, mode="text")).pack(side="left")
            tb.Button(fr, text="*image", bootstyle="link",
                      command=lambda f=folder: self.load_page(f, mode="image")).pack(side="left")

    # ------------------ VIEWER ------------------
    def create_viewer(self):
        self.viewer_frame = tb.Frame(self)
        self.viewer_frame.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        self.text_frame = tk.Frame(self.viewer_frame)
        self.text_frame.pack(fill="both", expand=True)
        self.text_widget = tk.Text(self.text_frame, wrap="word")
        self.text_widget.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(self.text_frame, command=self.text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        self.text_widget.config(yscrollcommand=scrollbar.set)
        self.image_labels = []

    def update_viewer_colors(self):
        bg = "#222" if self.dark_mode.get() else "#fff"
        fg = "#eee" if self.dark_mode.get() else "#000"
        self.text_widget.config(bg=bg, fg=fg)
        for lbl in self.image_labels:
            lbl.config(bg=bg)

    def load_page(self, folder, mode="default"):
        log(f"Loading page '{folder}' with mode: {mode}")
        self.text_widget.delete("1.0", "end")
        for lbl in self.image_labels:
            lbl.destroy()
        self.image_labels = []

        html_file = os.path.join(folder, "page.html")
        if not os.path.exists(html_file):
            log(f"Page HTML not found: {html_file}")
            return
        with open(html_file, "r", encoding="utf-8") as f:
            content = f.read()
        if mode == "*text":
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator="\n")
            self.text_widget.insert("end", text)
        elif mode == "*image":
            img_dir = os.path.join(folder, "images")
            if os.path.exists(img_dir):
                for fname in os.listdir(img_dir):
                    if fname.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                        path = os.path.join(img_dir, fname)
                        try:
                            img = Image.open(path)
                            img.thumbnail((500, 500))
                            imgtk = ImageTk.PhotoImage(img)
                            lbl = tk.Label(self.text_widget, image=imgtk)
                            lbl.image = imgtk
                            lbl.pack()
                            self.image_labels.append(lbl)
                        except:
                            continue
        else:
            self.text_widget.insert("end", content)

        self.update_viewer_colors()
        self.progress["value"] = 100
        self.update_stats(page=os.path.basename(folder))

    # ------------------ PROGRESS & STATS ------------------
    def create_progress(self):
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(side="top", fill="x", padx=5, pady=2)

    def create_stats(self):
        self.stats_label = tb.Label(self, text="Pages: 0 | Current: None | Images: 0", bootstyle=INFO)
        self.stats_label.pack(side="top", fill="x", padx=5, pady=2)

    def update_stats(self, page="", images=0):
        self.pages_archived += 1
        self.current_page = page
        self.images_downloaded += images
        self.stats_label.config(
            text=f"Pages: {self.pages_archived} | Current: {self.current_page} | Images: {self.images_downloaded}"
        )

    # ------------------ AUTO-ARCHIVE ------------------
    def run_auto_archive(self):
        start_pages = ["/wiki/Mathematics", "/wiki/Chemical_substance", "/wiki/United_Kingdom"]
        for page in start_pages:
            if not self.auto_archive.get():
                log("Auto-archive paused/stopped")
                break
            folder = self.crawler.crawl_page(page)
            if folder:
                self.update_stats(page=os.path.basename(folder))
                self.progress["value"] = 100
            time.sleep(1)
        log("Auto-archive finished")

if __name__ == "__main__":
    app = WikiApp()
    app.mainloop()
