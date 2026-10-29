#!/data/data/com.termux/files/usr/bin/bash
# zyon_install.sh — instalador + auto-start do motor
set -u

AUTO_RUN=1
[ "${1:-}" = "--no-run" ] && AUTO_RUN=0

G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; C=$'\033[36m'; B=$'\033[1m'; N=$'\033[0m'
ok()   { printf "%b✓%b %s\n" "$G" "$N" "$1"; }
warn() { printf "%b!%b %s\n" "$Y" "$N" "$1"; }
err()  { printf "%b✗%b %s\n" "$R" "$N" "$1"; }
step() { printf "\n%b%b▸ %s%b\n" "$B" "$C" "$1" "$N"; }

step "[1/5] dependências"
pkg install -y python python-numpy python-pillow curl git wget >/dev/null 2>&1
ok "pkg base"

if python -c "import onnxruntime as ort; assert hasattr(ort,'InferenceSession')" 2>/dev/null; then
    ok "onnxruntime"
else
    warn "onnxruntime quebrado — reinstalando"
    pip uninstall -y onnxruntime onnxruntime-gpu 2>/dev/null
    rm -rf $PREFIX/lib/python*/site-packages/onnxruntime* 2>/dev/null
    pkg install -y --reinstall python-onnxruntime >/dev/null 2>&1
    python -c "import onnxruntime as ort; assert hasattr(ort,'InferenceSession')" 2>/dev/null \
        && ok "onnxruntime recuperado" || err "onnxruntime falhou"
fi

step "[2/5] repositório"
cd ~/Zyon--aim--db || { err "repo ausente"; exit 1; }
git pull --rebase --autostash >/dev/null 2>&1 && ok "pull" || warn "pull com avisos"
ok "em $(pwd)"

step "[3/5] modelo yolov8n.onnx"
if [ -f model.onnx ] && [ "$(wc -c < model.onnx)" -gt 2000000 ]; then
    ok "presente ($(du -h model.onnx|cut -f1))"
else
    rm -f model.onnx
    GOT=0
    for u in \
        "https://huggingface.co/Kalray/yolov8/resolve/main/yolov8n.onnx" \
        "https://huggingface.co/cabelo/yolov8/resolve/main/yolov8n.onnx" \
        "https://huggingface.co/Xenova/yolov8n/resolve/main/onnx/model.onnx"
    do
        printf "  → %s\n" "$(echo "$u"|cut -d/ -f3)"
        curl -L --fail -s -o model.onnx "$u" 2>/dev/null
        SZ=$(wc -c < model.onnx 2>/dev/null || echo 0)
        MG=$(head -c1 model.onnx 2>/dev/null | xxd -p 2>/dev/null)
        if [ "$SZ" -gt 2000000 ] && [ "$MG" = "08" ]; then
            ok "modelo $((SZ/1024/1024)) MB"
            GOT=1; break
        fi
        rm -f model.onnx
    done
    [ "$GOT" -eq 0 ] && err "modelo falhou"
fi

step "[4/5] shell (rish / adb)"
SHELL_OK=0; BACKEND=""
if command -v rish >/dev/null 2>&1; then
    OUT=$(rish -c "id" 2>&1 | head -1)
    if echo "$OUT" | grep -q "uid=2000"; then
        ok "rish funcional"; SHELL_OK=1; BACKEND="rish"
    else
        warn "rish quebrado: ${OUT:0:60}"
        warn "atualize o rish pelo app Shizuku → Use in terminal apps → Export files"
    fi
fi
if [ "$SHELL_OK" -eq 0 ] && command -v adb >/dev/null 2>&1; then
    OUT=$(adb shell id 2>&1 | head -1)
    if echo "$OUT" | grep -q "uid=2000"; then
        ok "adb shell funcional"; SHELL_OK=1; BACKEND="adb"
    fi
fi
if [ "$SHELL_OK" -eq 0 ]; then
    err "sem shell — instale Shizuku ou pareie ADB"
    echo "  https://f-droid.org/packages/moe.shizuku.privileged.api/"
fi

step "[5/5] verificação"
[ -f zyon_ultimate.py ] && ok "motor" || err "motor ausente"
python -m py_compile zyon_ultimate.py 2>/dev/null && ok "sintaxe" || err "sintaxe"
[ -f model.onnx ] && ok "modelo" || err "modelo"

printf "\n%b════════════════════════════════════════════%b\n" "$B" "$N"
if [ "$SHELL_OK" -eq 1 ] && [ -f model.onnx ] && [ -f zyon_ultimate.py ]; then
    printf "%b%b ✅ TUDO PRONTO (shell: %s)%b\n" "$B" "$G" "$BACKEND" "$N"
    printf "%b════════════════════════════════════════════%b\n" "$B" "$N"

    if [ "$AUTO_RUN" -eq 1 ]; then
        printf "\n%b%b▸ iniciando motor em 5s…%b\n" "$B" "$C" "$N"
        printf "%b  → abra o jogo e entre numa partida AGORA%b\n" "$Y" "$N"
        printf "%b  → Ctrl+C no toolbar do Termux pra sair%b\n\n" "$Y" "$N"
        sleep 5
        cd ~/Zyon--aim--db && exec python zyon_ultimate.py
    else
        printf "\n  para rodar manualmente:\n  %bcd ~/Zyon--aim--db && python zyon_ultimate.py%b\n" "$C" "$N"
    fi
else
    printf "%b%b ⚠ pendências — veja ✗ acima%b\n" "$B" "$Y" "$N"
    printf "%b════════════════════════════════════════════%b\n" "$B" "$N"
fi
