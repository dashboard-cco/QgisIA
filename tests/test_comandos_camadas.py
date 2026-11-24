# -*- coding: utf-8 -*-
"""Frases de camadas no interpretador (sem QGIS, sem IA): salvar na pasta do projeto,
criar camada, abrir arquivo/pasta, grupos, sistema, estilo, informações.

    python tests\\test_comandos_camadas.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "qgis_ia"))

import comandos as C  # noqa: E402

CTX = {
    "camadas": ["lotes", "Regiões", "lotes_buffer_50m"],
    "campos": {"lotes": ["id", "bairro"], "Regiões": ["ra"], "lotes_buffer_50m": ["id"]},
    "ativa": "lotes",
    "layouts": [],
}
FALHAS = []


def caso(frase, action, ativa="lotes", **params):
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
        if st["params"].get(k) != v:
            FALHAS.append(f"{frase!r}: {k}={st['params'].get(k)!r} (esperava {v!r})")


def erro(frase, contem="", ativa="lotes"):
    try:
        p = C.interpretar(frase, dict(CTX, ativa=ativa))
    except C.ErroComando as e:
        if contem and contem not in str(e):
            FALHAS.append(f"{frase!r}: erro sem '{contem}': {e}")
        return
    FALHAS.append(f"{frase!r}: devia dar erro, deu {p and p['steps'][0]['action']}")


# salvar na pasta do projeto (mesmo formato e sistema dos arquivos do projeto)
for f in ["salvar camada", "salvar a camada", "salvar camada na pasta do projeto", "salve na pasta do projeto",
          "gravar a camada no projeto", "tornar permanente", "deixar a camada permanente",
          "salvar camada igual aos outros", "guardar a camada"]:
    caso(f, "save_layer_to_project", layer_name="lotes")
caso("salvar camada como buffer_final", "save_layer_to_project", output_name="buffer_final")
caso("salvar camada na pasta do projeto como coleta_2026", "save_layer_to_project", output_name="coleta_2026")
caso("salvar camada", "save_layer_to_project", ativa="lotes_buffer_50m", layer_name="lotes_buffer_50m")
erro("salvar camada Regiões na pasta do projeto", contem="camada selecionada")
# continuam no comando antigo (cópia em formato/caminho escolhido)
caso("salvar camada como geojson", "save_layer_as", format="geojson")
caso("exportar camada em shapefile", "save_layer_as", format="shp")
caso("salvar camada em C:\\saida\\x.gpkg", "save_layer_as", output_path="C:\\saida\\x.gpkg")
caso("salvar selecionadas em csv", "save_layer_as", only_selected=True)
caso("salvar edição", "commit_edits")
caso("salvar projeto", "save_project")
caso("salvar o projeto em C:\\mapas\\a.qgz", "save_project")

# criar camada
caso("criar camada de pontos chamada postes", "create_layer", name="postes", geometry_type="point")
caso("criar camada de linhas vias_novas", "create_layer", name="vias_novas", geometry_type="line")
caso("criar nova camada de polígonos quadras", "create_layer", name="quadras", geometry_type="polygon")
caso("criar camada de pontos", "create_layer", name="pontos_novos", geometry_type="point")
caso('criar camada de pontos postes com campos "nome" texto e "altura" decimal', "create_layer", name="postes",
     fields=[{"name": "nome", "type": "string"}, {"name": "altura", "type": "double"}])
caso('criar camada de polígonos lotes_novos com campo "uso"', "create_layer",
     fields=[{"name": "uso", "type": "string"}])
caso('criar camada de pontos postes com os campos "id" inteiro, "data" data', "create_layer",
     fields=[{"name": "id", "type": "integer"}, {"name": "data", "type": "date"}])
caso("criar camada de pontos postes em 4326", "create_layer", name="postes", crs="EPSG:4326")
caso("criar camada de pontos chamada postes em WGS84", "create_layer", name="postes", crs="EPSG:4326")
caso("criar camada de linhas temporária", "create_layer", temporary=True, geometry_type="line")
caso("criar camada temporária de pontos rascunho", "create_layer", temporary=True, name="rascunho")
caso("criar tabela controle", "create_layer", geometry_type="none", name="controle")
caso("criar camada de áreas zonas", "create_layer", geometry_type="polygon", name="zonas")
erro("criar camada chamada postes", contem="tipo da camada")
erro("criar camada de pontos com campos nome e altura", contem="entre aspas")
erro("criar camada de pontos chamada lotes", contem="Já existe")
caso('criar campo "x"', "add_field")  # campo continua sendo campo

# abrir arquivos
caso("abrir C:\\dados\\lotes.shp", "load_files", path="C:\\dados\\lotes.shp")
caso("carregar o arquivo C:\\dados\\base.gpkg", "load_files", path="C:\\dados\\base.gpkg")
caso("abrir todos os arquivos da pasta C:\\dados\\Shp", "load_files", path="C:\\dados\\Shp")
caso("adicionar camada E:\\Gdb\\SLU.gdb", "load_files", path="E:\\Gdb\\SLU.gdb")
caso('abrir "C:\\com espaço\\a.geojson"', "load_files", path="C:\\com espaço\\a.geojson")

# grupos
caso("criar grupo Coleta", "create_group", name="Coleta")
caso("criar um grupo chamado Bases de 2026", "create_group", name="Bases de 2026")
caso("mover para o grupo Coleta", "move_layer_to_group", layer_name="lotes", group="Coleta")
caso("colocar a camada no grupo Bases", "move_layer_to_group", group="Bases")
erro("mover Regiões para o grupo Bases", contem="camada selecionada")

# sistema de coordenadas
caso("definir sistema 31983", "set_layer_crs", crs="EPSG:31983", layer_name="lotes")
caso("definir o sistema da camada como SIRGAS 2000 UTM 23S", "set_layer_crs", crs="EPSG:31983")
caso("corrigir a projeção para 4326", "set_layer_crs", crs="EPSG:4326")
erro("definir sistema xyz", contem="não reconhecido")
caso("reprojetar para 31983", "geoprocess", tool="reproject")  # converter continua sendo reprojetar
caso("corrigir geometrias", "geoprocess", tool="fix_geometries")

# estilo
caso("copiar estilo de Regiões", "copy_style", from_layer="Regiões", to_layer="lotes")
caso("usar o mesmo estilo da camada Regiões", "copy_style", from_layer="Regiões")
caso("mesmo estilo de Regiões", "copy_style", from_layer="Regiões")
erro("copiar estilo de lotes", contem="própria selecionada")
caso("copiar camada como lotes_backup", "duplicate_layer")  # cópia de camada não mudou

# informações
for f in ["informações da camada", "info", "propriedades", "qual o sistema da camada?", "onde está salva?"]:
    caso(f, "get_layer_info", layer_name="lotes")
caso("padrão do projeto", "project_storage_info")
caso("como o projeto salva?", "project_storage_info")

# regra 1: sem camada selecionada
for f in ["salvar camada", "informações da camada", "definir sistema 31983", "copiar estilo de Regiões"]:
    erro(f, ativa=None, contem="Nenhuma camada selecionada")

for f in FALHAS:
    print("FALHOU:", f)
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
sys.exit(1 if FALHAS else 0)
