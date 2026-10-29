#!/data/data/com.termux/files/usr/bin/bash
# zyon install.sh — instalador completo (deps + modelo + shell + AimBuddy + auto-run)
set -u

AUTO_RUN=1
[ "${1:-}" = "--no-run" ] && AUTO_RUN=0

G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; C=$'\033[36m'; B=$'\033[1m'; N=$'\033[0m'
ok()   { printf "%b✓%b %s\n" "$G" "$N" "$1"; }
warn() { printf "%b!%b %s\n" "$Y" "$N" "$1"; }
err()  { printf "%b✗%b %s\n" "$R" "$N" "$1"; }
step() { printf "\n%b%b▸ %s%b\n" "$B" "$C" "$1" "$N"; }

step "[1/7] pkg base"
pkg install -y python python-numpy python-pillow curl git wget >/dev/null 2>&1
ok "pacotes"

step "[2/7] onnxruntime"
if python -c "import onnxruntime as ort; assert hasattr(ort,'InferenceSession')" 2>/dev/null; then
    ok "funcional"
else
    warn "quebrado — reinstalando"
    pip uninstall -y onnxruntime onnxruntime-gpu 2>/dev/null
    rm -rf $PREFIX/lib/python*/site-packages/onnxruntime* 2>/dev/null
    pkg install -y --reinstall python-onnxruntime >/dev/null 2>&1
    python -c "import onnxruntime as ort; assert hasattr(ort,'InferenceSession')" 2>/dev/null \
        && ok "recuperado" || err "falhou"
fi

step "[3/7] repo"
cd ~/Zyon--aim--db || { err "repo ausente"; exit 1; }
git pull --rebase --autostash >/dev/null 2>&1 && ok "pull" || warn "pull com avisos"
ok "em $(pwd)"

step "[4/7] modelo onnx"
if [ -f model.onnx ] && [ "$(wc -c < model.onnx)" -gt 2000000 ]; then
    SZ=$(du -h model.onnx | cut -f1)
    MG=$(head -c1 model.onnx | xxd -p)
    if [ "$MG" = "08" ]; then
        ok "presente ($SZ, magic ok)"
    else
        warn "corrompido — rebaixando"
        rm -f model.onnx
    fi
fi
if [ ! -f model.onnx ] || [ "$(wc -c < model.onnx 2>/dev/null || echo 0)" -lt 2000000 ]; then
    GOT=0
    for u in \
        "https://huggingface.co/Kalray/yolov8/resolve/main/yolov8n.onnx" \
        "https://huggingface.co/cabelo/yolov8/resolve/main/yolov8n.onnx" \
        "https://huggingface.co/Xenova/yolov8n/resolve/main/onnx/model.onnx"
    do
        printf "  → %s\n" "$(echo "$u" | cut -d/ -f3)"
        curl -L --fail -s -o model.onnx "$u" 2>/dev/null
        SZ=$(wc -c < model.onnx 2>/dev/null || echo 0)
        MG=$(head -c1 model.onnx 2>/dev/null | xxd -p 2>/dev/null)
        if [ "$SZ" -gt 2000000 ] && [ "$MG" = "08" ]; then
            ok "$((SZ/1024/1024)) MB"
            GOT=1
            break
        fi
        rm -f model.onnx
    done
    [ "$GOT" -eq 0 ] && err "todas URLs falharam"
fi

step "[5/7] shell (rish / adb)"
SHELL_OK=0
BACKEND=""

# rish (com retry)
for i in 1 2; do
    if command -v rish >/dev/null 2>&1; then
        OUT=$(rish -c "id" 2>&1 | head -1)
        if echo "$OUT" | grep -q "uid=2000"; then
            ok "rish funcional"
            SHELL_OK=1
            BACKEND="rish"
            break
        fi
    fi
done

# adb (start-server + retry + reconnect)
if [ "$SHELL_OK" -eq 0 ]; then
    if command -v adb >/dev/null 2>&1; then
        adb start-server >/dev/null 2>&1
        for i in 1 2 3; do
            OUT=$(adb shell id 2>&1 | head -1)
            if echo "$OUT" | grep -q "uid=2000"; then
                ok "adb funcional"
                SHELL_OK=1
                BACKEND="adb"
                break
            fi
            sleep 1
        done
        # reconecta se ainda falhou
        if [ "$SHELL_OK" -eq 0 ]; then
            DEVS=$(adb devices | grep -v "List" | grep -E "offline|device" | awk '{print $1}' | head -1)
            if [ -n "$DEVS" ]; then
                adb disconnect "$DEVS" >/dev/null 2>&1
                adb connect "$DEVS" >/dev/null 2>&1
                sleep 2
                if adb shell id 2>/dev/null | grep -q "uid=2000"; then
                    ok "adb reconectado"
                    SHELL_OK=1
                    BACKEND="adb"
                fi
            fi
        fi
    fi
fi

if [ "$SHELL_OK" -eq 0 ]; then
    err "sem shell funcional"
    echo "  ${B}A) Shizuku${N}: f-droid.org/packages/moe.shizuku.privileged.api/"
    echo "  ${B}B) ADB${N}:    Emparelhar dispositivo em Depuração sem fio"
fi

step "[6/7] AimBuddy"
AB="com.aimbuddy"
if command -v adb >/dev/null 2>&1; then
    if adb shell pm list packages 2>/dev/null | grep -q "$AB"; then
        ok "instalado (auto-launch ativo)"
    else
        warn "não instalado — instale o APK do repositório 1337Xcode/AimBuddy"
    fi
fi

step "[7/7] verificação"
[ -f zyon_ultimate.py ] && ok "motor" || err "motor ausente"
python -m py_compile zyon_ultimate.py 2>/dev/null && ok "sintaxe" || err "sintaxe"
[ -f model.onnx ] && ok "modelo" || err "modelo"

printf "\n%b════════════════════════════════════════════%b\n" "$B" "$N"
if [ "$SHELL_OK" -eq 1 ] && [ -f model.onnx ] && [ -f zyon_ultimate.py ]; then
    printf "%b%b ✅ TUDO PRONTO%b  ${C}shell=%s${N}  ${C}modelo=%s${N}\n" \
        "$B" "$G" "$N" "$BACKEND" "$(du -h model.onnx | cut -f1)"
    printf "%b════════════════════════════════════════════%b\n" "$B" "$N"

    if [ "$AUTO_RUN" -eq 1 ]; then
        printf "\n%b%b▸ motor inicia em 5s…%b\n" "$B" "$C" "$N"
        printf "%b  ⚠ ABRA O JOGO E ENTRE EM PARTIDA AGORA%b\n" "$Y" "$N"
        printf "%b  ⚠ Ctrl+C no toolbar do Termux pra sair%b\n\n" "$Y" "$N"
        sleep 5
        exec python zyon_ultimate.py
    else
        printf "\n  rodar: %bcd ~/Zyon--aim--db && python zyon_ultimate.py%b\n" "$C" "$N"
    fi
else
    printf "%b%b ⚠ pendências%b\n" "$B" "$Y" "$N"
    printf "%b════════════════════════════════════════════%b\n" "$B" "$N"
    printf "\n  corrige e roda: %bbash install.sh%b\n" "$C" "$N"
fi
