# -*- coding: utf-8 -*-
"""
Actions: styling - Simbologia, rótulos, mapas de fundo, canvas e layouts.
"""
import random

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer, QgsSymbol, QgsRendererCategory,
    QgsCategorizedSymbolRenderer, QgsGraduatedSymbolRenderer, QgsSingleSymbolRenderer,
    QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling,
    QgsRectangle, QgsCoordinateReferenceSystem, QgsPrintLayout, QgsLayoutItemMap,
    QgsLayoutItemLabel, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes,
)
from qgis.PyQt.QtGui import QColor, QFont

XYZ_SOURCES = {
    "osm": ("https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png", 19),
    "opentopomap": ("https://a.tile.opentopomap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png", 17),
    "esri_satellite": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/"
        "tile/%7Bz%7D/%7By%7D/%7Bx%7D", 19),
    "esri_topo": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/"
        "tile/%7Bz%7D/%7By%7D/%7Bx%7D", 19),
    "carto_light": ("https://a.basemaps.cartocdn.com/light_all/%7Bz%7D/%7Bx%7D/%7By%7D.png", 20),
    "carto_dark": ("https://a.basemaps.cartocdn.com/dark_all/%7Bz%7D/%7Bx%7D/%7By%7D.png", 20),
}


def _layer(layer_name):
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        raise ValueError(f"Camada não encontrada: {layer_name}")
    return layers[0]


def _vector(layer_name):
    layer = _layer(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"'{layer_name}' não é uma camada vetorial")
    return layer


def _color(value, fallback=None):
    """Aceita '#ff0000', 'red', '255,0,0'. None gera uma cor aleatória legível."""
    if value is None:
        if fallback is not None:
            return fallback
        return QColor.fromHsv(random.randint(0, 359), random.randint(120, 220),
                              random.randint(150, 230))
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return QColor(int(value[0]), int(value[1]), int(value[2]))
    text = str(value).strip()
    if "," in text:
        parts = [int(p) for p in text.split(",")[:3]]
        return QColor(*parts)
    color = QColor(text)
    if not color.isValid():
        raise ValueError(f"Cor inválida: {value}")
    return color


def _symbol(layer, color=None, size=None, outline_color=None, outline_width=None):
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    if symbol is None:
        raise RuntimeError(f"Não consegui criar símbolo para '{layer.name()}'.")
    symbol.setColor(_color(color))
    sym_layer = symbol.symbolLayer(0)
    if size is not None and hasattr(sym_layer, "setSize"):
        sym_layer.setSize(float(size))
    if outline_color is not None and hasattr(sym_layer, "setStrokeColor"):
        sym_layer.setStrokeColor(_color(outline_color))
    if outline_width is not None and hasattr(sym_layer, "setStrokeWidth"):
        sym_layer.setStrokeWidth(float(outline_width))
    return symbol


def _refresh(layer):
    layer.triggerRepaint()
    try:
        from qgis.utils import iface
        if iface is not None:
            iface.layerTreeView().refreshLayerSymbology(layer.id())
    except Exception:
        pass


def set_layer_style(layer_name, color=None, size=None, outline_color=None,
                    outline_width=None, opacity=None):
    """Símbolo único: cor de preenchimento, tamanho/espessura e contorno."""
    layer = _vector(layer_name)
    layer.setRenderer(QgsSingleSymbolRenderer(
        _symbol(layer, color, size, outline_color, outline_width)))
    if opacity is not None:
        layer.setOpacity(max(0.0, min(float(opacity), 1.0)))
    _refresh(layer)
    return {"success": True, "layer": layer_name, "renderer": "singleSymbol"}


def set_categorized_style(layer_name, field, colors=None):
    """Cores por valor único de um campo. colors: {"valor": "#rrggbb"} (opcional)."""
    layer = _vector(layer_name)
    if layer.fields().indexOf(field) < 0:
        raise ValueError(f"Campo não encontrado em '{layer_name}': {field}")
    colors = colors or {}
    categories = []
    values = sorted(layer.uniqueValues(layer.fields().indexOf(field)),
                    key=lambda v: (v is None, str(v)))
    if len(values) > 100:
        raise ValueError(f"O campo '{field}' tem {len(values)} valores distintos "
                         "(máx. 100 para categorizar). Use set_graduated_style.")
    for value in values:
        key = "" if value is None else str(value)
        symbol = _symbol(layer, colors.get(key))
        categories.append(QgsRendererCategory(value, symbol, key or "(vazio)"))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))
    _refresh(layer)
    return {"success": True, "layer": layer_name, "field": field,
            "categories": len(categories)}


def set_graduated_style(layer_name, field, classes=5, mode="EqualInterval",
                        color_start="#f7fbff", color_end="#08306b"):
    """Classes graduadas sobre um campo numérico."""
    layer = _vector(layer_name)
    if layer.fields().indexOf(field) < 0:
        raise ValueError(f"Campo não encontrado em '{layer_name}': {field}")
    modes = {
        "EqualInterval": QgsGraduatedSymbolRenderer.EqualInterval,
        "Quantile": QgsGraduatedSymbolRenderer.Quantile,
        "Jenks": QgsGraduatedSymbolRenderer.Jenks,
        "StdDev": QgsGraduatedSymbolRenderer.StdDev,
        "Pretty": QgsGraduatedSymbolRenderer.Pretty,
    }
    if mode not in modes:
        raise ValueError(f"Modo inválido: {mode}. Use: {sorted(modes)}")

    from qgis.core import QgsGradientColorRamp
    ramp = QgsGradientColorRamp(_color(color_start), _color(color_end))
    renderer = QgsGraduatedSymbolRenderer.createRenderer(
        layer, field, int(classes), modes[mode], _symbol(layer), ramp)
    if renderer is None or not renderer.ranges():
        raise RuntimeError(f"Não consegui classificar '{field}'. Ele é numérico?")
    layer.setRenderer(renderer)
    _refresh(layer)
    return {"success": True, "layer": layer_name, "field": field,
            "classes": len(renderer.ranges()), "mode": mode}


