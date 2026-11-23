# -*- coding: utf-8 -*-
"""
Actions: editing - Edição de feições e campos.

Todas as funções usam startEditing/commitChanges com rollBack em caso de erro,
para não deixar a camada num estado parcial.
"""
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsField
from qgis.PyQt.QtCore import QVariant

FIELD_TYPES = {
    "string": QVariant.String,
    "integer": QVariant.Int,
    "int": QVariant.Int,
    "double": QVariant.Double,
    "float": QVariant.Double,
    "boolean": QVariant.Bool,
    "bool": QVariant.Bool,
    "date": QVariant.Date,
    "datetime": QVariant.DateTime,
    "long": QVariant.LongLong,
}


def _vector(layer_name):
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        raise ValueError(f"Camada não encontrada: {layer_name}")
    layer = layers[0]
    if not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"'{layer_name}' não é uma camada vetorial")
    return layer


def _edit(layer, fn, descricao="QGIS_IA"):
    """Roda fn(layer) dentro de uma sessão de edição, com rollback em erro.

    Se a camada já estava em edição, as mudanças ficam no buffer como UM passo
    de desfazer (Ctrl+Z / 'desfazer' volta a ação inteira) e não são gravadas.
    """
    already = layer.isEditable()
    if not already and not layer.startEditing():
        raise RuntimeError(f"Não consegui abrir edição em '{layer.name()}'.")
    if already:
        layer.beginEditCommand(descricao)
    try:
        result = fn(layer)
        if already:
            layer.endEditCommand()
        elif not layer.commitChanges():
            errors = "; ".join(layer.commitErrors())
            layer.rollBack()
            raise RuntimeError(f"Falha ao gravar as alterações: {errors}")
        return result
    except Exception:
        if already:
            layer.destroyEditCommand()
        else:
            layer.rollBack()
        raise


def add_features(layer_name, features):
    """Adiciona feições. features: [{"geom": "<WKT>", "attrs": {"campo": valor}}]."""
    layer = _vector(layer_name)
    if not features:
        raise ValueError("Informe ao menos uma feição em 'features'.")
    field_names = [f.name() for f in layer.fields()]

    def do(lyr):
        feats = []
        for item in features:
            feat = QgsFeature(lyr.fields())
            wkt = item.get("geom")
            if wkt:
                geom = QgsGeometry.fromWkt(wkt)
                if geom.isNull():
                    raise ValueError(f"Geometria WKT inválida: {wkt}")
                feat.setGeometry(geom)
            attrs = item.get("attrs") or {}
            unknown = set(attrs) - set(field_names)
            if unknown:
                raise ValueError(f"Campos inexistentes em '{layer_name}': {sorted(unknown)}")
            for name, value in attrs.items():
                feat.setAttribute(name, value)
            feats.append(feat)
        if not lyr.addFeatures(feats):
            raise RuntimeError("addFeatures falhou.")
        return len(feats)

    added = _edit(layer, do)
    layer.updateExtents()
    return {"success": True, "added": added, "feature_count": layer.featureCount()}


def update_features(layer_name, expression, attributes):
    """Atualiza atributos das feições que casam com a expressão QGIS."""
    layer = _vector(layer_name)
    if not attributes:
        raise ValueError("Informe 'attributes' com os campos a atualizar.")
    idx = {}
    for name in attributes:
        i = layer.fields().indexOf(name)
        if i < 0:
            raise ValueError(f"Campo não encontrado em '{layer_name}': {name}")
        idx[name] = i

    from qgis.core import QgsFeatureRequest, QgsExpression
    expr = QgsExpression(expression)
    if expr.hasParserError():
        raise ValueError(f"Erro na expressão: {expr.parserErrorString()}")
    request = QgsFeatureRequest().setFilterExpression(expression)
    fids = [f.id() for f in layer.getFeatures(request)]

    def do(lyr):
        for fid in fids:
            for name, value in attributes.items():
                if not lyr.changeAttributeValue(fid, idx[name], value):
                    raise RuntimeError(f"Falha ao atualizar a feição {fid}, campo '{name}'.")
        return len(fids)

    return {"success": True, "updated": _edit(layer, do)}


