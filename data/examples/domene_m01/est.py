import json
k=0.03528
W=204.1*k; D=233.8*k; per=2*(W+D)
H=2.75; nl=2
baies=[("Mext18","Est",0.60,1.00,"fenêtre"),("Mext19","Est",0.60,1.00,"fenêtre"),("Pext04","Est",1.00,2.20,"porte vitrée"),
("Mext20","Sud",1.40,2.15,"porte-fenêtre + BSO"),("Mext21","Ouest",2.70,2.15,"baie coulissante"),("Mext22","Ouest",0.90,2.15,"porte-fenêtre"),
("Mext24","Est",1.0,1.5,"fenêtre"),("Mext25","Est",1.0,1.5,"fenêtre"),("Mext26","Ouest",1.0,1.5,"fenêtre"),("Mext27","Ouest",1.0,1.5,"fenêtre")]
by={}
for n,o,w,h,t in baies: by[o]=by.get(o,0)+w*h
Sb=sum(by.values()); brut=per*H*nl
mur=brut-Sb; toit=W*D; pb=W*D
perim_baies=sum(2*(w+h) for _,_,w,h,_ in baies)
Sref=100.0
def run(Uw,Um,Ut,Upb,psi_men):
    PT=0.6*per+0.05*per*2+0.05*per+0.05*4*H*nl*2/2+0.03*28+psi_men*perim_baies
    vent=17.74*Sref/212.2
    perm=69.46*(brut+toit)/413.5
    dep=Um*mur+Ut*toit+Upb*pb+Uw*Sb+PT+vent+perm
    ch=dep*22.6/Sref
    bbio=2*ch+2*2+5*2.3
    return dict(PT_W_K=round(PT,1),ratio_psi=round(PT/Sref,2),dep_W_K=round(dep,0),besoin_ch=round(ch,1),bbio=round(bbio,0))
out=dict(echelle_m_par_pt=k,emprise_bloc_m=[round(W,2),round(D,2)],perimetre_m=round(per,1),hauteur_hyp=H,
 murs_bruts_m2=round(brut,0),murs_nets_m2=round(mur,0),toit_m2=round(toit,1),pb_m2=round(pb,1),baies_par_orient=by,baies_total=round(Sb,2),
 perimetre_baies_m=round(perim_baies,1),
 nord_lecture="flèche vers haut-gauche : haut de page = Est, droite = Sud, bas = Ouest, gauche = Nord",
 scenario_menuiserie_avec_retour=run(1.4,0.18,0.10,0.14,0.15),scenario_sans_retour=run(1.4,0.18,0.10,0.14,0.62))
json.dump(out,open('domene_m01.json','w'),ensure_ascii=False,indent=1)
print(json.dumps(out,ensure_ascii=False,indent=1))
