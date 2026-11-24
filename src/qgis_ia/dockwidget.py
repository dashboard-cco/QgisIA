# -*- coding: utf-8 -*-
"""
Dock Widget principal - Interface de chat
"""
import json
import os
import sys
from qgis.PyQt.QtWidgets import (
    QDockWidget, QVBoxLayout, QWidget, QTextEdit, QLineEdit,
    QPushButton, QHBoxLayout, QLabel, QComboBox, QMessageBox,
    QGroupBox, QCheckBox, QApplication
)
from qgis.PyQt.QtCore import Qt, pyqtSignal, QThread, QObject, QTimer
from qgis.core import QgsProject, QgsMessageLog, QgsVectorLayer, QgsWkbTypes

from .executor import execute_plan, DESTRUTIVAS
from . import comandos


def _resumo(result):
    """Resultado de uma ação em uma linha legível."""
    if not isinstance(result, dict):
        if isinstance(result, list):
            return ", ".join(map(str, result)) or "(vazio)"
        return str(result) if result is not None else "OK"
    r = result
    if "fields" in r and r.get("fields") and isinstance(r["fields"][0], dict):
        return (f"Campos de '{r.get('layer')}' ({r.get('feature_count')} feições): "
                + ", ".join(f"{f['name']} ({f['type']})" for f in r["fields"]))
    partes = []
    rotulos = [("output_layer", "camada criada"), ("field", "campo criado"), ("removed", "removido"),
               ("renamed", "renomeado"), ("new_name", "novo nome"), ("selected_count", "selecionadas"),
               ("count", "feições"), ("updated_features", "atualizadas"), ("updated", "atualizadas"),
               ("added", "adicionadas"), ("deleted", "apagadas"), ("saved", "salvas"),
               ("discarded", "descartadas"), ("undone", "desfeito"), ("redone", "refeito"),
               ("feature_count", "total de feições"), ("editing", "em edição")]
    for chave, rot in rotulos:
        if chave in r and r[chave] not in (None, True):
            v = r[chave]
            if isinstance(v, list):
                v = ", ".join(json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else str(x)
                              for x in v) or "nenhuma"
            partes.append(f"{rot}: {v}")
    if r.get("pending"):
        partes.append("pendente até salvar a edição")
    return "; ".join(partes) or "OK"


class WorkerSignals(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)


class AiWorker(QThread):
    """Thread só para a chamada de rede à IA (não trava a UI do QGIS).

    A execução do plano NÃO acontece aqui: a API do QGIS (projeto, camadas,
    iface) só é segura no thread principal. Quem executa é on_worker_finished.
    """
    def __init__(self, claude_client, prompt, context_layers):
        super().__init__()
        self.claude_client = claude_client
        self.prompt = prompt
        self.context_layers = context_layers
        self.signals = WorkerSignals()

    def run(self):
        try:
            # Pede plano à IA (Anthropic → OpenRouter → Mock)
            plan = self.claude_client.ask_claude(self.prompt, self.context_layers)
            self.signals.progress.emit(f"Plano recebido: {len(plan.get('steps', []))} passo(s)")
            self.signals.finished.emit({"plan": plan})
        except Exception as e:
            import traceback
            self.signals.error.emit(traceback.format_exc())


