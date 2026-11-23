# -*- coding: utf-8 -*-
"""
Actions: processing - Algoritmos de processamento (buffer, intersecção, etc)
"""
from qgis.core import QgsProject, QgsProcessingFeedback, QgsProcessingContext
import processing


def _get_layer(layer_name):
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        raise ValueError(f"Camada não encontrada: {layer_name}")
    return layers[0]


def run_buffer(input_layer, distance, segments=5, end_cap_style=0, join_style=0, miter_limit=2, output_name="buffer_result"):
    """Buffer via processing (nativo QGIS)."""
    layer = _get_layer(input_layer)

    params = {
        "INPUT": layer,
        "DISTANCE": distance,
        "SEGMENTS": segments,
        "END_CAP_STYLE": end_cap_style,  # 0=Round, 1=Flat, 2=Square
        "JOIN_STYLE": join_style,        # 0=Round, 1=Miter, 2=Bevel
        "MITER_LIMIT": miter_limit,
        "DISSOLVE": False,
        "OUTPUT": "memory:" + output_name
    }

    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:buffer", params, context=context, feedback=feedback)

    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_intersection(input_layer, overlay_layer, output_name="intersecao", input_fields=None, overlay_fields=None, overlay_fields_prefix=""):
    """Intersecção entre duas camadas."""
    in_layer = _get_layer(input_layer)
    ov_layer = _get_layer(overlay_layer)

    params = {
        "INPUT": in_layer,
        "OVERLAY": ov_layer,
        "INPUT_FIELDS": input_fields or [],
        "OVERLAY_FIELDS": overlay_fields or [],
        "OVERLAY_FIELDS_PREFIX": overlay_fields_prefix,
        "OUTPUT": "memory:" + output_name
    }

    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:intersection", params, context=context, feedback=feedback)

    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_difference(input_layer, overlay_layer, output_name="diferenca"):
    """Diferença (A - B)."""
    in_layer = _get_layer(input_layer)
    ov_layer = _get_layer(overlay_layer)

    params = {
        "INPUT": in_layer,
        "OVERLAY": ov_layer,
        "OUTPUT": "memory:" + output_name
    }

    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:difference", params, context=context, feedback=feedback)

    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_union(input_layer, overlay_layer, output_name="uniao"):
    """União de duas camadas."""
    in_layer = _get_layer(input_layer)
    ov_layer = _get_layer(overlay_layer)

    params = {
        "INPUT": in_layer,
        "OVERLAY": ov_layer,
        "OUTPUT": "memory:" + output_name
    }

    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:union", params, context=context, feedback=feedback)

    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_dissolve(input_layer, field=None, output_name="dissolvido"):
    """Dissolve (agrega feições)."""
    layer = _get_layer(input_layer)

    params = {
        "INPUT": layer,
        "FIELD": field or [],
        "OUTPUT": "memory:" + output_name
    }

    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:dissolve", params, context=context, feedback=feedback)

    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_clip(input_layer, overlay_layer, output_name="clip_result"):
    """Recorta uma camada pelos limites de outra (native:clip)."""
    in_layer = _get_layer(input_layer)
    ov_layer = _get_layer(overlay_layer)

    params = {
        "INPUT": in_layer,
        "OVERLAY": ov_layer,
        "OUTPUT": "memory:" + output_name
    }
    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:clip", params, context=context, feedback=feedback)

    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_merge_layers(input_layers, output_name="merge_result"):
    """Mescla (une) várias camadas vetoriais em uma só (native:mergevectorlayers)."""
    layers_objs = [_get_layer(n) for n in input_layers]

    params = {
        "LAYERS": layers_objs,
        "OUTPUT": "memory:" + output_name
    }
    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:mergevectorlayers", params, context=context, feedback=feedback)

    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_reproject(input_layer, target_crs, output_name="reprojetado"):
    """Reprojeta uma camada para outro CRS (native:reprojectlayer). target_crs ex: 'EPSG:31983'."""
    layer = _get_layer(input_layer)

    params = {
        "INPUT": layer,
        "TARGET_CRS": target_crs,
        "OUTPUT": "memory:" + output_name
    }
    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:reprojectlayer", params, context=context, feedback=feedback)

    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_centroids(input_layer, output_name="centroides"):
    """Gera pontos de centroide das feições (native:centroids)."""
    layer = _get_layer(input_layer)
    params = {"INPUT": layer, "OUTPUT": "memory:" + output_name}
    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:centroids", params, context=context, feedback=feedback)
    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_convex_hull(input_layer, output_name="convex_hull"):
    """Gera o fecho convexo das feições (native:convexhull)."""
    layer = _get_layer(input_layer)
    params = {"INPUT": layer, "OUTPUT": "memory:" + output_name}
    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:convexhull", params, context=context, feedback=feedback)
    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_simplify(input_layer, tolerance=1.0, output_name="simplificado"):
    """Simplifica geometrias (native:simplifygeometries)."""
    layer = _get_layer(input_layer)
    params = {
        "INPUT": layer,
        "METHOD": 0,
        "TOLERANCE": tolerance,
        "OUTPUT": "memory:" + output_name
    }
    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:simplifygeometries", params, context=context, feedback=feedback)
    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_spatial_join(input_layer, join_layer, output_name="join_result", join_type="one-to-many"):
    """Junta atributos por localização espacial (native:joinattributesbylocation)."""
    in_layer = _get_layer(input_layer)
    jn_layer = _get_layer(join_layer)
    discard = 1 if join_type == "one-to-one" else 0
    params = {
        "INPUT": in_layer,
        "JOIN": jn_layer,
        "PREDICATE": [0],  # intersects
        "JOIN_FIELDS": [],
        "METHOD": discard,
        "DISCARD_NONMATCHING": False,
        "OUTPUT": "memory:" + output_name
    }
    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run("native:joinattributesbylocation", params, context=context, feedback=feedback)
    out_layer = result["OUTPUT"]
    out_layer.setName(output_name)
    QgsProject.instance().addMapLayer(out_layer)
    return {"output_layer": output_name, "feature_count": out_layer.featureCount()}


