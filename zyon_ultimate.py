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

CFG={"sw":1080,"sh":2400,"fire":[950,1800],
     "fov":450,"kp":0.32,"kd":0.08,
     "rec":18.0,"cd":110,
     "conf":0.30,"iou":0.50,"sz":640,"sz_idle":640,
     "head":0.12,"dz":6,"max_swipe":180,"ema":0.45,
     "tiou":0.25,"mmiss":10,"ab":"com.aimbuddy"}

SHELL={"f":lambda c:""}

def rish(c,t=3):
    try:return subprocess.run(["rish","-c",c],capture_output=True,text=True,timeout=t).stdout.strip()
    except:return ""
def adb(c,t=3):
    try:return subprocess.run(["adb","shell",c],capture_output=True,text=True,timeout=t).stdout.strip()
    except:return ""
def check():
    # tenta rish primeiro (mais rápido quando funciona)
    for attempt in range(2):
        r = rish("id", t=5)
        if "uid=2000" in r:
            SHELL["f"] = rish
            return "rish"
    # adb: acorda o daemon e tenta com timeout maior
    subprocess.run(["adb", "start-server"], capture_output=True, timeout=10)
    for attempt in range(3):
        a = adb("id", t=6)
        if "uid=2000" in a:
            SHELL["f"] = adb
            return "adb"
    # última tentativa: reconectar adb
    try:
        devs = subprocess.run(["adb","devices"],capture_output=True,text=True,timeout=5).stdout
        for line in devs.splitlines():
            if "\tdevice" in line:
                addr = line.split("\t")[0]
                subprocess.run(["adb","disconnect",addr],capture_output=True,timeout=5)
                subprocess.run(["adb","connect",addr],capture_output=True,timeout=10)
                time.sleep(1)
                if "uid=2000" in adb("id", t=6):
                    SHELL["f"] = adb
                    return "adb"
    except Exception:
        pass
    return None

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

def open_ab():
    p=CFG["ab"]
    out=SHELL["f"](f"pm list packages | grep -F {p}")
    if p not in (out or ""):return False
    r=SHELL["f"](f"am start -n {p}/.MainActivity 2>/dev/null")
    if "Error" in (r or ""):
        SHELL["f"](f"monkey -p {p} -c android.intent.category.LAUNCHER 1 2>/dev/null")
    return True

class KF2D:
    def __init__(s,x,y):
        s.x=np.array([x,y,0.,0.]);s.P=np.eye(4)*100.
        s.F=np.array([[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]],dtype=float)
        s.H=np.array([[1,0,0,0],[0,1,0,0]],dtype=float)
        s.R=np.eye(2)*4.;s.Q=np.eye(4)*0.05
    def pred(s):
        s.x=s.F@s.x;s.P=s.F@s.P@s.F.T+s.Q
        return s.x[:2].copy()
    def upd(s,z):
        z=np.array(z,float);y=z-s.H@s.x
        S=s.H@s.P@s.H.T+s.R;K=s.P@s.H.T@np.linalg.inv(S)
        s.x=s.x+K@y;s.P=(np.eye(4)-K@s.H)@s.P
        return s.x[:2]

class Track:
    _id=1
    def __init__(s,box):
        s.id=Track._id;Track._id+=1
        cx,cy=(box[0]+box[2])/2,(box[1]+box[3])/2
        s.kf=KF2D(cx,cy);s.box=box;s.missed=0;s.conf=box[4]
        s.fires=0;s.hits=0;s.age=1
    def upd(s,box):
        cx,cy=(box[0]+box[2])/2,(box[1]+box[3])/2
        s.kf.upd([cx,cy]);s.box=box;s.missed=0;s.conf=box[4];s.age+=1
    def pred(s):return tuple(s.kf.pred())
    def ctr(s):return ((s.box[0]+s.box[2])/2,(s.box[1]+s.box[3])/2)
    def head(s):
        x1,y1,x2,y2=s.box[:4];hr=CFG["head"]
        return ((x1+x2)/2,y1+(y2-y1)*hr)

def iou(a,b):
    x1=max(a[0],b[0]);y1=max(a[1],b[1])
    x2=min(a[2],b[2]);y2=min(a[3],b[3])
    if x2<=x1 or y2<=y1:return 0.
    i=(x2-x1)*(y2-y1)
    aa=(a[2]-a[0])*(a[3]-a[1]);bb=(b[2]-b[0])*(b[3]-b[1])
    return i/(aa+bb-i+1e-6)

class Tracker:
    def __init__(s):
        s.tracks=[];s.thr=CFG["tiou"];s.mm=CFG["mmiss"]
    def step(s,dets):
        for t in s.tracks:t.pred()
        used=set()
        for t in s.tracks:
            bi,bv=-1,s.thr
            for i,d in enumerate(dets):
                if i in used:continue
                v=iou(t.box,d)
                if v>bv:bv,bi=v,i
            if bi>=0:t.upd(dets[bi]);used.add(bi)
            else:t.missed+=1
        for i,d in enumerate(dets):
            if i not in used:s.tracks.append(Track(d))
        s.tracks=[t for t in s.tracks if t.missed<=s.mm]
        return s.tracks

