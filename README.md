# 🤖 Telegram Video Downloader Bot

Bot de Telegram para descargar videos de cualquier página web **sin marca de agua**.

Usa **yt-dlp**, que soporta más de 1000 sitios: YouTube, Instagram, TikTok,
Facebook, Twitter/X, Reddit, Twitch, Vimeo y muchos más.

## 🚀 Configuración

1. **Crea un bot en Telegram** con [@BotFather](https://t.me/BotFather):
   - Envía `/newbot`
   - Copia el **token** que te da

2. **Configura el token** en `config.py`:
   ```python
   BOT_TOKEN = "TU_TOKEN_AQUI"
   ```

3. **Inicia el bot**:
   ```bash
   ./start.sh
   ```

> Nota: si `deno` está instalado, la extracción de YouTube es más potente.
> Si no lo tienes, ejecuta:
> ```bash
> curl -fsSL https://deno.land/install.sh | sh
> ```

## 📖 Uso

| Acción | Comando |
|---|---|
| Descargar video | Envía el enlace directamente en el chat |
| Descargar solo audio | `/audio <enlace>` |
| Ayuda | `/start` |

## 📁 Estructura

```
tg_downloader/
├── bot.py            # Lógica principal del bot
├── config.py         # Token y configuración
├── requirements.txt  # Dependencias
├── start.sh          # Script de inicio
└── downloads/        # Archivos temporales (se limpian solos)
```

## ⚙️ Notas

- Los archivos >48 MB se envían como documento (límite de Telegram en chats normales).
- Los archivos temporales se eliminan automáticamente tras enviarse.

## 🐦 Twitter / X (requiere cookies)

Twitter/X exige autenticación para descargar la mayoría de videos. Si al enviar
un enlace de Twitter/X el bot falla, necesitas exportar tus cookies:

1. Instala la extensión **"Get cookies.txt LOCALLY"** en Chrome/Edge/Firefox.
   - Chrome: https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc
   - Firefox: https://addons.mozilla.org/firefox/addon/get-cookiestxt-locally/
2. Abre [https://x.com](https://x.com) **con tu sesión iniciada**.
3. Haz clic en la extensión y pulsa **"Export"**.
4. Guarda el archivo generado como `cookies.txt` **en la misma carpeta donde está `bot.py`**.
5. Reinicia el bot con `./start.sh`.

> ⚠️ El archivo `cookies.txt` contiene tu sesión de Twitter/X. **Nunca lo compartas** ni lo subas a un repositorio público.