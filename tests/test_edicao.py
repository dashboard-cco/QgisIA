# -*- coding: utf-8 -*-
"""Testa os comandos de edição de ponta a ponta dentro do QGIS (sem interface).

    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests\\test_edicao.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from qgis.core import QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry  # noqa: E402

app = QgsApplication([], False)
app.initQgis()
sys.path.append(os.path.join(QgsApplication.prefixPath(), "python", "plugins"))

from qgis_ia import comandos  # noqa: E402
from qgis_ia.executor import execute_plan, ACTIONS  # noqa: E402

FALHAS = []


def check(cond, msg):
    if not cond:
        FALHAS.append(msg)
        print("FALHOU:", msg)


lotes = QgsVectorLayer("Polygon?crs=EPSG:31983&field=id:integer&field=bairro:string(50)&field=uso:string(20)",
                       "lotes", "memory")
feats = []
for i, (bairro, uso, lado) in enumerate([("Centro", "residencial", 10), ("Centro", "comercial", 50),
                                         ("Sul", "residencial", 100), ("Norte", None, 1)]):
    f = QgsFeature(lotes.fields())
    x = i * 200
    f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 0,{x+lado} 0,{x+lado} {lado},{x} {lado},{x} 0))"))
    f.setAttributes([i + 1, bairro, uso])
    feats.append(f)
lotes.dataProvider().addFeatures(feats)
QgsProject.instance().addMapLayer(lotes)


def ctx():
    camadas = [l.name() for l in QgsProject.instance().mapLayers().values()]
    campos = {l.name(): [f.name() for f in l.fields()] for l in QgsProject.instance().mapLayers().values()}
    return {"camadas": camadas, "campos": campos, "ativa": SEL[0]}


SEL = ["lotes"]  # camada selecionada no painel de camadas


def rodar(frase, sel=None):
    if sel:
        SEL[0] = sel
    plano = comandos.interpretar(frase, ctx())
    check(plano is not None, f"não reconheceu: {frase}")
    if plano is None:
        return None
    for s in plano["steps"]:
        check(s["action"] in ACTIONS, f"ação sem implementação no executor: {s['action']}")
    res = execute_plan(plano)
    for r in res:
        check(r.get("success"), f"{frase}: {str(r.get('error'))[-300:]}")
    return res[0].get("result") if res else None


campos = lambda l: [f.name() for f in l.fields()]

# campos
rodar('criar campo "area_ha" tipo decimal')
check("area_ha" in campos(lotes), "campo area_ha criado")
rodar('calcular campo "area_ha" com área em hectares')
v = {f["id"]: f["area_ha"] for f in lotes.getFeatures()}
check(abs(v[3] - 1.0) < 1e-9, f"área do lote 3 = 1 ha ({v[3]})")
rodar('renomear campo "area_ha" para "hectares"')
check("hectares" in campos(lotes) and "area_ha" not in campos(lotes), "campo renomeado")
rodar('criar campo "obs"')
rodar('apagar campos "obs" e "hectares"')
check(campos(lotes) == ["id", "bairro", "uso"], f"campos apagados ({campos(lotes)})")

# seleção / contagem
r = rodar('selecionar onde "bairro" igual a Centro')
check(lotes.selectedFeatureCount() == 2, "2 lotes no Centro")
rodar("inverter seleção")
check(lotes.selectedFeatureCount() == 2, "inverteu")
rodar("limpar seleção")
check(lotes.selectedFeatureCount() == 0, "seleção limpa")
r = rodar('contar feições onde "uso" vazio')
check(r and r["count"] == 1, f"1 lote sem uso ({r})")

# cópia
r = rodar("copiar camada como lotes_bkp")
bkp = QgsProject.instance().mapLayersByName("lotes_bkp")
check(bkp and bkp[0].featureCount() == 4, "cópia com 4 feições")
rodar('selecionar onde "uso" igual a residencial')
r = rodar("copiar só as selecionadas")
sel = QgsProject.instance().mapLayersByName("lotes_copia")
check(sel and sel[0].featureCount() == 2, "cópia só das selecionadas")

# sessão de edição + desfazer
rodar("editar camada")
check(lotes.isEditable(), "edição ligada")
rodar("apagar feições selecionadas")
check(lotes.featureCount() == 2, f"2 apagadas no buffer ({lotes.featureCount()})")
rodar("desfazer")
check(lotes.featureCount() == 4, f"desfez a exclusão ({lotes.featureCount()})")
rodar('criar campo "nivel" tipo inteiro')
check("nivel" in campos(lotes), "campo no buffer de edição")
r = rodar("o que está em edição?")
check(r and r["editing"] and r["editing"][0]["layer"] == "lotes", f"status de edição ({r})")
rodar("cancelar edição")
check(not lotes.isEditable() and "nivel" not in campos(lotes) and lotes.featureCount() == 4,
      "edição descartada")
rodar("editar")
rodar("apagar feições onde area menor que 2")  # sem campo 'area': usa $area (lote 4 tem 1 m²)
check(lotes.featureCount() == 3, f"apagou o lote de 1 m² ({lotes.featureCount()})")
rodar("salvar edição")
check(not lotes.isEditable() and lotes.featureCount() == 3, "edição salva e fechada")

# filtro
rodar('filtrar onde "bairro" igual a Sul')
check(lotes.featureCount() == 1, "filtro aplicado")
rodar("limpar filtro")
check(lotes.featureCount() >= 3, "filtro removido")

# camadas
rodar("renomear camada para lotes_backup", sel="lotes_bkp")
check(QgsProject.instance().mapLayersByName("lotes_backup"), "camada renomeada")
rodar("remover camada", sel="lotes_backup")
check(not QgsProject.instance().mapLayersByName("lotes_backup"), "camada removida")

QgsProject.instance().clear()
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
app.exitQgis()
sys.exit(1 if FALHAS else 0)
