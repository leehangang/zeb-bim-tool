# -*- coding: utf-8 -*-
"""
Radiant Threshold — canvas expression (Pillow renderer).
Single-page plate -> high-res PNG + PDF.
"""
import math
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = (
    "C:/Users/이혁주/AppData/Roaming/Claude/local-agent-mode-sessions/"
    "skills-plugin/6ee99a2a-dbbb-4d9b-888e-5f7f0516e7f0/"
    "bc0df438-a07f-4782-90a7-054918b99edd/skills/canvas-design/canvas-fonts/"
)
BASE = "C:/Users/이혁주/Desktop/zeb-chatbot/presentation_design/"

# ---- palette (closed, calibrated) ---------------------------------------
PAPER   = (239, 235, 224)
INK     = (27, 38, 32)
GREEN_B = (18, 43, 25)
GREEN_M = (47, 106, 59)
GOLD    = (194, 138, 44)
GOLD_HI = (231, 188, 92)
RULE    = (58, 70, 60)

def lerp(a, b, t): return tuple(round(a[i] + (b[i]-a[i])*t) for i in range(3))
def mix(c, alpha): return lerp(PAPER, c, max(0.0, min(1.0, alpha)))
def grad(t):
    return lerp(GREEN_B, GREEN_M, t/0.55) if t < 0.55 else lerp(GREEN_M, GOLD, (t-0.55)/0.45)

# ---- geometry (logical points; origin bottom-left) ----------------------
S = 2.2
Wpt, Hpt = 1000.0, 1414.0
W, H = round(Wpt*S), round(Hpt*S)
M = 92.0
FX0, FY0, FX1, FY1 = M, M, Wpt-M, Hpt-M
CX0, CX1 = M+78, Wpt-M-66
CY0 = 446.0
CYT = FY1-156
VMAX = 130.0
THRESH = [20, 40, 60, 80, 100, 120]
def yval(v): return CY0 + (v/VMAX)*(CYT-CY0)

K, T0 = 6.4, 0.58
def _L(t): return 1.0/(1.0+math.exp(-K*(t-T0)))
_L0, _L1 = _L(0.0), _L(1.0)
def av(t): return 6.0 + 96.0*((_L(t)-_L0)/(_L1-_L0))   # summit ~102
def avc(t): return min(av(t), 100.0)                   # capped at equilibrium
def xfor(t): return CX0 + (CX1-CX0)*t
def t_for_value(target):
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo+hi)/2
        if av(mid) < target: lo = mid
        else: hi = mid
    return (lo+hi)/2
T_REAL = t_for_value(23.4)
T_EQ   = t_for_value(100.0)

# ---- pixel-space helpers (scale + y-flip) -------------------------------
def PX(x): return x*S
def PY(y): return (Hpt - y)*S
img = Image.new("RGB", (W, H), PAPER)
d = ImageDraw.Draw(img)

def font(fn, size): return ImageFont.truetype(FONT_DIR+fn, round(size*S))
DISPLAY = "BigShoulders-Bold.ttf"; MONO="GeistMono-Regular.ttf"; MONOB="GeistMono-Bold.ttf"
SERIF="InstrumentSerif-Italic.ttf"; THIN="Jura-Light.ttf"

def line(x0,y0,x1,y1,color,w=1.0):
    d.line([PX(x0),PY(y0),PX(x1),PY(y1)], fill=color, width=max(1,round(w*S)))
def dline(x0,y0,x1,y1,color,w,dash=2.0,gap=3.0):
    L=math.hypot(x1-x0,y1-y0);
    if L==0: return
    ux,uy=(x1-x0)/L,(y1-y0)/L; pos=0.0
    while pos<L:
        a=pos; b=min(pos+dash,L)
        line(x0+ux*a,y0+uy*a,x0+ux*b,y0+uy*b,color,w); pos+=dash+gap
