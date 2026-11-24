# -*- coding: utf-8 -*-
"""Comandos de camadas de ponta a ponta dentro do QGIS (sem interface).

    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests\\test_camadas.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,  # noqa: E402
                       QgsCoordinateReferenceSystem, QgsVectorFileWriter, QgsFillSymbol,
                       QgsSingleSymbolRenderer)

app = QgsApplication([], False)
app.initQgis()
sys.path.append(os.path.join(QgsApplication.prefixPath(), "python", "plugins"))
from processing.core.Processing import Processing  # noqa: E402
Processing.initialize()

from qgis_ia import comandos  # noqa: E402
from qgis_ia.executor import execute_plan  # noqa: E402

FALHAS = []
PROJ = QgsProject.instance()
SEL = [None]


def check(cond, msg):
    if not cond:
        FALHAS.append(msg)
        print("FALHOU:", msg)


def ctx():
    return {"camadas": [l.name() for l in PROJ.mapLayers().values()],
            "campos": {l.name(): [f.name() for f in l.fields()] for l in PROJ.mapLayers().values()
                       if isinstance(l, QgsVectorLayer)},
            "ativa": SEL[0], "layouts": []}


def rodar(frase, sel=None, deve_falhar=False):
    if sel:
        SEL[0] = sel
    plano = comandos.interpretar(frase, ctx())
    check(plano is not None, f"não reconheceu: {frase}")
    if plano is None:
        return None
    res = execute_plan(plano)
    ok = all(r.get("success") for r in res)
    if deve_falhar:
        check(not ok, f"{frase}: devia falhar")
        return res[-1].get("error")
    for r in res:
        check(r.get("success"), f"{frase}: {str(r.get('error'))[-400:]}")
    out = res[-1].get("result") if res else None
    if isinstance(out, dict) and out.get("output_layer"):
        SEL[0] = out["output_layer"]
    return out


def lyr(nome):
    ls = PROJ.mapLayersByName(nome)
    return ls[0] if ls else None


def memoria(uri, nome, wkts):
    c = QgsVectorLayer(uri, nome, "memory")
    fs = []
    for w in wkts:
        f = QgsFeature(c.fields())
        f.setGeometry(QgsGeometry.fromWkt(w))
        fs.append(f)
    c.dataProvider().addFeatures(fs)
    return c


def gravar(camada, caminho, driver, tabela=None):
    op = QgsVectorFileWriter.SaveVectorOptions()
    op.driverName = driver
    if tabela:
        op.layerName = tabela
        if os.path.exists(caminho):
            op.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    err = QgsVectorFileWriter.writeAsVectorFormatV3(camada, caminho, PROJ.transformContext(), op)
    assert err[0] == QgsVectorFileWriter.NoError, err


QUAD = "POLYGON((0 0,100 0,100 100,0 100,0 0))"

# ------------------------------------------------ projeto em GeoPackage (31983)
A = tempfile.mkdtemp(prefix="qgisia_cam_gpkg_")
PROJ.setFileName(os.path.join(A, "projeto.qgz"))
PROJ.setCrs(QgsCoordinateReferenceSystem("EPSG:31983"))
base = os.path.join(A, "dados", "base.gpkg")
os.makedirs(os.path.dirname(base))
gravar(memoria("Polygon?crs=EPSG:31983&field=id:integer", "lotes", [QUAD]), base, "GPKG", "lotes")
gravar(memoria("Point?crs=EPSG:31983", "postes_ant", ["POINT(5 5)"]), base, "GPKG", "postes_ant")
lotes = QgsVectorLayer(f"{base}|layername=lotes", "lotes", "ogr")
check(lotes.isValid(), "lotes do gpkg")
PROJ.addMapLayer(lotes)

r = rodar("padrão do projeto", sel="lotes")
check(r and r["formato"] == "GPKG" and r["geopackage"] == base and r["sistema"] == "EPSG:31983",
      f"padrão gpkg: {r}")

# buffer (memória) -> salvar camada: vai para o MESMO gpkg e troca a temporária
r = rodar("buffer de 10 m", sel="lotes")
buf = lyr("lotes_buffer_10m")
sym = QgsFillSymbol.createSimple({"color": "#ff0000"})
buf.setRenderer(QgsSingleSymbolRenderer(sym))
id_antigo = buf.id()
r = rodar("salvar camada")
novo = lyr("lotes_buffer_10m")
check(r and r["output_path"] == base, f"gravou no mesmo gpkg: {r}")
check(novo is not None and novo.providerType() == "ogr" and novo.id() != id_antigo,
      "camada temporária trocada pela gravada")
check(len(PROJ.mapLayersByName("lotes_buffer_10m")) == 1, "não ficou duplicada")
check(novo and novo.renderer().symbol().color().name() == "#ff0000", "estilo mantido")
check(novo and novo.featureCount() == 1, "feições gravadas")

# camada em graus (memória) -> salva reprojetada para o sistema do projeto
pts = memoria("Point?crs=EPSG:4326", "pontos_gps", ["POINT(-47.9 -15.8)"])
PROJ.addMapLayer(pts)
r = rodar("salvar na pasta do projeto", sel="pontos_gps")
check(r and r["sistema"] == "EPSG:31983", f"reprojetou para 31983: {r}")
pg = lyr("pontos_gps")
check(pg and pg.crs().authid() == "EPSG:31983" and pg.extent().xMinimum() > 100000, "coordenadas em UTM")

# camada que já é arquivo: cópia ao lado, original fica
r = rodar("salvar camada como lotes_copia", sel="lotes")
check(lyr("lotes") is not None and lyr("lotes_copia") is not None, f"cópia de camada em arquivo: {r}")

# criar camada
r = rodar('criar camada de pontos chamada postes com campos "nome" texto e "altura" decimal')
p = lyr("postes")
check(p is not None and p.providerType() == "ogr" and base in p.source(), f"postes no gpkg: {r}")
check(p and [f.name() for f in p.fields()][-2:] == ["nome", "altura"], f"campos: {p and p.fields().names()}")
check(p and p.isEditable(), "postes em edição")
check(p and p.crs().authid() == "EPSG:31983", "postes em 31983")
check(SEL[0] == "postes", "camada nova vira a selecionada")
p.rollBack()
r = rodar("criar camada de linhas temporária rascunho")
check(lyr("rascunho") and lyr("rascunho").providerType() == "memory", "temporária na memória")

# grupos, sistema, estilo, info
rodar("criar grupo Coleta")
check(PROJ.layerTreeRoot().findGroup("Coleta") is not None, "grupo criado")
rodar("mover para o grupo Coleta", sel="lotes")
g = PROJ.layerTreeRoot().findGroup("Coleta")
check(g and g.findLayer(lotes.id()) is not None, "lotes no grupo")
rodar("mover para o grupo Bases", sel="postes")
check(PROJ.layerTreeRoot().findGroup("Bases") is not None, "grupo criado ao mover")
rodar("copiar estilo de lotes_buffer_10m", sel="lotes")
check(lotes.renderer().symbol().color().name() == "#ff0000", "estilo copiado")
rodar("definir sistema 4326", sel="rascunho")
check(lyr("rascunho").crs().authid() == "EPSG:4326", "sistema definido")
r = rodar("informações da camada", sel="lotes")
check(r and r["crs"] == "EPSG:31983" and r["feature_count"] == 1, f"info: {r}")

# ------------------------------------------------ projeto em shapefile (pasta Shp)
PROJ.clear()
B = tempfile.mkdtemp(prefix="qgisia_cam_shp_")
PROJ.setFileName(os.path.join(B, "projeto.qgz"))
shp = os.path.join(B, "Shp")
os.makedirs(shp)
gravar(memoria("Polygon?crs=EPSG:31983&field=id:integer", "quadras", [QUAD]), os.path.join(shp, "quadras.shp"),
       "ESRI Shapefile")
quadras = QgsVectorLayer(os.path.join(shp, "quadras.shp"), "quadras", "ogr")
PROJ.addMapLayer(quadras)
rodar("gerar centroides", sel="quadras")
r = rodar("tornar permanente")
check(r and r["output_path"] == os.path.join(shp, "quadras_centroides.shp"), f"shp na pasta Shp: {r}")
rodar("gerar centroides", sel="quadras")
r = rodar("salvar camada", sel="quadras_centroides_2")
check(r and r["output_path"] == os.path.join(shp, "quadras_centroides_2.shp"), f"nome livre: {r}")

# abrir arquivos / pasta / gpkg com várias tabelas
PROJ.clear()
r = rodar(f"abrir {shp}")
check(r and len(r["adicionadas"]) == 3, f"pasta: {r}")
r = rodar(f"abrir o arquivo {base}")
check(r and sorted(r["adicionadas"]) == ["lotes", "lotes_buffer_10m", "lotes_copia", "pontos_gps", "postes",
                                          "postes_ant"], f"gpkg: {r}")
rodar(f"abrir C:\\nao\\existe.shp", deve_falhar=True)

# projeto não salvo e sem arquivos
PROJ.clear()
PROJ.setFileName("")
r = rodar("criar camada de pontos teste")
check(r and lyr("teste").providerType() == "memory" and "não salvo" in (r.get("aviso") or ""), f"sem projeto: {r}")
err = rodar("salvar camada", sel="teste", deve_falhar=True)
check("Salve o projeto" in str(err), f"aviso de projeto não salvo: {str(err)[-200:]}")

print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
app.exitQgis()
sys.exit(1 if FALHAS else 0)
