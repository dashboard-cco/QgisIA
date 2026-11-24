# -*- coding: utf-8 -*-
"""
Actions: geoproc - Geoprocessamento pensado para os comandos simples.

A camada de entrada é sempre a selecionada no painel (regra dos comandos); a
segunda camada, quando existe, é só "molde" (recorte, interseção, junção...).
O resultado entra no projeto como camada nova, com nome único, e o painel
passa a selecioná-la para encadear o próximo comando.
"""
import os

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsProcessingFeedback, QgsProcessingContext,
    QgsProcessingFeatureSourceDefinition, QgsCoordinateReferenceSystem,
    QgsVectorFileWriter, QgsWkbTypes, QgsDistanceArea, QgsUnitTypes,
)
import processing

# operação -> (algoritmo, sufixo do nome de saída, precisa de distância métrica)
FERRAMENTAS = {
    "buffer": ("native:buffer", "buffer", True),
    "dissolve": ("native:dissolve", "dissolvido", False),
    "clip": ("native:clip", "recorte", False),
    "intersection": ("native:intersection", "intersecao", False),
    "difference": ("native:difference", "diferenca", False),
    "union": ("native:union", "uniao", False),
    "merge": ("native:mergevectorlayers", "mesclado", False),
    "reproject": ("native:reprojectlayer", "reprojetado", False),
    "centroids": ("native:centroids", "centroides", False),
    "convex_hull": ("native:convexhull", "envoltoria", False),
    "convex_hull_all": ("qgis:minimumboundinggeometry", "envoltoria", False),
    "simplify": ("native:simplifygeometries", "simplificado", True),
    "spatial_join": ("native:joinattributesbylocation", "juncao", False),
    "nearest_join": ("native:joinbynearest", "mais_proximo", False),
    "count_points": ("native:countpointsinpolygon", "contagem", False),
    "fix_geometries": ("native:fixgeometries", "corrigido", False),
    "single_parts": ("native:multiparttosingleparts", "partes", False),
    "delete_duplicates": ("native:deleteduplicategeometries", "sem_duplicadas", False),
    "extract_vertices": ("native:extractvertices", "vertices", False),
    "polygons_to_lines": ("native:polygonstolines", "linhas", False),
    "lines_to_polygons": ("native:linestopolygons", "poligonos", False),
    "grid": ("native:creategrid", "grade", True),
    "split_length": ("native:splitlinesbylength", "trechos", True),
    "split_lines": ("native:splitwithlines", "dividido", False),
    "snap": ("native:snapgeometries", "encaixado", False),
}

PREDICADOS = {"intersects": 0, "contains": 1, "disjoint": 2, "equals": 3, "touches": 4,
              "overlaps": 5, "within": 6, "crosses": 7}


def _layer(nome):
    camadas = QgsProject.instance().mapLayersByName(nome)
    if not camadas:
        raise ValueError(f"Camada não encontrada: {nome}")
    camada = camadas[0]
    if not isinstance(camada, QgsVectorLayer):
        raise ValueError(f"'{nome}' não é uma camada vetorial.")
    return camada


def _fonte(camada, so_selecionadas):
    if so_selecionadas:
        if not camada.selectedFeatureCount():
            raise ValueError(f"Nenhuma feição selecionada em '{camada.name()}'.")
        return QgsProcessingFeatureSourceDefinition(camada.id(), selectedFeaturesOnly=True)
    return camada


def _nome_livre(base):
    proj = QgsProject.instance()
    if not proj.mapLayersByName(base):
        return base
    n = 2
    while proj.mapLayersByName(f"{base}_{n}"):
        n += 1
    return f"{base}_{n}"


def _exige_metros(camada, oque):
    if camada.crs().isGeographic():
        raise ValueError(
            f"'{camada.name()}' está em graus ({camada.crs().authid()}); {oque} em metros não "
            "funciona assim. Reprojete antes: 'reprojetar para 31983' (SIRGAS 2000 / UTM 23S, DF).")


def _crs(valor):
    crs = QgsCoordinateReferenceSystem(str(valor))
    if not crs.isValid():
        raise ValueError(f"Sistema de coordenadas inválido: {valor}")
    return crs


