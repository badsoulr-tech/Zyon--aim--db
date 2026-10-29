import subprocess, time, json, os, threading, sys, re, datetime
import numpy as np

DB_DIR = os.path.expanduser("~/zyon_db")
CONFIG_FILE = os.path.join(DB_DIR, "config.json")
LOG_FILE = os.path.join(DB_DIR, "learning_log.json")

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            db = json.load(f)
            return db if isinstance(db, dict) and "games" in db else {"games": {}}
    except: return {"games": {}}

def push_to_github(score, context):
    if not os.path.exists(os.path.join(DB_DIR, ".git")): return
    try:
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "add", "config.json"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", f"Evolucao: score={score:.1f}"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push", "origin", "main"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[+] Parâmetros salvos.")
    except: pass

def run_adb(cmd_str):
    return subprocess.run(["adb", "shell"] + cmd_str.split(), capture_output=True, text=True)

def get_active_package():
    try:
        out = run_adb("dumpsys window").stdout
        for pat in [r'mCurrentFocus=.*?u0 ([a-zA-Z0-9._]+)/', r'mFocusedApp=.*?u0 ([a-zA-Z0-9._]+)/']:
            m = re.search(pat, out)
            if m: return m.group(1)
    except: pass
    return "unknown"

def get_res():
    try:
        out = run_adb("wm size").stdout
        line = [l for l in out.split("\n") if "Physical size" in l][0]
        w,h = map(int, line.split(":")[1].strip().split("x")); return w,h
    except: return 1080,2400

