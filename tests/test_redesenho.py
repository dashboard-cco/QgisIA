# -*- coding: utf-8 -*-
"""Testes do núcleo do redesenho (rede, vias de passagem, segmentação).

    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests\\test_redesenho.py
"""
import os
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(AQUI, "..", "src", "qgis_ia")
sys.path.insert(0, PLUGIN)
sys.path.insert(0, os.path.join(PLUGIN, "actions"))

import redesenho as R  # noqa: E402
from osgeo import ogr, osr  # noqa: E402

FALHAS = []


def check(cond, msg):
    if not cond:
        FALHAS.append(msg)
        print("FALHOU:", msg)


def malha(path, sentidos):
    """Grade 4x4 de quarteirões de 200 m. sentidos: {ID: 'FT'|'TF'}."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(31983)
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    lr = ds.CreateLayer("ArquivoRua", srs, ogr.wkbLineString)
    lr.CreateField(ogr.FieldDefn("ID", ogr.OFTInteger))
    lr.CreateField(ogr.FieldDefn("compriment", ogr.OFTReal))
    ls = ds.CreateLayer("sentidos", srs, ogr.wkbLineString)
    ls.CreateField(ogr.FieldDefn("ID", ogr.OFTInteger))
    ls.CreateField(ogr.FieldDefn("sentido_proposto", ogr.OFTString))
    i, ids = 0, {}
    for y in range(5):
        for x in range(4):
            ids[("h", x, y)] = i
            wkt = f"LINESTRING({x*200} {y*200},{(x+1)*200} {y*200})"
            for lyr in (lr, ls):
                f = ogr.Feature(lyr.GetLayerDefn())
                f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
                f.SetField("ID", i)
                if lyr is lr:
                    f.SetField("compriment", 200.0)
                else:
                    f.SetField("sentido_proposto", sentidos.get(i, "B_PADRAO_OSM"))
                lyr.CreateFeature(f)
            i += 1
    for x in range(5):
        for y in range(4):
            ids[("v", x, y)] = i
            wkt = f"LINESTRING({x*200} {y*200},{x*200} {(y+1)*200})"
            for lyr in (lr, ls):
                f = ogr.Feature(lyr.GetLayerDefn())
                f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
                f.SetField("ID", i)
                if lyr is lr:
                    f.SetField("compriment", 200.0)
                else:
                    f.SetField("sentido_proposto", sentidos.get(i, "B_PADRAO_OSM"))
                lyr.CreateFeature(f)
            i += 1
    ds = None
    return ids


tmp = tempfile.mkdtemp(prefix="qgis_ia_red_")
try:
    gpkg = os.path.join(tmp, "rede.gpkg")
    ids = malha(gpkg, {})
    rede = R.Rede(gpkg, "ArquivoRua")
    check(rede.n == 40 and len(rede.no_xy) == 25, f"grade: {rede.n} trechos, {len(rede.no_xy)} nós")

    # duas ruas de coleta separadas por uma quadra: passagem liga as duas
    req = {ids[("h", 0, 0)], ids[("h", 3, 4)]}
    pas, lib = R._vias_de_passagem(rede, req)
    check(pas and not (pas & req), "passagem criada e sem repetir a coleta")
    check(not lib, "sem contramão em mão dupla")
    km = sum(rede.comp[i] for i in pas)
    check(km <= 1400, f"passagem curta (caminho mínimo): {km} m")

    # mão única: rua de coleta FT isolada exige volta por outro caminho
    malha(os.path.join(tmp, "rede2.gpkg"), {})
    rede2 = R.Rede(os.path.join(tmp, "rede2.gpkg"), "ArquivoRua")
    rede2.sent[0] = "FT"  # trecho 0 passa a ser mão única; refaz a adjacência
    rede2.adj.clear(); rede2.radj.clear()
    for k in range(rede2.n):
        u, v, c = rede2.u[k], rede2.v[k], rede2.comp[k]
        if rede2.sent[k] in ("B", "FT"):
            rede2.adj[u].append((v, c, k, 1)); rede2.radj[v].append((u, c, k, 1))
        if rede2.sent[k] in ("B", "TF"):
            rede2.adj[v].append((u, c, k, -1)); rede2.radj[u].append((v, c, k, -1))
    pas2, lib2 = R._vias_de_passagem(rede2, {0})
    check(sum(rede2.comp[i] for i in pas2) >= 600, "mão única: volta pela quadra (>= 600 m)")
    check(not lib2, "mão única: sem contramão")

    # segmentação: 3 trechos de 200 m em linha (nós de grau 2 só no meio da grade? não)
    desloc = {ids[("h", x, 0)]: 0 for x in range(4)}
    segs = R._segmentar(rede, desloc, desloc)
    check(all(s[0].length <= R.LIN_MAX + 1e-6 for s in segs), "pedaços <= 130 m")
    check(abs(sum(s[0].length for s in segs) - 800) < 1e-6, "comprimento total preservado")
    # nós da borda inferior têm grau 3 na grade: não pode emendar através deles
    check(all(len(s[2]) == 1 for s in segs), "não emenda através de cruzamentos")
    check(len(segs) == 8, f"cada trecho de 200 m vira 2 de 100 m ({len(segs)})")
    # junção de circuitos para caber na frota
    from shapely.geometry import box

    def circ(cod, x, nome, ra, dias, km, turno="Noturno"):
        pa = {"id_tipo_equipamento": 0, "turno": turno, "nome_circuito": nome,
              "horario_inicio": "19:00", "horario_termino": "03:20"}
        pa.update({d: (1 if i in dias else 0) for i, d in enumerate(
            ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"])})
        return {"cod": cod, "pa": pa, "ra": ra, "km": km, "req": set(), "cts": [], "pts": {},
                "fundidos": [], "pg": box(x, 0, x + 100, 100)}

    SQS, TQS = (0, 2, 4), (1, 3, 5)
    dados = [circ(1, 0, "Asa Norte 1 A3SQS", 1, SQS, 10), circ(2, 150, "Asa Sul 2 A3SQS", 1, SQS, 5),
             circ(3, 300, "Asa Sul 3 A3SQS", 1, SQS, 8), circ(4, 0, "Gama 4 A3TQS", 2, TQS, 9)]
    fus, sem = R._planejar_fusoes(dados, {0: {"Noturno": 2}}, 1500)
    check(fus == [(3, 2)], f"junta só Asa Sul com Asa Sul ({fus})")
    check(not sem and len(dados) == 3, "cabe em 2 veículos por noite")
    c3 = next(d for d in dados if d["cod"] == 3)
    check(c3["km"] == 13 and c3["fundidos"] == [2], "carga somada")
    dados = [circ(1, 0, "Asa Norte 1 A3SQS", 1, SQS, 10), circ(2, 150, "Asa Sul 2 A3SQS", 1, SQS, 5)]
    fus, sem = R._planejar_fusoes(dados, {0: {"Noturno": 1}}, 1500)
    check(not fus and sem, "Asa Norte + Asa Sul não juntam: sobra pendência")
    dados = [circ(1, 0, "Gama 1 A3SQS", 2, SQS, 10), circ(2, 150, "Gama 2 A3TQS", 2, TQS, 5)]
    fus, sem = R._planejar_fusoes(dados, {0: {"Noturno": 1}}, 1500)
    check(not fus and not sem, "dias diferentes já cabem: nada a juntar")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
sys.exit(1 if FALHAS else 0)
