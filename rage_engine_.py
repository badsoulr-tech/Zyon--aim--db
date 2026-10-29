cat << 'PYEOF' > ~/zyon_db/rage_engine.py
import subprocess, time, json, os, threading, sys, re, random
import numpy as np

DB_DIR = os.path.expanduser("~/zyon_db")
CONFIG_FILE = os.path.join(DB_DIR, "config.json")

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

def adb_devices():
    out = run(["adb", "devices"]).stdout
    return [l for l in out.strip().split('\n')[1:] if "device" in l and "offline" not in l]

def get_local_ip():
    """Pega o IP da rede Wi-Fi (wlan0)."""
    try:
        out = run(["ip", "route", "get", "8.8.8.8"]).stdout
        match = re.search(r'src\s+([0-9.]+)', out)
        if match: return match.group(1)
        
        out = run(["ifconfig", "wlan0"]).stdout
        match = re.search(r'inet\s+(?:addr:)?([0-9.]+)', out)
        if match: return match.group(1)
    except: pass
    return None

def ensure_adb_connection():
    print("[*] Verificando conexão ADB...")
    if adb_devices():
        print("[+] ADB já conectado.")
        return True

    print("[*] Conexão perdida. Tentando reconectar automaticamente...")

    # 1. Tenta mDNS
    services = run(["adb", "mdns", "services"]).stdout
    if "connect" in services:
        for line in services.splitlines():
            if "_adb-tls-connect._tcp" in line:
                addr = line.split()[-1]
                print(f"[*] mDNS encontrou: {addr}")
                run(["adb", "connect", addr])
                time.sleep(2)
                if adb_devices(): return True

    # 2. Tenta IP Local direto (porta 5555 ou porta padrão do Android 11+)
    local_ip = get_local_ip()
    if local_ip:
        print(f"[*] Testando IP local: {local_ip}")
        for port in [5555, 5037, 37000]: # Tenta portas comuns de debug
            addr = f"{local_ip}:{port}"
            run(["adb", "connect", addr])
            time.sleep(1)
            if adb_devices():
                print(f"[+] Conectado via IP Local: {addr}")
                return True

    # 3. Falha total
    print("\n❌ FALHA NO ADB AUTOMÁTICO.")
    print("⚠️  ATENÇÃO: O seu roteador pode estar bloqueando o mDNS ou a depuração está desligada.")
    print("   Para corrigir, faça UMA VEZ manualmente:")
    print("   1. Abra 'Depuração sem fio' nas Opções do Desenvolvedor.")
    print("   2. Toque em 'Parear dispositivo com código'.")
    print("   3. Rode no Termux: adb pair IP:PORTA")
    print("   4. Digite o código e depois rode: adb connect IP:PORTA_CONEXAO")
    print("   5. Após parear, o script vai se conectar sozinho nas próximas vezes.\n")
    return False

# ═════════════════════════════════════════════════════════════════
# RESTO DO CÓDIGO (IGUAL AO ANTERIOR)
# ═════════════════════════════════════════════════════════════════
def load_config():
    try:
        with open(CONFIG_FILE) as f:
            db = json.load(f)
            return db if isinstance(db, dict) and "games" in db else {"games": {}}
    except: return {"games": {}}

def push_to_github():
    if not os.path.exists(os.path.join(DB_DIR, ".git")): return
    try:
        run(["git", "pull", "--rebase", "origin", "main"], cwd=DB_DIR)
        run(["git", "add", "config.json"], cwd=DB_DIR)
        run(["git", "commit", "-m", f"Rage-Tune: {time.strftime('%H:%M')}"], cwd=DB_DIR)
        run(["git", "push", "origin", "main"], cwd=DB_DIR)
        print("[+] Modelo Evolutivo salvo no GitHub.")
    except: pass

class KalmanFilter:
    def __init__(self):
        self.x = np.zeros((4,1)); self.P = np.eye(4)*1000
        self.A = np.array([[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]], dtype=float)
        self.H = np.array([[1,0,0,0],[0,1,0,0]], dtype=float)
        self.Q = np.eye(4)*0.1; self.R = np.eye(2)*5; self.init = False
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

def get_active_package():
    try:
        out = run(["adb", "shell", "dumpsys", "window"]).stdout
        for pat in [r'mCurrentFocus=.*?u0 ([a-zA-Z0-9._]+)/', r'mFocusedApp=.*?u0 ([a-zA-Z0-9._]+)/']:
            m = re.search(pat, out)
            if m: return m.group(1)
    except: pass
    return "unknown"

def get_res():
    try:
        out = run(["adb","shell","wm","size"]).stdout
        line = [l for l in out.split("\n") if "Physical size" in l][0]
        w,h = map(int, line.split(":")[1].strip().split("x")); return w,h
    except: return 1080,2400

