#!/usr/bin/env python3
import subprocess,time,sys,math,warnings
from pathlib import Path
from collections import deque
import numpy as np
from PIL import Image
warnings.filterwarnings("ignore")

DIR=Path(__file__).parent
CLEAR="\033[H\033[J"
G="\033[32m";R="\033[31m";Y="\033[33m";C="\033[36m";D="\033[90m";N="\033[0m";B="\033[1m"
CFG={"sw":1080,"sh":2400,"fire":[950,1800],"fov":450,"kp":0.35,
     "rec":18.0,"cd":120,"conf":0.35,"iou":0.45,"sz":640}

SHELL={"f":lambda c:""}

def rish(c,t=3):
    try:return subprocess.run(["rish","-c",c],capture_output=True,text=True,timeout=t).stdout.strip()
    except:return ""
def adb(c,t=3):
    try:return subprocess.run(["adb","shell",c],capture_output=True,text=True,timeout=t).stdout.strip()
    except:return ""
def check():
    for n,f in [("rish",rish),("adb",adb)]:
        if "uid=2000" in f("id"):
            SHELL["f"]=f
            return n
    return None
AIMBUDDY_PKG = None  # auto-detectado no main()
def open_aimbuddy():
    """Abre o app AimBuddy via shell se instalado."""
    global AIMBUDDY_PKG
    if AIMBUDDY_PKG is None:
        out = SHELL["f"](r"pm list packages 2>/dev/null | grep -iE 'aimbuddy|com\.aim'")
        for line in (out or "").split("\n"):
            if "package:" in line:
                AIMBUDDY_PKG = line.split("package:")[1].strip()
                break
    if not AIMBUDDY_PKG:
        return False
    SHELL["f"](f"am start -n {AIMBUDDY_PKG}/.MainActivity 2>/dev/null || am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {AIMBUDDY_PKG}")
    return True

def cap():
    SHELL["f"]("screencap -p /sdcard/_z.png")
    try:return Image.open("/sdcard/_z.png").convert("RGB")
    except:return None
def swipe(dx,dy):
    cx,cy=CFG["sw"]//2,CFG["sh"]//2
    ex=max(20,min(CFG["sw"]-20,cx+int(dx)))
    ey=max(20,min(CFG["sh"]-20,cy+int(dy)))
    SHELL["f"](f"input swipe {cx} {cy} {ex} {ey} 4")
    return (ex,ey)
def tap(x,y):SHELL["f"](f"input tap {x} {y}")

class Yolo:
    def __init__(s,p,sz):
        import onnxruntime as ort
        s.s=ort.InferenceSession(p,providers=["CPUExecutionProvider"])
        s.n=sz;s.i=s.s.get_inputs()[0].name
    def det(s,img,cf,io):
        w0,h0=img.size
        a=np.array(img.resize((s.n,s.n)),dtype=np.float32)/255.
        a=np.transpose(a,(2,0,1))[None,...]
        o=s.s.run(None,{s.i:a})[0][0]
        p=o.T if o.shape[0]<o.shape[1] else o
        sc=p[:,4:].max(1);cl=p[:,4:].argmax(1);m=(sc>cf)&(cl==0)
        if not m.any():return []
        b=p[m,:4];sv=sc[m]
        cx,cy,bw,bh=b[:,0],b[:,1],b[:,2],b[:,3]
        x1=(cx-bw/2)*w0;y1=(cy-bh/2)*h0;x2=(cx+bw/2)*w0;y2=(cy+bh/2)*h0
        return list(zip(x1,y1,x2,y2,sv))

class Recoil:
    def __init__(s):s.base=CFG["rec"];s.cur=s.base;s.h=deque(maxlen=30)
    def hit(s):s.h.append(1);s.cur=max(s.base*0.3,s.cur*0.92)
    def miss(s):s.h.append(0);s.cur=min(s.base*2,s.cur*1.05)
    def rate(s):return sum(s.h)/len(s.h) if s.h else 0.

