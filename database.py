import sqlite3
from datetime import datetime
import os

DB_FILE = 'bot_database.db'


class BotDatabase:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.criar_tabelas()

    def criar_tabelas(self):
        """Cria as tabelas se não existirem"""
        
        # Tabela de confirmações
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS confirmacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                codigo TEXT NOT NULL UNIQUE,
                mensagem TEXT NOT NULL,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabela de usuários bloqueados
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios_bloqueados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                motivo TEXT,
                data_bloqueio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabela de duplicados (tentativas fraudulentas)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS duplicados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                codigo TEXT NOT NULL,
                data_tentativa TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabela de histórico de ações
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                acao TEXT NOT NULL,
                descricao TEXT,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabela de transações
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS transacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                vpn_tipo TEXT NOT NULL,
                codigo_confirmacao TEXT,
                valor REAL,
                status TEXT,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.conn.commit()

    # ===== CONFIRMAÇÕES =====
    def adicionar_confirmacao(self, user_id, codigo, mensagem):
        """Adiciona uma confirmação"""
        try:
            self.cursor.execute('''
                INSERT INTO confirmacoes (user_id, codigo, mensagem)
                VALUES (?, ?, ?)
            ''', (user_id, codigo, mensagem))
            self.conn.commit()
            self.registrar_historico(user_id, 'CONFIRMACAO_ACEITA', f'Código: {codigo}')
            return True
        except sqlite3.IntegrityError:
            return False  # Código duplicado

    def codigo_ja_usado(self, codigo):
        """Verifica se o código já foi usado"""
        self.cursor.execute('SELECT id FROM confirmacoes WHERE codigo = ?', (codigo,))
        return self.cursor.fetchone() is not None

    def get_confirmacoes_usuario(self, user_id):
        """Retorna todas as confirmações de um usuário"""
        self.cursor.execute('''
            SELECT codigo, mensagem, data_hora FROM confirmacoes 
            WHERE user_id = ? ORDER BY data_hora DESC
        ''', (user_id,))
        return self.cursor.fetchall()

    def get_todas_confirmacoes(self):
        """Retorna todas as confirmações (para admin)"""
        self.cursor.execute('''
            SELECT user_id, codigo, data_hora FROM confirmacoes 
            ORDER BY data_hora DESC
        ''')
        return self.cursor.fetchall()

    # ===== BLOQUEADOS =====
    def bloquear_usuario(self, user_id, motivo="Não especificado"):
        """Bloqueia um usuário"""
        try:
            self.cursor.execute('''
                INSERT INTO usuarios_bloqueados (user_id, motivo)
                VALUES (?, ?)
            ''', (user_id, motivo))
            self.conn.commit()
            self.registrar_historico(user_id, 'USUARIO_BLOQUEADO', motivo)
            return True
        except sqlite3.IntegrityError:
            return False  # Já está bloqueado

    def desbloquear_usuario(self, user_id):
        """Desbloqueia um usuário"""
        self.cursor.execute('DELETE FROM usuarios_bloqueados WHERE user_id = ?', (user_id,))
        self.conn.commit()
        self.registrar_historico(user_id, 'USUARIO_DESBLOQUEADO', 'Desbloqueado manualmente')

    def esta_bloqueado(self, user_id):
        """Verifica se um usuário está bloqueado"""
        self.cursor.execute('SELECT id FROM usuarios_bloqueados WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone() is not None

    def get_bloqueados(self):
        """Retorna lista de usuários bloqueados"""
        self.cursor.execute('''
            SELECT user_id, motivo, data_bloqueio FROM usuarios_bloqueados 
            ORDER BY data_bloqueio DESC
        ''')
        return self.cursor.fetchall()

    def get_motivo_bloqueio(self, user_id):
        """Retorna o motivo do bloqueio"""
        self.cursor.execute(
            'SELECT motivo FROM usuarios_bloqueados WHERE user_id = ?', 
            (user_id,)
        )
        resultado = self.cursor.fetchone()
        return resultado[0] if resultado else None

    # ===== DUPLICADOS =====
    def adicionar_duplicado(self, user_id, codigo):
        """Registra tentativa de usar código duplicado"""
        self.cursor.execute('''
            INSERT INTO duplicados (user_id, codigo)
            VALUES (?, ?)
        ''', (user_id, codigo))
        self.conn.commit()
        self.registrar_historico(user_id, 'TENTATIVA_DUPLICADA', f'Código: {codigo}')

    def get_duplicados_usuario(self, user_id):
        """Retorna tentativas de duplicação de um usuário"""
        self.cursor.execute('''
            SELECT codigo, data_tentativa FROM duplicados 
            WHERE user_id = ? ORDER BY data_tentativa DESC
        ''', (user_id,))
        return self.cursor.fetchall()

    def get_todos_duplicados(self):
        """Retorna todos os duplicados (para admin)"""
        self.cursor.execute('''
            SELECT user_id, codigo, data_tentativa FROM duplicados 
            ORDER BY data_tentativa DESC
        ''')
        return self.cursor.fetchall()

    # ===== TRANSAÇÕES =====
    def adicionar_transacao(self, user_id, vpn_tipo, codigo_confirmacao, valor, status='completo'):
        """Registra uma transação"""
        self.cursor.execute('''
            INSERT INTO transacoes (user_id, vpn_tipo, codigo_confirmacao, valor, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, vpn_tipo, codigo_confirmacao, valor, status))
        self.conn.commit()

    def get_transacoes_usuario(self, user_id):
        """Retorna transações de um usuário"""
        self.cursor.execute('''
            SELECT vpn_tipo, valor, status, data_hora FROM transacoes 
            WHERE user_id = ? ORDER BY data_hora DESC
        ''', (user_id,))
        return self.cursor.fetchall()

    def get_total_vendas(self):
        """Retorna total de vendas"""
        self.cursor.execute('SELECT SUM(valor) FROM transacoes WHERE status = "completo"')
        resultado = self.cursor.fetchone()
        return resultado[0] if resultado[0] else 0

    # ===== HISTÓRICO =====
    def registrar_historico(self, user_id, acao, descricao):
        """Registra uma ação no histórico"""
        self.cursor.execute('''
            INSERT INTO historico (user_id, acao, descricao)
            VALUES (?, ?, ?)
        ''', (user_id, acao, descricao))
        self.conn.commit()

    def get_historico_usuario(self, user_id):
        """Retorna histórico de um usuário"""
        self.cursor.execute('''
            SELECT acao, descricao, data_hora FROM historico 
            WHERE user_id = ? ORDER BY data_hora DESC LIMIT 50
        ''', (user_id,))
        return self.cursor.fetchall()

    def get_historico_completo(self):
        """Retorna histórico completo (para admin)"""
        self.cursor.execute('''
            SELECT user_id, acao, descricao, data_hora FROM historico 
            ORDER BY data_hora DESC LIMIT 100
        ''')
        return self.cursor.fetchall()

    # ===== ESTATÍSTICAS =====
    def get_estatisticas(self):
        """Retorna estatísticas gerais"""
        self.cursor.execute('SELECT COUNT(*) FROM confirmacoes')
        total_confirmacoes = self.cursor.fetchone()[0]

        self.cursor.execute('SELECT COUNT(*) FROM usuarios_bloqueados')
        total_bloqueados = self.cursor.fetchone()[0]

        self.cursor.execute('SELECT COUNT(*) FROM duplicados')
        total_duplicados = self.cursor.fetchone()[0]

        self.cursor.execute('SELECT COUNT(DISTINCT user_id) FROM confirmacoes')
        usuarios_ativos = self.cursor.fetchone()[0]

        self.cursor.execute('SELECT SUM(valor) FROM transacoes WHERE status = "completo"')
        total_vendas = self.cursor.fetchone()[0] or 0

        return {
            'confirmacoes': total_confirmacoes,
            'bloqueados': total_bloqueados,
            'duplicados': total_duplicados,
            'usuarios_ativos': usuarios_ativos,
            'total_vendas': total_vendas
        }

    # ===== EXPORTAÇÃO =====
    def exportar_confirmados(self, arquivo='confirmados.txt'):
        """Exporta confirmações para arquivo TXT"""
        confirmacoes = self.get_todas_confirmacoes()
        with open(arquivo, 'w', encoding='utf-8') as f:
            f.write("=== CONFIRMAÇÕES REGISTRADAS ===\n")
            f.write(f"Data de geração: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n")
            for user_id, codigo, data_hora in confirmacoes:
                f.write(f"USER_ID: {user_id} | CÓDIGO: {codigo} | DATA: {data_hora}\n")

    def exportar_bloqueados(self, arquivo='blocked_ids.txt'):
        """Exporta bloqueados para arquivo TXT"""
        bloqueados = self.get_bloqueados()
        with open(arquivo, 'w', encoding='utf-8') as f:
            f.write("=== USUÁRIOS BLOQUEADOS ===\n")
            f.write(f"Data de geração: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n")
            for user_id, motivo, data_bloqueio in bloqueados:
                f.write(f"USER_ID: {user_id} | MOTIVO: {motivo} | DATA: {data_bloqueio}\n")

    def exportar_duplicados(self, arquivo='duplicados.txt'):
        """Exporta duplicados para arquivo TXT"""
        duplicados = self.get_todos_duplicados()
        with open(arquivo, 'w', encoding='utf-8') as f:
            f.write("=== TENTATIVAS DE DUPLICAÇÃO ===\n")
            f.write(f"Data de geração: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n")
            for user_id, codigo, data_tentativa in duplicados:
                f.write(f"USER_ID: {user_id} | CÓDIGO: {codigo} | DATA: {data_tentativa}\n")

    def fechar_conexao(self):
        """Fecha a conexão com o banco"""
        self.conn.close()