def start_stream(w,h):
    adb = subprocess.Popen(["adb","exec-out","screenrecord","--output-format=h264","--bit-rate","12000000","-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ff = ["ffmpeg","-loglevel","error","-hwaccel","mediacodec","-i","-","-f","rawvideo","-pix_fmt","rgb24","-vf",f"scale={w}:{h},fps=60","-"]
    return subprocess.Popen(ff, stdin=adb.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

def swipe(x1,y1,x2,y2,ms):
    subprocess.Popen(["adb","shell","input","swipe",str(int(x1)),str(int(y1)),str(int(x2)),str(int(y2)),str(int(ms))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def tap(x,y):
    subprocess.Popen(["adb","shell","input","tap",str(int(x)),str(int(y))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def detect_rage(frame, cx, cy, cfg, fov):
    sw = int(cfg["search_w"]*fov); sb = int(cfg["search_bottom"]*fov)
    x1,x2 = int(max(0,cx-sw//2)), int(min(frame.shape[1],cx+sw//2))
    y1,y2 = int(max(0, 300-(fov-1)*50)), int(min(frame.shape[0],cy+sb))
    roi = frame[y1:y2,x1:x2]
    r,g,b = roi[:,:,0].astype(int),roi[:,:,1].astype(int),roi[:,:,2].astype(int)
    mask = (r > cfg["r_min"]) & (g < cfg["gb_max"]) & (b < cfg["gb_max"])
    best_x, best_y, max_pixels = None, None, 0
    bs = 20; h, w = mask.shape
    for by in range(0, h - bs, bs):
        for bx in range(0, w - bs, bs):
            count = np.sum(mask[by:by+bs, bx:bx+bs])
            if count > 15:
                tx, ty = bx + bs//2 + x1, by + bs//2 + y1
                dist_to_center = np.hypot(tx - cx, ty - cy)
                score = count - (dist_to_center * 0.1)
                if score > max_pixels:
                    max_pixels = score; best_x, best_y = tx, ty
    return (best_x, best_y) if best_x else None

def main():
    print("═══════════════════════════════════════════")
    print("🔥 MAGIC BULLET RAGE ENGINE 🔥")
    print("═══════════════════════════════════════════")
    
    if not ensure_adb_connection(): sys.exit(1)
    
    db = load_config(); W,H = get_res(); CX,CY = W//2,H//2
    print(f"[*] Tela: {W}x{H} | Abrindo AimBuddy...")
    run(["adb", "shell", "monkey", "-p", "com.aimbuddy", "-c", "android.intent.category.LAUNCHER", "1"])
    time.sleep(3)
    
    print("[*] Rage Mode Ativado. Aguardando inimigos...")
    kf = KalmanFilter()
    stream = start_stream(W,H); fs = W*H*3
    last_aim=last_shot=0; hist=[]; fov=1.0; no_target=0; last_pkg=time.time()
    cur_pkg="unknown"; cfg=None

    try:
        while True:
            if time.time()-last_pkg > 3:
                npkg = get_active_package()
                if npkg != cur_pkg and npkg not in ["com.android.systemui","com.termux","unknown","com.aimbuddy"]:
                    cur_pkg=npkg
                    if cur_pkg not in db["games"]:
                        db["games"][cur_pkg]={"best_score":9999.0,"pid_kp":2.5,"pid_kd":0.05,"recoil_strength":10,"r_min":140,"gb_max":90,"search_w":600,"search_bottom":200,"aim_speed_ms":10}
                    cfg = db["games"][cur_pkg]
                    print(f"\n[🚀] JOGO DETECTADO: {cur_pkg.upper()}")
                last_pkg=time.time()
            
            if cfg is None:
                time.sleep(0.5); continue
            
            raw = stream.stdout.read(fs)
            if len(raw)!=fs: continue
            frame = np.frombuffer(raw,np.uint8).reshape((H,W,3))
            target = detect_rage(frame,CX,CY,cfg,fov); now=time.time()
            
            if target:
                no_target=0; fov=max(0.6,fov-0.05)
                tx,ty = target; px,py = kf.update(tx,ty)
                ex,ey = px-CX,py-CY; dist = np.hypot(ex,ey)
                
                if dist > 150 and (now - last_aim > 0.03):
                    swipe(CX, CY, px, py, 5); last_aim = now
                elif dist > 20 and (now - last_aim > 0.01):
                    swipe(CX, CY, CX + ex*0.8, CY + ey*0.8, 15); last_aim = now
                
                if dist < 25 and (now - last_shot > 0.1):
                    tap(CX,CY); swipe(CX,CY,CX,CY+cfg["recoil_strength"],10); last_shot=now
            else:
                no_target+=1
                if no_target>20: fov=min(2.0,fov+0.05)
                kf.init=False
                
    except KeyboardInterrupt:
        print("\n[!] Rage Engine Desligado.")

if __name__ == "__main__":
    main()
PYEOF
echo "✅ Script atualizado com resolução de IP Local!"