def circle(cx,cy,r,color=None,outline=None,w=1.0):
    bb=[PX(cx)-r*S,PY(cy)-r*S,PX(cx)+r*S,PY(cy)+r*S]
    d.ellipse(bb, fill=color, outline=outline, width=max(1,round(w*S)))
def text(x,y,s,fn,size,color,anchor="ls",track=0.0):
    f=font(fn,size)
    if track==0:
        d.text((PX(x),PY(y)),s,font=f,fill=color,anchor=anchor)
    else:
        cx=PX(x)
        for ch in s:
            d.text((cx,PY(y)),ch,font=f,fill=color,anchor="ls")
            cx+=f.getlength(ch)+track*S
def strwidth(s,fn,size,track=0.0):
    f=font(fn,size); return sum(f.getlength(ch)+track*S for ch in s)/S

# ==========================================================================
# grain: patient accumulation, weighted low
seed=20260618
def rnd():
    global seed; seed=(1103515245*seed+12345)&0x7fffffff; return seed/0x7fffffff
for _ in range(2600):
    gx=FX0+rnd()*(FX1-FX0); gy=FY0+(rnd()**1.7)*(FY1-FY0)
    a=0.05+rnd()*0.06; s=0.7+rnd()*0.7
    d.rectangle([PX(gx),PY(gy),PX(gx)+s*S,PY(gy)+s*S], fill=mix(RULE,a*1.4))

# indexed strata
for v in THRESH:
    y=yval(v); eq=(v==100)
    col=mix(GOLD if eq else RULE, 0.55 if eq else 0.30)
    if eq: line(CX0,y,CX1,y,col,1.1)
    else:  dline(CX0,y,CX1,y,col,0.6,1.4,3.2)
    text(CX1+10,y-3,f"{v:03d}",MONOB if eq else MONO,8.2, GOLD if eq else mix(RULE,0.85),"ls")
    line(CX0-6,y,CX0,y,mix(RULE,0.5),0.8)
# baseline
line(CX0,CY0,CX1,CY0,INK,1.4)
text(CX1+10,CY0-3,"000",MONO,8.2,mix(RULE,0.9),"ls")

# ascending field — each stroke a vertical gradient: deep mineral base -> summit hue
N=260; SEG=16
for i in range(N+1):
    t=i/N; vt=avc(t); x=xfor(t); ytop=yval(vt)
    frac=min((av(t)-6.0)/96.0, 1.0)
    topcol=grad(frac)
    realized=(t<=T_REAL); a=0.94 if realized else 0.34
    for s in range(SEG):
        fa=s/SEG; fb=(s+1)/SEG
        cseg=lerp(GREEN_B, topcol, ((fa+fb)/2)**0.85)
        line(x, CY0+(ytop-CY0)*fa, x, CY0+(ytop-CY0)*fb, mix(cseg,a), 1.5 if realized else 1.2)

# threshold trace: realized solid
prev=None
for j in range(81):
    t=T_REAL*j/80; pt=(xfor(t),yval(avc(t)))
    if prev: line(prev[0],prev[1],pt[0],pt[1],INK,2.2)
    prev=pt
# projected dashed (aspiration up to equilibrium)
prev=None
for j in range(121):
    t=T_REAL+(T_EQ-T_REAL)*j/120; pt=(xfor(t),yval(avc(t)))
    if prev: dline(prev[0],prev[1],pt[0],pt[1],mix(GOLD,0.9),1.5,2.4,2.8)
    prev=pt
# plateau of balance (held at 100)
line(xfor(T_EQ),yval(100.0),CX1,yval(100.0),mix(GOLD,0.5),1.0)

# annotated nodes
def node(t,label):
    x,y=xfor(t),yval(av(t))
    circle(x,y,4.2,color=PAPER,outline=INK,w=1.4); circle(x,y,1.5,color=INK)
    text(x+8,y+12,label,MONOB,9,INK,"ls")
node(t_for_value(9.3),"9.3"); node(T_REAL,"23.4")

# radiant event
xd,yd=xfor(T_EQ),yval(100.0)
for r,a in [(60,0.05),(50,0.07)]:          # soft halo
    circle(xd,yd,r,color=mix(GOLD_HI,a))
