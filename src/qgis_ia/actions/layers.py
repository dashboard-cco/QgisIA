# -*- coding: utf-8 -*-
"""
Actions: layers - Operações com camadas
"""
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer, QgsFeature, QgsGeometry,
    QgsField, QgsWkbTypes, QgsCoordinateReferenceSystem,
    QgsVectorFileWriter
)
from qgis.PyQt.QtCore import QVariant


def _get_layer(layer_name):
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        raise ValueError(f"Camada não encontrada: {layer_name}")
    return layers[0]


def list_layers():
    """Lista todas as camadas do projeto."""
    return [l.name() for l in QgsProject.instance().mapLayers().values()]


def add_vector_layer(file_path, layer_name=None):
    """Carrega uma camada vetorial de um arquivo (shapefile, geopackage, etc)."""
    name = layer_name or file_path.split("/")[-1].split("\\")[-1]
    layer = QgsVectorLayer(file_path, name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Falha ao carregar camada vetorial: {file_path}")
    QgsProject.instance().addMapLayer(layer)
    return {"layer_name": layer.name(), "feature_count": layer.featureCount()}


def add_raster_layer(file_path, layer_name=None):
    """Carrega uma camada raster de um arquivo (GeoTIFF, etc)."""
    name = layer_name or file_path.split("/")[-1].split("\\")[-1]
    layer = QgsRasterLayer(file_path, name)
    if not layer.isValid():
        raise RuntimeError(f"Falha ao carregar camada raster: {file_path}")
    QgsProject.instance().addMapLayer(layer)
    return {"layer_name": layer.name()}


def remove_layer(layer_name):
    """Remove uma camada do projeto pelo nome."""
    layer = _get_layer(layer_name)
    QgsProject.instance().removeMapLayer(layer.id())
    return {"success": True, "removed": layer_name}


def zoom_to_layer(layer_name):
    """Centraliza/ajusta o mapa na extensão de uma camada."""
    from qgis.utils import iface
    layer = _get_layer(layer_name)
    iface.mapCanvas().setExtent(layer.extent())
    iface.mapCanvas().refresh()
    return {"success": True, "layer": layer_name}


def export_layer(layer_name, output_path, format="GPKG"):
    """
    Exporta/salva uma camada vetorial para arquivo.
    format: 'GPKG' (GeoPackage), 'ESRI Shapefile', 'CSV', 'GeoJSON', etc.
    """
    layer = _get_layer(layer_name)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = format
    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, output_path, QgsProject.instance().transformContext(), options
    )
    if error[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Falha ao exportar camada: {error}")
    return {"success": True, "output_path": output_path}


def duplicate_layer(layer_name, output_name=None, only_selected=False, keep_style=True):
    """Cria uma cópia independente (em memória) da camada, com estilo.

    A cópia não mexe no arquivo original. Para gravá-la em disco use export_layer.
    """
    from qgis.core import QgsFeatureRequest
    layer = _get_layer(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        clone = layer.clone()
    else:
        req = QgsFeatureRequest()
        if only_selected:
            ids = layer.selectedFeatureIds()
            if not ids:
                raise ValueError(f"Nenhuma feição selecionada em '{layer.name()}'.")
            req.setFilterFids(ids)
        clone = layer.materialize(req)
        if keep_style:
            from qgis.core import QgsMapLayerStyle
            estilo = QgsMapLayerStyle()
            estilo.readFromLayer(layer)
            estilo.writeToLayer(clone)
    nomes = {l.name() for l in QgsProject.instance().mapLayers().values()}
    nome = output_name or f"{layer.name()}_copia"
    base, n = nome, 2
    while nome in nomes:
        nome, n = f"{base}_{n}", n + 1
    clone.setName(nome)
    QgsProject.instance().addMapLayer(clone)
    out = {"success": True, "output_layer": nome}
    if isinstance(clone, QgsVectorLayer):
        out["feature_count"] = clone.featureCount()
    return out


def zoom_to_selection(layer_name=None):
    """Aproxima o mapa das feições selecionadas."""
    from qgis.utils import iface
    canvas = iface.mapCanvas()
    if layer_name:
        layer = _get_layer(layer_name)
        if not layer.selectedFeatureCount():
            raise ValueError(f"Nenhuma feição selecionada em '{layer.name()}'.")
        canvas.zoomToSelected(layer)
    else:
        canvas.zoomToSelected()
    canvas.refresh()
    return {"success": True}


def rename_layer(layer_name, new_name):
    """Renomeia uma camada."""
    layer = _get_layer(layer_name)
    layer.setName(new_name)
    return {"success": True, "new_name": new_name}


def select_by_expression(layer_name, expression):
    """Seleciona feições por expressão QGIS."""
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        raise ValueError(f"Camada não encontrada: {layer_name}")
    layer = layers[0]
    layer.selectByExpression(expression)
    return {"selected_count": layer.selectedFeatureCount()}


def create_memory_layer(name, geometry_type="Point", fields=None, features=None):
    """Cria layer temporário em memória."""
    # Mapeia tipo string para QgsWkbTypes
    type_map = {
        "Point": QgsWkbTypes.Point,
        "LineString": QgsWkbTypes.LineString,
        "Polygon": QgsWkbTypes.Polygon,
        "MultiPoint": QgsWkbTypes.MultiPoint,
        "MultiLineString": QgsWkbTypes.MultiLineString,
        "MultiPolygon": QgsWkbTypes.MultiPolygon,
    }
    wkb_type = type_map.get(geometry_type, QgsWkbTypes.Point)

    uri = f"{geometry_type}?crs=epsg:4326"
    layer = QgsVectorLayer(uri, name, "memory")
    if not layer.isValid():
        raise RuntimeError("Falha ao criar layer em memória")

    prov = layer.dataProvider()

    # Campos
    if fields:
        qgs_fields = []
        for f in fields:
            fname = f.get("name", "campo")
            ftype_str = f.get("type", "String").lower()
            type_map_field = {
                "string": QVariant.String,
                "int": QVariant.Int,
                "integer": QVariant.Int,
                "double": QVariant.Double,
                "float": QVariant.Double,
                "bool": QVariant.Bool,
                "boolean": QVariant.Bool,
                "date": QVariant.Date,
            }
            qvar_type = type_map_field.get(ftype_str, QVariant.String)
            qgs_fields.append(QgsField(fname, qvar_type))
        prov.addAttributes(qgs_fields)
        layer.updateFields()

    # Feições
    if features:
        feats = []
        for f in features:
            feat = QgsFeature(layer.fields())
            geom_wkt = f.get("geom")
            if geom_wkt:
                geom = QgsGeometry.fromWkt(geom_wkt)
                if geom.isNull():
                    raise ValueError(f"Geometria WKT inválida: {geom_wkt}")
                feat.setGeometry(geom)
            attrs = f.get("attrs", [])
            feat.setAttributes(attrs)
            feats.append(feat)
        prov.addFeatures(feats)
        layer.updateExtents()

    QgsProject.instance().addMapLayer(layer)
    return {"layer_id": layer.id(), "feature_count": layer.featureCount()}