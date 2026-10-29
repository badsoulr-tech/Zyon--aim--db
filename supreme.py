cat << 'PYEOF' > ~/zyon_db/supreme.py
import subprocess, time, json, os, threading, sys, re
import numpy as np

DB_DIR = os.path.expanduser("~/zyon_db")
CONFIG_FILE = os.path.join(DB_DIR, "config.json")

# ═════════════════════════════════════════════════════════════════
# AUTO-CONNECT ADB (mDNS) CORRIGIDO
# ═════════════════════════════════════════════════════════════════
def auto_adb_connect():
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
    # Pega apenas as linhas de dispositivos reais, ignorando o cabeçalho
    lines = out.strip().split('\n')[1:]
    if any("device" in line and "offline" not in line for line in lines):
        return True
    
    print("[*] ADB desconectado. Procurando celular na rede (mDNS)...")
    try:
        mdns = subprocess.check_output(["adb", "mdns", "services"], text=True, stderr=subprocess.DEVNULL)
        for line in mdns.splitlines():
            if "_adb-tls-connect._tcp" in line:
                addr = line.split()[-1]
                print(f"[*] Celular encontrado em: {addr}")
                subprocess.run(["adb", "connect", addr], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(2)
                # Verifica novamente se conectou
                out2 = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
                lines2 = out2.strip().split('\n')[1:]
                if any("device" in line for line in lines2):
                    return True
    except:
        pass
    
    print("[!] Não foi possível conectar automaticamente.")
    print("⚠️  Vá em Opções do Desenvolvedor > Depuração sem fio > Parear dispositivo.")
    return False

# ═════════════════════════════════════════════════════════════════
# CONFIGURAÇÕES E GIT (Proteção contra KeyError)
# ═════════════════════════════════════════════════════════════════
def load_config():
    try:
        with open(CONFIG_FILE) as f:
            db = json.load(f)
            # Garante que a chave 'games' exista
            if not isinstance(db, dict): db = {"games": {}}
            if "games" not in db: db["games"] = {}
            return db
    except: 
        return {"games": {}}

def push_to_github():
    if not os.path.exists(os.path.join(DB_DIR, ".git")): return
    try:
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "add", "config.json"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", f"Auto-Tune: {time.strftime('%H:%M')}"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push", "origin", "main"], cwd=DB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[+] IA evoluiu e enviou para o GitHub.")
    except: pass

def get_active_package():
    try:
        out = subprocess.check_output(["adb", "shell", "dumpsys", "window"], stderr=subprocess.DEVNULL).decode()
        for pat in [r'mCurrentFocus=.*?u0 ([a-zA-Z0-9._]+)/', r'mFocusedApp=.*?u0 ([a-zA-Z0-9._]+)/']:
            m = re.search(pat, out)
            if m: return m.group(1)
    except: pass
    return "unknown"

# ═════════════════════════════════════════════════════════════════
# ALGORITMOS DE CONTROLE
# ═════════════════════════════════════════════════════════════════
class KalmanFilter:
    def __init__(self):
        self.x = np.zeros((4,1)); self.P = np.eye(4)*1000
        self.A = np.array([[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]], dtype=float)
        self.H = np.array([[1,0,0,0],[0,1,0,0]], dtype=float)
        self.Q = np.eye(4)*0.05; self.R = np.eye(2)*10; self.init = False
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

class PID:
    def __init__(self, kp, kd):
        self.kp, self.kd = kp, kd; self.pe = np.array([0.0,0.0])
    def compute(self, e, dt):
        e = np.array(e, dtype=float)
        d = (e - self.pe)/dt if dt>0 else np.array([0.0,0.0])
        o = self.kp*e + self.kd*d; self.pe = e; return o

# ═════════════════════════════════════════════════════════════════
# VISÃO E INJEÇÃO
# ═════════════════════════════════════════════════════════════════
def get_res():
    try:
        out = subprocess.check_output(["adb","shell","wm","size"]).decode()
        line = [l for l in out.split("\n") if "Physical size" in l][0]
        w,h = map(int, line.split(":")[1].strip().split("x")); return w,h
    except: return 1080,2400

