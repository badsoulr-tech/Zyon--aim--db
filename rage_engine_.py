#!/usr/bin/env python3
"""
rage_engine.py — Motor de mira universal
Funciona sem root (ADB + visão) e evolui via auto-tune de parâmetros.
"""

import subprocess, time, json, os, threading, re
import numpy as np

BASE = os.path.expanduser("~/zyon_db")
CFG = os.path.join(BASE, "config.json")
OFFS_DIR = os.path.join(BASE, "offsets")

# ────────────────────────────── CONFIG ──────────────────────────────
def load_cfg():
    try:
        with open(CFG) as f:
            c = json.load(f)
            c.setdefault("games", {})
            c.setdefault("global", {})
            return c
    except:
        return {"games": {}, "global": {}}

def save_cfg(c):
    with open(CFG, "w") as f:
        json.dump(c, f, indent=2)

def push_async():
    def _push():
        try:
            subprocess.run(["git", "pull", "--rebase", "origin", "main"],
                           cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "add", "config.json"],
                           cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=BASE).returncode != 0:
                subprocess.run(["git", "commit", "-m", "auto-tune"],
                               cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["git", "push", "origin", "main"],
                               cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("[+] Parâmetros salvos no GitHub.")
        except:
            pass
    threading.Thread(target=_push, daemon=True).start()

# ────────────────────────────── ADB ──────────────────────────────
def adb(cmd):
    return subprocess.run(["adb", "shell"] + cmd.split(), capture_output=True, text=True)

def active_pkg():
    try:
        out = adb("dumpsys window").stdout
        for pat in [r'mCurrentFocus=.*?u0 ([a-zA-Z0-9._]+)/',
                    r'mFocusedApp=.*?u0 ([a-zA-Z0-9._]+)/']:
            m = re.search(pat, out)
            if m:
                return m.group(1)
    except:
        pass
    return "unknown"

def screen_size():
    try:
        out = adb("wm size").stdout
        line = [l for l in out.split("\n") if "Physical size" in l][0]
        w, h = map(int, line.split(":")[1].strip().split("x"))
        return w, h
    except:
        return 1080, 2400

def start_stream(w, h):
    adb_proc = subprocess.Popen(
        ["adb", "exec-out", "screenrecord", "--output-format=h264",
         "--bit-rate", "4000000", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    ff_cmd = ["ffmpeg", "-loglevel", "error", "-hwaccel", "mediacodec",
              "-i", "-", "-f", "rawvideo", "-pix_fmt", "rgb24",
              "-vf", f"scale={w}:{h},fps=30", "-"]
    return subprocess.Popen(ff_cmd, stdin=adb_proc.stdout,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

def swipe(x1, y1, x2, y2, ms=5):
    subprocess.Popen(
        ["adb", "shell", "input", "swipe",
         str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(ms))],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def tap(x, y):
    subprocess.Popen(
        ["adb", "shell", "input", "tap", str(int(x)), str(int(y))],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

# ────────────────────────────── KALMAN ──────────────────────────────
class Kalman:
    def __init__(self):
        self.x = np.zeros((4, 1))
        self.P = np.eye(4) * 1000
        self.A = np.array([[1, 0, 1, 0], [0, 1, 0, 1],
                           [0, 0, 1, 0], [0, 0, 0, 1]], float)
        self.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], float)
        self.Q = np.eye(4) * 0.15
        self.R = np.eye(2) * 4
        self.initialized = False

    def update(self, x, y):
        if not self.initialized:
            self.x = np.array([[x], [y], [0], [0]], float)
            self.initialized = True
            return int(self.x[0, 0]), int(self.x[1, 0])
        z = np.array([[x], [y]], float)
        self.x = self.A @ self.x
        self.P = self.A @ self.P @ self.A.T + self.Q
        y_err = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y_err
        self.P = (np.eye(4) - K @ self.H) @ self.P
        return int(self.x[0, 0]), int(self.x[1, 0])

# ────────────────────────────── DETECÇÃO ──────────────────────────────
def detect_hp_bar(frame, cx, cy, fov):
    """Detecta barra de vida vermelha com filtro de aspecto."""
    sw = int(600 * fov)
    sb = int(400 * fov)
    x1 = max(0, cx - sw // 2)
    x2 = min(frame.shape[1], cx + sw // 2)
    y1 = max(0, 200 - (int(fov) - 1) * 50)
    y2 = min(frame.shape[0], cy + sb)

    roi = frame[y1:y2, x1:x2]
    r = roi[:, :, 0].astype(int)
    g = roi[:, :, 1].astype(int)
    b = roi[:, :, 2].astype(int)
    mask = (r > 160) & (g < 70) & (b < 70)

    yc, xc = np.where(mask)
    if len(xc) < 10:
        return None
    return int(np.mean(xc)) + x1, int(np.mean(yc)) + y1

# ────────────────────────────── RECOIL DATA ──────────────────────────────
RECOIL_TABLE = {
    "com.tencent.ig": {
        "AKM":   24, "SCAR-L": 20, "M16A4": 25,
        "M416":  21, "UMP9":   18, "UZI":   16
    },
    "com.activision.callofduty.shooter": {
        "default": 18
    }
}

def read_offsets_for(pkg):
    """Lê offsets do jogo se disponíveis."""
    if not os.path.isdir(OFFS_DIR):
        return {}
    short = pkg.split(".")[-1].lower()
    for name in os.listdir(OFFS_DIR):
        if short in name.lower() or ("pubg" in name.lower() and "tencent" in pkg):
            try:
                out = {}
                for line in open(os.path.join(OFFS_DIR, name)):
                    line = line.strip()
                    if "=" in line and not line.startswith("//"):
                        k, v = line.split("=", 1)
                        out[k.strip()] = v.strip()
                return out
            except:
                pass
    return {}

# ────────────────────────────── LOOP ──────────────────────────────
def main():
    cfg = load_cfg()
    W, H = screen_size()
    CX, CY = W // 2, H // 2
    print(f"[*] Tela: {W}x{H}")

    adb("monkey -p com.aimbuddy -c android.intent.category.LAUNCHER 1")
    time.sleep(3)
    adb("setprop debug.hwui.renderer skiavk")
    adb("cmd thermalservice override-status 0")

    kf = Kalman()
    stream = start_stream(W, H)
    frame_size = W * H * 3

    last_aim = 0
    last_shot = 0
    hist = []
    fov = 1.0
    cur_pkg = "unknown"
    game = None
    direction = {"recoil": 1, "kp": 1, "kd": 1}

    try:
        while True:
            p = active_pkg()
            if p != cur_pkg and p not in (
                "com.android.systemui", "com.termux", "unknown", "com.aimbuddy"
            ):
                cur_pkg = p
                if cur_pkg not in cfg["games"]:
                    offs = read_offsets_for(cur_pkg)
                    base_recoil = float(offs.get("RecoilFactor", 12))
                    # Usa tabela de recuo se disponível
                    weapons = RECOIL_TABLE.get(cur_pkg, {})
                    if weapons:
                        base_recoil = sum(weapons.values()) / len(weapons)
                    cfg["games"][cur_pkg] = {
                        "best_score": 9999.0,
                        "recoil": base_recoil,
                        "kp": 2.5,
                        "kd": 0.05,
                        "weapon": "default"
                    }
                    save_cfg(cfg)
                game = cfg["games"][cur_pkg]
                print(f"\n[🚀] JOGO: {cur_pkg.upper()}")
                print(f"     recuo={game['recoil']:.1f} kp={game['kp']:.2f} kd={game['kd']:.2f}")

            if game is None:
                time.sleep(0.5)
                continue

            raw = stream.stdout.read(frame_size)
            if len(raw) != frame_size:
                continue
            frame = np.frombuffer(raw, np.uint8).reshape((H, W, 3))
            target = detect_hp_bar(frame, CX, CY, fov)
            now = time.time()

            if target:
                fov = max(0.8, fov - 0.05)
                tx, ty = target
                px, py = kf.update(tx, ty)
                ex, ey = px - CX, py - CY
                dist = np.hypot(ex, ey)

                # Movimento — snap se longe, track se perto
                if dist > 100 and now - last_aim > 0.02:
                    swipe(CX, CY,
                          CX + ex * game["kp"], CY + ey * game["kp"], 5)
                    last_aim = now
                elif dist > 20 and now - last_aim > 0.01:
                    swipe(CX, CY, CX + ex, CY + ey, 10)
                    last_aim = now

                # Disparo + recuo
                if dist < 30 and now - last_shot > 0.08:
                    tap(CX, CY)
                    swipe(CX, CY, CX, CY + game["recoil"], 10)
                    last_shot = now

                # Coleta para auto-tune
                hist.append(dist)
                if len(hist) > 100:
                    sc = float(np.mean(hist) + np.std(hist))
                    if sc < game["best_score"]:
                        game["best_score"] = sc
                        save_cfg(cfg)
                        push_async()
                        print(f"[+] Recorde {cur_pkg}: {sc:.1f}")
                    else:
                        # Muta para tentar algo melhor
                        game["recoil"] = max(2, game["recoil"] + 0.1 * direction["recoil"])
                        game["kp"] = max(0.5, min(6.0, game["kp"] + 0.1 * direction["kp"]))
                        game["kd"] = max(0.01, min(0.5, game["kd"] + 0.01 * direction["kd"]))
                        for k in direction:
                            direction[k] *= -1
                    hist.clear()
            else:
                fov = min(1.5, fov + 0.05)
                kf.initialized = False

    except KeyboardInterrupt:
        print("\n[!] Parando motor...")
        save_cfg(cfg)

if __name__ == "__main__":
    main()