def run_algorithm(algorithm_id, params, output_name=None):
    """
    Executa QUALQUER algoritmo de Processing do QGIS pelo seu ID
    (ex: "native:extractbyattribute", "qgis:fieldcalculator", "gdal:cliprasterbymasklayer").
    Use list_algorithms para descobrir IDs e use_layer_name=True em params
    onde o algoritmo pede uma camada (o nome exato da camada no projeto).

    params: dict no formato esperado pelo algoritmo (chaves maiúsculas, como na
            caixa de ferramentas do QGIS). Nomes de camada em params são resolvidos
            automaticamente para o objeto de camada do projeto.
    output_name: se informado, o resultado em params['OUTPUT'] (ou primeira saída
                 encontrada) é adicionado ao projeto com este nome.
    """
    resolved_params = {}
    for key, value in (params or {}).items():
        if isinstance(value, str):
            matches = QgsProject.instance().mapLayersByName(value)
            resolved_params[key] = matches[0] if matches else value
        else:
            resolved_params[key] = value

    if "OUTPUT" not in resolved_params and output_name:
        resolved_params["OUTPUT"] = "memory:" + output_name

    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    result = processing.run(algorithm_id, resolved_params, context=context, feedback=feedback)

    if output_name and "OUTPUT" in result:
        out_layer = result["OUTPUT"]
        if hasattr(out_layer, "setName"):
            out_layer.setName(output_name)
            QgsProject.instance().addMapLayer(out_layer)
            return {"output_layer": output_name, "feature_count": out_layer.featureCount()}

    # Resultado não é uma camada (ex: estatísticas, arquivo exportado) - retorna bruto
    safe_result = {}
    for k, v in result.items():
        safe_result[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
    return safe_result


def list_algorithms(search_text=""):
    """
    Lista IDs de algoritmos de Processing disponíveis no QGIS, opcionalmente
    filtrando por texto (ex: 'buffer', 'clip', 'raster'). Use para descobrir
    o algorithm_id certo antes de chamar run_algorithm.
    """
    from qgis.core import QgsApplication
    registry = QgsApplication.processingRegistry()
    search_lower = (search_text or "").lower()
    results = []
    for alg in registry.algorithms():
        alg_id = alg.id()
        alg_name = alg.displayName()
        if search_lower and search_lower not in alg_id.lower() and search_lower not in alg_name.lower():
            continue
        results.append({"id": alg_id, "name": alg_name})
    return results[:200]