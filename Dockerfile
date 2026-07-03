FROM python:3.11-slim

# Systemabhängigkeiten:
# - build-essential: für den Build von pyswisseph (C-Extension), falls
#   PyPI kein vorgefertigtes Wheel für diese Plattform anbietet.
# - libpango/libcairo/libgdk-pixbuf/libffi/shared-mime-info: für
#   WeasyPrint (PDF-Rendering aus HTML/CSS).
# - fonts-liberation: Basis-Schriftarten, damit der PDF-Bericht nicht mit
#   Ersatzglyphen/Kästchen gerendert wird.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 5000

# --workers 1: absichtlich, siehe Config.ENABLE_INPROCESS_PAYMENT_POLLER in
# docs/ARCHITECTURE.md — mehrere Worker würden mehrere Payment-Poller-Threads
# starten und doppelte WhatsApp-Nachrichten verschicken. Bei Bedarf für mehr
# Worker: ENABLE_INPROCESS_PAYMENT_POLLER=false setzen und den Poller separat
# starten (python -m app.services.payment_poller).
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "120", "run:app"]
