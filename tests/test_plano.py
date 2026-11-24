# -*- coding: utf-8 -*-
"""Planos de Serviço SLU-DF por mensagem, de ponta a ponta dentro do QGIS (sem interface):
criar o .gdb, validar, preencher, exportar, gerar plano/programação/texto, e o preparo
das linhas (dividir, encaixar, preencher pelo lugar, gravar no .gdb).

    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests\\test_plano.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,  # noqa: E402
                       QgsCoordinateReferenceSystem, QgsProviderRegistry)

app = QgsApplication([], False)
app.initQgis()
sys.path.append(os.path.join(QgsApplication.prefixPath(), "python", "plugins"))
from processing.core.Processing import Processing  # noqa: E402
Processing.initialize()

from qgis_ia import comandos  # noqa: E402
from qgis_ia.executor import execute_plan  # noqa: E402

FALHAS = []
PROJ = QgsProject.instance()
PASTA = tempfile.mkdtemp(prefix="qgisia_plano_")
PROJ.setFileName(os.path.join(PASTA, "projeto.qgz"))
PROJ.setCrs(QgsCoordinateReferenceSystem("EPSG:31983"))
SEL = [None]


def check(cond, msg):
    if not cond:
        FALHAS.append(msg)
        print("FALHOU:", msg)


def ctx():
    ls = PROJ.mapLayersByName(SEL[0]) if SEL[0] else []
    return {"camadas": [l.name() for l in PROJ.mapLayers().values()],
            "campos": {l.name(): [f.name() for f in l.fields()] for l in PROJ.mapLayers().values()
                       if isinstance(l, QgsVectorLayer)},
            "ativa": SEL[0], "layouts": [], "fonte_ativa": ls[0].source() if ls else "",
            "pasta_projeto": PROJ.homePath()}


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
        check(r.get("success"), f"{frase}: {str(r.get('error'))[-500:]}")
    out = res[-1].get("result") if res else None
    if isinstance(out, dict) and out.get("output_layer"):
        SEL[0] = out["output_layer"]
    return out


def mesmo(a, b):
    return bool(a) and os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def lyr(nome):
    ls = PROJ.mapLayersByName(nome)
    return ls[0] if ls else None


def memoria(uri, nome, feicoes):
    c = QgsVectorLayer(uri, nome, "memory")
    fs = []
    for wkt, attrs in feicoes:
        f = QgsFeature(c.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes(attrs)
        fs.append(f)
    c.dataProvider().addFeatures(fs)
    PROJ.addMapLayer(c)
    return c


# --------------------------------------------------- .gdb modelo por mensagem
r = rodar("criar gdb da coleta convencional lote 1")
gdb = os.path.join(PASTA, "CC01.gdb")
check(r and mesmo(r.get("gdb"), gdb) and os.path.isdir(gdb), f"CC01.gdb criado na pasta do projeto: {r}")
do_gdb = [l for l in PROJ.mapLayers().values() if ".gdb" in l.source().lower()]
check(len(do_gdb) >= 4, f"camadas do gdb carregadas: {[l.name() for l in do_gdb]}")
linha_gdb = next((l for l in do_gdb if l.geometryType() == 1), None)
check(linha_gdb is not None, "camada de linhas do gdb")
SEL[0] = linha_gdb.name() if linha_gdb else None

r = rodar("validar plano")
check(r and "aprovado_sem_erros" in r and r.get("circuitos") == 0, f"validar gdb vazio: {r and {k: r[k] for k in ('circuitos', 'erros')}}")
r = rodar("validar plano com relatório")
check(r and os.path.exists(r.get("relatorio_xlsx", "")), "relatório xlsx gravado")
r = rodar("preencher atributos do plano")
check(r and "feicoes_alteradas" in r, f"preencher: {r}")
r = rodar("exportar tabela do plano")
check(r and os.path.exists(os.path.join(PASTA, "CC01_tabela_atributos.xlsx")), f"tabela: {r}")
r = rodar("gerar texto do plano")
check(r and os.path.exists(os.path.join(PASTA, "P1_CC01_plano_de_servico.docx")), f"docx: {r}")
r = rodar("gerar plano")
check(r and mesmo(r["arquivos"].get("gdb"), gdb) and os.path.exists(r["arquivos"]["docx"]), f"plano com o gdb ativo: {r}")
r = rodar("gerar programação trimestral da pintura de meio-fio lote 1 do 2º trimestre de 2026")
check(r and os.path.exists(os.path.join(PASTA, "FR01_programacao_2026_T2.xlsx")), f"programação: {r}")
r = rodar("regras do edital para P5")
check(isinstance(r, dict) and r.get("servico") == "P5", f"regras: {str(r)[:200]}")

# --------------------------------------------------- preparo das linhas
vias = memoria("LineString?crs=EPSG:31983&field=nome:string", "vias",
               [("LINESTRING(0 0, 500 0)", ["A"]), ("LINESTRING(250 -100, 250 100)", ["B"])])
r = rodar("dividir linhas a cada 100 m", sel="vias")
tr = lyr(r["output_layer"]) if r else None
check(tr is not None and tr.featureCount() == 7, f"trechos de 100 m: {tr and tr.featureCount()}")
check(tr and max(f.geometry().length() for f in tr.getFeatures()) <= 100.01, "nenhum trecho > 100 m")
r = rodar("dividir linhas nos cruzamentos", sel="vias")
cz = lyr(r["output_layer"]) if r else None
check(cz is not None and cz.featureCount() == 4, f"cruzamento: {cz and cz.featureCount()}")

pts = memoria("Point?crs=EPSG:31983&field=id:integer&field=codigo_ra:integer", "pontos",
              [("POINT(120 3)", [1, None]), ("POINT(400 -2)", [2, None]), ("POINT(900 900)", [3, None])])
r = rodar("encaixar nas linhas de vias com tolerância de 5 m", sel="pontos")
enc = lyr(r["output_layer"]) if r else None
if enc:
    ys = sorted(round(f.geometry().asPoint().y(), 3) for f in enc.getFeatures())
    check(ys[:2] == [0.0, 0.0] and ys[2] == 900, f"pontos encaixados na linha: {ys}")

limites = memoria("Polygon?crs=EPSG:31983&field=Código_RA:integer&field=nome:string", "Limites",
                  [("POLYGON((0 -50,300 -50,300 50,0 50,0 -50))", [9, "Ceilândia"]),
                   ("POLYGON((300 -50,600 -50,600 50,300 50,300 -50))", [12, "Samambaia"])])
r = rodar('preencher "codigo_ra" pela camada Limites campo "Código_RA"', sel="pontos")
check(r and r["updated"] == 2 and r["sem_correspondencia"] == 1, f"preencher pelo lugar: {r}")
check({f["id"]: f["codigo_ra"] for f in pts.getFeatures()} == {1: 9, 2: 12, 3: None},
      f"valores: {[(f['id'], f['codigo_ra']) for f in pts.getFeatures()]}")
rodar('preencher "codigo_ra" pela camada Limites', sel="pontos", deve_falhar=True)  # campo de nome diferente

# gravar no .gdb: como mais uma camada do arquivo
r = rodar(f"exportar camada para {gdb}", sel="vias")
nomes = {d.name() for d in QgsProviderRegistry.instance().querySublayers(gdb)}
check("vias" in nomes, f"vias dentro do CC01.gdb: {sorted(nomes)}")
rodar(f"exportar camada para {gdb}", sel="vias", deve_falhar=True)  # já existe
# projeto feito de .gdb: 'salvar camada' grava no mesmo .gdb
r = rodar("salvar camada", sel=tr.name() if tr else "vias")
check(r and mesmo(r.get("output_path"), gdb), f"salvar camada no gdb do projeto: {r}")

print("Saída:", PASTA)
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
app.exitQgis()
sys.exit(1 if FALHAS else 0)
