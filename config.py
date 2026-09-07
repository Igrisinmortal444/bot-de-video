import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8398512030:AAF1I1PamBFsVBUUMdsYBeXPf_XDr9s-_S4")

MAX_SIZE = 48 * 1024 * 1024

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
