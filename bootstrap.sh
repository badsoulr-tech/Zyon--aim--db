cat > ~/fix_zyon.sh << 'FIX_EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${YELLOW}Cole o Token do GitHub:${NC}"
read GH_TOKEN
echo ""

GH_USER="badsoulr-tech"; REPO="Zyon--aim--db"

echo -e "${YELLOW}[1/5] Instalando dependências...${NC}"
pkg update -y >/dev/null 2>&1
pkg install python python-numpy android-tools ffmpeg git wget curl -y >/dev/null 2>&1

echo -e "\n${YELLOW}[2/5] Sincronizando repositório...${NC}"
rm -rf ~/zyon_db
git clone "https://${GH_USER}:${GH_TOKEN}@github.com/${GH_USER}/${REPO}.git" ~/zyon_db 2>/dev/null || {
    echo -e "${RED}❌ Clone falhou. Verifique o token.${NC}"
    exit 1
}
cd ~/zyon_db
mkdir -p offsets
[ ! -f "config.json" ] && echo '{"version":2,"games":{},"global":{}}' > config.json

echo -e "\n${YELLOW}[3/5] Baixando rish e dumper...${NC}"
curl -L "https://github.com/RikkaApps/Shizuku/releases/latest/download/rish" -o $PREFIX/bin/rish 2>/dev/null || true
chmod +x $PREFIX/bin/rish 2>/dev/null || true

DUMPER="$HOME/dumper64"
curl -L "https://github.com/RrQxSaWaR/aio-ue4-dumper/raw/main/AndUE4Dumper/UE4Dump3r_arm64" -o "$DUMPER" 2>/dev/null || true
chmod +x "$DUMPER" 2>/dev/null || true

if rish -c "id" 2>/dev/null | grep -q "uid=2000"; then
    echo "rish OK."
    if rish -c "pidof com.tencent.ig" >/dev/null 2>&1; then
        rish -c "$DUMPER -o /sdcard/Download -p com.tencent.ig" 2>/dev/null || true
        sleep 3
        [ -f "/sdcard/Download/script.json" ] && cp "/sdcard/Download/script.json" "offsets/pubg_$(date +%Y%m%d).json"
    fi
else
    echo -e "${YELLOW}rish indisponível — modo visual será usado.${NC}"
fi

echo -e "\n${YELLOW}[4/5] Conectando ADB...${NC}"
export ADB_MDNS_OPENSCREEN=1
adb kill-server >/dev/null 2>&1
adb start-server >/dev/null 2>&1
sleep 2

MDNS=$(adb mdns services 2>/dev/null)
ADDR=$(echo "$MDNS" | grep "_adb-tls-connect._tcp" | awk '{print $NF}' | head -n 1)
if [ -n "$ADDR" ]; then
    echo "mDNS: $ADDR"
    adb connect "$ADDR" >/dev/null 2>&1
    sleep 1
fi

if ! adb devices | grep -q "device$"; then
    echo -e "${YELLOW}ADB não encontrado automaticamente.${NC}"
    echo "Abra: Opções do Desenvolvedor > Depuração sem fio"
    echo "Copie a 'Porta de Conexão' e digite abaixo."
    read -p "Porta (ex: 43567): " PORT
    if [ -n "$PORT" ]; then
        adb connect "localhost:$PORT" >/dev/null 2>&1
        sleep 1
    fi
fi

if ! adb devices | grep -q "device$"; then
    echo -e "${RED}❌ ADB não conectado.${NC}"
    echo "Pareamento manual:"
    echo "  adb pair localhost:PORTA_PAREAMENTO"
    echo "  adb connect localhost:PORTA_CONEXAO"
    echo "  python ~/zyon_db/rage_engine.py"
    exit 1
fi

echo -e "\n${YELLOW}[5/5] Iniciando motor...${NC}"
adb shell cmd thermalservice override-status 0 >/dev/null 2>&1
python ~/zyon_db/rage_engine.py
FIX_EOF

chmod +x ~/fix_zyon.sh
bash ~/fix_zyon.sh