def delete_features(layer_name, expression):
    """Apaga as feições que casam com a expressão QGIS. [destrutivo]"""
    layer = _vector(layer_name)
    from qgis.core import QgsFeatureRequest, QgsExpression
    expr = QgsExpression(expression)
    if expr.hasParserError():
        raise ValueError(f"Erro na expressão: {expr.parserErrorString()}")
    fids = [f.id() for f in layer.getFeatures(QgsFeatureRequest().setFilterExpression(expression))]
    if not fids:
        return {"success": True, "deleted": 0, "feature_count": layer.featureCount()}

    def do(lyr):
        if not lyr.deleteFeatures(fids):
            raise RuntimeError("deleteFeatures falhou.")
        return len(fids)

    deleted = _edit(layer, do)
    return {"success": True, "deleted": deleted, "feature_count": layer.featureCount()}


def _novo_campo(nome, qtype, length=0, precision=0):
    """QgsField sem o construtor depreciado (QVariant) quando possível."""
    try:
        from qgis.PyQt.QtCore import QMetaType
        mt = {QVariant.String: QMetaType.Type.QString, QVariant.Int: QMetaType.Type.Int,
              QVariant.Double: QMetaType.Type.Double, QVariant.Bool: QMetaType.Type.Bool,
              QVariant.Date: QMetaType.Type.QDate, QVariant.DateTime: QMetaType.Type.QDateTime,
              QVariant.LongLong: QMetaType.Type.LongLong}[qtype]
        return QgsField(nome, mt, len=length, prec=precision)
    except Exception:
        return QgsField(nome, qtype, len=length, prec=precision)


def _campo(layer, field_name):
    """Índice do campo, tolerando maiúsculas/minúsculas."""
    idx = layer.fields().indexOf(field_name)
    if idx < 0:
        idx = layer.fields().lookupField(field_name)
    if idx < 0:
        raise ValueError(f"Campo não encontrado em '{layer.name()}': {field_name}. "
                         f"Campos: {[f.name() for f in layer.fields()]}")
    return idx


def add_field(layer_name, field_name, field_type="String", length=255, precision=0):
    """Cria um campo novo (vazio) na camada.

    Se a camada já está em edição, o campo entra no buffer (dá para desfazer
    com Ctrl+Z ou 'desfazer'); senão é gravado direto no arquivo.
    """
    layer = _vector(layer_name)
    if layer.fields().lookupField(field_name) >= 0:
        raise ValueError(f"O campo '{field_name}' já existe em '{layer_name}'.")
    qtype = FIELD_TYPES.get(str(field_type).lower())
    if qtype is None:
        raise ValueError(f"Tipo inválido: {field_type}. Use: {sorted(set(FIELD_TYPES))}")
    if qtype == QVariant.Double and not precision:
        precision = 3
    if qtype != QVariant.String and length == 255:
        length = 0
    campo = _novo_campo(field_name, qtype, length, precision)
    if layer.isEditable():
        if not layer.addAttribute(campo):
            raise RuntimeError(f"Não consegui criar o campo '{field_name}'.")
    elif not layer.dataProvider().addAttributes([campo]):
        raise RuntimeError(f"O provedor de dados recusou criar o campo '{field_name}'.")
    layer.updateFields()
    return {"success": True, "field": field_name,
            "fields": [f.name() for f in layer.fields()]}


def delete_field(layer_name, field_name):
    """Remove um ou mais campos da camada. [destrutivo]

    field_name pode ser um nome ou uma lista de nomes.
    """
    layer = _vector(layer_name)
    nomes = field_name if isinstance(field_name, (list, tuple)) else [field_name]
    idxs = [_campo(layer, n) for n in nomes]
    removidos = [layer.fields().at(i).name() for i in idxs]
    if layer.isEditable():
        for i in sorted(idxs, reverse=True):
            if not layer.deleteAttribute(i):
                raise RuntimeError(f"Não consegui remover o campo de índice {i}.")
    elif not layer.dataProvider().deleteAttributes(idxs):
        raise RuntimeError(f"O provedor de dados recusou remover {removidos}.")
    layer.updateFields()
    return {"success": True, "removed": removidos,
            "fields": [f.name() for f in layer.fields()]}


