# -*- coding: utf-8 -*-
"""Frases de mapas e layouts no interpretador (sem QGIS, sem IA).

    python tests\\test_comandos_mapas.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "qgis_ia"))

import comandos as C  # noqa: E402

CTX = {
    "camadas": ["lotes", "Vias Principais", "pontos_coleta", "Regiões", "regioes de saude"],
    "campos": {
        "lotes": ["id", "area", "bairro", "nome_rua", "uso", "populacao"],
        "Vias Principais": ["ID", "nome", "comprimento"],
        "pontos_coleta": ["fid", "tipo", "endereco"],
        "Regiões": ["ra", "nome"],
        "regioes de saude": ["nome"],
    },
    "ativa": "lotes",
    "layouts": ["Mapa", "Coleta 2026"],
}
SEM_LAYOUT = dict(CTX, layouts=[])
UM_LAYOUT = dict(CTX, layouts=["Mapa"])

FALHAS = []


def caso(frase, action, ctx=CTX, passos=None, **params):
    try:
        p = C.interpretar(frase, ctx)
    except C.ErroComando as e:
        FALHAS.append(f"{frase!r}: ErroComando {e}")
        return
    if p is None:
        FALHAS.append(f"{frase!r}: não reconhecido")
        return
    if passos is not None and len(p["steps"]) != passos:
        FALHAS.append(f"{frase!r}: {len(p['steps'])} passos (esperava {passos})")
    st = p["steps"][-1] if passos else p["steps"][0]
    if st["action"] != action:
        FALHAS.append(f"{frase!r}: ação {st['action']} (esperava {action}) {st['params']}")
        return
    for k, v in params.items():
        if st["params"].get(k, "<ausente>") != v:
            FALHAS.append(f"{frase!r}: {k}={st['params'].get(k, '<ausente>')!r} (esperava {v!r})")


def nada(frase, ctx=CTX):
    try:
        p = C.interpretar(frase, ctx)
    except C.ErroComando as e:
        FALHAS.append(f"{frase!r}: devia ir para a IA, deu erro: {e}")
        return
    if p is not None:
        FALHAS.append(f"{frase!r}: devia ir para a IA, virou {p['steps']}")


def erro(frase, ctx=CTX):
    try:
        p = C.interpretar(frase, ctx)
        FALHAS.append(f"{frase!r}: devia dar erro, virou {p and p['steps']}")
    except C.ErroComando:
        pass


AZUL, PRETO, VERDE_ESC, VERMELHO = "#1f78b4", "#000000", "#00441b", "#e31a1c"

# --- cor única
caso("pintar lotes de azul", "update_symbol", layer_name="lotes", color=AZUL)
caso("pinte a camada lotes de azul", "update_symbol", layer_name="lotes", color=AZUL)
caso("pintar de azul", "update_symbol", layer_name="lotes", color=AZUL)
caso("colorir Vias Principais de vermelho", "update_symbol", layer_name="Vias Principais", color=VERMELHO)
caso("mudar a cor de lotes para verde escuro", "update_symbol", layer_name="lotes", color=VERDE_ESC)
caso("mude a cor da camada Regiões para verde-escuro", "update_symbol", layer_name="Regiões", color=VERDE_ESC)
caso("cor azul em lotes", "update_symbol", layer_name="lotes", color=AZUL)
caso("deixar lotes amarelo", "update_symbol", layer_name="lotes", color="#ffd92f")
caso("deixe regiões vermelha", "update_symbol", layer_name="Regiões", color=VERMELHO)
caso("pintar regioes de saude de azul", "update_symbol", layer_name="regioes de saude", color=AZUL)
caso("pintar lotes de #ff8800", "update_symbol", layer_name="lotes", color="#ff8800")
caso("pintar lotes com a cor 255,0,0", "update_symbol", layer_name="lotes", color="#ff0000")
caso("pintar lotes de azul com contorno preto", "update_symbol", layer_name="lotes", color=AZUL,
     outline_color=PRETO)
caso("pintar lotes de verde clara", "update_symbol", color="#b2df8a")
caso("deixar lotes sem preenchimento", "update_symbol", layer_name="lotes", no_fill=True)
caso("pintar lotes de transparente", "update_symbol", layer_name="lotes", no_fill=True)
erro("pintar lotes de furta-cor")
erro("pintar quadras de azul")

# --- contorno e tamanho
caso("contorno preto em lotes", "update_symbol", layer_name="lotes", outline_color=PRETO)
caso("contorno preto de 0.5 em lotes", "update_symbol", layer_name="lotes", outline_color=PRETO,
     outline_width=0.5)
caso("borda vermelha com espessura 1 na camada Regiões", "update_symbol", layer_name="Regiões",
     outline_color=VERMELHO, outline_width=1.0)
caso("contorno 0,8 mm", "update_symbol", layer_name="lotes", outline_width=0.8)
caso("sem contorno em lotes", "update_symbol", layer_name="lotes", outline_color="#00000000")
caso("tirar o contorno", "update_symbol", layer_name="lotes", outline_color="#00000000")
caso("espessura 1.5 em Vias Principais", "update_symbol", layer_name="Vias Principais", size=1.5)
caso("espessura das linhas de Vias Principais para 2", "update_symbol", layer_name="Vias Principais", size=2.0)
caso("tamanho dos pontos de pontos_coleta 4 mm", "update_symbol", layer_name="pontos_coleta", size=4.0)
caso("aumentar tamanho de pontos_coleta para 5", "update_symbol", layer_name="pontos_coleta", size=5.0)
caso("espessura do contorno de lotes 0.3", "update_symbol", layer_name="lotes", outline_width=0.3)

# --- transparência
caso("transparência 50% em lotes", "set_layer_opacity", layer_name="lotes", opacity=0.5)
caso("colocar transparência de 30% na camada Regiões", "set_layer_opacity", layer_name="Regiões", opacity=0.7)
caso("deixar lotes 40% transparente", "set_layer_opacity", layer_name="lotes", opacity=0.6)
caso("deixar lotes transparente", "set_layer_opacity", layer_name="lotes", opacity=0.5)
caso("deixar lotes semitransparente", "set_layer_opacity", layer_name="lotes", opacity=0.5)
caso("opacidade 80% em lotes", "set_layer_opacity", layer_name="lotes", opacity=0.8)
caso("lotes sem transparência", "set_layer_opacity", layer_name="lotes", opacity=1.0)
caso("transparência 25", "set_layer_opacity", layer_name="lotes", opacity=0.75)

# --- cores por campo
caso("cores por bairro em lotes", "set_categorized_style", layer_name="lotes", field="bairro")
caso("cores por bairro", "set_categorized_style", layer_name="lotes", field="bairro")
caso("colorir lotes por bairro", "set_categorized_style", layer_name="lotes", field="bairro")
caso("pintar lotes por uso", "set_categorized_style", layer_name="lotes", field="uso")
caso("pintar regiões por ra", "set_categorized_style", layer_name="Regiões", field="ra")
caso("categorizar lotes pelo campo uso", "set_categorized_style", layer_name="lotes", field="uso")
caso("cores por tipo na camada pontos_coleta", "set_categorized_style", layer_name="pontos_coleta", field="tipo")
caso("classificar lotes por populacao em 5 classes", "set_graduated_style", layer_name="lotes",
     field="populacao", classes=5)
caso("classificar lotes por populacao em 7 classes quebras naturais", "set_graduated_style",
     classes=7, mode="Jenks")
caso("colorir lotes por populacao em 4 classes em tons de vermelho", "set_graduated_style",
     classes=4, color_end=VERMELHO)
caso("graduar lotes por area do amarelo ao vermelho", "set_graduated_style", field="area",
     color_start="#ffd92f", color_end=VERMELHO)
caso("classificar lotes por quantil por populacao", "set_graduated_style", mode="Quantile", field="populacao")
caso("cores por área em hectares", "set_graduated_style", field="$area / 10000")
erro("cores por xyz em lotes")

# --- rótulos
caso("rótulos com nome_rua em lotes", "set_labels", layer_name="lotes", field="nome_rua")
caso("rotulos com nome em Vias Principais", "set_labels", layer_name="Vias Principais", field="nome")
caso("rotular lotes por bairro", "set_labels", layer_name="lotes", field="bairro")
caso("rotular Vias Principais com o nome", "set_labels", layer_name="Vias Principais", field="nome")
caso("colocar rótulos de bairro", "set_labels", layer_name="lotes", field="bairro")
caso("mostrar rótulos do campo uso na camada lotes", "set_labels", layer_name="lotes", field="uso")
caso("rótulos com bairro tamanho 12 negrito", "set_labels", field="bairro", size=12.0, bold=True)
caso("rótulos com bairro na cor vermelha", "set_labels", field="bairro", color=VERMELHO)
caso("rótulos com bairro sem halo", "set_labels", field="bairro", buffer=False)
caso("rotular com nome na camada Regiões", "set_labels", layer_name="Regiões", field="nome")
caso('rótulos com "bairro" || \' - \' || "uso"', "set_labels", field='"bairro" || \' - \' || "uso"')
caso("tirar rótulos de lotes", "set_labels", layer_name="lotes", enabled=False)
caso("desligar os rótulos", "set_labels", layer_name="lotes", enabled=False)
caso("sem rótulos em Vias Principais", "set_labels", layer_name="Vias Principais", enabled=False)
erro("rótulos com xyz em lotes")

# --- mapa de fundo
caso("mapa de fundo satélite", "add_basemap", source="esri_satellite")
caso("adicionar mapa de fundo", "add_basemap", source="osm")
caso("colocar fundo google satélite", "add_basemap", source="google_satellite")
caso("colocar imagem de satélite do google", "add_basemap", source="google_satellite")
caso("adicionar satélite", "add_basemap", source="esri_satellite")
caso("mapa base claro", "add_basemap", source="carto_light")
caso("adicionar google maps", "add_basemap", source="google_maps")
caso("adicionar openstreetmap", "add_basemap", source="osm")
caso("fundo híbrido", "add_basemap", source="google_hybrid")
erro("mapa de fundo marciano")

# --- mapa: zoom, escala, ordem, visibilidade, projeto
caso("zoom total", "zoom_full")
caso("ver tudo", "zoom_full")
caso("zoom em todas as camadas", "zoom_full")
caso("escala 1:5000", "set_scale", scale=5000.0)
caso("escala 1/10.000", "set_scale", scale=10000.0)
caso("mudar escala para 25 mil", "set_scale", scale=25000.0)
caso("trazer lotes para frente", "move_layer", layer_name="lotes", position="top")
caso("mandar Regiões para trás", "move_layer", layer_name="Regiões", position="bottom")
caso("colocar a camada lotes no topo", "move_layer", layer_name="lotes", position="top")
caso("subir lotes uma posição acima", "move_layer", position="up")
caso("esconder camada lotes", "set_layer_visibility", layer_name="lotes", visible=False)
caso("ocultar Vias Principais", "set_layer_visibility", layer_name="Vias Principais", visible=False)
caso("desligar a camada Regiões", "set_layer_visibility", layer_name="Regiões", visible=False)
caso("mostrar camada lotes", "set_layer_visibility", layer_name="lotes", visible=True)
caso("ligar lotes", "set_layer_visibility", layer_name="lotes", visible=True)
caso("mostrar todas as camadas", "set_layer_visibility", visible=True)
caso("esconder todas", "set_layer_visibility", visible=False)
caso("salvar projeto", "save_project")
caso("salvar o projeto em C:\\mapas\\coleta.qgz", "save_project", path="C:\\mapas\\coleta.qgz")

# --- layouts
caso("criar layout", "create_print_layout")
caso("criar layout A4 com título Mapa de Lotes", "create_print_layout", title="Mapa de Lotes")
caso("criar layout A3 retrato com título 'Coleta e Varrição'", "create_print_layout",
     page_size="A3", orientation="portrait", title="Coleta e Varrição")
caso("criar um mapa para impressão em A4 paisagem com legenda, escala e norte", "create_print_layout",
     page_size="A4", orientation="landscape")
caso("criar layout sem legenda", "create_print_layout", legend=False)
caso("criar layout A4 sem norte e sem escala", "create_print_layout", north_arrow=False, scalebar=False)
caso("criar layout só o mapa", "create_print_layout", legend=False, scalebar=False, north_arrow=False)
caso("criar layout chamado Prancha 01 com título Lotes", "create_print_layout", layout_name="Prancha 01",
     title="Lotes")
caso('criar layout com título "Rotas" e subtítulo "Setor Norte"', "create_print_layout", title="Rotas",
     subtitle="Setor Norte")
caso("montar uma prancha A2", "create_print_layout", page_size="A2")
caso("exportar layout Mapa em pdf", "export_layout", layout_name="Mapa", format="pdf")
caso("exportar o layout Coleta 2026 em png com 150 dpi", "export_layout", layout_name="Coleta 2026",
     format="png", dpi=150)
caso("exportar layout em pdf", "export_layout", ctx=UM_LAYOUT, layout_name="Mapa", format="pdf")
caso("exportar mapa em pdf", "export_layout", ctx=UM_LAYOUT, layout_name="Mapa", format="pdf")
caso("exportar layout Mapa em C:\\saida\\mapa.pdf", "export_layout", layout_name="Mapa",
     output_path="C:\\saida\\mapa.pdf", format="pdf")
caso("exportar layout Mapa para C:\\saida\\mapa.png", "export_layout", format="png")
caso("imprimir o layout Mapa", "export_layout", layout_name="Mapa", format="pdf")
caso("salvar mapa em pdf", "export_layout", ctx=SEM_LAYOUT, passos=2, layout_name="Mapa", format="pdf")
caso("salvar imagem do mapa", "export_map_image", ctx=SEM_LAYOUT)
caso("exportar mapa como png", "export_map_image", ctx=SEM_LAYOUT)
caso("tirar print do mapa", "export_map_image", ctx=SEM_LAYOUT)
erro("exportar layout em pdf")  # dois layouts no projeto: precisa dizer qual
erro("exportar layout Inexistente em pdf")
caso("abrir layout Mapa", "open_layout", layout_name="Mapa")
caso("editar layout Coleta 2026", "open_layout", layout_name="Coleta 2026")
caso("abrir layout", "open_layout", ctx=UM_LAYOUT)
caso("listar layouts", "list_print_layouts")
caso("quais layouts tem", "list_print_layouts")
caso("apagar layout Coleta 2026", "remove_layout", layout_name="Coleta 2026")
caso("adicionar legenda no layout Mapa", "add_layout_item", item="legend", layout_name="Mapa")
caso("adicionar escala no layout", "add_layout_item", ctx=UM_LAYOUT, item="scalebar")
caso("colocar norte no layout Mapa", "add_layout_item", item="north_arrow")
caso('adicionar título "Coleta 2026" no layout Mapa', "add_layout_item", item="title", text="Coleta 2026")
caso('acrescentar texto "Fonte: SLU" no layout Mapa', "add_layout_item", item="text", text="Fonte: SLU")
p = C.interpretar("apagar layout Mapa", CTX)
if not (p and p.get("destrutivo")):
    FALHAS.append("apagar layout devia pedir confirmação")

# --- não roubar frases de outros comandos / da IA
caso("mostrar campos de lotes", "list_fields", layer_name="lotes")
caso("listar camadas", "list_layers")
caso("zoom na camada lotes", "zoom_to_layer", layer_name="lotes")
caso("apagar campo uso", "delete_field", field_name="uso")
caso("salvar edição", "commit_edits")
caso("editar camada lotes", "start_editing", layer_name="lotes")
nada("faça um mapa temático da população por RA")
nada("gerar um relatório das rotas")
nada("qual a área total dos lotes?")
nada("deixar o mapa bonito")

for f in FALHAS:
    print("FALHOU:", f)
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
sys.exit(1 if FALHAS else 0)