def geoprocess(tool, layer_name, overlay=None, overlays=None, distance=None, field=None,
               crs=None, tolerance=None, dissolve=False, one_to_one=True, grid_type="rectangle",
               only_selected=False, output_name=None):
    """Roda uma operação de geoprocessamento na camada e adiciona o resultado ao projeto.

    tool: buffer, dissolve, clip, intersection, difference, union, merge, reproject,
    centroids, convex_hull, convex_hull_all, simplify, spatial_join, nearest_join,
    count_points, fix_geometries, single_parts, delete_duplicates, extract_vertices,
    polygons_to_lines, lines_to_polygons, grid, split_length (trechos de 'distance' m),
    split_lines (quebra nos cruzamentos; overlay opcional), snap (encaixa na camada
    'overlay' com tolerância 'distance' m, padrão 5).
    Distâncias (buffer, simplify, grid) em metros: a camada precisa estar em CRS projetado.
    """
    if tool not in FERRAMENTAS:
        raise ValueError(f"Operação desconhecida: {tool}. Use: {', '.join(sorted(FERRAMENTAS))}")
    alg, sufixo, metrico = FERRAMENTAS[tool]
    camada = _layer(layer_name)
    if metrico:
        _exige_metros(camada, "distância")
    entrada = _fonte(camada, only_selected)
    outra = None
    if tool in ("clip", "intersection", "difference", "union", "spatial_join", "nearest_join",
                "count_points", "snap"):
        if not overlay:
            raise ValueError("Diga a outra camada (ex.: recortar pela camada Regiões).")
        outra = _layer(overlay)
        if outra.id() == camada.id():
            raise ValueError("A outra camada não pode ser a própria camada selecionada.")

    p = {"INPUT": entrada}
    if tool == "buffer":
        if distance is None:
            raise ValueError("Diga a distância (ex.: buffer de 50 m).")
        p.update(DISTANCE=float(distance), SEGMENTS=8, END_CAP_STYLE=0, JOIN_STYLE=0,
                 MITER_LIMIT=2, DISSOLVE=bool(dissolve))
        sufixo = f"buffer_{float(distance):g}m"
    elif tool == "dissolve":
        campos = field if isinstance(field, list) else ([field] if field else [])
        for c in campos:
            if camada.fields().indexOf(c) < 0:
                raise ValueError(f"Campo não encontrado em '{layer_name}': {c}")
        p["FIELD"] = campos
    elif tool in ("clip", "difference"):
        p["OVERLAY"] = outra
    elif tool in ("intersection", "union"):
        p.update(OVERLAY=outra)
    elif tool == "merge":
        nomes = overlays or ([overlay] if overlay else [])
        if not nomes:
            raise ValueError("Diga com quais camadas mesclar.")
        p = {"LAYERS": [entrada] + [_layer(n) for n in nomes]}
    elif tool == "reproject":
        destino = _crs(crs)
        p["TARGET_CRS"] = destino
        sufixo = destino.authid().replace(":", "_").lower()
    elif tool == "convex_hull_all":
        p.update(FIELD="", TYPE=3)
    elif tool == "simplify":
        if tolerance is None:
            raise ValueError("Diga a tolerância (ex.: simplificar 5 m).")
        p.update(METHOD=0, TOLERANCE=float(tolerance))
    elif tool == "spatial_join":
        p.update(JOIN=outra, PREDICATE=[0], JOIN_FIELDS=[], METHOD=1 if one_to_one else 0,
                 DISCARD_NONMATCHING=False, PREFIX="")
    elif tool == "nearest_join":
        p.update(INPUT_2=outra, FIELDS_TO_COPY=[], DISCARD_NONMATCHING=False, PREFIX="",
                 NEIGHBORS=1, MAX_DISTANCE=None)
    elif tool == "count_points":
        if camada.geometryType() != QgsWkbTypes.PolygonGeometry:
            raise ValueError("Para contar pontos em cada polígono, selecione a camada de polígonos.")
        nome_campo = ("qtd_" + outra.name().lower().replace(" ", "_"))[:30]
        p = {"POLYGONS": entrada, "POINTS": outra, "WEIGHT": "", "CLASSFIELD": "",
             "FIELD": nome_campo}
    elif tool == "grid":
        if distance is None:
            raise ValueError("Diga o tamanho da célula (ex.: grade de 500 m).")
        ext = camada.extent()
        tipos = {"rectangle": 2, "hexagon": 4, "diamond": 3, "point": 0}
        p = {"TYPE": tipos.get(grid_type, 2),
             "EXTENT": f"{ext.xMinimum()},{ext.xMaximum()},{ext.yMinimum()},{ext.yMaximum()} "
                       f"[{camada.crs().authid()}]",
             "HSPACING": float(distance), "VSPACING": float(distance),
             "HOVERLAY": 0, "VOVERLAY": 0, "CRS": camada.crs()}
        sufixo = f"grade_{float(distance):g}m"
    elif tool == "split_length":
        if distance is None:
            raise ValueError("Diga o tamanho dos trechos (ex.: dividir linhas a cada 100 m).")
        if camada.geometryType() != QgsWkbTypes.LineGeometry:
            raise ValueError("Dividir em trechos vale para camada de linhas.")
        p["LENGTH"] = float(distance)
        sufixo = f"trechos_{float(distance):g}m"
    elif tool == "split_lines":
        if camada.geometryType() != QgsWkbTypes.LineGeometry:
            raise ValueError("Dividir nos cruzamentos vale para camada de linhas.")
        p["LINES"] = _layer(overlay) if overlay else camada
    elif tool == "snap":
        if distance is not None:
            _exige_metros(camada, "tolerância")
        p.update(REFERENCE_LAYER=outra, TOLERANCE=float(distance) if distance is not None else 5.0,
                 BEHAVIOR=1)

    nome = _nome_livre(output_name or f"{camada.name()}_{sufixo}")
    p["OUTPUT"] = "memory:" + nome
    contexto = QgsProcessingContext()
    contexto.setProject(QgsProject.instance())
    res = processing.run(alg, p, context=contexto, feedback=QgsProcessingFeedback())
    saida = res["OUTPUT"]
    if isinstance(saida, str):
        saida = contexto.takeResultLayer(saida) or QgsProject.instance().mapLayer(saida)
    saida.setName(nome)
    QgsProject.instance().addMapLayer(saida)
    out = {"success": True, "output_layer": nome, "feature_count": saida.featureCount()}
    if tool == "count_points":
        out["campo_criado"] = p["FIELD"]
    if tool == "nearest_join":
        out["campo_distancia"] = "distance"
    return out