def hud(st):
    L=[f"{G}{B}● ACTIVE{N}  FPS {st['fps']:4.1f}  TGT {len(st['dets'])}  "
       f"FIRES {st['fires']}  HITS {G}{st['hits']}{N}",""]
    L+=["── SUBSISTEMAS ───────────────────────"]
    L+=[f"  {G}✓{N} YOLO     inf={st['inf']:.0f}ms"]
    L+=[f"  {G}✓{N} CAPTURE  cap={st['cap']:.0f}ms"]
    L+=[f"  {G}✓{N} SHELL    {st['shell']}"]
    L+=["","── DETECÇÕES ─────────────────────────"]
    if not st["dets"]:L+=["  (nenhuma pessoa detectada)"]
    else:
        for i,(x1,y1,x2,y2,sc) in enumerate(st["dets"][:5]):
            cx,cy=(x1+x2)/2,(y1+y2)/2
            d=math.hypot(cx-CFG["sw"]//2,cy-CFG["sh"]//2)
            tag=f"{G}◉LOCK{N}" if d<=CFG["fov"] else "·"
            L+=[f"  [{i}] ({cx:4.0f},{cy:4.0f}) d={d:3.0f} c={sc:.2f} {tag}"]
    L+=["","── AIM+RECOIL ────────────────────────"]
    L+=[f"  {st['aim']}"]
    L+=[f"  recuo {Y}{st['rec']:5.2f}{N}  hit {st['hr']*100:2.0f}%",""]
    L+=[f"{D}Ctrl+C toolbar Termux → sair{N}"]
    sys.stdout.write(CLEAR+"\n".join(L)+"\n");sys.stdout.flush()

def main():
    mp=DIR/"model.onnx"
    if not mp.exists():print(f"[!] modelo ausente: {mp}");sys.exit(1)
    print("[*] YOLO…")
    y=Yolo(str(mp),CFG["sz"])
    print("[*] modelo OK")
    sh=check()
    if not sh:print("[!] SEM SHELL — instale Shizuku e rode: rish -c id");sys.exit(2)
    print(f"[*] shell: {sh}")
    print("[*] abrindo AimBuddy…")
    if open_aimbuddy(): print("[*] AimBuddy ativo")
    else: print("[*] AimBuddy não instalado — overlay desabilitado")
    print("[*] abrindo AimBuddy…")
    if open_aimbuddy(): print("[*] AimBuddy ativo")
    else: print("[*] AimBuddy não instalado — overlay desabilitado")
    rec=Recoil()
    st={"fps":0.,"fires":0,"hits":0,"dets":[],"aim":"idle","rec":CFG["rec"],
        "inf":0.,"cap":0.,"shell":sh,"hr":0.}
    lfms=0.;n=0;t0=time.time();lh=0.
    while True:
        tc=time.time();img=cap();st["cap"]=(time.time()-tc)*1000
        if img is None:time.sleep(0.1);continue
        ti=time.time();dets=y.det(img,CFG["conf"],CFG["iou"]);st["inf"]=(time.time()-ti)*1000
        st["dets"]=dets
        cr=(CFG["sw"]//2,CFG["sh"]//2)
        best=None;bd=1e9
        for d in dets:
            cx,cy=(d[0]+d[2])/2,(d[1]+d[3])/2
            dd=math.hypot(cx-cr[0],cy-cr[1])
            if dd<bd and dd<=CFG["fov"]:bd,best=dd,d
        if best:
            tx=int((best[0]+best[2])/2)
            ty=int(best[1]+(best[3]-best[1])*0.15)
            dx=(tx-cr[0])*CFG["kp"];dy=(ty-cr[1])*CFG["kp"]-rec.cur
            ex,ey=swipe(dx,dy)
            st["aim"]=f"alvo ({tx},{ty}) d={bd:.0f} swipe→({ex},{ey})"
            nm=time.time()*1000
            if nm-lfms>CFG["cd"]:
                tap(CFG["fire"][0],CFG["fire"][1])
                lfms=nm;st["fires"]+=1;st["hits"]+=1
                rec.hit()
        else:
            st["aim"]="idle (sem alvo no fov)"
            rec.miss()
        st["rec"]=rec.cur;st["hr"]=rec.rate()
        n+=1
        if time.time()-t0>1.0:st["fps"]=n/(time.time()-t0);n=0;t0=time.time()
        if time.time()-lh>0.2:hud(st);lh=time.time()

if __name__=="__main__":
    try:main()
    except KeyboardInterrupt:sys.stdout.write(CLEAR);print("[!] encerrado")