def rename_field(layer_name, field_name, new_name):
    """Renomeia um campo."""
    layer = _vector(layer_name)
    idx = _campo(layer, field_name)
    if layer.fields().lookupField(new_name) >= 0:
        raise ValueError(f"Já existe um campo '{new_name}' em '{layer_name}'.")
    antigo = layer.fields().at(idx).name()
    if layer.isEditable():
        ok = layer.renameAttribute(idx, new_name)
    else:
        ok = layer.dataProvider().renameAttributes({idx: new_name})
    if not ok:
        raise RuntimeError(f"O provedor de dados recusou renomear '{antigo}'.")
    layer.updateFields()
    return {"success": True, "renamed": antigo, "new_name": new_name,
            "fields": [f.name() for f in layer.fields()]}


def list_fields(layer_name):
    """Campos da camada com tipo, tamanho e precisão."""
    layer = _vector(layer_name)
    return {"layer": layer.name(), "feature_count": layer.featureCount(),
            "fields": [{"name": f.name(), "type": f.typeName(), "length": f.length(),
                        "precision": f.precision()} for f in layer.fields()]}


# ------------------------------------------------------- seleção / sessão de edição
def select_features(layer_name, expression=None, mode="new"):
    """Seleciona feições por expressão (sem expressão: todas).

    mode: new (substitui), add (soma à seleção), remove (tira da seleção),
    intersect (dentro da seleção atual).
    """
    from qgis.core import QgsExpression, Qgis
    layer = _vector(layer_name)
    if not expression:
        layer.selectAll()
    else:
        expr = QgsExpression(expression)
        if expr.hasParserError():
            raise ValueError(f"Erro na expressão: {expr.parserErrorString()}")
        modos = {"new": Qgis.SelectBehavior.SetSelection, "add": Qgis.SelectBehavior.AddToSelection,
                 "remove": Qgis.SelectBehavior.RemoveFromSelection,
                 "intersect": Qgis.SelectBehavior.IntersectSelection}
        layer.selectByExpression(expression, modos.get(mode, Qgis.SelectBehavior.SetSelection))
    return {"layer": layer.name(), "selected_count": layer.selectedFeatureCount(),
            "feature_count": layer.featureCount()}


def clear_selection(layer_name=None):
    """Limpa a seleção de uma camada (sem nome: de todas)."""
    if layer_name:
        camadas = [_vector(layer_name)]
    else:
        camadas = [l for l in QgsProject.instance().mapLayers().values()
                   if isinstance(l, QgsVectorLayer)]
    for l in camadas:
        l.removeSelection()
    return {"success": True, "layers": [l.name() for l in camadas]}


def invert_selection(layer_name):
    """Inverte a seleção da camada."""
    layer = _vector(layer_name)
    layer.invertSelection()
    return {"layer": layer.name(), "selected_count": layer.selectedFeatureCount()}


def delete_selected_features(layer_name):
    """Apaga as feições selecionadas. [destrutivo]"""
    layer = _vector(layer_name)
    fids = list(layer.selectedFeatureIds())
    if not fids:
        raise ValueError(f"Nenhuma feição selecionada em '{layer.name()}'.")

    def do(lyr):
        if not lyr.deleteFeatures(fids):
            raise RuntimeError("deleteFeatures falhou.")
        return len(fids)

    deleted = _edit(layer, do, f"Apagar {len(fids)} feições selecionadas")
    return {"success": True, "deleted": deleted, "feature_count": layer.featureCount(),
            "pending": layer.isEditable()}


def start_editing(layer_name):
    """Liga o modo de edição da camada (as mudanças ficam pendentes até salvar)."""
    layer = _vector(layer_name)
    if not layer.isEditable() and not layer.startEditing():
        raise RuntimeError(f"A camada '{layer.name()}' não permite edição.")
    try:
        from qgis.utils import iface
        if iface:
            iface.setActiveLayer(layer)
    except Exception:
        pass
    return {"success": True, "layer": layer.name(), "editing": True}


