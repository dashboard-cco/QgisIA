# -*- coding: utf-8 -*-
"""Teste de duplicar_camada_com_ra com o QGIS sem interface.

    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests\\test_duplicar_ra.py
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "src"))
import qgis  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(qgis.__file__)), "plugins"))

from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer, QgsFeature,  # noqa: E402
                       QgsGeometry)

app = QgsApplication([], False)
app.initQgis()

from qgis_ia.actions.layers import duplicar_camada_com_ra  # noqa: E402

FALHAS = []


def check(cond, msg):
    if not cond:
        FALHAS.append(msg)
        print("FALHOU:", msg)


proj = QgsProject.instance()

# 1) camada com codigo_ra (polígonos reais do CC01.gdb, só leitura)
gdb = os.path.join(AQUI, "..", "Gdb", "CC01.gdb")
if os.path.isdir(gdb):
    pol = QgsVectorLayer(f"{gdb}|layername=lm_area_circuito_planejado", "circuitos", "ogr")
    check(pol.isValid(), "abre CC01")
    proj.addMapLayer(pol)
    r = duplicar_camada_com_ra("circuitos")
    copia = proj.mapLayersByName(r["layer_name"])[0]
    check(r["layer_name"] == "circuitos_RA", "nome padrão")
    check(copia.fields().indexOf("RA") >= 0, "campo RA criado")
    check(pol.fields().indexOf("RA") < 0, "original intacta")
    check(r["feature_count"] == pol.featureCount(), "mesmo nº de feições")
    check(r["ra_preenchida"] > 0, f"RA preenchida pelo codigo_ra ({r})")
    from qgis_ia import edital_slu as E
    f = next(f for f in copia.getFeatures() if f["codigo_ra"] in E.RA)
    check(f["RA"] == E.RA[f["codigo_ra"]], f"codigo_ra {f['codigo_ra']} -> {f['RA']}")
    r2 = duplicar_camada_com_ra("circuitos")
    check(r2["layer_name"] == "circuitos_RA (2)", "não repete nome")
    print("codigo_ra:", r)

# 2) por localização
ras = QgsVectorLayer("Polygon?crs=EPSG:31983&field=nome:string", "limites_ra", "memory")
fa, fb = QgsFeature(ras.fields()), QgsFeature(ras.fields())
fa.setGeometry(QgsGeometry.fromWkt("POLYGON((0 0,100 0,100 100,0 100,0 0))"))
fa.setAttributes(["Gama"])
fb.setGeometry(QgsGeometry.fromWkt("POLYGON((100 0,200 0,200 100,100 100,100 0))"))
fb.setAttributes(["Santa Maria"])
ras.dataProvider().addFeatures([fa, fb])
proj.addMapLayer(ras)

pts = QgsVectorLayer("Point?crs=EPSG:31983&field=id:integer", "pontos", "memory")
feats = []
for i, (x, y) in enumerate([(10, 10), (150, 50), (500, 500)]):
    f = QgsFeature(pts.fields())
    f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} {y})"))
    f.setAttributes([i])
    feats.append(f)
pts.dataProvider().addFeatures(feats)
proj.addMapLayer(pts)
r = duplicar_camada_com_ra("pontos", "pontos_com_ra", ra_layer="limites_ra")
copia = proj.mapLayersByName("pontos_com_ra")[0]
vals = {f["id"]: f["RA"] for f in copia.getFeatures()}
check(vals[0] == "Gama" and vals[1] == "Santa Maria" and not vals[2],
      f"RA por localização: {vals}")
check(r["ra_preenchida"] == 2 and r["ra_vazia"] == 1, "contagens")
print("localização:", r)

# 3) sem fonte: coluna vazia; e erro se já existir RA
r = duplicar_camada_com_ra("pontos", "pontos_vazio")
check(r["ra_preenchida"] == 0 and r["origem_ra"] == "vazio", "coluna vazia")
try:
    duplicar_camada_com_ra("pontos_vazio")
    check(False, "deveria recusar camada que já tem RA")
except ValueError:
    pass

app.exitQgis()
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
sys.exit(1 if FALHAS else 0)
