# -*- coding: utf-8 -*-
"""Comandos de mapas e layouts de ponta a ponta dentro do QGIS (sem interface).

    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests\\test_mapas.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,  # noqa: E402
                       QgsCategorizedSymbolRenderer, QgsGraduatedSymbolRenderer,
                       QgsSingleSymbolRenderer, QgsLayoutItemLegend, QgsLayoutItemScaleBar,
                       QgsLayoutItemPicture, QgsLayoutItemLabel, QgsCoordinateReferenceSystem)

app = QgsApplication([], False)
app.initQgis()
sys.path.append(os.path.join(QgsApplication.prefixPath(), "python", "plugins"))

from qgis_ia import comandos  # noqa: E402
from qgis_ia.executor import execute_plan, ACTIONS  # noqa: E402

FALHAS = []
SAIDA = tempfile.mkdtemp(prefix="qgisia_mapas_")


def check(cond, msg):
    if not cond:
        FALHAS.append(msg)
        print("FALHOU:", msg)


QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31983"))
lotes = QgsVectorLayer("Polygon?crs=EPSG:31983&field=id:integer&field=bairro:string(50)&field=pop:integer",
                       "lotes", "memory")
feats = []
for i, (bairro, pop, lado) in enumerate([("Centro", 100, 10), ("Centro", 250, 50),
                                         ("Sul", 900, 100), ("Norte", 40, 30), ("Sul", 500, 70)]):
    f = QgsFeature(lotes.fields())
    x = i * 200
    f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 0,{x+lado} 0,{x+lado} {lado},{x} {lado},{x} 0))"))
    f.setAttributes([i + 1, bairro, pop])
    feats.append(f)
lotes.dataProvider().addFeatures(feats)
vias = QgsVectorLayer("LineString?crs=EPSG:31983&field=nome:string(50)", "vias", "memory")
f = QgsFeature(vias.fields())
f.setGeometry(QgsGeometry.fromWkt("LINESTRING(0 -10, 1000 -10)"))
f.setAttributes(["Av. Central"])
vias.dataProvider().addFeatures([f])
QgsProject.instance().addMapLayers([lotes, vias])


def ctx():
    proj = QgsProject.instance()
    return {"camadas": [l.name() for l in proj.mapLayers().values()],
            "campos": {l.name(): [f.name() for f in l.fields()] for l in proj.mapLayers().values()},
            "ativa": "lotes",
            "layouts": [l.name() for l in proj.layoutManager().printLayouts()]}


def rodar(frase, deve_funcionar=True):
    plano = comandos.interpretar(frase, ctx())
    check(plano is not None, f"não reconheceu: {frase}")
    if plano is None:
        return None
    for s in plano["steps"]:
        check(s["action"] in ACTIONS, f"ação sem implementação no executor: {s['action']}")
    res = execute_plan(plano)
    if deve_funcionar:
        for r in res:
            check(r.get("success"), f"{frase}: {str(r.get('error'))[-400:]}")
    return res[-1].get("result") if res else None


def simbolo(layer):
    return layer.renderer().symbol()


# --- cor, contorno, tamanho
rodar("pintar lotes de azul")
check(isinstance(lotes.renderer(), QgsSingleSymbolRenderer), "pintar: símbolo único")
check(simbolo(lotes).color().name() == "#1f78b4", f"pintar: cor {simbolo(lotes).color().name()}")
rodar("contorno preto de 0.6 em lotes")
sl = simbolo(lotes).symbolLayer(0)
check(sl.strokeColor().name() == "#000000" and abs(sl.strokeWidth() - 0.6) < 1e-6,
      f"contorno: {sl.strokeColor().name()} {sl.strokeWidth()}")
check(simbolo(lotes).color().name() == "#1f78b4", "contorno não pode mudar a cor de preenchimento")
rodar("espessura 1.2 em vias")
check(abs(simbolo(vias).width() - 1.2) < 1e-6, f"espessura da linha: {simbolo(vias).width()}")
rodar("deixar lotes sem preenchimento")
check(simbolo(lotes).color().alpha() == 0, "sem preenchimento")
rodar("pintar vias de vermelho")
check(simbolo(vias).color().name() == "#e31a1c", "linha vermelha")

# --- transparência
rodar("transparência 30% em lotes")
check(abs(lotes.opacity() - 0.7) < 1e-6, f"opacidade {lotes.opacity()}")

# --- cores por campo
rodar("cores por bairro em lotes")
r = lotes.renderer()
check(isinstance(r, QgsCategorizedSymbolRenderer) and len(r.categories()) == 3,
      "categorizado por bairro com 3 classes")
rodar("contorno branco em lotes")
check(all(c.symbol().symbolLayer(0).strokeColor().name() == "#ffffff" for c in lotes.renderer().categories()),
      "contorno em todas as categorias, sem desfazer o categorizado")
check(isinstance(lotes.renderer(), QgsCategorizedSymbolRenderer), "categorizado mantido após contorno")
rodar("classificar lotes por pop em 3 classes em tons de vermelho")
r = lotes.renderer()
check(isinstance(r, QgsGraduatedSymbolRenderer) and len(r.ranges()) == 3, "graduado por pop em 3 classes")
rodar("cores por área em 4 classes quantil")
r = lotes.renderer()
check(isinstance(r, QgsGraduatedSymbolRenderer) and r.classAttribute() == "$area",
      f"graduado por expressão $area: {getattr(r, 'classAttribute', lambda: None)()}")

# --- rótulos
rodar("rótulos com bairro tamanho 12 negrito")
check(lotes.labelsEnabled() and lotes.labeling().settings().fieldName == "bairro", "rótulos ligados")
fmt = lotes.labeling().settings().format()
check(fmt.font().bold() and abs(fmt.size() - 12) < 1e-6 and fmt.buffer().enabled(),
      "rótulo negrito, 12, com halo")
rodar('rótulos com "bairro" || \' (\' || "pop" || \')\'')
check(lotes.labeling().settings().isExpression, "rótulo por expressão")
rodar("tirar rótulos de lotes")
check(not lotes.labelsEnabled(), "rótulos desligados")

# --- ordem e visibilidade
root = QgsProject.instance().layerTreeRoot()
rodar("mandar lotes para trás")
check(root.layerOrder()[-1].name() == "lotes" if root.layerOrder() else False,
      f"lotes no fundo: {[l.name() for l in root.layerOrder()]}")
rodar("trazer lotes para frente")
check([n.name() for n in root.findLayers()][0] == "lotes", "lotes na frente")
rodar("esconder camada vias")
check(not root.findLayer(vias.id()).isVisible(), "vias escondida")
rodar("mostrar todas as camadas")
check(root.findLayer(vias.id()).isVisible(), "todas visíveis")

# --- layouts
res = rodar("criar layout A4 com título Mapa de Lotes")
lm = QgsProject.instance().layoutManager()
lay = lm.layoutByName("Mapa de Lotes")
check(lay is not None, f"layout criado: {res}")
if lay is not None:
    tipos = [type(i).__name__ for i in lay.items()]
    for t in (QgsLayoutItemLegend, QgsLayoutItemScaleBar, QgsLayoutItemPicture, QgsLayoutItemLabel):
        check(t.__name__ in tipos, f"layout sem {t.__name__}: {tipos}")
rodar("criar layout A3 retrato chamado Prancha 02 sem legenda")
p2 = lm.layoutByName("Prancha 02")
check(p2 is not None and p2.pageCollection().page(0).pageSize().height() > 400,
      "A3 retrato (420 mm de altura)")
check(p2 is not None and not any(isinstance(i, QgsLayoutItemLegend) for i in p2.items()), "sem legenda")
rodar("adicionar legenda no layout Prancha 02")
check(any(isinstance(i, QgsLayoutItemLegend) for i in p2.items()), "legenda acrescentada")
rodar('adicionar texto "Fonte: SLU-DF" no layout Prancha 02')

rodar(f"exportar layout Mapa de Lotes em png com 80 dpi para {os.path.join(SAIDA, 'paisagem.png')}")
pdf = os.path.join(SAIDA, "lotes.pdf")
rodar(f"exportar layout Mapa de Lotes em {pdf}")
check(os.path.exists(pdf) and os.path.getsize(pdf) > 1000, f"PDF gerado: {pdf}")
png = os.path.join(SAIDA, "prancha.png")
rodar(f"exportar layout Prancha 02 em png com 72 dpi para {png}")
check(os.path.exists(png) and os.path.getsize(png) > 1000, f"PNG gerado: {png}")
pasta = os.path.join(SAIDA, "pasta_nova")
rodar(f"exportar layout Prancha 02 em pdf para {pasta}\\")
check(os.path.exists(os.path.join(pasta, "Prancha 02.pdf")), "PDF numa pasta, com o nome do layout")

res = rodar("listar layouts")
check(isinstance(res, list) and len(res) == 2, f"listar layouts: {res}")
rodar("apagar layout Prancha 02")
check(lm.layoutByName("Prancha 02") is None, "layout apagado")

# sem layout nenhum: 'salvar mapa em pdf' cria um e exporta
lm.removeLayout(lm.layoutByName("Mapa de Lotes"))
QgsProject.instance().setFileName(os.path.join(SAIDA, "projeto.qgz"))
QgsProject.instance().write()
rodar("salvar mapa em pdf")
check(os.path.exists(os.path.join(SAIDA, "Mapa.pdf")), "PDF automático na pasta do projeto")

# canvas: sem interface deve falhar com mensagem clara (não quebrar)
lm.removeLayout(lm.layoutByName("Mapa"))
for frase in ("zoom total", "escala 1:5000", "salvar imagem do mapa"):
    res = execute_plan(comandos.interpretar(frase, ctx()))
    check(not res[0]["success"] and "indispon" in res[0]["error"], f"{frase}: erro claro sem interface")

print("Saída:", SAIDA)
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
app.exitQgis()
sys.exit(1 if FALHAS else 0)
