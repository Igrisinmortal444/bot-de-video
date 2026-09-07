import asyncio
import logging
import os
import re
import shutil
import subprocess
import time
import uuid

from aiohttp import ClientSession, ClientTimeout, web
import yt_dlp
from telegram import Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import BOT_TOKEN, DOWNLOAD_DIR, MAX_SIZE

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

JS_RUNTIME = os.environ.get("JS_RUNTIME_PATH", "")
EXTRA_OPTS: dict = {}
if not JS_RUNTIME:
    found = shutil.which("deno")
    JS_RUNTIME = found or ""
if JS_RUNTIME:
    EXTRA_OPTS["js_runtimes"] = {"deno": {"path": JS_RUNTIME}}
    EXTRA_OPTS["remote_components"] = ["ejs:github"]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TWITTER_RE = re.compile(
    r"(twitter\.com|x\.com|t\.co)/", re.IGNORECASE
)

COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")

# Archivos intermedios de yt-dlp: ejemplo "titulo [id].f137.mp4"
INTERMEDIATE = re.compile(r"\.f\d+\.[^/\\]+$")


def build_opts(workdir: str, url: str | None = None) -> dict:
    opts = {
        "outtmpl": os.path.join(workdir, "video_%(id)s.%(ext)s"),
        "format": (
            "bv*[ext=mp4][vcodec^=avc1][filesize<47M]+ba[ext=m4a]"
            "/b[ext=mp4][vcodec^=avc1][filesize<47M]"
            "/bv*[ext=mp4][filesize<47M]+ba[ext=m4a]"
            "/b[ext=mp4][filesize<47M]"
            "/bv*+ba/b"
            "/wv*+wa/w"
        ),
        "merge_output_format": "mp4",
        "max_filesize": 49_000_000,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "http_headers": {"User-Agent": UA},
    }
    if url and TWITTER_RE.search(url):
        opts["http_headers"]["User-Agent"] = UA
        opts["http_headers"]["Accept"] = "*/*"
        opts["http_headers"]["Accept-Language"] = "en-US,en;q=0.5"
        opts["extractor_args"] = {
            "twitter": {
                "force": ["true"],
            }
        }
        if os.path.isfile(COOKIES_FILE):
            opts["cookiefile"] = COOKIES_FILE
        else:
            logger.warning(
                "URL de Twitter/X detectada pero no existe %s. "
                "Twitter suele exigir cookies. Usa cookies.txt para evitar fallos.",
                COOKIES_FILE,
            )
    opts.update(EXTRA_OPTS)
    return opts


def look_for_file(workdir: str, seconds: int = 600) -> str | None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        for name in os.listdir(workdir):
            path = os.path.join(workdir, name)
            if not os.path.isfile(path):
                continue
            if name.endswith((".part", ".ytdl", ".json", ".tmp.mp4", ".ok.mp4")):
                continue
            if INTERMEDIATE.search(name):
                continue
            return path
        time.sleep(2)
    return None


def ensure_valid_mp4(path: str) -> str:
    """Garantiza un MP4 compatible con Telegram (códec h264+aac y moov inicial)."""
    base, ext = os.path.splitext(path)
    if ext.lower() != ".mp4":
        out = base + ".mp4"
        cmd = [
            "ffmpeg", "-y", "-i", path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", out,
        ]
        logger.info("Reencodeando a MP4: %s", path)
    else:
        out = path + ".ok.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", path,
            "-c", "copy", "-movflags", "+faststart", out,
        ]
        logger.info("Aplicando faststart: %s", path)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("ffmpeg falló: %s", proc.stderr[-2000:])
        try:
            os.remove(out)
        except OSError:
            pass
        return path
    try:
        os.remove(path)
    except OSError:
        pass
    return out


async def send_big_file(update: Update, path: str, caption: str = "") -> None:
    size = os.path.getsize(path)
    if size > 50_000_000:
        await update.message.reply_text("El archivo supera los 50 MB, Telegram no puede enviarlo.")
        return

    await update.message.chat.send_action(ChatAction.UPLOAD_VIDEO if size <= MAX_SIZE else ChatAction.UPLOAD_DOCUMENT)

    if size > MAX_SIZE:
        try:
            with open(path, "rb") as fh:
                await update.message.reply_document(
                    fh,
                    filename=os.path.basename(path),
                    caption=f"{caption}\n(preparado, supera 48 MB, se envía como documento)",
                    read_timeout=600,
                    write_timeout=600,
                )
            return
        except TelegramError as exc:
            logger.error("Fallo enviando documento: %s", exc)
            await update.message.reply_text(f"❌ No se pudo enviar. Error: {exc}")
            return

    ext = os.path.splitext(path)[1].lower()
    if ext == ".mp3":
        try:
            with open(path, "rb") as fh:
                await update.message.reply_audio(
                    fh,
                    caption=caption,
                    title=os.path.splitext(os.path.basename(path))[0],
                    read_timeout=600,
                    write_timeout=600,
                )
            return
        except TelegramError as exc:
            logger.error("Fallo enviando audio: %s", exc)
            await update.message.reply_text(f"❌ No se pudo enviar el audio. Error: {exc}")
            return

    if ext != ".mp4":
        path = ensure_valid_mp4(path)

    try:
        with open(path, "rb") as fh:
            await update.message.reply_video(
                fh,
                caption=caption,
                supports_streaming=True,
                read_timeout=600,
                write_timeout=600,
            )
    except TelegramError as exc:
        logger.error("Fallo enviando video: %s", exc)
        fixed = ensure_valid_mp4(path)
        try:
            with open(fixed, "rb") as fh:
                await update.message.reply_video(
                    fh,
                    caption=caption,
                    read_timeout=600,
                    write_timeout=600,
                )
        except TelegramError as exc2:
            logger.error("Fallo reenviando video: %s", exc2)
            await update.message.reply_text(f"❌ No se pudo enviar el video. Error: {exc2}")


