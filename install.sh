#!/data/data/com.termux/files/usr/bin/bash
# zyon_install.sh — instalador completo ZYON aim db
set -u

G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"; B="\033[1m"; N="\033[0m"
ok() { printf "${G}✓${N} %s\n" "$1"; }
warn() { printf "${Y}!${N} %s\n" "$1"; }
err() { printf "${R}✗${N} %s\n" "$1"; }
step() { printf "\n${B}${C}▸ %s${N}\n" "$1"; }

step "[1/5] dependências"
pkg install -y python python-numpy python-pillow curl git wget >/dev/null 2>&1
ok "pkg base"

if python -c "import onnxruntime as ort; assert hasattr(ort,'InferenceSession')" 2>/dev/null; then
    ok "onnxruntime funcional"
else
    warn "onnxruntime quebrado — reinstalando"
    pip uninstall -y onnxruntime onnxruntime-gpu 2>/dev/null
    rm -rf $PREFIX/lib/python*/site-packages/onnxruntime* 2>/dev/null
    pkg install -y --reinstall python-onnxruntime >/dev/null 2>&1
    if python -c "import onnxruntime as ort; assert hasattr(ort,'InferenceSession')" 2>/dev/null; then
        ok "onnxruntime recuperado"
    else
        err "onnxruntime falhou — abra issue"
    fi
fi

step "[2/5] repositório"
cd ~/Zyon--aim--db || { err "repo ausente"; exit 1; }
git pull --rebase --autostash >/dev/null 2>&1 && ok "pull" || warn "pull com avisos"
ok "em $(pwd)"

step "[3/5] modelo yolov8n.onnx"
if [ -f model.onnx ] && [ "$(wc -c < model.onnx)" -gt 2000000 ]; then
    ok "já presente ($(du -h model.onnx|cut -f1))"
else
    rm -f model.onnx
    URLS=(
        "https://huggingface.co/Kalray/yolov8/resolve/main/yolov8n.onnx"
        "https://huggingface.co/cabelo/yolov8/resolve/main/yolov8n.onnx"
        "https://huggingface.co/Xenova/yolov8n/resolve/main/onnx/model.onnx"
    )
    GOT=0
    for u in "${URLS[@]}"; do
        printf "  → %s\n" "$(echo $u|cut -d/ -f3)"
        curl -L --fail -s -o model.onnx "$u" 2>/dev/null
        SZ=$(wc -c < model.onnx 2>/dev/null || echo 0)
        MG=$(head -c1 model.onnx 2>/dev/null | xxd -p 2>/dev/null)
        if [ "$SZ" -gt 2000000 ] && [ "$MG" = "08" ]; then
            ok "modelo: $((SZ/1024/1024)) MB"
            GOT=1; break
        fi
        rm -f model.onnx
    done
    [ "$GOT" -eq 0 ] && err "modelo falhou em todas as URLs"
fi

step "[4/5] shell (rish / adb)"
SHELL_OK=0
if command -v rish >/dev/null 2>&1; then
    OUT=$(rish -c "id" 2>&1 | head -1)
    if echo "$OUT" | grep -q "uid=2000"; then
        ok "rish funcional"
        SHELL_OK=1
    else
        warn "rish existe mas retornou: $OUT"
    fi
else
    warn "rish não instalado (PATH ou Shizuku ausente)"
fi

if [ "$SHELL_OK" -eq 0 ] && command -v adb >/dev/null 2>&1; then
    OUT=$(adb shell id 2>&1 | head -1)
    if echo "$OUT" | grep -q "uid=2000"; then
        ok "adb shell funcional"
        SHELL_OK=1
    fi
fi

if [ "$SHELL_OK" -eq 0 ]; then
    echo ""
    echo "${Y}para o aimbot capturar tela e injetar toque, precisa de shell:${N}"
    echo "  ${B}A) Shizuku${N} (recomendado):"
    echo "     1. baixa o APK em f-droid.org/packages/moe.shizuku.privileged.api/"
    echo "     2. ativa Depuração sem fio em Configurações → Desenvolvedor"
    echo "     3. abre Shizuku → Start via Wireless debugging"
    echo "     4. no Termux: rish -c 'id'  → deve retornar uid=2000"
    echo ""
    echo "  ${B}B) ADB wireless${N}:"
    echo "     1. Emparelhar dispositivo em Depuração sem fio"
    echo "     2. adb pair IP:PORTA  &&  adb connect IP:PORTA"
fi

step "[5/5] verificação"
[ -f zyon_ultimate.py ] && ok "zyon_ultimate.py" || err "zyon_ultimate.py ausente"
python -m py_compile zyon_ultimate.py 2>/dev/null && ok "sintaxe python" || err "sintaxe quebrada"
[ -f model.onnx ] && ok "model.onnx" || err "model.onnx ausente"

echo ""
if [ "$SHELL_OK" -eq 1 ] && [ -f model.onnx ] && [ -f zyon_ultimate.py ]; then
    printf "${B}${G}════════════════════════════════════════════${N}\n"
    printf "${B}${G} ✅ TUDO PRONTO — 0 pendências${N}\n"
    printf "${B}${G}════════════════════════════════════════════${N}\n"
    echo ""
    echo "  abra o jogo → partida → rode:"
    echo "  ${C}cd ~/Zyon--aim--db && python zyon_ultimate.py${N}"
else
    printf "${B}${Y}════════════════════════════════════════════${N}\n"
    printf "${Y} ⚠ pendências manuais (passo 4)${N}\n"
    printf "${B}${Y}════════════════════════════════════════════${N}\n"
fi
