import json
r=json.load(open('raw.json'))
k=2.50/113.35  # m/pt, calé sur baies sud (cote lue sur élévation)
m=lambda v:round(v*k,2)
e=r['pages']['RDC']['emprise_pt']
W=m(e[2]-e[0]);D=m(e[3]-e[1])
S=r['_mesures_sud_pt']
t_struct=m(S['A_struct'][1]-S['A_struct'][0]);t_tot=m(S['B_contour'][1]-S['B_contour'][0]);t_iso=m(S['C_hachure_y'][1]-S['C_hachure_y'][0])
def L(ops): return [round((b-a)*k,2) for a,b in ops]
out={'projet':'Charleville lot 3','source':r['source'],
 'echelle_m_par_pt':{'valeur':round(k,5),'tag':'déduit','source':'baies sud 113,35 pt = 2,50 m (élévation)','confiance':'moyenne'},
 'emprise_m':{'largeur':W,'profondeur':D,'tag':'déduit','confiance':'moyenne'},
 'murs_facade_sud':{'structure_m':t_struct,'hachure_isolant_m':t_iso,'epaisseur_totale_m':t_tot,
   'position_isolant':'extérieur (hachure côté extérieur) → ITE probable','tag':'déduit','confiance':'faible à moyenne',
   'a_verifier':'hachure fine (5,8 pt) à confirmer vs coupe/notice : épaisseur isolant et nature du mur'},
 'ouvertures_m':{n:{'RDC':L(r['pages']['RDC']['ouvertures_pt'][n]),'R+1':L(r['pages']['R+1']['ouvertures_pt'][n])} for n in ('sud','nord','ouest','est')},
 'ouvertures_tag':'déduit (trous dans le mur) ; ouest RDC 3,6 m = baie large ou mur non détecté → à vérifier',
 'hauteur_sous_plafond':{'valeur_m':2.50,'tag':'supposé','source':'défaut, à lire sur coupe/élévation'},
 'ponts_thermiques_ml_par_niveau':{'plancher_bas_mur':round(2*(W+D),1),'plancher_interm_mur':round(2*(W+D),1),'toiture_mur':round(2*(W+D),1),'angles_sortants_ml':round(4*2.5,1),'tag':'déduit (périmètre emprise)'},
 'manquants':['hauteurs étage (coupe)','composition exacte murs/plancher/toiture','menuiseries Uw/Sw','système chauffage/ECS','type de mur (maçonnerie ?) – légende plan']}
json.dump(out,open('charleville_lot3.json','w'),indent=1,ensure_ascii=False)
print(json.dumps(out,indent=1,ensure_ascii=False))
