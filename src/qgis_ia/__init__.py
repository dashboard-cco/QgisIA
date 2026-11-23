# -*- coding: utf-8 -*-
"""
Plugin principal: QGIS_IA para QGIS
"""
import os
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsApplication, QgsMessageLog

from .dockwidget import QgisIaDockWidget
from .ai_client import ClaudeClient
from .mcp_socket import McpSocketServer


class QgisIaPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dockwidget = None
        self.claude_client = None
        self.mcp_server = None
        self.plugin_dir = os.path.dirname(__file__)

    def initGui(self):
        """Cria ação no menu Plugins e toolbar."""
        icon_path = os.path.join(self.plugin_dir, "icon.svg")
        if not os.path.exists(icon_path):
            # Ícone padrão do QGIS se não houver customizado
            icon_path = ":images/themes/default/mIconConsole.svg"

        self.action = QAction(
            QIcon(icon_path),
            "QGIS_IA",
            self.iface.mainWindow()
        )
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle_dockwidget)

        self.iface.addPluginToMenu("&QGIS_IA", self.action)
        self.iface.addToolBarIcon(self.action)

        # Inicializa cliente Claude (lazy - só quando abrir)
        self.claude_client = None

    def unload(self):
        """Remove menu/toolbar ao desativar plugin."""
        self.iface.removePluginMenu("&QGIS_IA", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.mcp_server:
            self.mcp_server.stop()
            self.mcp_server.deleteLater()
            self.mcp_server = None
        if self.dockwidget:
            self.dockwidget.close()
            self.dockwidget.deleteLater()

    def toggle_dockwidget(self, checked):
        if checked:
            self.show_dockwidget()
        else:
            self.hide_dockwidget()

    def show_dockwidget(self):
        if not self.dockwidget:
            self.dockwidget = QgisIaDockWidget(
                self.iface, self.get_claude_client(), self.get_mcp_server()
            )
            self.dockwidget.closed.connect(self.on_dockwidget_closed)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
        self.dockwidget.show()
        self.dockwidget.raise_()
        self.action.setChecked(True)

    def hide_dockwidget(self):
        if self.dockwidget:
            self.dockwidget.hide()
        self.action.setChecked(False)

    def on_dockwidget_closed(self):
        self.action.setChecked(False)

    def get_mcp_server(self):
        """Servidor MCP vive no plugin (não no painel): continua ativo se o painel for fechado."""
        if self.mcp_server is None:
            self.mcp_server = McpSocketServer(self.iface.mainWindow())
        return self.mcp_server

    def get_claude_client(self):
        """Lazy init do cliente de IA (Anthropic -> OpenRouter -> Mock)."""
        if self.claude_client is None:
            has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
            has_openrouter = bool(os.environ.get("OPENROUTER_API_KEY", ""))
            if not has_anthropic and not has_openrouter:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "QGIS_IA",
                    "Nenhuma chave de API encontrada.\n"
                    "Defina a variável de ambiente ANTHROPIC_API_KEY e/ou "
                    "OPENROUTER_API_KEY (variáveis de ambiente do Windows) "
                    "para habilitar respostas reais da IA.\n"
                    "Sem nenhuma das duas, o plugin funciona em modo mock "
                    "(respostas simuladas, só para teste)."
                )
            self.claude_client = ClaudeClient()
        return self.claude_client


def classFactory(iface):
    """Chamado pelo QGIS para instanciar o plugin."""
    return QgisIaPlugin(iface)