def select_by_location(layer_name, overlay, predicate="intersects", distance=None, mode="new"):
    """Seleciona feições da camada pela relação espacial com outra camada.

    predicate: intersects, within, contains, touches, crosses, overlaps, disjoint, equals.
    distance (m): seleciona as que estão a até essa distância da outra camada.
    """
    camada = _layer(layer_name)
    outra = _layer(overlay)
    metodo = {"new": 0, "add": 1, "remove": 2, "intersect": 3}.get(mode, 0)
    if distance is not None:
        _exige_metros(camada, "distância")
        processing.run("native:selectwithindistance",
                       {"INPUT": camada, "REFERENCE": outra, "DISTANCE": float(distance),
                        "METHOD": metodo})
    else:
        if predicate not in PREDICADOS:
            raise ValueError(f"Relação inválida: {predicate}. Use: {', '.join(PREDICADOS)}")
        processing.run("native:selectbylocation",
                       {"INPUT": camada, "PREDICATE": [PREDICADOS[predicate]],
                        "INTERSECT": outra, "METHOD": metodo})
    return {"success": True, "layer": layer_name, "selected": camada.selectedFeatureCount()}


def measure_total(layer_name, only_selected=False):
    """Área total (polígonos) ou comprimento total (linhas), elipsoidal, em m²/ha/km²/m/km."""
    camada = _layer(layer_name)
    da = QgsDistanceArea()
    da.setSourceCrs(camada.crs(), QgsProject.instance().transformContext())
    da.setEllipsoid(QgsProject.instance().ellipsoid() or "GRS80")
    feats = camada.getSelectedFeatures() if only_selected else camada.getFeatures()
    tipo = camada.geometryType()
    total, n = 0.0, 0
    for f in feats:
        g = f.geometry()
        if g is None or g.isEmpty():
            continue
        n += 1
        if tipo == QgsWkbTypes.PolygonGeometry:
            total += da.convertAreaMeasurement(da.measureArea(g), QgsUnitTypes.AreaSquareMeters)
        elif tipo == QgsWkbTypes.LineGeometry:
            total += da.convertLengthMeasurement(da.measureLength(g), QgsUnitTypes.DistanceMeters)
    if tipo == QgsWkbTypes.PolygonGeometry:
        return {"layer": layer_name, "feicoes": n, "area_m2": round(total, 2),
                "area_ha": round(total / 10000, 4), "area_km2": round(total / 1e6, 6)}
    if tipo == QgsWkbTypes.LineGeometry:
        return {"layer": layer_name, "feicoes": n, "comprimento_m": round(total, 2),
                "comprimento_km": round(total / 1000, 4)}
    return {"layer": layer_name, "feicoes": n, "aviso": "Pontos não têm área nem comprimento."}


