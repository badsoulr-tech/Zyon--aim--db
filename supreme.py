cat << 'PYEOF' > ~/zyon_db/supreme.py
import subprocess, time, json, os, threading
import numpy as np

# ═════════════════════════════════════════════════════════════════
# CONFIGURAÇÕES DO GITHUB
# ═════════════════════════════════════════════════════════════════
DB_DIR = os.path.expanduser("~/zyon_db")
CONFIG_FILE = os.path.join(DB_DIR, "config.json")

def sync_from_github():
    """Puxa atualizações do GitHub (Código e config.json) antes de rodar."""
    print("[*] Verificando atualizações no GitHub...")
    try:
        # Verifica se há novos commits no servidor
        subprocess.run(["git", "fetch", "origin", "main"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Pega o hash local e o hash remoto
        local_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=DB_DIR).decode().strip()
        remote_hash = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=DB_DIR).decode().strip()
        
        if local_hash != remote_hash:
            print("[+] Novas atualizações encontradas! Baixando...")
            subprocess.run(["git", "pull", "origin", "main"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("[+] Código sincronizado com o GitHub com sucesso!")
            return True
        else:
            print("[*] Você já está na versão mais recente.")
            return False
    except Exception as e:
        print(f"[!] Erro ao sincronizar: {e}. Rodando com a versão local.")
        return False

def push_to_github():
    try:
        subprocess.run(["git", "add", "config.json"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "Auto-Tune: Nova precisao otimizada"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push", "origin", "main"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[+] IA evoluiu! Novo config salvo no GitHub.")
    except Exception:
        pass

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return {"best_score": 9999.0, "pid_kp": 1.5, "pid_kd": 0.1, "r_min": 150, "gb_max": 80, "search_w": 500, "search_bottom": 150, "aim_speed_ms": 25}

# ═════════════════════════════════════════════════════════════════
# ALGORITMOS DE CONTROLE
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
        self.kp = kp
        self.kd = kd
        self.prev_error = np.array([0.0, 0.0], dtype=float)

    def compute(self, error, dt):
        error = np.array(error, dtype=float)
        deriv = (error - self.prev_error) / dt if dt > 0 else np.array([0.0, 0.0], dtype=float)
        out = (self.kp * error) + (self.kd * deriv)
        self.prev_error = error
        return out

# ═════════════════════════════════════════════════════════════════
# CAPTURA E DETECÇÃO
# ═════════════════════════════════════════════════════════════════
def get_screen_resolution():
    try:
        out = subprocess.check_output(["adb", "shell", "wm", "size"]).decode()
        line = [l for l in out.split("\n") if "Physical size" in l][0]
        w, h = map(int, line.split(":")[1].strip().split("x"))
        return w, h
    except:
        return 1080, 2400

def start_video_stream(w, h):
    adb_proc = subprocess.Popen(["adb", "exec-out", "screenrecord", "--output-format=h264", "--bit-rate", "8000000", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ffmpeg_cmd = ["ffmpeg", "-loglevel", "error", "-i", "-", "-f", "rawvideo", "-pix_fmt", "rgb24", "-vf", f"scale={w}:{h},fps=30", "-"]
    return subprocess.Popen(ffmpeg_cmd, stdin=adb_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

def inject_swipe(x1, y1, x2, y2, ms):
    cmd = f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(ms)}"
    subprocess.Popen(["adb", "shell"] + cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def detect_target(frame, cx, cy, cfg):
    sw, sb = cfg["search_w"], cfg["search_bottom"]
    x1, x2 = max(0, cx - sw // 2), min(frame.shape[1], cx + sw // 2)
    y1, y2 = 350, min(frame.shape[0], cy + sb)
    roi = frame[y1:y2, x1:x2]

    r, g, b = roi[:,:,0].astype(int), roi[:,:,1].astype(int), roi[:,:,2].astype(int)
    mask = (r > cfg["r_min"]) & (g < cfg["gb_max"]) & (b < cfg["gb_max"])
    
    best_target, best_score = None, 0
    block_size = 20
    h, w = mask.shape
    
    for by in range(0, h - block_size, block_size):
        for bx in range(0, w - block_size, block_size):
            count = np.sum(mask[by:by+block_size, bx:bx+block_size])
            if count > 20:
                tx = bx + block_size // 2 + x1
                ty = by + block_size // 2 + y1
                dist = np.hypot(tx - cx, ty - cy)
                score = count - (dist * 0.1)
                if score > best_score:
                    best_score = score
                    best_target = (tx, ty)
    return best_target

# ═════════════════════════════════════════════════════════════════
# LOOP PRINCIPAL
# ═════════════════════════════════════════════════════════════════
def main():
    # 1. Tenta puxar o código mais recente do GitHub
    synced = sync_from_github()
    
    # Se baixou uma versão nova do próprio supreme.py, reinicia o script automaticamente
    if synced:
        print("[*] Reiniciando o motor com a versão mais recente...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    cfg = load_config()
    W, H = get_screen_resolution()
    CX, CY = W // 2, H // 2
    print(f"🧠 MOTOR SUPREMO ATIVO | Melhor Score: {cfg['best_score']:.2f}")
    
    kf = KalmanFilter()
    pid = SelfImprovingPID(cfg["pid_kp"], cfg["pid_kd"])
    stream = start_video_stream(W, H)
    frame_size = W * H * 3
    last_aim = 0

    error_history = []
    current_tune_step = 0.05
    direction_kp = 1
    direction_kd = 1

    try:
        while True:
            raw = stream.stdout.read(frame_size)
            if len(raw) != frame_size: continue
            frame = np.frombuffer(raw, np.uint8).reshape((H, W, 3))
            
            target = detect_target(frame, CX, CY, cfg)
            now = time.time()

            if target:
                tx, ty = target
                px, py = kf.update(tx, ty)
                err_x, err_y = px - CX, py - CY
                dist = np.hypot(err_x, err_y)
                
                error_array = np.array([err_x, err_y], dtype=float)
                move = pid.compute(error_array, 0.033)

                error_history.append(dist)
                if len(error_history) > 150:  
                    avg_error = np.mean(error_history)
                    jitter = np.std(error_history)
                    score = avg_error + (jitter * 2)
                    
                    if score < cfg["best_score"]:
                        cfg["best_score"] = score
                        cfg["pid_kp"] = pid.kp
                        cfg["pid_kd"] = pid.kd
                        with open(CONFIG_FILE, "w") as f:
                            json.dump(cfg, f, indent=2)
                        
                        threading.Thread(target=push_to_github).start()
                        print(f"[+] Novo recorde! Score: {score:.2f} | Kp: {pid.kp:.3f} Kd: {pid.kd:.3f}")
                    else:
                        pid.kp -= (current_tune_step * direction_kp)
                        pid.kd -= (current_tune_step * direction_kd)
                        direction_kp *= -1
                        direction_kd *= -1
                    
                    pid.kp += (current_tune_step * direction_kp)
                    pid.kd += (current_tune_step * direction_kd)
                    
                    pid.kp = max(0.1, pid.kp)
                    pid.kd = max(0.01, pid.kd)
                    error_history.clear()

                if dist > 25 and (now - last_aim > 0.04):
                    inject_swipe(CX, CY, CX + move[0], CY + move[1], cfg["aim_speed_ms"])
                    last_aim = now

            else:
                kf.initialized = False

    except KeyboardInterrupt:
        print("\n[!] Parando motor...")

if __name__ == "__main__":
    import sys
    main()
PYEOF
echo "✅ Código atualizado com Auto-Pull!"
