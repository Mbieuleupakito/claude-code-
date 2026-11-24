import pdfplumber, json, statistics as st, ezdxf, sys
SRC='/mnt/user-data/uploads/a753bf1e-PLANS__PROJET_LOT_3.pdf'
pdf=pdfplumber.open(SRC)
def key(o):
    c=o.get('non_stroking_color') if o.get('fill') else o.get('stroking_color')
    return tuple(round(x,2) for x in c) if isinstance(c,(tuple,list)) else (c,)
STYLE={ # signature graphique -> (calque, sens), à valider une fois par dossier
 (0.35,0.32,0.18):('MUR_STRUCTURE','mur porteur (aplat olive)'),
 (0.21,0.2,0.16):('MUR_CONTOUR','contour/aplat sombre des murs'),
 (0.89,0.68,0.17):('ISOLANT_HACHURE','hachure jaune = isolant'),
 (0.71,0.64,0.36):('CLOISON','cloison intérieure'),
 (0.97,0.88,0.27):('AUTRE_JAUNE','à identifier'),
}
def merge(iv,tol=1):
    iv=sorted(iv); m=[]
    for a,b in iv:
        if m and a<=m[-1][1]+tol: m[-1][1]=max(m[-1][1],b)
        else: m.append([a,b])
    return m
def run(pi):
    p=pdf.pages[pi]
    objs=[o for o in p.lines+p.curves+p.rects]
    by={}
    for o in objs:
        k=key(o)
        if k in STYLE: by.setdefault(k,[]).append(o)
    return p,by
def pts(o):
    return o.get('pts') or [(o['x0'],o['top']),(o['x1'],o['bottom'])]
res={'source':SRC.split('/')[-1],'pages':{}}
doc=ezdxf.new('R2010')
for pi in (0,1):
    p,by=run(pi)
    name=['RDC','R+1'][pi]
    off=pi*1300
    for k,l in by.items():
        lay=f"{name}_{STYLE[k][0]}"
        if lay not in doc.layers: doc.layers.add(lay)
        for o in l:
            P=[(x+off,-y) for x,y in pts(o)]
            if len(P)>=2: doc.modelspace().add_lwpolyline(P,dxfattribs={'layer':lay})
    for ch in p.chars:
        pass
    struct=by.get((0.35,0.32,0.18),[])+by.get((0.21,0.2,0.16),[])
    x0=min(o['x0'] for o in struct);x1=max(o['x1'] for o in struct)
    y0=min(o['top'] for o in struct);y1=max(o['bottom'] for o in struct)
    res['pages'][name]={'emprise_pt':[round(v,1) for v in (x0,y0,x1,y1)],
      'objets_par_style':{STYLE[k][0]:len(l) for k,l in by.items()}}
    # ouvertures = trous dans la bande structurelle de chaque façade
    band=14
    def gaps(sel,axis):
        iv=merge([(o['x0'],o['x1']) if axis=='x' else (o['top'],o['bottom']) for o in sel])
        lo,hi=(x0,x1) if axis=='x' else (y0,y1)
        return [(round(a[1],1),round(b[0],1)) for a,b in zip(iv,iv[1:]) if b[0]-a[1]>8]
    S=[o for o in struct if o['top']>y1-band*1.6]
    N=[o for o in struct if o['bottom']<y0+band*1.6 and (o['bottom']-o['top'])<40]
    W=[o for o in struct if o['x1']<x0+band*3 and (o['x1']-o['x0'])<40]
    E=[o for o in struct if o['x0']>x1-band*3 and (o['x1']-o['x0'])<40]
    res['pages'][name]['ouvertures_pt']={'sud':gaps(S,'x'),'nord':gaps(N,'x'),'ouest':gaps(W,'y'),'est':gaps(E,'y')}
    if pi==0:
        south=gaps(S,'x')
        # épaisseurs sur façade sud (bande)
        A=[o for o in by[(0.35,0.32,0.18)] if o['top']>y1-band*1.6]
        B=[o for o in by[(0.21,0.2,0.16)] if o['top']>y1-band*1.6]
        C=[o for o in by[(0.89,0.68,0.17)] if o['top']>y1-band*1.6 and 440<o['x0']<590]
        res['_mesures_sud_pt']={'A_struct':[min(o['top'] for o in A),max(o['bottom'] for o in A)],
          'B_contour':[min(o['top'] for o in B),max(o['bottom'] for o in B)],
          'C_hachure_y':[min(o['top'] for o in C),max(o['bottom'] for o in C)] if C else None}
        res['_ouvertures_sud_pt']=south
doc.saveas('charleville_lot3_RDC_R1.dxf')
json.dump(res,open('raw.json','w'),indent=1,ensure_ascii=False)
print(json.dumps(res,indent=1,ensure_ascii=False))
