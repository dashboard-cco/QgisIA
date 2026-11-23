# -*- coding: utf-8 -*-
"""
Actions: expressions - Calculadora de campos, filtros
"""
from qgis.core import QgsProject, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
from qgis.PyQt.QtCore import QVariant


def _get_layer(layer_name):
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        raise ValueError(f"Camada não encontrada: {layer_name}")
    return layers[0]


def calculate_field(layer_name, field_name, expression, field_type="String", field_length=255, field_precision=0, only_selected=False):
    """Calcula/atualiza campo via expressão QGIS."""
    layer = _get_layer(layer_name)

    # Tipos suportados
    type_map = {
        "String": QVariant.String,
        "Int": QVariant.Int,
        "Integer": QVariant.Int,
        "Double": QVariant.Double,
        "Float": QVariant.Double,
        "Bool": QVariant.Bool,
        "Boolean": QVariant.Bool,
        "Date": QVariant.Date,
    }
    qvar_type = type_map.get(field_type, QVariant.String)

    # Adiciona campo se não existe
    if field_name not in [f.name() for f in layer.fields()]:
        from qgis.core import QgsField
        layer.dataProvider().addAttributes([QgsField(field_name, qvar_type, len=field_length, prec=field_precision)])
        layer.updateFields()

    # Prepara contexto de expressão
    context = QgsExpressionContext()
    context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))

    expr = QgsExpression(expression)
    if expr.hasParserError():
        raise ValueError(f"Erro na expressão: {expr.parserErrorString()}")

    # Edita
    layer.startEditing()
    try:
        features = layer.selectedFeatures() if only_selected else layer.getFeatures()
        count = 0
        for feat in features:
            context.setFeature(feat)
            value = expr.evaluate(context)
            if expr.hasEvalError():
                raise RuntimeError(f"Erro ao avaliar: {expr.evalErrorString()}")
            layer.changeAttributeValue(feat.id(), layer.fields().indexOf(field_name), value)
            count += 1
        layer.commitChanges()
    except Exception:
        layer.rollBack()
        raise

    return {"updated_features": count, "field_name": field_name}


def filter_layer(layer_name, expression):
    """Aplica filtro (subset string) na camada."""
    layer = _get_layer(layer_name)
    layer.setSubsetString(expression)
    return {"success": True, "filter": expression, "feature_count": layer.featureCount()}


def clear_filter(layer_name):
    """Remove filtro da camada."""
    layer = _get_layer(layer_name)
    layer.setSubsetString("")
    return {"success": True, "feature_count": layer.featureCount()}