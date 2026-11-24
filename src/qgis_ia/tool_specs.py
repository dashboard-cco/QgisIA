# -*- coding: utf-8 -*-
"""
Descrição das ferramentas expostas via MCP (nome, descrição, JSON Schema).

Sem dependências do QGIS: é importado tanto pelo plugin quanto pela ponte
mcp_server.py. Cada nome aqui precisa existir em executor.ACTIONS ou em
actions/inspection.TOOLS (há um teste para isso).
"""


def _obj(props=None, required=()):
    return {"type": "object", "properties": props or {}, "required": list(required)}


_S = {"type": "string"}
_N = {"type": "number"}
_I = {"type": "integer"}
_B = {"type": "boolean"}


def _s(desc):
    return {"type": "string", "description": desc}


_LAYER = _s("Nome exato da camada no projeto (diferencia maiúsculas/minúsculas)")
_OUT = _s("Nome da camada de saída que será adicionada ao projeto")

TOOLS = {
    # ------------------------------------------------------------ inspeção
    "ping": ("Testa a conexão com o QGIS. Devolve {\"pong\": true}.", _obj()),
    "get_project_info": (
        "Resumo do projeto: título, arquivo, CRS, camadas (nome e tipo) e extensão do mapa.",
        _obj()),
    "get_layer_info": (
        "Detalhes de uma camada: CRS, tipo de geometria, campos (nome/tipo), nº de feições, "
        "extensão, filtro, seleção. Use ANTES de montar expressões ou filtros.",
        _obj({"layer_name": _LAYER}, ["layer_name"])),
    "get_features": (
        "Amostra de feições com atributos (máx. 500). Aceita filtro por expressão QGIS.",
        _obj({
            "layer_name": _LAYER,
            "limit": {"type": "integer", "description": "Máximo de feições (padrão 20)"},
            "expression": _s("Expressão QGIS para filtrar, ex.: \"area\" > 100"),
            "fields": {"type": "array", "items": _S, "description": "Campos a devolver (padrão: todos)"},
            "include_geometry": {"type": "boolean", "description": "Inclui a geometria em WKT"},
        }, ["layer_name"])),
    "get_algorithm_help": (
        "Parâmetros e saídas de um algoritmo do Processing, com os nomes exatos para run_algorithm.",
        _obj({"algorithm_id": _s("Ex.: native:extractbyattribute")}, ["algorithm_id"])),
    "render_map": (
        "Renderiza o mapa atual como imagem PNG para você ver o resultado.",
        _obj({"width": {"type": "integer", "description": "Largura em px (100-4000, padrão 1200)"},
              "height": {"type": "integer", "description": "Altura em px (100-4000, padrão 800)"}})),
    "set_layer_visibility": (
        "Liga ou desliga a visibilidade de uma camada (sem layer_name: todas).",
        _obj({"layer_name": _LAYER, "visible": _B})),
    "save_project": (
        "Salva o projeto. Informe 'path' se ele ainda não tem arquivo. [grava arquivo]",
        _obj({"path": _s("Caminho do .qgz/.qgs (opcional)")})),

    # ------------------------------------------------------------- camadas
    "list_layers": ("Lista os nomes das camadas do projeto.", _obj()),
    "select_by_expression": (
        "Seleciona feições por expressão QGIS.",
        _obj({"layer_name": _LAYER, "expression": _s("Ex.: \"campo\" = 'valor'")},
             ["layer_name", "expression"])),
    "create_memory_layer": (
        "Cria uma camada temporária (memória, EPSG:4326) com campos e feições opcionais.",
        _obj({
            "name": _s("Nome da camada"),
            "geometry_type": {"type": "string",
                              "enum": ["Point", "LineString", "Polygon", "MultiPoint",
                                       "MultiLineString", "MultiPolygon"]},
            "fields": {"type": "array", "items": _obj(
                {"name": _S, "type": {"type": "string",
                                      "enum": ["String", "Integer", "Double", "Boolean", "Date"]}},
                ["name"])},
            "features": {"type": "array", "description": "Lista de {geom: WKT, attrs: [valores]}",
                         "items": _obj({"geom": _s("Geometria em WKT"),
                                        "attrs": {"type": "array"}})},
        }, ["name"])),
    "add_vector_layer": (
        "Carrega uma camada vetorial de um arquivo (shp, gpkg, geojson...).",
        _obj({"file_path": _S, "layer_name": _S}, ["file_path"])),
    "add_raster_layer": (
        "Carrega uma camada raster de um arquivo (tif...).",
        _obj({"file_path": _S, "layer_name": _S}, ["file_path"])),
    "remove_layer": (
        "Remove uma camada do projeto. [destrutivo]",
        _obj({"layer_name": _LAYER}, ["layer_name"])),
    "zoom_to_layer": (
        "Ajusta o mapa à extensão da camada.",
        _obj({"layer_name": _LAYER}, ["layer_name"])),
    "export_layer": (
        "Exporta uma camada vetorial para arquivo; pode sobrescrever. [grava arquivo]",
        _obj({"layer_name": _LAYER, "output_path": _S,
              "format": _s("GPKG, ESRI Shapefile, CSV, GeoJSON... (padrão GPKG)")},
             ["layer_name", "output_path"])),
    "rename_layer": (
        "Renomeia uma camada.",
        _obj({"layer_name": _LAYER, "new_name": _S}, ["layer_name", "new_name"])),

    # ---------------------------------------------------- geoprocessamento
    "run_buffer": (
        "Buffer. Distância em unidades do CRS da camada (metros se CRS métrico).",
        _obj({"input_layer": _LAYER, "distance": _N, "segments": _I, "output_name": _OUT},
             ["input_layer", "distance"])),
    "run_intersection": (
        "Interseção entre duas camadas.",
        _obj({"input_layer": _LAYER, "overlay_layer": _LAYER, "output_name": _OUT},
             ["input_layer", "overlay_layer"])),
    "run_difference": (
        "Diferença (entrada menos sobreposição).",
        _obj({"input_layer": _LAYER, "overlay_layer": _LAYER, "output_name": _OUT},
             ["input_layer", "overlay_layer"])),
    "run_union": (
        "União de duas camadas.",
        _obj({"input_layer": _LAYER, "overlay_layer": _LAYER, "output_name": _OUT},
             ["input_layer", "overlay_layer"])),
    "run_dissolve": (
        "Dissolve feições, opcionalmente agrupando por campo.",
        _obj({"input_layer": _LAYER, "field": _s("Campo de agrupamento (opcional)"),
              "output_name": _OUT}, ["input_layer"])),
    "run_clip": (
        "Recorta uma camada pelos limites de outra.",
        _obj({"input_layer": _LAYER, "overlay_layer": _LAYER, "output_name": _OUT},
             ["input_layer", "overlay_layer"])),
    "run_merge_layers": (
        "Mescla várias camadas vetoriais em uma.",
        _obj({"input_layers": {"type": "array", "items": _S}, "output_name": _OUT},
             ["input_layers"])),
    "run_reproject": (
        "Reprojeta uma camada para outro CRS.",
        _obj({"input_layer": _LAYER, "target_crs": _s("Ex.: EPSG:31983"), "output_name": _OUT},
             ["input_layer", "target_crs"])),
    "run_centroids": (
        "Gera os centroides das feições.",
        _obj({"input_layer": _LAYER, "output_name": _OUT}, ["input_layer"])),
    "run_convex_hull": (
        "Gera o fecho convexo das feições.",
        _obj({"input_layer": _LAYER, "output_name": _OUT}, ["input_layer"])),
    "run_simplify": (
        "Simplifica geometrias.",
        _obj({"input_layer": _LAYER, "tolerance": _N, "output_name": _OUT}, ["input_layer"])),
    "run_spatial_join": (
        "Junta atributos por localização (interseção).",
        _obj({"input_layer": _LAYER, "join_layer": _LAYER, "output_name": _OUT,
              "join_type": {"type": "string", "enum": ["one-to-many", "one-to-one"]}},
             ["input_layer", "join_layer"])),
    "list_algorithms": (
        "Lista algoritmos do Processing (id e nome), filtrando por texto. Máx. 200.",
        _obj({"search_text": _S})),
    "run_algorithm": (
        "Executa QUALQUER algoritmo do Processing. Nomes de camada em 'params' viram a camada "
        "do projeto. Use get_algorithm_help para os nomes exatos dos parâmetros. [pode gravar arquivo]",
        _obj({"algorithm_id": _s("Ex.: native:extractbyattribute"),
              "params": {"type": "object", "description": "Parâmetros do algoritmo (chaves em maiúsculas)"},
              "output_name": _s("Se informado, a saída vira camada com este nome")},
             ["algorithm_id", "params"])),

    # --------------------------------------------------------------- layout
    "list_layouts": ("Lista os layouts de impressão do projeto.", _obj()),
    "export_layout_pdf": (
        "Exporta um layout para PDF. [grava arquivo]",
        _obj({"layout_name": _S, "output_path": _S}, ["layout_name", "output_path"])),
    "export_layout_image": (
        "Exporta um layout para imagem. [grava arquivo]",
        _obj({"layout_name": _S, "output_path": _S, "dpi": _I},
             ["layout_name", "output_path"])),

    # ---------------------------------------------------------- expressões
    "calculate_field": (
        "Calcula um campo por expressão QGIS (cria o campo se não existir) e grava na camada. [altera dados]",
        _obj({"layer_name": _LAYER, "field_name": _S, "expression": _S,
              "field_type": {"type": "string",
                             "enum": ["String", "Integer", "Double", "Boolean", "Date"]},
              "only_selected": _B},
             ["layer_name", "field_name", "expression"])),
    "filter_layer": (
        "Aplica filtro (subset string) à camada.",
        _obj({"layer_name": _LAYER, "expression": _S}, ["layer_name", "expression"])),
    "clear_filter": (
        "Remove o filtro da camada.",
        _obj({"layer_name": _LAYER}, ["layer_name"])),

    # ------------------------------------------------------------ edição
    "add_features": (
        "Adiciona feições a uma camada vetorial. [altera dados]",
        _obj({"layer_name": _LAYER,
              "features": {"type": "array", "description":
                           "Lista de {geom: '<WKT>', attrs: {campo: valor}}",
                           "items": _obj({"geom": _s("Geometria em WKT, no CRS da camada"),
                                          "attrs": {"type": "object"}})}},
             ["layer_name", "features"])),
    "update_features": (
        "Atualiza atributos das feições que casam com a expressão. [altera dados]",
        _obj({"layer_name": _LAYER,
              "expression": _s("Expressão QGIS, ex.: \"tipo\" = 'via'"),
              "attributes": {"type": "object", "description": "{campo: novo_valor}"}},
             ["layer_name", "expression", "attributes"])),
    "delete_features": (
        "Apaga as feições que casam com a expressão. [destrutivo]",
        _obj({"layer_name": _LAYER, "expression": _s("Expressão QGIS")},
             ["layer_name", "expression"])),
    "add_field": (
        "Cria um campo novo e vazio na camada. [altera dados]",
        _obj({"layer_name": _LAYER, "field_name": _S,
              "field_type": {"type": "string",
                             "enum": ["String", "Integer", "Double", "Boolean", "Date"]},
              "length": _I, "precision": _I},
             ["layer_name", "field_name"])),
    "delete_field": (
        "Remove um ou mais campos da camada. [destrutivo]",
        _obj({"layer_name": _LAYER,
              "field_name": {"anyOf": [_S, {"type": "array", "items": _S}],
                             "description": "Nome do campo ou lista de nomes"}},
             ["layer_name", "field_name"])),
    "rename_field": (
        "Renomeia um campo. [altera dados]",
        _obj({"layer_name": _LAYER, "field_name": _S, "new_name": _S},
             ["layer_name", "field_name", "new_name"])),
    "list_fields": (
        "Campos da camada com tipo, tamanho e precisão.",
        _obj({"layer_name": _LAYER}, ["layer_name"])),
    "duplicate_layer": (
        "Cópia independente (em memória) da camada, com o mesmo estilo. O original não muda.",
        _obj({"layer_name": _LAYER, "output_name": _OUT,
              "only_selected": _B, "keep_style": _B}, ["layer_name"])),
    "select_features": (
        "Seleciona feições por expressão QGIS (sem expressão: todas).",
        _obj({"layer_name": _LAYER, "expression": _S,
              "mode": {"type": "string", "enum": ["new", "add", "remove", "intersect"]}},
             ["layer_name"])),
    "clear_selection": (
        "Limpa a seleção de uma camada (sem nome: de todas).",
        _obj({"layer_name": _LAYER})),
    "invert_selection": (
        "Inverte a seleção da camada.",
        _obj({"layer_name": _LAYER}, ["layer_name"])),
    "zoom_to_selection": (
        "Aproxima o mapa das feições selecionadas.",
        _obj({"layer_name": _LAYER})),
    "delete_selected_features": (
        "Apaga as feições selecionadas. [destrutivo]",
        _obj({"layer_name": _LAYER}, ["layer_name"])),
    "count_features": (
        "Conta as feições (todas ou as que casam com a expressão).",
        _obj({"layer_name": _LAYER, "expression": _S}, ["layer_name"])),
    "start_editing": (
        "Liga o modo de edição: as mudanças ficam pendentes até salvar e podem ser desfeitas.",
        _obj({"layer_name": _LAYER}, ["layer_name"])),
    "commit_edits": (
        "Salva as edições pendentes (sem nome: de todas as camadas em edição). [altera dados]",
        _obj({"layer_name": _LAYER, "stop": _B})),
    "rollback_edits": (
        "Descarta as edições pendentes (sem nome: de todas). [destrutivo]",
        _obj({"layer_name": _LAYER, "stop": _B})),
    "undo_edit": (
        "Desfaz as últimas alterações de uma camada em edição (como Ctrl+Z).",
        _obj({"layer_name": _LAYER, "steps": _I}, ["layer_name"])),
    "redo_edit": (
        "Refaz alterações desfeitas de uma camada em edição.",
        _obj({"layer_name": _LAYER, "steps": _I}, ["layer_name"])),
    "edit_status": (
        "Camadas em edição e quantas alterações estão pendentes.",
        _obj()),

    # ---------------------------------------------------------- estatística
    "get_field_statistics": (
        "Estatísticas de um campo numérico: contagem, nulos, mín, máx, média, soma, mediana, desvio.",
        _obj({"layer_name": _LAYER, "field": _S}, ["layer_name", "field"])),
    "get_unique_values": (
        "Valores distintos de um campo (máx. 1000). Use antes de categorizar ou filtrar.",
        _obj({"layer_name": _LAYER, "field": _S, "limit": _I}, ["layer_name", "field"])),
    "get_raster_stats": (
        "Estatísticas de uma banda raster: mín, máx, média, desvio, no-data.",
        _obj({"layer_name": _LAYER, "band": _I}, ["layer_name"])),

    # -------------------------------------------------- simbologia / canvas
    "set_layer_style": (
        "Símbolo único: cor, tamanho/espessura, contorno e opacidade.",
        _obj({"layer_name": _LAYER,
              "color": _s("Cor do preenchimento: '#ff0000', 'red' ou '255,0,0'"),
              "size": _s("Tamanho do ponto ou espessura da linha, em mm"),
              "outline_color": _S, "outline_width": _N,
              "opacity": _s("0 a 1")},
             ["layer_name"])),
    "set_categorized_style": (
        "Cores por valor único de um campo (máx. 100 valores).",
        _obj({"layer_name": _LAYER, "field": _S,
              "colors": {"type": "object", "description": "{valor: cor} (opcional)"}},
             ["layer_name", "field"])),
    "set_graduated_style": (
        "Classes graduadas sobre um campo numérico, com rampa de cores.",
        _obj({"layer_name": _LAYER, "field": _S, "classes": _I,
              "mode": {"type": "string",
                       "enum": ["EqualInterval", "Quantile", "Jenks", "StdDev", "Pretty"]},
              "color_start": _S, "color_end": _S},
             ["layer_name", "field"])),
    "set_labels": (
        "Liga ou desliga rótulos a partir de um campo ou expressão.",
        _obj({"layer_name": _LAYER, "field": _s("Nome do campo ou expressão QGIS"),
              "enabled": _B, "size": _N, "color": _S, "bold": _B,
              "buffer": _s("Contorno branco no texto (padrão true)")},
             ["layer_name"])),
    "set_layer_opacity": (
        "Opacidade da camada, de 0 (transparente) a 1 (opaca).",
        _obj({"layer_name": _LAYER, "opacity": _N}, ["layer_name", "opacity"])),
    "add_basemap": (
        "Adiciona um mapa de fundo XYZ (precisa de internet).",
        _obj({"source": {"type": "string",
                         "enum": ["osm", "opentopomap", "esri_satellite", "esri_topo",
                                  "carto_light", "carto_dark", "google_satellite",
                                  "google_hybrid", "google_maps"]},
              "layer_name": _S})),
    "set_canvas_extent": (
        "Move o mapa para a extensão informada.",
        _obj({"xmin": _N, "ymin": _N, "xmax": _N, "ymax": _N,
              "crs": _s("CRS das coordenadas, ex.: EPSG:4326 (padrão: o do mapa)")},
             ["xmin", "ymin", "xmax", "ymax"])),
    "create_print_layout": (
        "Cria um layout de impressão pronto: título, mapa com o enquadramento atual, "
        "legenda, barra de escala e seta de norte. Abre o layout se houver interface.",
        _obj({"layout_name": _s("Nome do layout (padrão: o título ou 'Mapa')"), "title": _S,
              "subtitle": _S,
              "orientation": {"type": "string", "enum": ["landscape", "portrait"]},
              "page_size": _s("A0 a A5, Letter... (padrão A4)"),
              "legend": _B, "scalebar": _B, "north_arrow": _B, "open_designer": _B})),

    # -------------------------------------------------------------- mapas
    "update_symbol": (
        "Ajusta o símbolo atual sem recriar o estilo: cor (vira símbolo único), contorno, "
        "espessura do contorno, tamanho do ponto/espessura da linha, sem preenchimento.",
        _obj({"layer_name": _LAYER, "color": _S, "outline_color": _S,
              "outline_width": _s("mm"), "size": _s("mm"), "no_fill": _B},
             ["layer_name"])),
    "move_layer": (
        "Muda a ordem de desenho da camada.",
        _obj({"layer_name": _LAYER,
              "position": {"type": "string", "enum": ["top", "bottom", "up", "down"]}},
             ["layer_name", "position"])),
    "zoom_full": ("Mostra todas as camadas do projeto no mapa.", _obj()),
    "set_scale": (
        "Muda a escala do mapa (5000 = 1:5.000).",
        _obj({"scale": _N}, ["scale"])),
    "export_map_image": (
        "Salva o mapa atual (canvas) como imagem. Sem caminho: pasta do projeto. [grava arquivo]",
        _obj({"output_path": _S})),
    "add_layout_item": (
        "Acrescenta legenda, escala, norte, título ou texto a um layout existente.",
        _obj({"item": {"type": "string",
                       "enum": ["legend", "scalebar", "north_arrow", "title", "text"]},
              "layout_name": _s("Opcional se o projeto tem um só layout"), "text": _S},
             ["item"])),
    "remove_layout": (
        "Apaga um layout do projeto. [destrutivo]",
        _obj({"layout_name": _S}, ["layout_name"])),
    "list_print_layouts": ("Lista os layouts de impressão do projeto.", _obj()),
    "open_layout": (
        "Abre um layout na janela de edição de layouts.",
        _obj({"layout_name": _S})),
    "export_layout": (
        "Exporta um layout para pdf, png, jpg, tif ou svg. Sem caminho: pasta do projeto "
        "com o nome do layout; uma pasta também serve. [grava arquivo]",
        _obj({"layout_name": _s("Opcional se o projeto tem um só layout"),
              "output_path": _S,
              "format": {"type": "string", "enum": ["pdf", "png", "jpg", "tif", "svg"]},
              "dpi": _I})),

    # ------------------------------------------------------ geoprocessamento
    "geoprocess": (
        "Geoprocessamento na camada (resultado vira camada nova no projeto, nome único). "
        "tool: buffer, dissolve, clip, intersection, difference, union, merge, reproject, "
        "centroids, convex_hull, convex_hull_all, simplify, spatial_join, nearest_join, "
        "count_points, fix_geometries, single_parts, delete_duplicates, extract_vertices, "
        "polygons_to_lines, lines_to_polygons, grid, split_length (trechos de distance m), "
        "split_lines (quebra nos cruzamentos), snap (encaixa em overlay, tolerância distance m). "
        "Distâncias em metros (CRS projetado).",
        _obj({"tool": _S, "layer_name": _LAYER,
              "overlay": _s("Segunda camada (recorte, interseção, junção, contagem...)"),
              "overlays": {"type": "array", "items": _S, "description": "Camadas para merge"},
              "distance": _s("Metros (buffer, grade)"), "field": _s("Campo do dissolve"),
              "crs": _s("Destino do reproject, ex.: EPSG:31983"), "tolerance": _N,
              "dissolve": _B, "one_to_one": _B,
              "grid_type": {"type": "string", "enum": ["rectangle", "hexagon", "diamond", "point"]},
              "only_selected": _B, "output_name": _S},
             ["tool", "layer_name"])),
    "select_by_location": (
        "Seleciona feições pela relação espacial com outra camada (ou a até X metros dela).",
        _obj({"layer_name": _LAYER, "overlay": _S,
              "predicate": {"type": "string", "enum": ["intersects", "within", "contains", "touches",
                                                       "crosses", "overlaps", "disjoint", "equals"]},
              "distance": _N, "mode": {"type": "string", "enum": ["new", "add", "remove", "intersect"]}},
             ["layer_name", "overlay"])),
    "measure_total": (
        "Área total (polígonos) ou comprimento total (linhas), elipsoidal.",
        _obj({"layer_name": _LAYER, "only_selected": _B}, ["layer_name"])),
    "save_layer_as": (
        "Grava a camada em arquivo: gpkg, shp, geojson, csv, kml, dxf, xlsx, gdb (num .gdb que já "
        "existe entra como mais uma camada). Sem caminho: "
        "pasta do projeto. [grava arquivo]",
        _obj({"layer_name": _LAYER, "output_path": _S, "format": _S, "only_selected": _B},
             ["layer_name"])),

    # ----------------------------------------------------------- camadas
    "save_layer_to_project": (
        "Grava a camada na pasta do projeto IGUAL aos outros arquivos do projeto: mesma pasta, "
        "mesmo formato (o mesmo GeoPackage, se for o caso) e mesmo sistema de coordenadas. "
        "Camada temporária é trocada pela gravada (mesmo nome, estilo e posição). [grava arquivo]",
        _obj({"layer_name": _LAYER, "output_name": _S, "keep_temporary": _B}, ["layer_name"])),
    "project_storage_info": (
        "Como o projeto guarda os dados: pasta, formato, GeoPackage e sistema mais usados.", _obj()),
    "create_layer": (
        "Cria camada nova vazia, pronta para desenhar (entra em edição). Por padrão grava na pasta "
        "do projeto no formato e sistema do projeto; temporary=true cria só na memória. [grava arquivo]",
        _obj({"name": _S,
              "geometry_type": {"type": "string", "enum": ["point", "line", "polygon", "multipoint",
                                                           "multiline", "multipolygon", "none"]},
              "fields": {"type": "array", "items": _obj({"name": _S, "type": {"type": "string", "enum": [
                  "string", "integer", "long", "double", "date", "datetime", "boolean"]}}, ["name"])},
              "crs": _s("Ex.: EPSG:31983; vazio = sistema dos arquivos do projeto"),
              "temporary": _B, "start_editing": _B},
             ["name"])),
    "load_files": (
        "Abre no projeto um arquivo (shp, gpkg — todas as tabelas —, geojson, kml, csv, tif...), "
        "uma pasta .gdb ou todos os arquivos de mapa de uma pasta.",
        _obj({"path": _S}, ["path"])),
    "create_group": ("Cria um grupo no painel de camadas.", _obj({"name": _S}, ["name"])),
    "move_layer_to_group": (
        "Põe a camada dentro de um grupo do painel (cria o grupo se não existir).",
        _obj({"layer_name": _LAYER, "group": _S}, ["layer_name", "group"])),
    "set_layer_crs": (
        "DEFINE o sistema de coordenadas da camada sem mexer nas coordenadas (corrigir etiqueta "
        "errada). Para converter coordenadas use geoprocess reproject.",
        _obj({"layer_name": _LAYER, "crs": _S}, ["layer_name", "crs"])),
    "fill_field_by_location": (
        "Preenche um campo que JÁ EXISTE na camada com o valor do polígono de outra camada onde "
        "cada feição está (ex.: codigo_ra pelos limites das RAs). [altera dados]",
        _obj({"layer_name": _LAYER, "field": _S, "overlay": _s("Camada de polígonos"),
              "overlay_field": _s("Campo de onde vem o valor (padrão: mesmo nome)"), "only_empty": _B},
             ["layer_name", "field", "overlay"])),
    "copy_style": (
        "Copia o estilo inteiro (cores, classes, rótulos) de uma camada para outra.",
        _obj({"from_layer": _S, "to_layer": _LAYER}, ["from_layer", "to_layer"])),

    "duplicar_camada_com_ra": (
        "Copia uma camada vetorial para uma nova camada temporária e cria nela a coluna 'RA' "
        "(Região Administrativa). Preenche a RA por localização se 'ra_layer' (polígonos das "
        "RAs) for informado; senão pelo campo codigo_ra, se existir; senão deixa vazia. "
        "A camada original não é alterada.",
        _obj({"layer_name": _LAYER,
              "output_name": _s("Nome da cópia (padrão: <camada>_RA)"),
              "ra_layer": _s("Camada de polígonos das RAs, para preencher por localização"),
              "ra_name_field": _s("Campo com o nome da RA em ra_layer (padrão: 1º campo texto)")},
             ["layer_name"])),

        # ------------------------------------- Planos de Serviço SLU-DF (Anexo G)
    "slu_info_edital": (
        "Regras do Anexo G do edital SLU-DF (Pregão 90005/2026): serviços P1-P12, siglas "
        "(CC, CS, VA, VE, MA, ME, VL, LE, FR, PE, TR), camadas, campos, códigos de circuito, "
        "RAs por lote, Tabela 4 de equipamentos. Consulte antes de montar um plano.",
        _obj({"servico": _s("Opcional: P1..P12 ou sigla, para detalhar um serviço")})),
    "slu_criar_gdb": (
        "Cria o File Geodatabase vazio do Plano de Serviço no padrão do Anexo G (ex.: CC01.gdb): "
        "camadas com nomes padronizados, campos, apelidos, domínios e SIRGAS 2000/UTM 23S. Para "
        "serviços sob demanda, com 'limite_df' já grava 1 polígono por turno. [grava arquivo]",
        _obj({"servico": _s("P1..P12 ou sigla (CC, CS, VA, VE, MA...)"),
              "lote": {"type": "integer", "enum": [1, 2, 3]},
              "pasta_saida": _s("Pasta onde o .gdb será criado"),
              "sobrescrever": _B, "carregar": _B,
              "limite_df": _s("Sob demanda: arquivo vetorial com o limite do DF (opcional)"),
              "turnos": {"type": "array", "items": {"type": "string",
                                                    "enum": ["Diurno", "Noturno"]}},
              "numero_equipes": _I},
             ["servico", "lote", "pasta_saida"])),
    "slu_validar_gdb": (
        "Confere um .gdb contra o Anexo G: camadas/campos/CRS, lote, Código Circuito, Código "
        "RA (e RAs do lote), Nome do Circuito, frequência x dias, ciclo/semana, horários, "
        "tipos, endereçamento e regras topológicas (single part, 50-130/200 m, overlap, "
        "intersect, linhas/pontos dentro do polígono, ponto sobre linha, 1 início e 1 fim). "
        "Serviço e lote saem do nome do arquivo. 'relatorio_xlsx' grava o relatório completo. "
        "[relatorio_xlsx grava arquivo]",
        _obj({"gdb_path": _S, "servico": _S, "lote": _I,
              "topologia_linhas": {"type": "boolean",
                                   "description": "Confere overlap/intersect entre linhas "
                                                  "(padrão true; mais lento)"},
              "relatorio_xlsx": _s("Caminho do relatório .xlsx (opcional)"),
              "carregar_erros": {"type": "boolean",
                                 "description": "Adiciona camada de pontos com os problemas"}},
             ["gdb_path"])),
    "slu_preencher_atributos": (
        "Preenche no .gdb os campos que o Anexo G define por regra: lote, frequência e Nome do "
        "Circuito (dos dias/ciclo/RA), tipo de serviço (do código), ciclo/semana padrão, "
        "Código RA de linhas e pontos (do polígono), turno, extensão da sarjeta. Faz backup "
        "do .gdb antes. [altera dados]",
        _obj({"gdb_path": _S, "servico": _S, "lote": _I,
              "sobrescrever": {"type": "boolean",
                               "description": "true recalcula também campos já preenchidos"},
              "backup": _B}, ["gdb_path"])),
    "slu_exportar_xlsx": (
        "Gera a TABELA .xlsx do plano (item 3.1.2) com as tabelas de atributos do .gdb: uma "
        "aba por camada, cabeçalhos do Anexo G, horários HH:MM:SS. [grava arquivo]",
        _obj({"gdb_path": _S, "saida_xlsx": _S}, ["gdb_path", "saida_xlsx"])),
    "slu_gerar_programacao_trimestral": (
        "Gera a programação trimestral .xlsx dos serviços sob demanda (P3, P4, P7-P12; seção 7, "
        "Tabela 5): todos os dias do trimestre agrupados por semana. [grava arquivo]",
        _obj({"servico": _S, "lote": _I, "ano": _I,
              "trimestre": {"type": "integer", "enum": [1, 2, 3, 4]}, "saida_xlsx": _S},
             ["servico", "lote", "ano", "trimestre", "saida_xlsx"])),
    "slu_gerar_docx": (
        "Gera o TEXTO .docx do Plano de Serviço (item 3.1.1) em Arial 12/14 com as seções "
        "exigidas; 'dados' preenche seções ({título: texto}); com 'gdb_path' inclui o quadro "
        "de circuitos. [grava arquivo]",
        _obj({"servico": _S, "lote": _I, "saida_docx": _S, "empresa": _S,
              "dados": {"type": "object", "description":
                        "Títulos: O que é o serviço; Tipo de material coletado; Local de origem "
                        "e destinação final do material; Planejamento das rotas e frequências; "
                        "Veículos utilizados e placas; Tipos de caminhões utilizados; Pessoal da "
                        "operação; Horários; Procedimentos operacionais; Equipe e contatos-chave"},
              "gdb_path": _S}, ["servico", "lote", "saida_docx"])),
    "slu_exportar_shapefile": (
        "Exporta o .gdb para shapefile (o edital, item 7.8, pede mapas em .shp). Nomes de campo "
        "são cortados em 10 caracteres; o retorno traz o mapa de nomes. [grava arquivo]",
        _obj({"gdb_path": _S, "pasta_saida": _S}, ["gdb_path", "pasta_saida"])),
    "slu_gerar_plano": (
        "Gera de uma vez os arquivos do Plano de Serviço (item 3.1): .gdb (novo ou "
        "'gdb_existente'), .xlsx (atributos e/ou programação trimestral) e .docx, numa pasta "
        "<servico>_<lote>. [grava arquivo]",
        _obj({"servico": _S, "lote": _I, "pasta_saida": _S, "ano": _I, "trimestre": _I,
              "gdb_existente": _s("Usar este .gdb já preenchido em vez de criar um vazio"),
              "empresa": _S, "dados_texto": {"type": "object"},
              "limite_df": _S, "turnos": {"type": "array", "items": _S},
              "numero_equipes": _I, "carregar": _B},
             ["servico", "lote", "pasta_saida"])),

    "slu_redesenhar_coleta": (
        "Redesenha um plano de coleta existente (CC0X/CS0X .gdb) sobre a rede viária, no padrão "
        "do Anexo G e com os lotes do novo edital: traduz as linhas atuais para a rede, tira o "
        "que ficou em outro lote, calcula as vias de passagem pela rede (respeitando a mão), "
        "corta em 50-130 m, refaz polígonos, início/fim, Código RA, nome e endereçamento. "
        "Grava um .gdb NOVO (o atual não muda), um GeoPackage de pendências e a validação. "
        "Demora alguns minutos. [grava arquivo]",
        _obj({"gdb_atual": _s("Plano atual, ex.: E:/.../Gdb/CC01.gdb"),
              "rede_gdb": _s("Rede viária, ex.: E:/.../Vias/RedeNetworkAnalyst.gdb"),
              "rede_camada": _s("Camada de linhas da rede (padrão ArquivoRua)"),
              "sentidos": _s("GeoPackage com ID e o campo de sentido (ArquivoRua.gpkg)"),
              "campo_sentido": _s("Campo com FT/TF para mão única (padrão sentido_proposto)"),
              "respeitar_sentido": _B,
              "vias_endereco": _s("Shapefile de vias com o campo Endereco"),
              "regioes": _s("Shapefile das RAs com ra_cira e Lote"),
              "pasta_saida": _S,
              "circuitos": {"type": "array", "items": _I,
                            "description": "Só estes códigos (para teste)"},
              "buffer_poligono": _N, "restaurar_shx": _B, "sobrescrever": _B, "carregar": _B,
              "ajustar_frota": {"type": "boolean", "description":
                                "Junta circuitos (mesmos dias/horário/RA, vizinhos) até cada "
                                "dia e turno caber na frota do Anexo R"},
              "distancia_fusao": _s("Distância máxima entre circuitos para juntar, em m "
                                    "(padrão 1500)")},
             ["gdb_atual", "rede_gdb", "regioes", "pasta_saida"])),

    "slu_planilha_soltura": (
        "Gera a planilha de soltura (.xlsx) de um plano de coleta: veículo, placa, horário e "
        "circuito por dia e turno. Dimensiona a frota pelos circuitos (cada circuito com "
        "veículo fixo, sem sobreposição de horário; códigos VA01, VA02...). Abas Soltura, "
        "Frota (placas a preencher), Grade semanal, Resumo e Circuitos. [grava arquivo]",
        _obj({"gdb_path": _S, "saida_xlsx": _S,
              "intervalo_min": _s("Folga mínima entre circuitos do mesmo veículo (padrão 60)"),
              "dois_turnos": {"type": "boolean",
                              "description": "Veículo pode fazer diurno e noturno (padrão true)"},
              "prefixo_veiculo": _s("Prefixo dos códigos de veículo (padrão VA)")},
             ["gdb_path", "saida_xlsx"])),

    # ----------------------------------------------------------- avançado
    "execute_code": (
        "Executa código PyQGIS arbitrário no QGIS e devolve o que foi impresso. "
        "Só funciona se 'Permitir execução de código Python' estiver marcado no painel. "
        "Use print() para devolver informação. [avançado, pode fazer qualquer coisa]",
        _obj({"code": _s("Código Python. 'iface', 'QgsProject' e 'processing' já estão disponíveis."),
              "return_variable": _s("Nome de uma variável definida pelo código, para devolver o valor")},
             ["code"])),
}