class Recoil:
    def __init__(s):
        s.base=CFG["rec"];s.cur=s.base;s.h=deque(maxlen=30)
    def hit(s):s.h.append(1);s.cur=max(s.base*0.3,s.cur*0.92)
    def miss(s):s.h.append(0);s.cur=min(s.base*2,s.cur*1.05)
    def rate(s):return sum(s.h)/len(s.h) if s.h else 0.

class PID:
    def __init__(s):
        s.kp=CFG["kp"];s.kd=CFG["kd"];s.le=(0.,0.)
    def step(s,ex,ey):
        dx=s.kp*ex+s.kd*(ex-s.le[0])
        dy=s.kp*ey+s.kd*(ey-s.le[1])
        s.le=(ex,ey);return dx,dy

def nms(boxes,scores,thr):
    if len(boxes)==0:return []
    x1,y1,x2,y2=boxes[:,0],boxes[:,1],boxes[:,2],boxes[:,3]
    areas=(x2-x1)*(y2-y1);order=scores.argsort()[::-1];keep=[]
    while order.size>0:
        i=order[0];keep.append(int(i))
        xx1=np.maximum(x1[i],x1[order[1:]]);yy1=np.maximum(y1[i],y1[order[1:]])
        xx2=np.minimum(x2[i],x2[order[1:]]);yy2=np.minimum(y2[i],y2[order[1:]])
        w=np.maximum(0.,xx2-xx1);h=np.maximum(0.,yy2-yy1)
        inter=w*h
        iou_=inter/(areas[i]+areas[order[1:]]-inter+1e-6)
        order=order[np.where(iou_<=thr)[0]+1]
    return keep

class Yolo:
    def __init__(s,p):
        import onnxruntime as ort
        s.s=ort.InferenceSession(p,providers=["CPUExecutionProvider"])
        s.i=s.s.get_inputs()[0].name
    def det(s,img,cf,io,quick=False):
        sz=s.s.get_inputs()[0].shape[2]
        w0,h0=img.size
        a=np.array(img.resize((sz,sz)),dtype=np.float32)/255.
        a=np.transpose(a,(2,0,1))[None,...]
        o=s.s.run(None,{s.i:a})[0][0]
        p=o.T if o.shape[0]<o.shape[1] else o
        sc=p[:,4:].max(1);cl=p[:,4:].argmax(1)
        m=(sc>cf)&(cl==0)
        if not m.any():return []
        b=p[m,:4];sv=sc[m]
        cx,cy,bw,bh=b[:,0],b[:,1],b[:,2],b[:,3]
        x1=(cx-bw/2)*w0;y1=(cy-bh/2)*h0
        x2=(cx+bw/2)*w0;y2=(cy+bh/2)*h0
        box=np.stack([x1,y1,x2,y2],1)
        wh=box[:,2:]-box[:,:2]
        good=(wh[:,0]>15)&(wh[:,1]>30)&(wh[:,0]<w0*0.6)&(wh[:,1]<h0*0.7)
        if not good.any():return []
        box=box[good];sv=sv[good]
        k=nms(box,sv,io)
        return [(float(box[i,0]),float(box[i,1]),float(box[i,2]),float(box[i,3]),float(sv[i])) for i in k]

