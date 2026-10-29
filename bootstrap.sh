#!/data/data/com.termux/files/usr/bin/bash
set -e

TOKEN="${1:?Uso: bootstrap.sh <token_github>}"
GH_USER="badsoulr-tech"
REPO="Zyon--aim--db"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${YELLOW}[1/4] Instalando dependências...${NC}"
pkg update -y >/dev/null 2>&1
pkg install python python-numpy android-tools ffmpeg git wget curl -y >/dev/null 2>&1

echo -e "\n${YELLOW}[2/4] Baixando repositório...${NC}"
rm -rf ~/zyon_db
git clone "https://${GH_USER}:${TOKEN}@github.com/${GH_USER}/${REPO}.git" ~/zyon_db 2>/dev/null
cd ~/zyon_db
mkdir -p offsets
[ ! -f "config.json" ] && echo '{"version":2,"games":{},"global":{}}' > config.json

echo -e "\n${YELLOW}[3/4] Configurando Shizuku e dumper...${NC}"
curl -L "https://github.com/RikkaApps/Shizuku/releases/latest/download/rish" -o $PREFIX/bin/rish 2>/dev/null || true
chmod +x $PREFIX/bin/rish 2>/dev/null || true

DUMPER="$HOME/dumper64"
curl -L "https://github.com/RrQxSaWaR/aio-ue4-dumper/raw/main/AndUE4Dumper/UE4Dump3r_arm64" -o "$DUMPER" 2>/dev/null || true
chmod +x "$DUMPER" 2>/dev/null || true

if rish -c "id" 2>/dev/null | grep -q "uid=2000"; then
    echo "rish OK. Tentando dump..."
    if rish -c "pidof com.tencent.ig" >/dev/null 2>&1; then
        rish -c "$DUMPER -o /sdcard/Download -p com.tencent.ig" 2>/dev/null || true
        sleep 3
        [ -f "/sdcard/Download/script.json" ] && cp "/sdcard/Download/script.json" "offsets/pubg_$(date +%Y%m%d).json"
    fi
else
    echo "rish indisponível — modo visual será usado."
fi

echo -e "\n${YELLOW}[4/4] Conectando ADB e iniciando...${NC}"
export ADB_MDNS_OPENSCREEN=1
adb kill-server >/dev/null 2>&1
adb start-server >/dev/null 2>&1
sleep 2
MDNS=$(adb mdns services 2>/dev/null)
ADDR=$(echo "$MDNS" | grep "_adb-tls-connect._tcp" | awk '{print $NF}' | head -n 1)
[ -n "$ADDR" ] && adb connect "$ADDR" >/dev/null 2>&1 && sleep 1

if ! adb devices | grep -q "device$"; then
    echo -e "${RED}ADB desconectado.${NC}"
    echo "Abra a Depuração sem fio e rode:"
    echo "  adb connect localhost:PORTA"
    echo "depois:"
    echo "  python ~/zyon_db/rage_engine.py"
    exit 1
fi

python ~/zyon_db/rage_engine.py