class QgisIaDockWidget(QDockWidget):
    closed = pyqtSignal()

    def __init__(self, iface, claude_client, mcp_server=None):
        super().__init__("QGIS_IA", iface.mainWindow())
        self.iface = iface
        self.claude_client = claude_client
        self.mcp_server = mcp_server
        self.worker = None
        self.setup_ui()
        if self.mcp_server is not None:
            self.mcp_server.status_changed.connect(self.on_mcp_status)
            self.mcp_server.log.connect(self.on_mcp_log)
            self.on_mcp_status(
                f"Servidor ativo na porta {self.mcp_server.port}."
                if self.mcp_server.is_running() else "Servidor parado."
            )

    def setup_ui(self):
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(380)

        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("🤖"))
        header.addWidget(QLabel("<b>QGIS_IA</b>"))
        header.addStretch()
        layout.addLayout(header)

        # Regra 1: os comandos valem para a camada selecionada no painel de Camadas
        self.ativa_label = QLabel()
        self.ativa_label.setWordWrap(True)
        layout.addWidget(self.ativa_label)
        self._atualizar_ativa()
        try:
            self.iface.currentLayerChanged.connect(self._atualizar_ativa)
        except Exception:
            pass

        # Lista de camadas (contexto)
        self.layer_combo = QComboBox()
        self.layer_combo.addItem("Todas as camadas")
        self.refresh_layers()
        layout.addWidget(QLabel("Contexto:"))
        layout.addWidget(self.layer_combo)

        # Chat area
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setStyleSheet("""
            QTextEdit { background: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace; font-size: 12px; }
        """)
        layout.addWidget(self.chat_log)

        # Input area
        input_layout = QHBoxLayout()
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText('Ex: pintar de azul · criar campo "area" tipo decimal · ajuda')
        self.prompt_input.returnPressed.connect(self.send_prompt)
        input_layout.addWidget(self.prompt_input)

        self.voz_btn = QPushButton("🎤")
        self.voz_btn.setToolTip("Comando por voz: abre a digitação por voz do Windows (Win+H).\n"
                                "Fale o comando; ele é enviado quando você parar de falar.\n"
                                "Para campos, diga 'aspas': criar campo aspas área aspas.")
        self.voz_btn.setFixedWidth(36)
        self.voz_btn.setCheckable(True)
        self.voz_btn.toggled.connect(self.on_voz)
        input_layout.addWidget(self.voz_btn)

        self.send_btn = QPushButton("Enviar")
        self.send_btn.clicked.connect(self.send_prompt)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        # Voz: envia quando o texto ditado para de mudar
        self._voz_timer = QTimer(self)
        self._voz_timer.setSingleShot(True)
        self._voz_timer.setInterval(2500)
        self._voz_timer.timeout.connect(self._voz_enviar)
        self._voz_limite = QTimer(self)
        self._voz_limite.setSingleShot(True)
        self._voz_limite.setInterval(30000)
        self._voz_limite.timeout.connect(lambda: self.voz_btn.setChecked(False))
        self.prompt_input.textChanged.connect(self._voz_texto)

        # Status
        self.status_label = QLabel("Pronto. Digite um comando acima.")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        # Conexões: MCP liga sozinho; a IA do chat usa Claude e, se falhar, OpenRouter
        conn_row = QHBoxLayout()
        self.conexao_label = QLabel()
        self.conexao_label.setStyleSheet("color: #888; font-size: 11px;")
        self.conexao_label.setWordWrap(True)
        conn_row.addWidget(self.conexao_label, 1)
        self.avancado_btn = QPushButton("⚙")
        self.avancado_btn.setToolTip("Mostrar/ocultar opções avançadas do servidor MCP")
        self.avancado_btn.setFixedWidth(28)
        self.avancado_btn.setCheckable(True)
        conn_row.addWidget(self.avancado_btn)
        layout.addLayout(conn_row)

        # Servidor MCP (permite o Claude Desktop / Claude Code controlarem o QGIS)
        if self.mcp_server is not None:
            box = QGroupBox("Servidor MCP (Claude Desktop / Claude Code)")
            box.setVisible(False)
            self.avancado_btn.toggled.connect(box.setVisible)
            box_layout = QVBoxLayout(box)

            self.mcp_btn = QPushButton("Iniciar servidor")
            self.mcp_btn.clicked.connect(self.toggle_mcp)
            box_layout.addWidget(self.mcp_btn)

            self.mcp_readonly = QCheckBox("Somente leitura (bloqueia ações que gravam ou removem)")
            self.mcp_readonly.toggled.connect(self.mcp_server.set_read_only)
            box_layout.addWidget(self.mcp_readonly)

            self.mcp_allow_code = QCheckBox("Permitir execução de código Python (avançado)")
            self.mcp_allow_code.setToolTip(
                "Libera a ferramenta execute_code. Com ela, quem estiver conectado "
                "pode rodar qualquer PyQGIS, inclusive ler e apagar arquivos.")
            self.mcp_allow_code.toggled.connect(self.on_allow_code)
            box_layout.addWidget(self.mcp_allow_code)

            copy_row = QHBoxLayout()
            code_btn = QPushButton("Copiar comando (Claude Code)")
            code_btn.clicked.connect(self.copy_claude_code_command)
            desktop_btn = QPushButton("Copiar JSON (Claude Desktop)")
            desktop_btn.clicked.connect(self.copy_claude_desktop_json)
            copy_row.addWidget(code_btn)
            copy_row.addWidget(desktop_btn)
            box_layout.addLayout(copy_row)

            self.mcp_status = QLabel("Servidor parado.")
            self.mcp_status.setStyleSheet("color: #888; font-size: 11px;")
            box_layout.addWidget(self.mcp_status)
            layout.addWidget(box)

        else:
            self.avancado_btn.setVisible(False)

        self.setWidget(main_widget)
        self._atualizar_conexao()

    # --- Servidor MCP ----------------------------------------------------
    def toggle_mcp(self):
        if self.mcp_server.is_running():
            self.mcp_server.stop()
        else:
            self.mcp_server.start()

    def on_mcp_status(self, msg):
        self.mcp_status.setText(msg)
        self.mcp_btn.setText("Parar servidor" if self.mcp_server.is_running() else "Iniciar servidor")
        self._atualizar_conexao()

    def on_mcp_log(self, msg):
        # Vai para o log do QGIS (Exibir > Painéis > Mensagens de log), não polui o chat
        QgsMessageLog.logMessage(msg, "QGIS_IA")

    def _atualizar_conexao(self, provedor=None):
        partes = []
        if self.mcp_server is not None:
            if self.mcp_server.is_running():
                partes.append(f"🟢 Claude Code (MCP) porta {self.mcp_server.port}")
            else:
                partes.append("🔴 MCP parado")
        cli = self.claude_client
        if provedor:
            partes.append(f"IA do chat: {provedor}")
        elif cli is not None:
            tem_a = getattr(cli, "anthropic_client", None) is not None
            tem_o = getattr(cli, "openrouter_client", None) is not None
            if tem_a and tem_o:
                partes.append("IA do chat: Claude (reserva: OpenRouter)")
            elif tem_a:
                partes.append("IA do chat: Claude")
            elif tem_o:
                partes.append("IA do chat: OpenRouter")
            else:
                partes.append("IA do chat: sem chave")
        self.conexao_label.setText(" · ".join(partes))

    # --- Voz ---------------------------------------------------------------
    def on_voz(self, ligado):
        if not ligado:
            self._voz_timer.stop()
            self._voz_limite.stop()
            self.voz_btn.setStyleSheet("")
            if self.status_label.text().startswith("🎤"):
                self.status_label.setText("Pronto.")
            return
        if os.name != "nt":
            QMessageBox.information(self, "QGIS_IA", "Comando por voz usa a digitação por voz do Windows.")
            self.voz_btn.setChecked(False)
            return
        self.voz_btn.setStyleSheet("background: #c62828; color: white;")
        self.prompt_input.clear()
        self.prompt_input.setFocus()
        self.status_label.setText("🎤 Fale o comando… (envia quando você parar de falar)")
        self._voz_limite.start()
        QTimer.singleShot(200, self._abrir_ditado)

    def _abrir_ditado(self):
        """Win+H: digitação por voz do Windows, escrevendo na caixa de comando."""
        try:
            import ctypes
            u = ctypes.windll.user32
            VK_LWIN, VK_H, UP = 0x5B, 0x48, 0x0002
            u.keybd_event(VK_LWIN, 0, 0, 0)
            u.keybd_event(VK_H, 0, 0, 0)
            u.keybd_event(VK_H, 0, UP, 0)
            u.keybd_event(VK_LWIN, 0, UP, 0)
        except Exception as e:
            self.append_chat("⚠️", f"Não consegui abrir a digitação por voz do Windows: {e}")
            self.voz_btn.setChecked(False)

    def _voz_texto(self, texto):
        if self.voz_btn.isChecked() and texto.strip():
            self._voz_timer.start()  # reinicia a contagem a cada palavra nova
            self._voz_limite.start()

    def _voz_enviar(self):
        if self.voz_btn.isChecked() and self.prompt_input.text().strip():
            self.voz_btn.setChecked(False)
            self.send_prompt()

    def on_allow_code(self, checked):
        if checked:
            answer = QMessageBox.warning(
                self, "QGIS_IA",
                "Isto libera a execução de código Python arbitrário no QGIS.\n\n"
                "Quem estiver conectado ao servidor poderá fazer qualquer coisa que o "
                "QGIS faz, inclusive ler e apagar arquivos do seu computador.\n\n"
                "Deseja continuar?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                self.mcp_allow_code.setChecked(False)
                return
        self.mcp_server.set_allow_code(checked)

    def copy_claude_code_command(self):
        python = self.mcp_server.python_path()
        path = self.mcp_server.bridge_path()
        cmd = f'claude mcp add -s user qgis-ia -- "{python}" "{path}"'
        QApplication.clipboard().setText(cmd)
        self.mcp_status.setText("Comando copiado. Cole no terminal e tecle Enter.")

    def copy_claude_desktop_json(self):
        python = self.mcp_server.python_path()
        path = self.mcp_server.bridge_path()
        cfg = {"mcpServers": {"qgis-ia": {"command": python, "args": [path]}}}
        QApplication.clipboard().setText(json.dumps(cfg, indent=2, ensure_ascii=False))
        self.mcp_status.setText("JSON copiado. Cole no claude_desktop_config.json.")

    def refresh_layers(self):
        self.layer_combo.clear()
        self.layer_combo.addItem("Todas as camadas")
        for layer in QgsProject.instance().mapLayers().values():
            self.layer_combo.addItem(layer.name(), layer.id())

    def get_context_layers(self):
        if self.layer_combo.currentIndex() == 0:
            return [l.name() for l in QgsProject.instance().mapLayers().values()]
        return [self.layer_combo.currentText()]

    def _camada_ativa(self):
        """Camada selecionada no painel de Camadas do QGIS (os comandos só valem para ela)."""
        layer = self.iface.activeLayer()
        return layer.name() if layer else None

    def _atualizar_ativa(self, *_):
        nome = self._camada_ativa()
        if nome:
            self.ativa_label.setText(f"Camada selecionada: <b>{nome}</b>")
            self.ativa_label.setStyleSheet("color: #2e7d32;")
        else:
            self.ativa_label.setText("Nenhuma camada selecionada: clique em uma no painel de Camadas.")
            self.ativa_label.setStyleSheet("color: #c62828;")

    def _contexto_comandos(self):
        """Nomes de camadas e campos para o interpretador de comandos simples."""
        camadas, campos = [], {}
        for l in QgsProject.instance().mapLayers().values():
            camadas.append(l.name())
            if isinstance(l, QgsVectorLayer):
                campos[l.name()] = [f.name() for f in l.fields()]
        layouts = [l.name() for l in QgsProject.instance().layoutManager().printLayouts()]
        return {"camadas": camadas, "campos": campos, "ativa": self._camada_ativa(),
                "layouts": layouts}

    def _contexto_ia(self):
        """Texto com camadas, tipos, campos e estado de edição para a IA."""
        ativa = self._camada_ativa()
        nomes = set(self.get_context_layers())
        linhas = [f"Camada ativa: {ativa or 'nenhuma'}", "Camadas:"]
        for l in QgsProject.instance().mapLayers().values():
            if l.name() not in nomes:
                continue
            if isinstance(l, QgsVectorLayer):
                geom = QgsWkbTypes.displayString(l.wkbType())
                extra = []
                if l.isEditable():
                    extra.append("em edição")
                if l.selectedFeatureCount():
                    extra.append(f"{l.selectedFeatureCount()} selecionadas")
                if l.subsetString():
                    extra.append(f"filtro: {l.subsetString()}")
                campos = ", ".join(f"{f.name()} ({f.typeName()})" for f in list(l.fields())[:60])
                linhas.append(f"- {l.name()} [{geom}, {l.featureCount()} feições, {l.crs().authid()}"
                              f"{', ' + ', '.join(extra) if extra else ''}] campos: {campos}")
            else:
                linhas.append(f"- {l.name()} [raster, {l.crs().authid()}]")
        layouts = [l.name() for l in QgsProject.instance().layoutManager().printLayouts()]
        linhas.append("Layouts: " + (", ".join(layouts) if layouts else "nenhum"))
        return "\n".join(linhas)

    def _confirmar(self, plano):
        """Pede confirmação se o plano tem passo destrutivo."""
        passos = [s.get("action") for s in plano.get("steps", []) if s.get("action") in DESTRUTIVAS]
        if not passos and not plano.get("destrutivo"):
            return True
        texto = plano.get("descricao") or "\n".join(
            f"• {s.get('action')} {json.dumps(s.get('params', {}), ensure_ascii=False)}"
            for s in plano.get("steps", []) if s.get("action") in DESTRUTIVAS)
        resp = QMessageBox.question(
            self, "QGIS_IA — confirmar",
            f"Esta ação apaga ou descarta dados:\n\n{texto}\n\nContinuar?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return resp == QMessageBox.Yes

    def _mostrar_resultados(self, results):
        for i, res in enumerate(results):
            if res.get("success"):
                self.append_chat("✅", _resumo(res.get("result")))
            else:
                erro = str(res.get("error", "")).strip().splitlines()
                self.append_chat("❌", f"Passo {i+1} falhou: {erro[-1] if erro else ''}")

    def send_prompt(self):
        prompt = self.prompt_input.text().strip()
        if not prompt:
            return

        self.prompt_input.clear()
        self.append_chat("👤 Você", prompt)

        # 1) Comando simples: resolve aqui, sem IA (rápido, grátis, previsível)
        try:
            plano = comandos.interpretar(prompt, self._contexto_comandos())
        except comandos.ErroComando as e:
            self.append_chat("⚠️", str(e))
            self.status_label.setText("Comando reconhecido, mas faltou um nome.")
            return
        if plano is not None:
            if plano.get("ajuda") is not None:
                self.append_chat("📖 Comandos simples (sem IA)",
                                 "<b>Regras:</b> o comando vale para a camada selecionada no painel "
                                 "de Camadas (não precisa dizer o nome). Nome de campo vai entre "
                                 "aspas: criar campo \"area\".<br>"
                                 + "<br>".join(f"• {e}" for e in plano["ajuda"])
                                 + "<br>Qualquer outra coisa é enviada para a IA.")
                return
            self.append_chat("⚡ Comando", plano["descricao"])
            if not self._confirmar(plano):
                self.append_chat("↩️", "Cancelado.")
                return
            self._mostrar_resultados(execute_plan(plano))
            self.status_label.setText("Concluído (comando simples, sem IA).")
            return

        # 2) Pedido livre: vai para a IA
        self.status_label.setText("Enviando para a IA...")
        self.send_btn.setEnabled(False)

        # Inicia worker
        self.worker = AiWorker(self.claude_client, prompt, self._contexto_ia())
        self.worker.signals.finished.connect(self.on_worker_finished)
        self.worker.signals.error.connect(self.on_worker_error)
        self.worker.signals.progress.connect(self.on_worker_progress)
        self.worker.start()

    def on_worker_progress(self, msg):
        self.status_label.setText(msg)

    def on_worker_finished(self, data):
        self.send_btn.setEnabled(True)
        plan = data["plan"]

        for warning in getattr(self.claude_client, "last_warnings", []):
            self.append_chat("⚠️", warning)
        provedor = getattr(self.claude_client, "last_provider", None) or "IA"
        self._atualizar_conexao(provedor)

        explanation = plan.get("explanation")
        if explanation:
            self.append_chat(f"🤖 {provedor}", explanation)
        if not plan.get("steps"):
            self.status_label.setText("Nada a executar.")
            return

        self.append_chat(f"🤖 {provedor}", f"Plano:{json.dumps(plan, ensure_ascii=False, indent=2)}")
        if not self._confirmar(plan):
            self.append_chat("↩️", "Cancelado.")
            self.status_label.setText("Cancelado.")
            return

        # Executa no thread principal (slot de sinal do QThread roda aqui)
        self.status_label.setText("Executando plano no QGIS...")
        self._mostrar_resultados(execute_plan(plan))
        self.status_label.setText("Concluído.")

    def on_worker_error(self, err):
        self.send_btn.setEnabled(True)
        self.append_chat("❌ Erro", err)
        self.status_label.setText("Erro - veja log.")

    def append_chat(self, sender, text):
        self.chat_log.append(f"<b>{sender}:</b> {text}")
        # Auto-scroll
        self.chat_log.verticalScrollBar().setValue(
            self.chat_log.verticalScrollBar().maximum()
        )

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        self.closed.emit()
        super().closeEvent(event)