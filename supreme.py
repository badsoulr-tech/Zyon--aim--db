cat << 'PYEOF' > ~/zyon_db/supreme.py
import subprocess, time, json, os, threading, sys, re
import numpy as np

DB_DIR = os.path.expanduser("~/zyon_db")
CONFIG_FILE = os.path.join(DB_DIR, "config.json")

# ═════════════════════════════════════════════════════════════════
# INTELIGÊNCIA DE AMBIENTE (Auto-Detect Game)
# ═════════════════════════════════════════════════════════════════
def get_active_package():
    """Lê o sistema Android para descobrir qual app está na tela."""
    try:
        out = subprocess.check_output(["adb", "shell", "dumpsys", "window"], stderr=subprocess.DEVNULL).decode()
        match = re.search(r'mCurrentFocus=.*?u0 ([^/]+)/', out)
        if match:
            return match.group(1)
    except:
        pass
    return "unknown"

def get_game_profile(package_name):
    """Puxa o perfil do jogo. Se não existir, cria um novo (IA Generativa)."""
    db = load_config()
    games = db.get("games", {})
    
    if package_name in games:
        return db, package_name, games[package_name]
    
    print(f"[🧠 IA] Novo jogo detectado: {package_name}. Criando perfil genérico...")
    # Perfil universal para novos jogos
    new_profile = {
        "best_score": 9999.0, "pid_kp": 1.5, "pid_kd": 0.1,
        "recoil_strength": 8, "r_min": 145, "gb_max": 85,
        "search_w": 500, "search_bottom": 150, "aim_speed_ms": 25
    }
    games[package_name] = new_profile
    db["games"] = games
    with open(CONFIG_FILE, "w") as f:
        json.dump(db, f, indent=2)
    
    threading.Thread(target=push_to_github).start()
    return db, package_name, new_profile

