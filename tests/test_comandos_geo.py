# -*- coding: utf-8 -*-
"""Frases de geoprocessamento no interpretador (sem QGIS, sem IA).

Entrada = camada selecionada; a outra camada (molde) é citada pelo nome.

    python tests\\test_comandos_geo.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "qgis_ia"))

import comandos as C  # noqa: E402

CTX = {
    "camadas": ["lotes", "Vias Principais", "pontos_coleta", "Regiões", "lotes_sul", "lotes_norte"],
    "campos": {"lotes": ["id", "area", "bairro", "uso", "populacao"],
               "Vias Principais": ["nome"], "pontos_coleta": ["tipo"], "Regiões": ["ra", "nome"],
               "lotes_sul": [], "lotes_norte": []},
    "ativa": "lotes",
    "layouts": [],
}
FALHAS = []
SELECIONE, ASPAS = "camada selecionada", "entre aspas"


def caso(frase, action="geoprocess", ativa="lotes", **params):
    try:
        p = C.interpretar(frase, dict(CTX, ativa=ativa))
    except C.ErroComando as e:
        FALHAS.append(f"{frase!r}: ErroComando {e}")
        return
    if p is None:
        FALHAS.append(f"{frase!r}: não reconhecido")
        return
    st = p["steps"][0]
    if st["action"] != action:
        FALHAS.append(f"{frase!r}: ação {st['action']} (esperava {action}) {st['params']}")
        return
    for k, v in params.items():
        if st["params"].get(k, "<ausente>") != v:
            FALHAS.append(f"{frase!r}: {k}={st['params'].get(k, '<ausente>')!r} (esperava {v!r})")


def erro(frase, ativa="lotes", contem=None):
    try:
        p = C.interpretar(frase, dict(CTX, ativa=ativa))
        FALHAS.append(f"{frase!r}: devia dar erro, virou {p and p['steps']}")
    except C.ErroComando as e:
        if contem and contem.lower() not in str(e).lower():
            FALHAS.append(f"{frase!r}: erro sem '{contem}': {e}")


def nada(frase):
    try:
        p = C.interpretar(frase, CTX)
    except C.ErroComando as e:
        FALHAS.append(f"{frase!r}: devia ir para a IA, deu erro: {e}")
        return
    if p is not None:
        FALHAS.append(f"{frase!r}: devia ir para a IA, virou {p['steps']}")


VIAS = "Vias Principais"

# buffer
caso("buffer de 50 m", tool="buffer", layer_name="lotes", distance=50.0)
caso("buffer de 2 km", tool="buffer", distance=2000.0)
caso("criar um buffer de 1,5 km dissolvido", tool="buffer", distance=1500.0, dissolve=True)
caso("área de influência de 300 metros", tool="buffer", distance=300.0)
caso("buffer de 100 m só nas selecionadas", tool="buffer", only_selected=True)
caso("buffer de 30 m como faixa_vias", ativa=VIAS, tool="buffer", layer_name=VIAS, output_name="faixa_vias")
caso("buffer de 20 m nos lotes", tool="buffer", distance=20.0)
erro("buffer de 100 m nas vias", contem=SELECIONE)
erro("buffer", contem="distância")

# dissolver
caso("dissolver", tool="dissolve")
caso("juntar tudo", tool="dissolve")
caso('dissolver por "bairro"', tool="dissolve", field="bairro")
caso('dissolver por "bairro" e "uso"', tool="dissolve", field=["bairro", "uso"])
erro("dissolver por bairro", contem=ASPAS)

# recortar / interseção / diferença / união / mesclar
caso("recortar pela camada Regiões", tool="clip", overlay="Regiões")
caso("recortar por regioes", tool="clip", overlay="Regiões")
caso("recorte usando Regiões como lotes_ra", tool="clip", overlay="Regiões", output_name="lotes_ra")
caso("recortar pela camada lotes", ativa=VIAS, tool="clip", layer_name=VIAS, overlay="lotes")
erro("recortar pela camada lotes", contem="própria")
erro("recortar pela camada Estradas", contem="não achei")
caso("interseção com Regiões", tool="intersection", overlay="Regiões")
caso("cruzar com Regiões", tool="intersection", overlay="Regiões")
caso("diferença com Regiões", tool="difference", overlay="Regiões")
caso("tirar a parte que está em Regiões", tool="difference", overlay="Regiões")
caso("união com Regiões", tool="union", overlay="Regiões")
caso("mesclar com lotes_sul e lotes_norte", tool="merge", overlays=["lotes_sul", "lotes_norte"])
caso("juntar com lotes_sul", tool="merge", overlays=["lotes_sul"])

# reprojetar
caso("reprojetar para 31983", tool="reproject", crs="EPSG:31983")
caso("reprojetar para EPSG:4326", tool="reproject", crs="EPSG:4326")
caso("reprojetar para SIRGAS 2000 UTM 23S", tool="reproject", crs="EPSG:31983")
caso("converter para WGS84", tool="reproject", crs="EPSG:4326")
caso("mudar o sistema para utm 22s", tool="reproject", crs="EPSG:31982")
erro("reprojetar para Marte", contem="não reconhecido")

# outras ferramentas
caso("gerar centroides", tool="centroids")
caso("pontos no centro", tool="centroids")
caso("envoltória", tool="convex_hull")
caso("envoltória de tudo", tool="convex_hull_all")
caso("simplificar 5 m", tool="simplify", tolerance=5.0)
caso("trazer atributos de Regiões", tool="spatial_join", overlay="Regiões")
caso("pegar os dados de Regiões", tool="spatial_join", overlay="Regiões")
caso("junção espacial com Regiões (todos)", tool="spatial_join", one_to_one=False)
caso("mais próximo de pontos_coleta", tool="nearest_join", overlay="pontos_coleta")
caso("distância até Vias Principais", tool="nearest_join", overlay=VIAS)
caso("contar pontos de pontos_coleta em cada polígono", tool="count_points", overlay="pontos_coleta")
caso("quantos pontos_coleta tem em cada lote", tool="count_points", overlay="pontos_coleta")
caso("corrigir geometrias", tool="fix_geometries")
caso("explodir multipartes", tool="single_parts")
caso("remover duplicadas", tool="delete_duplicates")
caso("apagar geometrias duplicadas", tool="delete_duplicates")
caso("extrair vértices", tool="extract_vertices")
caso("polígonos para linhas", tool="polygons_to_lines")
caso("converter linhas em polígonos", ativa=VIAS, tool="lines_to_polygons")
caso("grade de 500 m", tool="grid", distance=500.0)
caso("criar grade hexagonal de 1 km", tool="grid", distance=1000.0, grid_type="hexagon")

# seleção por localização
caso("selecionar dentro de Regiões", "select_by_location", overlay="Regiões", predicate="within")
caso("selecionar os que tocam Regiões", "select_by_location", predicate="touches")
caso("selecionar a até 50 m de Vias Principais", "select_by_location", overlay=VIAS, distance=50.0)
caso("selecionar os pontos fora de Regiões", "select_by_location", ativa="pontos_coleta",
     layer_name="pontos_coleta", predicate="disjoint")
erro("selecionar perto de Vias Principais", contem="distância")

# consultas
caso("área total", "measure_total", layer_name="lotes")
caso("comprimento total", "measure_total", ativa=VIAS, layer_name=VIAS)
caso("área total das selecionadas", "measure_total", only_selected=True)
caso('estatísticas de "populacao"', "get_field_statistics", field="populacao")
caso('soma do campo "populacao"', "get_field_statistics", field="populacao")
caso('valores únicos de "bairro"', "get_unique_values", field="bairro")
erro("estatísticas de populacao", contem=ASPAS)

# gravar camada em arquivo
caso("exportar camada em shapefile", "save_layer_as", layer_name="lotes", format="shp")
caso("salvar camada como geojson", "save_layer_as", format="geojson")
caso("exportar camada para C:\\saida\\lotes.gpkg", "save_layer_as", output_path="C:\\saida\\lotes.gpkg")
caso("exportar selecionadas em csv", "save_layer_as", format="csv", only_selected=True)
caso("salvar em excel", "save_layer_as", format="xlsx")
erro("exportar camada Regiões em shp", contem=SELECIONE)

# não roubar outros comandos
caso("salvar edição", "commit_edits")
caso("salvar projeto", "save_project")
caso('contar feições onde "uso" vazio', "count_features")
caso('selecionar onde "bairro" igual a Centro', "select_features")
caso("converter para 31983", tool="reproject", crs="EPSG:31983")
nada("crie um mapa de calor dos pontos de coleta")
nada("qual o melhor caminho entre dois pontos?")

for f in FALHAS:
    print("FALHOU:", f)
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
sys.exit(1 if FALHAS else 0)