def start_stream(w,h):
    adb = subprocess.Popen(["adb","exec-out","screenrecord","--output-format=h264","--bit-rate","8000000","-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ff = ["ffmpeg","-loglevel","error","-hwaccel","mediacodec","-i","-","-f","rawvideo","-pix_fmt","rgb24","-vf",f"scale={w}:{h},fps=60","-"]
    return subprocess.Popen(ff, stdin=adb.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

def swipe(x1,y1,x2,y2,ms):
    subprocess.Popen(["adb","shell","input","swipe",str(int(x1)),str(int(y1)),str(int(x2)),str(int(y2)),str(int(ms))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def tap(x,y):
    subprocess.Popen(["adb","shell","input","tap",str(int(x)),str(int(y))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def detect(frame, cx, cy, cfg, fov):
    sw = int(cfg["search_w"]*fov); sb = int(cfg["search_bottom"]*fov)
    x1,x2 = int(max(0,cx-sw//2)), int(min(frame.shape[1],cx+sw//2))
    y1,y2 = int(max(0,350-(fov-1)*50)), int(min(frame.shape[0],cy+sb))
    roi = frame[y1:y2,x1:x2]
    r,g,b = roi[:,:,0].astype(int),roi[:,:,1].astype(int),roi[:,:,2].astype(int)
    mask = (r>cfg["r_min"])&(g<cfg["gb_max"])&(b<cfg["gb_max"])
    best, bestsc = None,0; bs=20; h,w = mask.shape
    for by in range(0,h-bs,bs):
        for bx in range(0,w-bs,bs):
            cnt = np.sum(mask[by:by+bs,bx:bx+bs])
            if cnt>15:
                tx,ty = bx+bs//2+x1, by+bs//2+y1
                dist = np.hypot(tx-cx,ty-cy)
                sc = cnt - dist*0.15
                if sc>bestsc: bestsc, best = sc, (tx,ty)
    return best

# ═════════════════════════════════════════════════════════════════
# LOOP PRINCIPAL
# ═════════════════════════════════════════════════════════════════
def main():
    print("═══════════════════════════════════════════")
    print("🧠 ZYON SUPREME ENGINE (Auto-Connect ADB)")
    print("═══════════════════════════════════════════")
    
    if not auto_adb_connect():
        sys.exit(1)
        
    print("[+] ADB Conectado com sucesso.")
    
    db = load_config(); W,H = get_res(); CX,CY = W//2,H//2
    print(f"[*] Resolução: {W}x{H}")
    
    print("[*] Abrindo AimBuddy...")
    subprocess.run(["adb", "shell", "monkey", "-p", "com.aimbuddy", "-c", "android.intent.category.LAUNCHER", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    
    print("[*] Iniciando captura e injeção. Aguardando jogo...")
    kf = KalmanFilter(); pid = PID(1.5,0.1)
    stream = start_stream(W,H); fs = W*H*3
    last_aim=last_shot=0; hist=[]; step=0.05; dk=dd=dr=1; fov=1.0; no_target=0; last_pkg=time.time()
    cur_pkg="unknown"; cfg=None

    try:
        while True:
            if time.time()-last_pkg>3:
                npkg = get_active_package()
                if npkg!=cur_pkg and npkg not in ["com.android.systemui","com.termux","unknown","com.aimbuddy"]:
                    cur_pkg=npkg
                    # Cria o jogo no banco se não existir
                    if cur_pkg not in db["games"]:
                        db["games"][cur_pkg]={
                            "best_score":9999.0,"pid_kp":1.5,"pid_kd":0.1,
                            "recoil_strength":8,"r_min":145,"gb_max":85,
                            "search_w":500,"search_bottom":150,"aim_speed_ms":25
                        }
                    cfg = db["games"][cur_pkg]
                    print(f"\n[🚀] JOGO DETECTADO: {cur_pkg.upper()} | Kp {cfg['pid_kp']}")
                    pid.kp,pid.kd = cfg["pid_kp"],cfg["pid_kd"]
                last_pkg=time.time()
            
            if cfg is None: 
                time.sleep(1)
                continue
            
            raw = stream.stdout.read(fs)
            if len(raw)!=fs: continue
            frame = np.frombuffer(raw,np.uint8).reshape((H,W,3))
            target = detect(frame,CX,CY,cfg,fov); now=time.time()
            
            if target:
                no_target=0; fov=max(0.6,fov-0.05)
                tx,ty = target; px,py = kf.update(tx,ty)
                ex,ey = px-CX,py-CY; dist=np.hypot(ex,ey)
                mv = pid.compute([ex,ey],0.016)
                
                if dist>25 and now-last_aim>0.03:
                    swipe(CX,CY,CX+mv[0],CY+mv[1],cfg["aim_speed_ms"]); last_aim=now
                
                if dist<20 and now-last_shot>0.12:
                    tap(CX,CY); last_shot=now; swipe(CX,CY,CX,CY+cfg["recoil_strength"],10)
                
                hist.append(dist)
                if len(hist)>100:
                    sc = np.mean(hist)+np.std(hist)*2
                    if sc<cfg["best_score"]:
                        cfg["best_score"]=sc; cfg["pid_kp"]=pid.kp; cfg["pid_kd"]=pid.kd
                        db["games"][cur_pkg]=cfg
                        with open(CONFIG_FILE,"w") as f: json.dump(db,f,indent=2)
                        threading.Thread(target=push_to_github).start()
                        print(f"[+] Evolução! Score {sc:.1f} | Kp {pid.kp:.2f}")
                    else:
                        pid.kp-=step*dk; pid.kd-=step*dd; cfg["recoil_strength"]-=step*dr
                        dk*=-1; dd*=-1; dr*=-1
                    pid.kp+=step*dk; pid.kd+=step*dd; cfg["recoil_strength"]+=step*dr
                    pid.kp=max(0.5,pid.kp); pid.kd=max(0.01,pid.kd); cfg["recoil_strength"]=max(2,cfg["recoil_strength"])
                    hist.clear()
            else:
                no_target+=1
                if no_target>30: fov=min(2.0,fov+0.02)
                kf.init=False
    except KeyboardInterrupt: 
        print("\n[!] Parando...")

if __name__ == "__main__":
    main()
PYEOF
echo "✅ Arquivo supreme.py corrigido!"