for r,a in [(46,0.06),(36,0.10),(27,0.15),(19,0.24)]:
    circle(xd,yd,r,outline=mix(GOLD,a),w=1.0)
for k in range(12):
    ang=math.radians(k*30)
    line(xd+13*math.cos(ang),yd+13*math.sin(ang),xd+52*math.cos(ang),yd+52*math.sin(ang),mix(GOLD,0.22),0.7)
circle(xd,yd,9.5,color=GOLD_HI); circle(xd,yd,5.0,color=GOLD)
text(xd,yd+58,"EQUILIBRIUM",MONOB,8.4,INK,"ms")
text(xd,yd-64,"NET BALANCE · 100",MONO,7.4,mix(RULE,0.9),"ms")

# left axis (rotated)
axt="A U T O N O M Y   I N D E X   ( % )"
af=font(THIN,10.5)
tw=round(af.getlength(axt)); th=round((af.getbbox(axt)[3]-af.getbbox(axt)[1])*1.6)
tmp=Image.new("RGBA",(tw+8,th+8),(0,0,0,0)); td=ImageDraw.Draw(tmp)
td.text((4,th-2),axt,font=af,fill=mix(RULE,0.85)+(255,),anchor="ls")
tmp=tmp.rotate(90,expand=True)
img.paste(tmp,(round(PX(FX0+14)),round(PY((CY0+CYT)/2)+tmp.size[1]/2)*0+round(PY((CY0+CYT)/2)-tmp.size[1]/2)),tmp)

# frame + registration corners
d.rectangle([PX(FX0),PY(FY1),PX(FX1),PY(FY0)],outline=INK,width=max(1,round(1.0*S)))
off=16
for (cx,cy,dx,dy) in [(FX0,FY0,off,off),(FX1,FY0,-off,off),(FX0,FY1,off,-off),(FX1,FY1,-off,-off)]:
    line(cx,cy,cx+dx,cy,INK,1.0); line(cx,cy,cx,cy+dy,INK,1.0)

# header
hy=FY1-40
text(FX0+26,hy,"RADIANT  THRESHOLD",MONOB,12.5,INK,"ls")
text(FX0+26,hy-15,"PLATE I  ·  THE MEASURED ASCENT",MONO,8.6,mix(RULE,0.9),"ls")
text(FX1-26,hy,"INDEX  09.3 → 100.0",MONO,8.6,mix(RULE,0.9),"rs")
text(FX1-26,hy-15,"N 36.12   E 128.11",MONO,8.6,mix(RULE,0.9),"rs")
line(FX0+26,hy-26,FX1-26,hy-26,mix(RULE,0.4),0.6)

# title zone
text(FX0+28,CY0-46,"the measured ascent toward balance",SERIF,19,INK,"ls")
hero="EQUILIBRIUM"; target=CX1-(FX0+28)-8; fs=200.0
while strwidth(hero,DISPLAY,fs,track=fs*0.012)>target and fs>10: fs-=0.5
text(FX0+26,196,hero,DISPLAY,fs,INK,"ls",track=fs*0.012)

text(FX1-26,168,"PRIMARY  CONVERSION",MONO,8.4,mix(RULE,0.9),"rs")
text(FX1-26,132,"× 2.75",DISPLAY,30,GOLD,"rs")

text(FX0+28,FY0+20,"FIG. 01  —  09.3 → 23.4  REALIZED   ·   PROJECTION TO NET BALANCE",MONO,7.8,mix(RULE,0.85),"ls")
text(FX1-26,FY0+20,"RT · 2026",MONO,7.8,mix(RULE,0.85),"rs")

# ---- export --------------------------------------------------------------
png=BASE+"radiant-threshold.png"; pdf=BASE+"radiant-threshold.pdf"
img.save(png,"PNG")
img.save(pdf,"PDF",resolution=200.0)
print("written:", png, "|", img.size)
