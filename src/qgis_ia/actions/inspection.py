# -*- coding: utf-8 -*-
"""
Actions: inspect - Ferramentas de leitura/inspeção para o agente (via MCP)
"""
import base64
import os
import tempfile

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer, QgsWkbTypes, QgsFeatureRequest,
    QgsExpression, QgsApplication, QgsMapSettings, QgsMapRendererSequentialJob,
)
from qgis.PyQt.QtCore import QVariant, QSize


def _get_layer(layer_name):
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        raise ValueError(f"Camada não encontrada: {layer_name}")
    return layers[0]


def _py(value):
    """Converte valores do QGIS/Qt em tipos serializáveis em JSON."""
    if value is None:
        return None
    if isinstance(value, QVariant):
        return None if value.isNull() else str(value.value())
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _extent(rect):
    return {"xmin": rect.xMinimum(), "ymin": rect.yMinimum(),
            "xmax": rect.xMaximum(), "ymax": rect.yMaximum()}


def ping():
    return {"pong": True}


def get_project_info():
    from qgis.utils import iface
    project = QgsProject.instance()
    layers = [{"name": l.name(), "type": "vector" if isinstance(l, QgsVectorLayer)
               else "raster" if isinstance(l, QgsRasterLayer) else str(l.type())}
              for l in project.mapLayers().values()]
    info = {
        "title": project.title(),
        "file": project.fileName(),
        "crs": project.crs().authid(),
        "layer_count": len(layers),
        "layers": layers,
    }
    if iface is not None:
        info["canvas_extent"] = _extent(iface.mapCanvas().extent())
    return info


def get_layer_info(layer_name):
    layer = _get_layer(layer_name)
    info = {
        "name": layer.name(),
        "id": layer.id(),
        "crs": layer.crs().authid(),
        "source": layer.source(),
        "extent": _extent(layer.extent()),
    }
    if isinstance(layer, QgsVectorLayer):
        info.update({
            "type": "vector",
            "geometry_type": QgsWkbTypes.displayString(layer.wkbType()),
            "feature_count": layer.featureCount(),
            "selected_count": layer.selectedFeatureCount(),
            "filter": layer.subsetString(),
            "is_editing": layer.isEditable(),
            "fields": [{"name": f.name(), "type": f.typeName(),
                        "length": f.length(), "precision": f.precision()}
                       for f in layer.fields()],
        })
    elif isinstance(layer, QgsRasterLayer):
        info.update({
            "type": "raster",
            "width": layer.width(),
            "height": layer.height(),
            "band_count": layer.bandCount(),
        })
    else:
        info["type"] = str(layer.type())
    return info


def get_features(layer_name, limit=20, expression=None, fields=None, include_geometry=False):
    """Amostra de feições com atributos. limit é limitado a 500."""
    layer = _get_layer(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"'{layer_name}' não é uma camada vetorial")
    limit = max(1, min(int(limit), 500))

    request = QgsFeatureRequest().setLimit(limit)
    if expression:
        expr = QgsExpression(expression)
        if expr.hasParserError():
            raise ValueError(f"Erro na expressão: {expr.parserErrorString()}")
        request.setFilterExpression(expression)
    if not include_geometry:
        request.setFlags(QgsFeatureRequest.NoGeometry)

    names = fields or [f.name() for f in layer.fields()]
    rows = []
    for feat in layer.getFeatures(request):
        row = {"fid": feat.id(), "attributes": {n: _py(feat[n]) for n in names}}
        if include_geometry and feat.hasGeometry():
            wkt = feat.geometry().asWkt(6)
            row["geometry_wkt"] = wkt if len(wkt) <= 500 else wkt[:500] + "..."
        rows.append(row)
    return {"layer": layer_name, "returned": len(rows), "features": rows}


def get_algorithm_help(algorithm_id):
    """Parâmetros e saídas de um algoritmo de Processing (para usar com run_algorithm)."""
    alg = QgsApplication.processingRegistry().algorithmById(algorithm_id)
    if alg is None:
        raise ValueError(f"Algoritmo não encontrado: {algorithm_id}. Use list_algorithms.")
    params = []
    for p in alg.parameterDefinitions():
        params.append({
            "name": p.name(),
            "description": p.description(),
            "type": p.type(),
            "default": _py(p.defaultValue()),
            "optional": bool(p.flags() & p.FlagOptional),
        })
    outputs = [{"name": o.name(), "description": o.description(), "type": o.type()}
               for o in alg.outputDefinitions()]
    return {"id": alg.id(), "name": alg.displayName(),
            "parameters": params, "outputs": outputs}