def hud(st):
    L=[f"{G}{B}● ACTIVE{N}  FPS {st['fps']:4.1f}  TGT {len(st['dets'])}  "
       f"FIRES {st['fires']}  HITS {G}{st['hits']}{N}  "
       f"{D}{st['sh']}/{st['sz']}{N}",""]
    L+=["── SUBSISTEMAS ───────────────────────"]
    L+=[f"  {G}✓{N} YOLO     inf={st['inf']:.0f}ms  sz={st['sz']}"]
    L+=[f"  {G}✓{N} CAPTURE  cap={st['cap']:.0f}ms"]
    L+=[f"  {G}✓{N} TRACKER  {len(st['tracks'])} ativos  lock={st['lock']}"]
    L+=[f"  {G}✓{N} PID      kp={CFG['kp']} kd={CFG['kd']} dz={CFG['dz']}"]
    L+=["","── DETECÇÕES ─────────────────────────"]
    if not st["tracks"]:L+=["  (nenhuma pessoa detectada)"]
    else:
        for t in st["tracks"][:5]:
            cx,cy=t.ctr();px,py=t.pred()
            d=math.hypot(cx-CFG["sw"]//2,cy-CFG["sh"]//2)
            tag=f"{G}◉LOCK{N}" if t.id==st["lock"] else ("·" if d>CFG["fov"] else "○")
            L+=[f"  [{t.id:02d}] ({cx:4.0f},{cy:4.0f}) pred=({px:4.0f},{py:4.0f}) d={d:3.0f} c={t.conf:.2f} age={t.age} {tag}"]
    L+=["","── AIM+RECOIL ────────────────────────"]
    L+=[f"  {st['aim']}"]
    L+=[f"  recuo {Y}{st['rec']:5.2f}{N}  hit {st['hr']*100:2.0f}%",""]
    L+=[f"{D}Ctrl+C toolbar Termux → sair{N}"]
    sys.stdout.write(CLEAR+"\n".join(L)+"\n");sys.stdout.flush()

def main():
    mp=DIR/"model.onnx"
    if not mp.exists():print(f"[!] modelo ausente");sys.exit(1)
    print("[*] YOLO…")
    y=Yolo(str(mp))
    print("[*] modelo OK")
    sh=check()
    if not sh:print("[!] SEM SHELL");sys.exit(2)
    print(f"[*] shell: {sh}")
    print("[*] abrindo AimBuddy…")
    if open_ab():print("[*] AimBuddy ativo")
    else:print("[*] AimBuddy não instalado")
    tracker=Tracker();rec=Recoil();pid=PID()
    st={"fps":0.,"fires":0,"hits":0,"dets":[],"tracks":[],"aim":"idle",
        "rec":CFG["rec"],"inf":0.,"cap":0.,"sh":sh,"hr":0.,"sz":CFG["sz"],"lock":None}
    lfms=0.;n=0;t0=time.time();lh=0.;ema=(0.,0.)
    while True:
        tc=time.time();img=cap();st["cap"]=(time.time()-tc)*1000
        if img is None:time.sleep(0.1);continue
        quick=len(tracker.tracks)==0
        st["sz"]=CFG["sz_idle"] if quick else CFG["sz"]
        ti=time.time();dets=y.det(img,CFG["conf"],CFG["iou"],quick=quick);st["inf"]=(time.time()-ti)*1000
        st["dets"]=dets
        tracks=tracker.step(dets)
        st["tracks"]=tracks
        cr=(CFG["sw"]//2,CFG["sh"]//2)
        # sticky lock: mantém o alvo travado se ele ainda existe
        locked=None
        if st["lock"] is not None:
            for t in tracks:
                if t.id==st["lock"] and t.missed==0:
                    locked=t;break
        if locked is None:
            # nova seleção: só candidatos atuais e confiáveis
            best=None;bd=1e9
            for t in tracks:
                if t.missed>0 or t.conf<0.35:continue
                px,py=t.pred()
                dd=math.hypot(px-cr[0],py-cr[1])
                if dd<bd and dd<=CFG["fov"]:bd,best=dd,t
            locked=best
            st["lock"]=best.id if best else None
        if locked:
            px,py=locked.pred()
            hx,hy=locked.head()
            # blend 70% head + 30% predição (lead de alvo móvel)
            tx=hx*0.7+px*0.3;ty=hy*0.7+py*0.3
            # alvo muito distante: mira no centro (cabeça é 1-2px)
            if (locked.box[3]-locked.box[1])<60:
                tx,ty=locked.ctr()
            ex=tx-cr[0];ey=ty-cr[1]
            if abs(ex)<CFG["dz"] and abs(ey)<CFG["dz"]:
                dx,dy=0.,-rec.cur
            else:
                dx,dy=pid.step(ex,ey);dy-=rec.cur
                dx=max(-CFG["max_swipe"],min(CFG["max_swipe"],dx))
                dy=max(-CFG["max_swipe"],min(CFG["max_swipe"],dy))
                ema=(ema[0]*(1-CFG["ema"])+dx*CFG["ema"],
                     ema[1]*(1-CFG["ema"])+dy*CFG["ema"])
                dx,dy=ema
            ex2,ey2=swipe(dx,dy)
            st["aim"]=f"alvo [{locked.id:02d}] ({tx:.0f},{ty:.0f}) swipe→({ex2},{ey2})"
            nm=time.time()*1000
            if nm-lfms>CFG["cd"]:
                tap(CFG["fire"][0],CFG["fire"][1])
                lfms=nm;st["fires"]+=1;st["hits"]+=1
                rec.hit();locked.hits+=1
        else:
            st["aim"]="idle (sem alvo no fov)"
            ema=(0.,0.);rec.miss()
        st["rec"]=rec.cur;st["hr"]=rec.rate()
        n+=1
        if time.time()-t0>1.0:st["fps"]=n/(time.time()-t0);n=0;t0=time.time()
        if time.time()-lh>0.2:hud(st);lh=time.time()

if __name__=="__main__":
    try:main()
    except KeyboardInterrupt:sys.stdout.write(CLEAR);print("[!] encerrado")
