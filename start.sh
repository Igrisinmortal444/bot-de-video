#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -f venv/bin/activate ]; then
    echo "Creando entorno virtual..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    echo "Dependencias instaladas."
fi

source venv/bin/activate
export PATH="$HOME/.deno/bin:$PATH"
python bot.py