def render_map(width=1200, height=800):
    """Renderiza o mapa atual como PNG e devolve em base64."""
    from qgis.utils import iface
    if iface is None:
        raise RuntimeError("Canvas do QGIS indisponível.")
    width = max(100, min(int(width), 4000))
    height = max(100, min(int(height), 4000))

    settings = QgsMapSettings(iface.mapCanvas().mapSettings())
    settings.setOutputSize(QSize(width, height))
    job = QgsMapRendererSequentialJob(settings)
    job.start()
    job.waitForFinished()
    image = job.renderedImage()

    fd, path = tempfile.mkstemp(suffix=".png", prefix="qgis_ia_")
    os.close(fd)
    try:
        if not image.save(path, "PNG"):
            raise RuntimeError("Falha ao salvar a imagem renderizada.")
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return {"mime": "image/png", "width": width, "height": height, "data_base64": data}


def set_layer_visibility(layer_name=None, visible=True):
    """Liga/desliga a camada no mapa. Sem layer_name: todas as camadas."""
    if not layer_name:
        root = QgsProject.instance().layerTreeRoot()
        nodes = root.findLayers()
        for node in nodes:
            node.setItemVisibilityChecked(bool(visible))
        for grupo in root.findGroups(True):
            grupo.setItemVisibilityChecked(True)
        return {"success": True, "layers": len(nodes), "visible": bool(visible)}
    layer = _get_layer(layer_name)
    node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
    if node is None:
        raise RuntimeError(f"Camada '{layer_name}' não está na árvore de camadas.")
    node.setItemVisibilityChecked(bool(visible))
    return {"success": True, "layer": layer_name, "visible": bool(visible)}


def save_project(path=None):
    project = QgsProject.instance()
    ok = project.write(path) if path else project.write()
    if not ok:
        raise RuntimeError("Falha ao salvar o projeto (informe 'path' se ele ainda não tem arquivo).")
    return {"success": True, "file": project.fileName()}


# Registro usado pelo servidor socket
TOOLS = {
    "ping": ping,
    "get_project_info": get_project_info,
    "get_layer_info": get_layer_info,
    "get_features": get_features,
    "get_algorithm_help": get_algorithm_help,
    "render_map": render_map,
    "set_layer_visibility": set_layer_visibility,
    "save_project": save_project,
}


def get_field_statistics(layer_name, field):
    """Estatísticas de um campo numérico: contagem, nulos, min, max, média, soma, mediana, desvio."""
    from qgis.core import QgsStatisticalSummary
    layer = _get_layer(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"'{layer_name}' não é uma camada vetorial")
    idx = layer.fields().indexOf(field)
    if idx < 0:
        raise ValueError(f"Campo não encontrado em '{layer_name}': {field}")

    stats = QgsStatisticalSummary()
    stats.calculate([f[field] for f in layer.getFeatures()
                     if isinstance(f[field], (int, float))])
    return {
        "layer": layer_name, "field": field,
        "count": stats.count(), "null_count": layer.featureCount() - stats.count(),
        "min": stats.min(), "max": stats.max(), "mean": stats.mean(),
        "sum": stats.sum(), "median": stats.median(), "stdev": stats.stDev(),
    }


def get_unique_values(layer_name, field, limit=100):
    """Valores distintos de um campo (máx. 1000). Use antes de categorizar ou filtrar."""
    layer = _get_layer(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"'{layer_name}' não é uma camada vetorial")
    idx = layer.fields().indexOf(field)
    if idx < 0:
        raise ValueError(f"Campo não encontrado em '{layer_name}': {field}")
    limit = max(1, min(int(limit), 1000))
    values = layer.uniqueValues(idx, limit + 1)
    truncated = len(values) > limit
    out = [_py(v) for v in list(values)[:limit]]
    return {"layer": layer_name, "field": field, "returned": len(out),
            "truncated": truncated, "values": out}


def get_raster_stats(layer_name, band=1):
    """Estatísticas de uma banda raster: min, max, média, desvio."""
    layer = _get_layer(layer_name)
    if not isinstance(layer, QgsRasterLayer):
        raise ValueError(f"'{layer_name}' não é uma camada raster")
    band = int(band)
    if band < 1 or band > layer.bandCount():
        raise ValueError(f"Banda {band} fora do intervalo (1..{layer.bandCount()}).")
    provider = layer.dataProvider()
    stats = provider.bandStatistics(band)
    return {
        "layer": layer_name, "band": band, "band_name": layer.bandName(band),
        "min": stats.minimumValue, "max": stats.maximumValue,
        "mean": stats.mean, "stdev": stats.stdDev,
        "no_data": provider.sourceNoDataValue(band),
        "width": layer.width(), "height": layer.height(),
    }


TOOLS.update({
    "get_field_statistics": get_field_statistics,
    "get_unique_values": get_unique_values,
    "get_raster_stats": get_raster_stats,
})