# ═════════════════════════════════════════════════════════════════
# SINCRONIZAÇÃO GITHUB
# ═════════════════════════════════════════════════════════════════
def sync_from_github():
    try:
        subprocess.run(["git", "fetch", "origin", "main"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        local_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=DB_DIR).decode().strip()
        remote_hash = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=DB_DIR).decode().strip()
        if local_hash != remote_hash:
            print("[+] Novas atualizações no GitHub! Baixando...")
            subprocess.run(["git", "pull", "origin", "main"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        return False
    except: return False

def push_to_github():
    try:
        subprocess.run(["git", "add", "config.json"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "Auto-Tune: IA Evoluiu e salvou novos parametros"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push", "origin", "main"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f: return json.load(f)
    except: return {"games": {}}

# ═════════════════════════════════════════════════════════════════
# MATEMÁTICA E CONTROLE
# ═════════════════════════════════════════════════════════════════
class KalmanFilter:
    def __init__(self):
        self.x = np.zeros((4, 1))
        self.P = np.eye(4) * 1000
        self.A = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
        self.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        self.Q = np.eye(4) * 0.05
        self.R = np.eye(2) * 10
        self.initialized = False

    def update(self, z_x, z_y):
        if not self.initialized:
            self.x = np.array([[z_x], [z_y], [0], [0]], dtype=float)
            self.initialized = True
            return int(self.x[0,0]), int(self.x[1,0])
        z = np.array([[z_x], [z_y]], dtype=float)
        self.x = self.A @ self.x
        self.P = self.A @ self.P @ self.A.T + self.Q
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ self.H) @ self.P
        return int(self.x[0,0]), int(self.x[1,0])

class SelfImprovingPID:
    def __init__(self, kp, kd):
        self.kp, self.kd = kp, kd
        self.prev_error = np.array([0.0, 0.0], dtype=float)

    def compute(self, error, dt):
        error = np.array(error, dtype=float)
        deriv = (error - self.prev_error) / dt if dt > 0 else np.array([0.0, 0.0], dtype=float)
        out = (self.kp * error) + (self.kd * deriv)
        self.prev_error = error
        return out

# ═════════════════════════════════════════════════════════════════
# VISÃO COMPUTACIONAL
# ═════════════════════════════════════════════════════════════════
def detect_target(frame, cx, cy, cfg, dynamic_fov):
    sw = cfg["search_w"] * dynamic_fov
    sb = cfg["search_bottom"] * dynamic_fov
    
    x1, x2 = int(max(0, cx - sw // 2)), int(min(frame.shape[1], cx + sw // 2))
    y1, y2 = int(max(0, 350 - (dynamic_fov-1)*50)), int(min(frame.shape[0], cy + sb))
    
    roi = frame[y1:y2, x1:x2]
    r, g, b = roi[:,:,0].astype(int), roi[:,:,1].astype(int), roi[:,:,2].astype(int)
    
    # Filtro de cor adaptativo
    mask = (r > cfg["r_min"]) & (g < cfg["gb_max"]) & (b < cfg["gb_max"])
    
    best_target, best_score = None, 0
    block_size = 20
    h, w = mask.shape
    
    for by in range(0, h - block_size, block_size):
        for bx in range(0, w - block_size, block_size):
            count = np.sum(mask[by:by+block_size, bx:bx+block_size])
            if count > 15: # Threshold de bloco levemente menor para pegar alvos longe
                tx = bx + block_size // 2 + x1
                ty = by + block_size // 2 + y1
                dist = np.hypot(tx - cx, ty - cy)
                score = count - (dist * 0.15)
                if score > best_score:
                    best_score = score
                    best_target = (tx, ty)
    return best_target

def start_video_stream(w, h):
    adb_proc = subprocess.Popen(["adb", "exec-out", "screenrecord", "--output-format=h264", "--bit-rate", "10000000", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ffmpeg_cmd = ["ffmpeg", "-loglevel", "error", "-hwaccel", "mediacodec", "-i", "-", "-f", "rawvideo", "-pix_fmt", "rgb24", "-vf", f"scale={w}:{h},fps=60", "-"] # Tentando 60 FPS
    return subprocess.Popen(ffmpeg_cmd, stdin=adb_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

def inject_swipe(x1, y1, x2, y2, ms):
    subprocess.Popen(["adb", "shell", "input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(ms))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def inject_tap(x, y):
    subprocess.Popen(["adb", "shell", "input", "tap", str(int(x)), str(int(y))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ═════════════════════════════════════════════════════════════════
# LOOP PRINCIPAL
# ═════════════════════════════════════════════════════════════════
def main():
    sync_from_github()
    W, H = 1080, 2400 # Fallback
    try:
        out = subprocess.check_output(["adb", "shell", "wm", "size"]).decode()
        line = [l for l in out.split("\n") if "Physical size" in l][0]
        W, H = map(int, line.split(":")[1].strip().split("x"))
    except: pass

    CX, CY = W // 2, H // 2
    print(f"🧠 SISTEMA SUPREMO DE IA | Resolução: {W}x{H}")
    
    current_pkg = "unknown"
    db, pkg, cfg = get_game_profile(current_pkg)
    
    kf = KalmanFilter()
    pid = SelfImprovingPID(cfg["pid_kp"], cfg["pid_kd"])
    stream = start_video_stream(W, H)
    frame_size = W * H * 3
    
    last_aim = 0
    last_shot = 0
    error_history = []
    tune_step = 0.05
    dir_kp, dir_kd, dir_recoil = 1, 1, 1
    
    # Variáveis de FOV Dinâmico (Visão Periférica)
    dynamic_fov = 1.0
    frames_without_target = 0

    try:
        while True:
            # 1. Atualiza o Jogo Ativo a cada 5 segundos
            if time.time() % 5 < 0.1:
                new_pkg = get_active_package()
                if new_pkg != current_pkg and new_pkg not in ["com.android.systemui", "com.termux"]:
                    current_pkg = new_pkg
                    db, pkg, cfg = get_game_profile(current_pkg)
                    print(f"\n[🚀] JOGO DETECTADO: {pkg.upper()}")
                    print(f"     -> Precisão: Kp {cfg['pid_kp']} | Cor: {cfg['r_min']}")
                    pid.kp, pid.kd = cfg["pid_kp"], cfg["pid_kd"]

            raw = stream.stdout.read(frame_size)
            if len(raw) != frame_size: continue
            frame = np.frombuffer(raw, np.uint8).reshape((H, W, 3))
            
            # 2. Detecção com FOV Dinâmico
            target = detect_target(frame, CX, CY, cfg, dynamic_fov)
            now = time.time()

            if target:
                frames_without_target = 0
                dynamic_fov = max(0.6, dynamic_fov - 0.05) # Foca no alvo
                
                tx, ty = target
                px, py = kf.update(tx, ty)
                err_x, err_y = px - CX, py - CY
                dist = np.hypot(err_x, err_y)
                
                move = pid.compute([err_x, err_y], 0.016)

                # Aim Assist
                if dist > 25 and (now - last_aim > 0.03):
                    inject_swipe(CX, CY, CX + move[0], CY + move[1], cfg["aim_speed_ms"])
                    last_aim = now

                # Triggerbot
                if dist < 20 and (now - last_shot > 0.12):
                    inject_tap(CX, CY)
                    last_shot = now
                    # Recoil Automático
                    inject_swipe(CX, CY, CX, CY + cfg["recoil_strength"], 10)

                # 3. Aprendizado Contínuo (Mutação Genética)
                error_history.append(dist)
                if len(error_history) > 100:  
                    score = np.mean(error_history) + (np.std(error_history) * 2)
                    
                    if score < cfg["best_score"]:
                        cfg["best_score"] = score
                        cfg["pid_kp"], cfg["pid_kd"] = pid.kp, pid.kd
                        db["games"][pkg] = cfg
                        with open(CONFIG_FILE, "w") as f: json.dump(db, f, indent=2)
                        threading.Thread(target=push_to_github).start()
                        print(f"[+] Evolução no {pkg}! Score: {score:.1f} | Kp: {pid.kp:.2f}")
                    else:
                        pid.kp -= (tune_step * dir_kp)
                        pid.kd -= (tune_step * dir_kd)
                        cfg["recoil_strength"] -= (tune_step * dir_recoil)
                        dir_kp *= -1; dir_kd *= -1; dir_recoil *= -1
                    
                    pid.kp += (tune_step * dir_kp)
                    pid.kd += (tune_step * dir_kd)
                    cfg["recoil_strength"] += (tune_step * dir_recoil)
                    pid.kp = max(0.5, pid.kp); pid.kd = max(0.01, pid.kd); cfg["recoil_strength"] = max(2, cfg["recoil_strength"])
                    error_history.clear()

            else:
                # Visão Periférica: Se não achar ninguém, expande o radar
                frames_without_target += 1
                if frames_without_target > 30:
                    dynamic_fov = min(2.0, dynamic_fov + 0.02)
                kf.initialized = False

    except KeyboardInterrupt:
        print("\n[!] Parando motor...")

if __name__ == "__main__":
    main()
PYEOF
echo "✅ Cérebro Neural atualizado!"