def set_labels(layer_name, field=None, enabled=True, size=10, color="#000000"):
    """Liga ou desliga rótulos a partir de um campo (ou expressão)."""
    layer = _vector(layer_name)
    if not enabled:
        layer.setLabelsEnabled(False)
        _refresh(layer)
        return {"success": True, "layer": layer_name, "labels": False}
    if not field:
        raise ValueError("Informe 'field' (nome de campo ou expressão) para rotular.")

    settings = QgsPalLayerSettings()
    settings.fieldName = field
    settings.isExpression = layer.fields().indexOf(field) < 0
    text_format = QgsTextFormat()
    font = QFont()
    font.setPointSize(int(size))
    text_format.setFont(font)
    text_format.setSize(float(size))
    text_format.setColor(_color(color))
    settings.setFormat(text_format)

    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    _refresh(layer)
    return {"success": True, "layer": layer_name, "labels": True, "field": field}


def set_layer_opacity(layer_name, opacity):
    """Opacidade de 0 (transparente) a 1 (opaca)."""
    layer = _layer(layer_name)
    value = max(0.0, min(float(opacity), 1.0))
    layer.setOpacity(value)
    _refresh(layer)
    return {"success": True, "layer": layer_name, "opacity": value}


def add_basemap(source="osm", layer_name=None):
    """Adiciona um mapa de fundo XYZ (precisa de internet)."""
    key = str(source).lower()
    if key not in XYZ_SOURCES:
        raise ValueError(f"Fonte inválida: {source}. Use: {sorted(XYZ_SOURCES)}")
    url, zmax = XYZ_SOURCES[key]
    name = layer_name or key
    uri = f"type=xyz&url={url}&zmin=0&zmax={zmax}"
    layer = QgsRasterLayer(uri, name, "wms")
    if not layer.isValid():
        raise RuntimeError(f"Falha ao carregar o mapa de fundo '{key}'.")
    QgsProject.instance().addMapLayer(layer)
    # Mapa de fundo vai para o fim da lista de camadas
    root = QgsProject.instance().layerTreeRoot()
    node = root.findLayer(layer.id())
    if node is not None:
        clone = node.clone()
        root.insertChildNode(-1, clone)
        root.removeChildNode(node)
    return {"success": True, "layer_name": name, "source": key}


def set_canvas_extent(xmin, ymin, xmax, ymax, crs=None):
    """Move o mapa para a extensão informada."""
    from qgis.utils import iface
    if iface is None:
        raise RuntimeError("Canvas do QGIS indisponível.")
    rect = QgsRectangle(float(xmin), float(ymin), float(xmax), float(ymax))
    canvas = iface.mapCanvas()
    if crs:
        from qgis.core import QgsCoordinateTransform
        source = QgsCoordinateReferenceSystem(crs)
        if not source.isValid():
            raise ValueError(f"CRS inválido: {crs}")
        transform = QgsCoordinateTransform(source, canvas.mapSettings().destinationCrs(),
                                           QgsProject.instance())
        rect = transform.transformBoundingBox(rect)
    canvas.setExtent(rect)
    canvas.refresh()
    return {"success": True, "extent": {"xmin": rect.xMinimum(), "ymin": rect.yMinimum(),
                                        "xmax": rect.xMaximum(), "ymax": rect.yMaximum()}}


def create_print_layout(layout_name, title=None, orientation="landscape"):
    """Cria um layout A4 com um mapa e, se informado, um título."""
    project = QgsProject.instance()
    manager = project.layoutManager()
    if manager.layoutByName(layout_name) is not None:
        raise ValueError(f"Já existe um layout chamado '{layout_name}'.")

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(layout_name)

    page = layout.pageCollection().page(0)
    width, height = (297, 210) if str(orientation).lower() == "landscape" else (210, 297)
    page.setPageSize(QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters))

    top = 10
    if title:
        label = QgsLayoutItemLabel(layout)
        label.setText(title)
        label.setFont(QFont("Arial", 16))
        label.adjustSizeToText()
        label.attemptMove(QgsLayoutPoint(10, 8, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(label)
        top = 22

    map_item = QgsLayoutItemMap(layout)
    map_item.attemptMove(QgsLayoutPoint(10, top, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(width - 20, height - top - 10,
                                         QgsUnitTypes.LayoutMillimeters))
    try:
        from qgis.utils import iface
        if iface is not None:
            map_item.setExtent(iface.mapCanvas().extent())
    except Exception:
        pass
    layout.addLayoutItem(map_item)

    manager.addLayout(layout)
    return {"success": True, "layout_name": layout_name,
            "page": {"width_mm": width, "height_mm": height}}


TOOLS = {
    "set_layer_style": set_layer_style,
    "set_categorized_style": set_categorized_style,
    "set_graduated_style": set_graduated_style,
    "set_labels": set_labels,
    "set_layer_opacity": set_layer_opacity,
    "add_basemap": add_basemap,
    "set_canvas_extent": set_canvas_extent,
    "create_print_layout": create_print_layout,
}