def commit_edits(layer_name=None, stop=True):
    """Salva as edições pendentes (sem nome: de todas as camadas em edição)."""
    camadas = [_vector(layer_name)] if layer_name else [
        l for l in QgsProject.instance().mapLayers().values()
        if isinstance(l, QgsVectorLayer) and l.isEditable()]
    salvas = []
    for l in camadas:
        if not l.isEditable():
            continue
        if not l.commitChanges(stopEditing=bool(stop)):
            raise RuntimeError(f"Falha ao salvar '{l.name()}': {'; '.join(l.commitErrors())}")
        salvas.append(l.name())
    return {"success": True, "saved": salvas}


def rollback_edits(layer_name=None, stop=True):
    """Descarta as edições pendentes (sem nome: de todas). [destrutivo]"""
    camadas = [_vector(layer_name)] if layer_name else [
        l for l in QgsProject.instance().mapLayers().values()
        if isinstance(l, QgsVectorLayer) and l.isEditable()]
    descartadas = []
    for l in camadas:
        if l.isEditable():
            l.rollBack(bool(stop))  # rollBack(deleteBuffer): False mantém a edição ligada
            descartadas.append(l.name())
    return {"success": True, "discarded": descartadas}


def undo_edit(layer_name, steps=1):
    """Desfaz as últimas alterações da camada em edição (como Ctrl+Z)."""
    layer = _vector(layer_name)
    pilha = layer.undoStack()
    if not layer.isEditable() or pilha is None or not pilha.canUndo():
        raise ValueError(f"Nada para desfazer em '{layer.name()}' "
                         "(só dá para desfazer enquanto a camada está em edição).")
    feitos = []
    for _ in range(max(1, int(steps))):
        if not pilha.canUndo():
            break
        feitos.append(pilha.undoText())
        pilha.undo()
    layer.triggerRepaint()
    return {"success": True, "undone": feitos}


def redo_edit(layer_name, steps=1):
    """Refaz alterações desfeitas na camada em edição (como Ctrl+Shift+Z)."""
    layer = _vector(layer_name)
    pilha = layer.undoStack()
    if not layer.isEditable() or pilha is None or not pilha.canRedo():
        raise ValueError(f"Nada para refazer em '{layer.name()}'.")
    feitos = []
    for _ in range(max(1, int(steps))):
        if not pilha.canRedo():
            break
        feitos.append(pilha.redoText())
        pilha.redo()
    layer.triggerRepaint()
    return {"success": True, "redone": feitos}


def count_features(layer_name, expression=None):
    """Conta as feições (todas ou as que casam com a expressão)."""
    from qgis.core import QgsFeatureRequest, QgsExpression
    layer = _vector(layer_name)
    if not expression:
        return {"layer": layer.name(), "count": layer.featureCount(),
                "selected": layer.selectedFeatureCount()}
    expr = QgsExpression(expression)
    if expr.hasParserError():
        raise ValueError(f"Erro na expressão: {expr.parserErrorString()}")
    req = QgsFeatureRequest().setFilterExpression(expression)
    req.setFlags(QgsFeatureRequest.NoGeometry)
    req.setNoAttributes()
    n = sum(1 for _ in layer.getFeatures(req))
    return {"layer": layer.name(), "count": n, "of": layer.featureCount(), "expression": expression}


def edit_status():
    """Camadas em edição e quantas alterações estão pendentes."""
    out = []
    for l in QgsProject.instance().mapLayers().values():
        if isinstance(l, QgsVectorLayer) and l.isEditable():
            buf = l.editBuffer()
            out.append({"layer": l.name(), "modified": l.isModified(),
                        "added": len(buf.addedFeatures()) if buf else 0,
                        "changed": len(buf.changedAttributeValues()) if buf else 0,
                        "deleted": len(buf.deletedFeatureIds()) if buf else 0})
    return {"editing": out}


TOOLS = {
    "add_features": add_features,
    "update_features": update_features,
    "delete_features": delete_features,
    "add_field": add_field,
    "delete_field": delete_field,
    "rename_field": rename_field,
    "list_fields": list_fields,
    "select_features": select_features,
    "clear_selection": clear_selection,
    "invert_selection": invert_selection,
    "delete_selected_features": delete_selected_features,
    "start_editing": start_editing,
    "commit_edits": commit_edits,
    "rollback_edits": rollback_edits,
    "undo_edit": undo_edit,
    "redo_edit": redo_edit,
    "edit_status": edit_status,
    "count_features": count_features,
}