def download_progress_hook(d):
    if d.get("status") == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes") or 0
        if total:
            logger.info("Descargando %s - %.1f%%", d.get("filename"), downloaded / total * 100)


class Downloader:
    def __init__(self, update: Update, url: str):
        self.update = update
        self.url = url
        self.workdir = os.path.join(DOWNLOAD_DIR, str(uuid.uuid4()))
        os.makedirs(self.workdir, exist_ok=True)

    def cleanup(self):
        shutil.rmtree(self.workdir, ignore_errors=True)

    def run(self, mode: str) -> tuple[bool, str]:
        if mode == "audio":
            opts = build_opts(self.workdir, self.url)
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        else:
            opts = build_opts(self.workdir, self.url)

        opts["progress_hooks"] = [download_progress_hook]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
        except Exception as exc:
            logger.error("Error de descarga: %s", exc)
            if TWITTER_RE.search(self.url):
                hint = ""
                if not os.path.isfile(COOKIES_FILE):
                    hint = (
                        "\n\n💡 Twitter/X exige autenticación. "
                        "El administrador debe exportar las cookies de su navegador "
                        "(extension 'Get cookies.txt LOCALLY') a un archivo `cookies.txt` "
                        "junto a bot.py y reiniciar el bot."
                    )
                return False, (
                    f"⚠️ No se pudo descargar el video de Twitter/X. Error: {exc}{hint}"
                )
            return False, f"⚠️ No se pudo descargar. Error: {exc}"

        path = look_for_file(self.workdir)
        if not path:
            return False, "❌ No se encontró el archivo descargado (posiblemente el sitio bloqueó la descarga)."
        return True, path


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 *Video Downloader Bot*\n\n"
        "Envíame el enlace de cualquier video y lo descargo sin marca de agua.\n\n"
        "Comandos:\n"
        "• Envía un enlace → descarga el video\n"
        "• `/audio <enlace>` → descarga solo el audio (MP3)\n\n"
        "Soporta YouTube, Instagram, TikTok, Facebook, Twitter/X, entre cientos de sitios más.",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("⚠️ Eso no parece un enlace válido.")
        return
    d = Downloader(update, url)
    await update.message.reply_text("⬇️ Descargando video... esto puede tomar unos segundos.")
    ok, result = await asyncio.to_thread(d.run, "video")
    if not ok:
        await update.message.reply_text(result)
        d.cleanup()
        return
    await send_big_file(update, result, caption="✅ Video sin marca de agua")
    logger.info("Enviado: %s", result)
    d.cleanup()


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /audio <enlace>")
        return
    url = context.args[0]
    d = Downloader(update, url)
    await update.message.reply_text("🎵 Extrayendo audio...")
    ok, result = await asyncio.to_thread(d.run, "audio")
    if not ok:
        await update.message.reply_text(result)
        d.cleanup()
        return
    await send_big_file(update, result, caption="🎵 Audio MP3 extraído")
    logger.info("Enviado: %s", result)
    d.cleanup()


async def health_server() -> None:
    """Servidor HTTP de salud para Render ($PORT); el bot sigue en polling."""

    async def ok(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)
    port = int(os.getenv("PORT", "10000"))
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info("🩺 Health HTTP server en puerto %s", port)


async def keepalive() -> None:
    """Ping silencioso cada 13 min para evitar el sleep de Render (free: 15 min)."""
    external = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not external:
        return
    url = f"{external}/health"
    timeout = ClientTimeout(total=15)
    async with ClientSession() as session:
        while True:
            await asyncio.sleep(13 * 60)
            try:
                async with session.get(url, timeout=timeout) as resp:
                    await resp.read()
            except Exception:
                pass


async def main() -> None:
    if BOT_TOKEN.startswith("PON_AQUI"):
        print("ERROR: Debes configurar BOT_TOKEN en config.py")
        return

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(600)
        .write_timeout(600)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("audio", handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot iniciado. Pulsa Ctrl+C para detener.")
    await app.initialize()
    await health_server()
    asyncio.create_task(keepalive())
    await app.updater.start_polling()
    await app.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())