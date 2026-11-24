#!/usr/bin/env bash
# Provisionering van try.factiz.org op een verse Ubuntu 24.04 (Hetzner, B21).
# Idempotent: elke stap controleert eerst of hij al gedaan is, dus het script
# mag opnieuw draaien na een onderbreking (bijvoorbeeld om de deploy key toe
# te voegen). Draaien als root:
#
#   scp -r deploy root@<ip>:/root/ && ssh root@<ip> bash /root/deploy/provision.sh
#
# Het corpus wordt niet gebouwd (uren op 4 vCPU); kopieer de eigen database:
#   scp doublecheck.db factiz@<ip>:/home/factiz/app/doublecheck.db
set -euo pipefail

APP_DIR=/home/factiz/app
REPO=git@github.com:factiz-org/factiz.git
REPO_HTTPS=https://github.com/factiz-org/factiz.git
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stap() { printf '\n==> %s\n' "$*"; }

stap "Pakketten (OCR-talen volgen config.toml [ocr] languages: nld+eng+deu+fra+spa)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3.12-venv git caddy ufw \
  tesseract-ocr tesseract-ocr-nld tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa \
  tesseract-ocr-osd tesseract-ocr-ara tesseract-ocr-fas tesseract-ocr-urd tesseract-ocr-ben tesseract-ocr-asm tesseract-ocr-rus tesseract-ocr-mon tesseract-ocr-hin tesseract-ocr-mar tesseract-ocr-nep tesseract-ocr-amh tesseract-ocr-guj tesseract-ocr-pan tesseract-ocr-chi-sim tesseract-ocr-chi-tra tesseract-ocr-kor tesseract-ocr-heb tesseract-ocr-jpn tesseract-ocr-kan tesseract-ocr-khm tesseract-ocr-lao tesseract-ocr-mal tesseract-ocr-sin tesseract-ocr-tam tesseract-ocr-tel tesseract-ocr-tha

stap "Firewall: alleen 22, 80 en 443"
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
ufw status | head -n 6

stap "Systeemgebruiker factiz"
if ! id factiz >/dev/null 2>&1; then
  adduser --system --group --home /home/factiz --shell /bin/bash factiz
fi
install -d -o factiz -g factiz -m 700 /home/factiz/.ssh

stap "Deploy key voor de private repository"
if [ ! -f /home/factiz/.ssh/id_ed25519 ]; then
  sudo -u factiz ssh-keygen -t ed25519 -N "" -C "deploy@try.factiz.org" \
    -f /home/factiz/.ssh/id_ed25519 >/dev/null
fi
sudo -u factiz ssh-keyscan -t ed25519 github.com 2>/dev/null \
  > /home/factiz/.ssh/known_hosts
if ! sudo -u factiz git ls-remote "$REPO" >/dev/null 2>&1; then
  cat <<MELDING

De server kan de repository nog niet lezen. Voeg deze publieke sleutel toe als
read-only deploy key (GitHub: factiz-org/factiz -> Settings -> Deploy keys)
en draai dit script daarna opnieuw; het gaat verder waar het bleef.

$(cat /home/factiz/.ssh/id_ed25519.pub)

(Na de launch is de repo publiek en kan $REPO_HTTPS zonder sleutel.)
MELDING
  exit 2
fi

stap "Code: clone of pull"
if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u factiz git clone -q "$REPO" "$APP_DIR"
else
  sudo -u factiz git -C "$APP_DIR" pull -q --ff-only
fi

stap "Python-omgeving"
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  sudo -u factiz python3.12 -m venv "$APP_DIR/.venv"
fi
sudo -u factiz "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u factiz "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" gunicorn

stap "Embeddingmodel vooraf ophalen (hoort bij provisionering, niet bij het eerste bezoek)"
sudo -u factiz "$APP_DIR/.venv/bin/python" - <<'PY'
import tomllib
from sentence_transformers import SentenceTransformer
with open("/home/factiz/app/config.toml", "rb") as f:
    naam = tomllib.load(f)["model_versions"]["text_embedding"].split("+")[0]
SentenceTransformer(naam)
print("model aanwezig:", naam)
PY

stap "Gewichten van de rechter (niet in git, #30.3; alleen als hij aanstaat)"
RECHTER=$(sudo -u factiz "$APP_DIR/.venv/bin/python" - <<'PY'
import tomllib
with open("/home/factiz/app/config.toml", "rb") as f:
    rechter = tomllib.load(f).get("rechter", {})
print(rechter.get("pad", "") if rechter.get("aan") else "")
PY
)
RECHTER_KLAAR=1
if [ -n "$RECHTER" ] && [ ! -f "$APP_DIR/$RECHTER/model.safetensors" ]; then
  RECHTER_KLAAR=0
  sudo -u factiz mkdir -p "$APP_DIR/$(dirname "$RECHTER")"
  echo "Geen gewichten in $APP_DIR/$RECHTER: kopieer de map (scp -r, RUNBOOK §Deploy);"
  echo "zonder weigert elke tekstvraag (DR6)."
fi

stap "systemd-unit en Caddy"
install -m 644 "$HIER/factiz.service" /etc/systemd/system/factiz.service
install -m 644 "$HIER/Caddyfile" /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable -q factiz caddy
if [ -f "$APP_DIR/doublecheck.db" ] && [ "$RECHTER_KLAAR" = 1 ]; then
  systemctl restart factiz
else
  echo "Database of rechter ontbreekt nog: kopieer ze (scp) en draai 'systemctl start factiz'."
fi
systemctl restart caddy

stap "Retention als dagelijks vangnet (de server veegt zelf elke sweep_interval_hours)"
CRON='17 4 * * * cd /home/factiz/app && .venv/bin/python -m doublecheck.retention'
( sudo -u factiz crontab -l 2>/dev/null | grep -v doublecheck.retention; echo "$CRON" ) \
  | sudo -u factiz crontab -

stap "Klaar. Controle:"
echo "  systemctl status factiz --no-pager | head -n 5"
echo "  curl -s https://try.factiz.org/.well-known/doublecheck | head -c 300"
echo "Vergeet niet: Hetzner-backups op de 7-daagse cyclus (korter dan de artefact-bewaartermijn, B11/B21)."
