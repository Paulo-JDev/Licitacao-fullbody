from modules.dispensa.model import DispensaEletronicaModel
from modules.dispensa.view import DispensaEletronicaWidget
from modules.dispensa.dialogs.add_item import AddItemDialog
from modules.dispensa.dialogs.salvar_tabela import DataManager
from modules.dispensa.dialogs.gerar_tabela import TabelaResumidaManager
from modules.dispensa.dialogs.edit_data.edit_data import EditarDadosWindow
from modules.dispensa.database_manager.db_manager import DatabaseManager
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
import pandas as pd
from paths import CONTROLE_DADOS
import sqlite3
import os
from modules.dispensa.dados_api.api_consulta import ConsultaAPIDialog

class DispensaEletronicaController(QObject): 
    def __init__(self, icons, view, model):
        super().__init__()
        self.icons = icons
        self.view = view
        self.edit_data_dialog = None
        self.model_add = model
        self.model = model.setup_model("controle_dispensas")
        self.controle_om = CONTROLE_DADOS  # Atribui o caminho diretamente ao controle_om                
        self.setup_connections()

    def setup_connections(self):
        # Conecta os sinais da view aos métodos do controlador
        self.view.addItem.connect(self.handle_add_item)
        self.view.deleteItem.connect(self.handle_delete_item)
        self.view.dataManager.connect(self.handle_data_manager)
        self.view.salvar_print.connect(self.handle_save_print)
        self.view.rowDoubleClicked.connect(self.handle_edit_item)
        self.view.request_consulta_api.connect(self.consultar_api)

    def consultar_api(self, cnpj, ano, sequencial, uasg, numero):
        # Inicia o diálogo de consulta API com o parent `self.view`
        dialog = ConsultaAPIDialog(numero, cnpj, sequencial, ano, uasg, parent=self.view)
        
        # Conecta o sinal `consulta_concluida` para processar os dados após a consulta
        dialog.consulta_concluida.connect(self.handle_api_data)
        dialog.exec()

    def handle_api_data(self, data_informacoes_lista, resultados_completos):
        # Estrutura os dados da API para salvar no banco de dados
        data_api_to_save = {
            "data_informacoes": data_informacoes_lista,
            "resultados_completos": resultados_completos
        }
        
        # Solicita ao modelo que salve os dados no banco de dados
        self.model_add.save_api_data(data_api_to_save)
        
    def handle_add_item(self):
        """Trata a ação de adicionar item."""
        dialog = AddItemDialog(self.icons, self.model.database_manager.db_path, self.controle_om, self.view)  # Passa o caminho do banco de dados
        if dialog.exec():
            item_data = dialog.get_data()
            # Adiciona a situação padrão 'Planejamento' antes de salvar
            item_data['situacao'] = 'Planejamento'
            self.model_add.insert_or_update_data(item_data)  # Salva no banco de dados
            self.view.refresh_model()   # Salva no banco de dados

    def handle_delete_item(self):
        """Trata a ação de exclusão de um item selecionado."""
        selection_model = self.view.table_view.selectionModel()
        print("Iniciando a exclusão do item...")

        if selection_model.hasSelection():
            index = selection_model.selectedRows(1)[0]  # Assumindo que a coluna 0 é 'id_processo'
            id_processo = index.data()
            print(f"ID do processo selecionado para exclusão: {id_processo}")

            if id_processo:
                confirmation = QMessageBox.question(
                    self.view, "Confirmação",
                    f"Tem certeza que deseja excluir o registro com ID '{id_processo}'?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                print("Confirmação de exclusão solicitada.")

                if confirmation == QMessageBox.StandardButton.Yes:
                    print(f"Confirmado. Excluindo o item com ID: {id_processo}")
                    # Usando o método delete_data corretamente
                    try:
                        self.model.database_manager.delete_data(id_processo)
                        print("Item excluído com sucesso.")
                        self.view.refresh_model()
                        print("Modelo atualizado após exclusão.")
                    except Exception as e:
                        print(f"Erro ao excluir o item: {e}")
                else:
                    print("Exclusão cancelada pelo usuário.")
        else:
            print("Nenhum item selecionado para exclusão.")
            QMessageBox.warning(self.view, "Nenhuma Seleção", "Por favor, selecione um item para excluir.")

    def handle_save_print(self):
        """Trata a ação de salvar uma imagem da tabela."""
        # Implementação de salvar print da tabela
        output_image_path = "tabela_resumida.png"
        # Supondo que um método `tirar_print_da_tabela` exista para salvar a tabela como imagem
        self.view.salvar_tabela_resumida()
        QMessageBox.information(self.view, "Imagem Salva", f"A tabela foi salva em {output_image_path}")

    def refresh_view(self):
        # Atualiza a visualização da tabela após alterações nos dados
        self.view.model.select()  # Recarrega os dados no modelo

    def handle_edit_item(self, data):
        # Extrai informações para compor o nome da tabela
        cnpj_matriz = data.get("cnpj_matriz")
        sequencial_pncp = data.get("sequencial_pncp")
        ano = str(data.get("ano", "0000"))[-4:]  # Captura apenas os 4 últimos dígitos do ano
        
        # Monta o nome da tabela com base nos dados
        table_name = f"{cnpj_matriz}_1_{sequencial_pncp}_{ano}"
        # print(f"DEBUG: Nome da tabela a ser verificada: {table_name}")

        # Conecta ao banco de dados para verificar se a tabela existe e realizar as consultas
        try:
            with self.model_add.database_manager as conn:
                cursor = conn.cursor()
                
                # Verifica se a tabela existe
                cursor.execute(f'SELECT name FROM sqlite_master WHERE type="table" AND name="{table_name}"')
                table_exists = cursor.fetchone() is not None
                
                if table_exists:
                    # print(f"Sucesso: A tabela '{table_name}' existe no banco de dados.")
                    
                    # Calcula `total_homologado`
                    cursor.execute(f'SELECT SUM(valorTotalHomologado) FROM "{table_name}" WHERE valorTotalHomologado IS NOT NULL')
                    total_homologado = cursor.fetchone()[0]
                    total_homologado = total_homologado if total_homologado is not None else None
                    print(f"Somatório de valorTotalHomologado: {total_homologado}")

                    # Conta `situacaoCompraItemNome` com valores específicos
                    cursor.execute(f'''
                        SELECT COUNT(*) 
                        FROM "{table_name}" 
                        WHERE situacaoCompraItemNome IN ("Anulado/Revogado/Cancelado", "Fracassado")
                    ''')
                    count_anulado_fracassado = cursor.fetchone()[0]
                    count_anulado_fracassado = count_anulado_fracassado if count_anulado_fracassado > 0 else None
                    print(f"Quantidade de itens 'Anulado/Revogado/Cancelado' ou 'Fracassado': {count_anulado_fracassado}")

                    # Conta `situacaoCompraItemResultadoNome` com valor "Informado"
                    cursor.execute(f'''
                        SELECT COUNT(*) 
                        FROM "{table_name}" 
                        WHERE situacaoCompraItemResultadoNome = "Informado"
                    ''')
                    count_informado = cursor.fetchone()[0]
                    count_informado = count_informado if count_informado > 0 else None
                    print(f"Quantidade de itens com situacaoCompraItemResultadoNome 'Informado': {count_informado}")
                    
                else:
                    print(f"Erro: A tabela '{table_name}' não foi encontrada no banco de dados.")
                    total_homologado, count_anulado_fracassado, count_informado = "Não Informado", "Não Informado", "Não Informado"
                    
        except sqlite3.Error as e:
            print(f"Erro ao consultar a tabela no banco de dados: {e}")
            total_homologado, count_anulado_fracassado, count_informado = "Não Informado", "Não Informado", "Não Informado"

        # Passa os valores para a instância de EditarDadosWindow
        self.edit_data_dialog = EditarDadosWindow(
            data, self.icons, table_name, self.view
        )
        self.edit_data_dialog.save_data_signal.connect(self.handle_save_data)
        self.view.connect_editar_dados_window(self.edit_data_dialog)  # Conecta sinais
        self.edit_data_dialog.show()
    
    def handle_save_data(self, data):
        try:
            # Use `self.model_add` que se refere a uma instância de `DispensaEletronicaModel`
            self.model_add.insert_or_update_data(data)
            self.view.refresh_model()  # Atualiza a visualização da tabela
        except AttributeError as e:
            QMessageBox.warning(self.view, "Erro", f"Ocorreu um erro ao salvar os dados: {str(e)}")

    def carregar_tabela(self):
        filepath, _ = QFileDialog.getOpenFileName(self.view, "Abrir arquivo de tabela", "", "Tabelas (*.xlsx *.xls *.ods)")
        if filepath:
            try:
                # Carrega o arquivo selecionado em um DataFrame
                df = pd.read_excel(filepath)
                self.validate_and_process_data(df)

                # Insere ou atualiza os dados no banco de dados
                for _, row in df.iterrows():
                    data = row.to_dict()
                    self.model_add.insert_or_update_data(data)
                    self.view.refresh_model()
                # Atualiza o modelo para refletir as alterações
                self.model.select()
                QMessageBox.information(self.view, "Carregamento concluído", "Dados carregados com sucesso.")
            except Exception as e:
                QMessageBox.warning(self.view, "Erro ao carregar", f"Ocorreu um erro ao carregar a tabela: {str(e)}")

    def validate_and_process_data(self, df):
        required_columns = ['ID Processo', 'NUP', 'Objeto', 'uasg']
        if not all(col in df.columns for col in required_columns):
            missing_columns = [col for col in required_columns if col not in df.columns]
            raise ValueError(f"As seguintes colunas estão ausentes: {', '.join(missing_columns)}")

        df.rename(columns={'ID Processo': 'id_processo', 'NUP': 'nup', 'Objeto': 'objeto'}, inplace=True)
        self.desmembramento_id_processo(df)
        self.salvar_detalhes_uasg_sigla_nome(df)

    def desmembramento_id_processo(self, df):
        df[['tipo', 'numero', 'ano']] = df['id_processo'].str.extract(r'(\D+)(\d+)/(\d+)', expand=True)
        df['tipo'] = df['tipo'].map({'DE ': 'Dispensa Eletrônica'}).fillna('Tipo Desconhecido')

    def salvar_detalhes_uasg_sigla_nome(self, df):
        print(f"[DEBUG] Conectando a {self.controle_om} para detalhes de UASG e Sigla")
        with sqlite3.connect(self.controle_om) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT uasg, sigla_om, orgao_responsavel FROM controle_om")
            om_details = {row[0]: {'sigla_om': row[1], 'orgao_responsavel': row[2]} for row in cursor.fetchall()}

        df['sigla_om'] = df['uasg'].map(lambda x: om_details.get(x, {}).get('sigla_om', ''))
        df['orgao_responsavel'] = df['uasg'].map(lambda x: om_details.get(x, {}).get('orgao_responsavel', ''))

    def salvar_tabela_completa(self):
        try:
            self.model.select()
            tabela_manager = TabelaResumidaManager(self.model)
            tabela_manager.carregar_dados()
            output_path = os.path.join(os.getcwd(), "tabela_completa.xlsx")
            tabela_manager.exportar_df_completo_para_excel(output_path)
            tabela_manager.abrir_arquivo_excel(output_path)
        except PermissionError:
            QMessageBox.warning(self.view, "Erro de Permissão", 
                                "Feche o arquivo 'tabela_completa.xlsx' se ele estiver aberto e tente novamente.")

    def salvar_tabela_resumida(self):
        try:
            self.model.select()
            tabela_manager = TabelaResumidaManager(self.model)
            tabela_manager.carregar_dados()
            output_path = os.path.join(os.getcwd(), "tabela_resumida.xlsx")
            tabela_manager.exportar_para_excel(output_path)
            tabela_manager.abrir_arquivo_excel(output_path)
        except PermissionError:
            QMessageBox.warning(self.view, "Erro de Permissão", 
                                "Feche o arquivo 'tabela_resumida.xlsx' se ele estiver aberto e tente novamente.")

    def excluir_database(self):
        reply = QMessageBox.question(self.view, "Confirmação de Exclusão",
                                     "Tem certeza de que deseja excluir todos os dados?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            with self.model.database_manager as conn:
                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS controle_dispensas")
                conn.commit()
            QMessageBox.information(self.view, "Sucesso", "Tabela excluída com sucesso.")
            self.view.refresh_model()
            # self.model.select()  # Atualiza o modelo para refletir a exclusão

    def handle_data_manager(self):
        """Trata a ação de salvar a tabela e gerenciar as ações de dados."""
        dialog = DataManager(self.icons, self.model, self, parent=self.view)
        dialog.exec()
        # self.model.select()
        
def show_warning_if_view_exists(view, title, message):
    if view is not None:
        QMessageBox.warning(view, title, message)
    else:
        print(message)  # Mensagem para o log, caso `view` esteja indisponível