# -*- coding: utf-8 -*-
"""Geoprocessamento por comandos, de ponta a ponta dentro do QGIS (sem interface).

    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests\\test_geo.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,  # noqa: E402
                       QgsCoordinateReferenceSystem)

app = QgsApplication([], False)
app.initQgis()
sys.path.append(os.path.join(QgsApplication.prefixPath(), "python", "plugins"))
from processing.core.Processing import Processing  # noqa: E402
Processing.initialize()

from qgis_ia import comandos  # noqa: E402
from qgis_ia.executor import execute_plan, ACTIONS  # noqa: E402

FALHAS = []
SAIDA = tempfile.mkdtemp(prefix="qgisia_geo_")
PROJ = QgsProject.instance()
PROJ.setCrs(QgsCoordinateReferenceSystem("EPSG:31983"))


def check(cond, msg):
    if not cond:
        FALHAS.append(msg)
        print("FALHOU:", msg)


def camada(uri, nome, feicoes):
    lyr = QgsVectorLayer(uri, nome, "memory")
    fs = []
    for wkt, attrs in feicoes:
        f = QgsFeature(lyr.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes(attrs)
        fs.append(f)
    lyr.dataProvider().addFeatures(fs)
    PROJ.addMapLayer(lyr)
    return lyr


def quadrado(x, y, lado):
    return f"POLYGON(({x} {y},{x+lado} {y},{x+lado} {y+lado},{x} {y+lado},{x} {y}))"


# lotes: 4 quadrados de 100 m (2 no bairro A, 2 no B); regiao: cobre só os 2 primeiros
lotes = camada("Polygon?crs=EPSG:31983&field=id:integer&field=bairro:string(10)&field=pop:integer", "lotes",
               [(quadrado(0, 0, 100), [1, "A", 10]), (quadrado(100, 0, 100), [2, "A", 20]),
                (quadrado(300, 0, 100), [3, "B", 30]), (quadrado(400, 0, 100), [4, "B", 40])])
regiao = camada("Polygon?crs=EPSG:31983&field=ra:string(10)", "Regiao", [(quadrado(-10, -10, 220), ["RA-1"])])
pontos = camada("Point?crs=EPSG:31983&field=tipo:string(10)", "pontos",
                [("POINT(50 50)", ["x"]), ("POINT(60 60)", ["x"]), ("POINT(150 50)", ["y"]),
                 ("POINT(450 50)", ["z"])])
vias = camada("LineString?crs=EPSG:31983&field=nome:string(20)", "vias",
              [("LINESTRING(0 -5, 500 -5)", ["Av. 1"])])
graus = camada("Point?crs=EPSG:4326&field=n:integer", "pontos_graus", [("POINT(-47.9 -15.8)", [1])])

SEL = ["lotes"]


def ctx():
    return {"camadas": [l.name() for l in PROJ.mapLayers().values()],
            "campos": {l.name(): [f.name() for f in l.fields()] for l in PROJ.mapLayers().values()},
            "ativa": SEL[0], "layouts": []}


def rodar(frase, sel=None, deve_falhar=False):
    if sel:
        SEL[0] = sel
    plano = comandos.interpretar(frase, ctx())
    check(plano is not None, f"não reconheceu: {frase}")
    if plano is None:
        return None
    for s in plano["steps"]:
        check(s["action"] in ACTIONS, f"ação sem implementação: {s['action']}")
    res = execute_plan(plano)
    ok = all(r.get("success") for r in res)
    if deve_falhar:
        check(not ok, f"{frase}: devia falhar")
        return res[-1].get("error")
    for r in res:
        check(r.get("success"), f"{frase}: {str(r.get('error'))[-400:]}")
    out = res[-1].get("result") if res else None
    if isinstance(out, dict) and out.get("output_layer"):
        SEL[0] = out["output_layer"]  # o painel seleciona a camada nova
    return out


def lyr(nome):
    ls = PROJ.mapLayersByName(nome)
    return ls[0] if ls else None


def area_total(layer):
    return sum(f.geometry().area() for f in layer.getFeatures())


# buffer -> dissolver (encadeado: a saída vira a selecionada)
r = rodar("buffer de 10 m", sel="lotes")
b = lyr(r["output_layer"]) if r else None
check(b is not None and b.featureCount() == 4, "buffer: 4 feições")
check(r and r["output_layer"] == "lotes_buffer_10m", f"nome da saída: {r and r['output_layer']}")
r = rodar("dissolver")
check(r and lyr(r["output_layer"]).featureCount() == 1, "dissolver tudo: 1 feição")
r = rodar("buffer de 10 m", sel="lotes")
check(r and r["output_layer"] == "lotes_buffer_10m_2", "segundo buffer ganha nome novo")
r = rodar('dissolver por "bairro"', sel="lotes")
check(r and lyr(r["output_layer"]).featureCount() == 2, "dissolver por bairro: 2")
r = rodar("buffer de 5 m dissolvido como faixa", sel="vias")
check(r and r["output_layer"] == "faixa" and lyr("faixa").featureCount() == 1, "buffer de linha com nome")

# só nas selecionadas
lotes.selectByExpression('"bairro" = \'B\'')
r = rodar("buffer de 1 m só nas selecionadas", sel="lotes")
check(r and lyr(r["output_layer"]).featureCount() == 2, "buffer só nas 2 selecionadas")
lotes.removeSelection()

# recorte / interseção / diferença / união / mesclar
r = rodar("recortar pela camada Regiao", sel="lotes")
check(r and lyr(r["output_layer"]).featureCount() == 2, "recorte: 2 lotes dentro da região")
r = rodar("interseção com Regiao", sel="lotes")
it = lyr(r["output_layer"]) if r else None
check(it is not None and "ra" in [f.name() for f in it.fields()], "interseção traz o campo 'ra'")
r = rodar("diferença com Regiao", sel="lotes")
check(r and lyr(r["output_layer"]).featureCount() == 2, "diferença: os 2 lotes de fora")
r = rodar("união com Regiao", sel="lotes")
check(r and lyr(r["output_layer"]).featureCount() >= 4, "união")
r = rodar("mesclar com Regiao", sel="lotes")
check(r and lyr(r["output_layer"]).featureCount() == 5, "mesclar: 4 + 1")

# reprojetar
r = rodar("reprojetar para WGS84", sel="lotes")
rp = lyr(r["output_layer"]) if r else None
check(rp is not None and rp.crs().authid() == "EPSG:4326", "reprojetado para 4326")
rodar("buffer de 10 m", sel=rp.name() if rp else "lotes", deve_falhar=True)  # em graus: avisa
err = rodar("buffer de 10 m", sel="pontos_graus", deve_falhar=True)
check("graus" in str(err), f"aviso de graus: {str(err)[-200:]}")

# outras
for frase, esperado in [("gerar centroides", 4), ("envoltória", 4), ("envoltória de tudo", 1),
                        ("simplificar 1 m", 4), ("corrigir geometrias", 4), ("explodir multipartes", 4),
                        ("remover duplicadas", 4), ("polígonos para linhas", 4)]:
    r = rodar(frase, sel="lotes")
    check(r and lyr(r["output_layer"]).featureCount() == esperado,
          f"{frase}: {r and lyr(r['output_layer']).featureCount()} (esperava {esperado})")
r = rodar("extrair vértices", sel="lotes")
check(r and lyr(r["output_layer"]).featureCount() >= 16, "vértices")
r = rodar("grade de 100 m", sel="lotes")
check(r and lyr(r["output_layer"]).featureCount() >= 5, f"grade: {r and lyr(r['output_layer']).featureCount()}")

# junções e contagem
r = rodar("trazer atributos de Regiao", sel="lotes")
jn = lyr(r["output_layer"]) if r else None
check(jn is not None and jn.featureCount() == 4 and "ra" in [f.name() for f in jn.fields()],
      "junção espacial 1:1 mantém 4 lotes com 'ra'")
r = rodar("mais próximo de vias", sel="pontos")
mp = lyr(r["output_layer"]) if r else None
check(mp is not None and "distance" in [f.name() for f in mp.fields()], "mais próximo com distância")
r = rodar("contar pontos de pontos em cada polígono", sel="lotes")
ct = lyr(r["output_layer"]) if r else None
if ct is not None:
    qtd = {f["id"]: f[r["campo_criado"]] for f in ct.getFeatures()}
    check(qtd == {1: 2, 2: 1, 3: 0, 4: 1}, f"contagem por lote: {qtd}")

# seleção por localização
rodar("selecionar dentro de Regiao", sel="lotes")
check(lotes.selectedFeatureCount() == 2, f"dentro: {lotes.selectedFeatureCount()}")
rodar("selecionar fora de Regiao", sel="lotes")
check(lotes.selectedFeatureCount() == 2, "fora")
rodar("selecionar a até 100 m de Regiao", sel="lotes")
check(lotes.selectedFeatureCount() == 3, f"a até 100 m: {lotes.selectedFeatureCount()}")
lotes.removeSelection()

# consultas
r = rodar("área total", sel="lotes")
check(r and abs(r["area_m2"] - 40000) < 50, f"área total ≈ 40.000 m²: {r}")
r = rodar("comprimento total", sel="vias")
check(r and abs(r["comprimento_m"] - 500) < 2, f"comprimento ≈ 500 m: {r}")
r = rodar('estatísticas de "pop"', sel="lotes")
check(r and r["sum"] == 100 and r["mean"] == 25, f"estatísticas: {r}")
r = rodar('valores únicos de "bairro"', sel="lotes")
check(r and sorted(r["values"]) == ["A", "B"], f"valores únicos: {r}")

# gravar em arquivo
for frase, arq in [(f"exportar camada em shapefile para {SAIDA}\\", "lotes.shp"),
                   (f"exportar camada para {SAIDA}\\lotes.gpkg", "lotes.gpkg"),
                   (f"salvar camada como geojson em {SAIDA}\\lotes.geojson", "lotes.geojson"),
                   (f"exportar selecionadas em csv para {SAIDA}\\sel.csv", None)]:
    if arq is None:
        lotes.selectByExpression('"id" = 1')
    rodar(frase, sel="lotes")
    if arq:
        check(os.path.exists(os.path.join(SAIDA, arq)), f"arquivo gravado: {arq}")
with open(os.path.join(SAIDA, "sel.csv"), encoding="utf-8") as f:
    linhas = [l for l in f.read().splitlines() if l.strip()]
check(len(linhas) == 2, f"CSV só com a selecionada: {len(linhas) - 1} linha(s)")
rodar(f"exportar camada para {SAIDA}\\lotes.gpkg", sel="lotes", deve_falhar=True)  # não sobrescreve

print("Saída:", SAIDA)
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
app.exitQgis()
sys.exit(1 if FALHAS else 0)