def start_stream(w,h):
    adb = subprocess.Popen(["adb","exec-out","screenrecord","--output-format=h264","--bit-rate","4000000","-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ff = ["ffmpeg","-loglevel","error","-hwaccel","mediacodec","-i","-","-f","rawvideo","-pix_fmt","rgb24","-vf",f"scale={w}:{h},fps=30","-"]
    return subprocess.Popen(ff, stdin=adb.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

def swipe_fast(x1,y1,x2,y2,ms=5):
    subprocess.Popen(["adb","shell","input","swipe",str(int(x1)),str(int(y1)),str(int(x2)),str(int(y2)),str(int(ms))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def tap_fast(x,y):
    subprocess.Popen(["adb","shell","input","tap",str(int(x)),str(int(y))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

class KalmanFilter:
    def __init__(self):
        self.x = np.zeros((4,1)); self.P = np.eye(4)*1000
        self.A = np.array([[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]], dtype=float)
        self.H = np.array([[1,0,0,0],[0,1,0,0]], dtype=float)
        self.Q = np.eye(4)*0.15; self.R = np.eye(2)*4; self.init = False
    def update(self, zx, zy):
        if not self.init:
            self.x = np.array([[zx],[zy],[0],[0]], dtype=float); self.init = True
            return int(self.x[0,0]), int(self.x[1,0])
        z = np.array([[zx],[zy]], dtype=float)
        self.x = self.A @ self.x; self.P = self.A @ self.P @ self.A.T + self.Q
        y = z - self.H @ self.x; S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y; self.P = (np.eye(4) - K @ self.H) @ self.P
        return int(self.x[0,0]), int(self.x[1,0])

# ═════════════════════════════════════════════════════════════════
# NOVO DETECTOR: BLOB + RASTREAMENTO POR HISTERESE
# ═════════════════════════════════════════════════════════════════
def detect_hp_bar_blob(frame, cx, cy, fov):
    sw = int(600 * fov); sb = int(400 * fov)
    x1,x2 = int(max(0,cx-sw//2)), int(min(frame.shape[1],cx+sw//2))
    y1,y2 = int(max(0, 200-(fov-1)*50)), int(min(frame.shape[0],cy+sb))
    roi = frame[y1:y2, x1:x2]
    
    r = roi[:,:,0].astype(int); g = roi[:,:,1].astype(int); b = roi[:,:,2].astype(int)
    # Filtro rígido para vermelho de HP bar (ignora sangue escuro)
    mask = (r > 170) & (g < 60) & (b < 60)
    
    # Encontra componentes conectados simples
    # (Varre a imagem em blocos para achar um retângulo horizontal)
    best_target = None
    best_score = 0
    
    # Bloco de varredura (tamanho da barra de vida)
    bw, bh = 40, 6 
    
    for by in range(0, mask.shape[0] - bh, 2):
        for bx in range(0, mask.shape[1] - bw, 2):
            block = mask[by:by+bh, bx:bx+bw]
            count = np.sum(block)
            
            # A barra precisa ter pelo menos 40% de pixels vermelhos no bloco
            if count > (bw * bh * 0.40):
                tx, ty = bx + bw//2 + x1, by + bh//2 + y1
                dist = np.hypot(tx - cx, ty - cy)
                # Score prioriza blocos com mais vermelho e mais perto do centro
                score = count - (dist * 0.1)
                if score > best_score:
                    best_score = score; best_target = (tx, ty)
                    
    return best_target

def main():
    print("🔥 RAGE ENGINE V4 (BLOB TRACKING) 🔥")
    db = load_config(); W,H = get_res(); CX,CY = W//2,H//2
    print(f"[*] Tela: {W}x{H}")
    kf = KalmanFilter()
    stream = start_stream(W,H); fs = W*H*3
    last_aim=last_shot=0; hist=[]; fov=1.0
    cur_pkg="unknown"; cfg=None
    
    # Variáveis de Histerese (para não tremer a mira)
    locked_target = None
    lost_frames = 0

    try:
        while True:
            npkg = get_active_package()
            if npkg != cur_pkg and npkg not in ["com.android.systemui","com.termux","unknown","com.aimbuddy"]:
                cur_pkg=npkg
                if cur_pkg not in db["games"]:
                    db["games"][cur_pkg]={"best_score":9999.0,"recoil_strength":12,"aim_speed_ms":5,"pid_kp":2.5}
                cfg = db["games"][cur_pkg]
                print(f"\n[🚀] JOGO: {cur_pkg.upper()}")
            
            if cfg is None: time.sleep(0.5); continue
            
            raw = stream.stdout.read(fs)
            if len(raw)!=fs: continue
            frame = np.frombuffer(raw,np.uint8).reshape((H,W,3))
            
            target = detect_hp_bar_blob(frame, CX, CY, fov)
            now = time.time()
            
            if target:
                lost_frames = 0
                locked_target = target
                fov = max(0.8, fov - 0.02) # Foca suavemente
                
                tx,ty = target
                px,py = kf.update(tx,ty)
                ex,ey = px-CX,py-CY; dist = np.hypot(ex,ey)
                
                # SNAP Rápido (Se longe)
                if dist > 80 and (now - last_aim > 0.03):
                    swipe_fast(CX, CY, px, py, 5); last_aim = now
                # MICRO-AJUSTE (Se perto)
                elif dist > 15 and (now - last_aim > 0.01):
                    swipe_fast(CX, CY, CX + ex*0.7, CY + ey*0.7, 15); last_aim = now
                
                # TRIGGER (Atira se estiver bem no centro)
                if dist < 25 and (now - last_shot > 0.1):
                    tap_fast(CX, CY)
                    # Puxa o recuo imediatamente
                    swipe_fast(CX, CY, CX, CY + cfg["recoil_strength"], 10)
                    last_shot = now
                
                hist.append(dist)
                if len(hist) > 100:
                    sc = np.mean(hist) + np.std(hist)
                    if sc < cfg["best_score"]:
                        cfg["best_score"] = sc; db["games"][cur_pkg] = cfg
                        with open(CONFIG_FILE,"w") as f: json.dump(db,f,indent=2)
                        threading.Thread(target=push_to_github, args=(sc, {"game": cur_pkg})).start()
                    hist.clear()
            else:
                # Histerese: só solta o alvo se ele sumir por 5 frames seguidos
                lost_frames += 1
                if lost_frames > 5:
                    locked_target = None
                    kf.init = False
                fov = min(1.5, fov + 0.05)
                
    except KeyboardInterrupt: print("\n[!] Parando...")

if __name__ == "__main__":
    main()