FORMATOS = {
    "gpkg": ("GPKG", "gpkg"), "geopackage": ("GPKG", "gpkg"),
    "shp": ("ESRI Shapefile", "shp"), "shapefile": ("ESRI Shapefile", "shp"),
    "geojson": ("GeoJSON", "geojson"), "json": ("GeoJSON", "geojson"),
    "csv": ("CSV", "csv"), "kml": ("KML", "kml"), "dxf": ("DXF", "dxf"),
    "xlsx": ("XLSX", "xlsx"), "excel": ("XLSX", "xlsx"),
    "gdb": ("OpenFileGDB", "gdb"), "geodatabase": ("OpenFileGDB", "gdb"),
}


def save_layer_as(layer_name, output_path=None, format=None, only_selected=False):
    """Grava a camada em arquivo (gpkg, shp, geojson, csv, kml, dxf, xlsx, gdb).

    Sem caminho: pasta do projeto, com o nome da camada. Formato pela extensão ou por 'format'.
    gdb: grava num File Geodatabase; se o .gdb já existir, entra como mais uma camada.
    """
    camada = _layer(layer_name)
    ext = os.path.splitext((output_path or "").rstrip("\\/"))[1].lower().lstrip(".")
    chave = (format or ext or "gpkg").lower()
    if chave not in FORMATOS:
        raise ValueError(f"Formato desconhecido: {chave}. Use: {', '.join(sorted(FORMATOS))}")
    driver, extensao = FORMATOS[chave]
    from .mapas import _caminho
    if output_path and output_path.rstrip("\\/").lower().endswith(".gdb"):
        caminho = output_path.rstrip("\\/")  # o próprio .gdb (é uma pasta)
    else:
        caminho = _caminho(output_path, camada.name(), extensao)
    opcoes = QgsVectorFileWriter.SaveVectorOptions()
    if driver == "OpenFileGDB" and os.path.isdir(caminho):
        # .gdb já existe: acrescenta a camada como mais uma feature class
        from qgis.core import QgsProviderRegistry
        tabelas = {d.name().lower() for d in QgsProviderRegistry.instance().querySublayers(caminho)}
        if camada.name().lower() in tabelas:
            raise ValueError(f"O {os.path.basename(caminho)} já tem a camada '{camada.name()}'.")
        opcoes.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    elif os.path.exists(caminho):
        raise ValueError(f"Já existe o arquivo {caminho}. Escolha outro nome (… em C:\\pasta\\novo.{extensao}).")
    opcoes.driverName = driver
    opcoes.fileEncoding = "UTF-8"
    opcoes.onlySelectedFeatures = bool(only_selected)
    if driver in ("GPKG", "OpenFileGDB"):
        opcoes.layerName = camada.name()
    erro = QgsVectorFileWriter.writeAsVectorFormatV3(
        camada, caminho, QgsProject.instance().transformContext(), opcoes)
    if erro[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Falha ao gravar: {erro[1]}")
    return {"success": True, "output_path": caminho, "formato": driver}


TOOLS = {
    "geoprocess": geoprocess,
    "select_by_location": select_by_location,
    "measure_total": measure_total,
    "save_layer_as": save_layer_as,
}
