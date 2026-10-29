#!/data/data/com.termux/files/usr/bin/bash

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
clear
echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
echo -e "${YELLOW}   ZYON AIM DB — BOOTSTRAP${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════${NC}\n"

# 1. Dependências
echo -e "${YELLOW}[1/4] Instalando dependências...${NC}"
pkg update -y > /dev/null 2>&1
pkg install python python-numpy android-tools ffmpeg git wget -y > /dev/null 2>&1

# 2. Git
echo -e "\n${YELLOW}[2/4] Configurando GitHub...${NC}"
GITHUB_USER="badsoulr-tech"; REPO="Zyon--aim--db"
echo -e "Cole o Token do GitHub:"
read GH_TOKEN; echo ""

mkdir -p ~/zyon_db && cd ~/zyon_db
git config --global user.name "Zyon AI"; git config --global user.email "zyon@ai.local"
[ ! -d ".git" ] && git init > /dev/null 2>&1 && git remote add origin "https://${GITHUB_USER}:${GH_TOKEN}@github.com/${GITHUB_USER}/${REPO}.git" > /dev/null 2>&1
git fetch origin main > /dev/null 2>&1
git reset --hard origin/main > /dev/null 2>&1

# 3. ADB
echo -e "\n${YELLOW}[3/4] Conectando ADB...${NC}"
export ADB_MDNS_OPENSCREEN=1
adb kill-server > /dev/null 2>&1; adb start-server > /dev/null 2>&1; sleep 2
MDNS_OUT=$(adb mdns services 2>/dev/null)
CONNECT_ADDR=$(echo "$MDNS_OUT" | grep "_adb-tls-connect._tcp" | awk '{print $NF}' | head -n 1)
[ -n "$CONNECT_ADDR" ] && adb connect "$CONNECT_ADDR" > /dev/null 2>&1 && sleep 1

if ! adb devices | grep -q "device$"; then
    echo -e "${YELLOW}Porta de conexão necessária (tela de Depuração sem fio).${NC}"
    read -p "Porta (ex: 43567): " ADB_PORT
    [ -n "$ADB_PORT" ] && adb connect localhost:$ADB_PORT > /dev/null 2>&1 && sleep 1
fi

if adb devices | grep -q "device$"; then
    adb shell cmd thermalservice override-status 0 > /dev/null 2>&1
    echo -e "${GREEN}✅ ADB + bypass térmico.${NC}"
else
    echo -e "${RED}❌ ADB não conectado.${NC}"
fi

# 4. Iniciar
echo -e "\n${YELLOW}[4/4] Iniciando Rage Engine...${NC}"
if [ -f "rage_engine.py" ]; then
    python rage_engine.py
else
    echo -e "${RED}❌ rage_engine.py não encontrado no repositório.${NC}"
    echo -e "${YELLOW}Faça upload do arquivo ou copie do histórico.${NC}"
fi
