import os
import re
import sqlite3
import logging
import asyncio
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, filters,
    ContextTypes, ConversationHandler, MessageHandler, ApplicationHandlerStop
)

print('Bot iniciado', flush=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ESPERANDO_COMPROVATIVO = 1

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bot_data.db")

NUMEROS_VALIDOS = ['875868157', '846430884']

# IDs do(s) administrador(es) — só estes IDs podem usar os comandos de gestão.
# Define via variável de ambiente ADMIN_IDS="123456789,987654321"
# (podes também colocar um único ID fixo aqui, ex: ADMIN_IDS = {123456789})
ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
}

if not ADMIN_IDS:
    logger.warning("Nenhum ADMIN_IDS configurado — os comandos de administração ficarão inacessíveis.")


def eh_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# =========================================================
#  BASE DE DADOS (persistente — sobrevive a reinícios)
# =========================================================

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            banned_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS used_transactions (
            transaction_id TEXT PRIMARY KEY,
            user_id INTEGER,
            message TEXT,
            used_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def esta_banido(user_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM banned_users WHERE user_id=?", (user_id,))
    resultado = cur.fetchone()
    conn.close()
    return resultado is not None


def banir_usuario(user_id: int, reason: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO banned_users (user_id, reason, banned_at) VALUES (?, ?, ?)",
        (user_id, reason, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def desbanir_usuario(user_id: int) -> bool:
    """Remove o utilizador da lista de banidos. Retorna True se ele estava banido."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
    afetados = cur.rowcount
    conn.commit()
    conn.close()
    return afetados > 0


def listar_banidos():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, reason, banned_at FROM banned_users ORDER BY banned_at DESC")
    linhas = cur.fetchall()
    conn.close()
    return linhas


def contar_banidos() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM banned_users")
    total = cur.fetchone()[0]
    conn.close()
    return total


def contar_transacoes() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM used_transactions")
    total = cur.fetchone()[0]
    conn.close()
    return total


def transacao_ja_usada(transaction_id: str):
    """Retorna o user_id que já usou esta transação, ou None se ainda não foi usada."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM used_transactions WHERE transaction_id=?", (transaction_id,))
    resultado = cur.fetchone()
    conn.close()
    return resultado[0] if resultado else None


def registrar_transacao(transaction_id: str, user_id: int, mensagem: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO used_transactions (transaction_id, user_id, message, used_at) VALUES (?, ?, ?, ?)",
        (transaction_id, user_id, mensagem, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


# =========================================================
#  VALIDAÇÃO DO FORMATO DO COMPROVATIVO
# =========================================================

# Ex: "ID da transacao PP260710.1613.O45888. Transferiste 10.00MT para conta
#      871572807, nome: EDUARDO FERNANDO MIGUEL as 16:13:36 de 10/07/2026. ..."
PADRAO_EMOLA = re.compile(
    r"ID da transac[aã]o\s+(?P<id>\S+?)\.\s*"
    r"Transferiste\s+(?P<valor>[\d.,]+)\s*MT\s*para conta\s+(?P<numero>\d+),\s*"
    r"nome:\s*(?P<nome>.+?)\s+as\s+(?P<hora>\d{1,2}:\d{2}:\d{2})\s+de\s+(?P<data>\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE
)

# Ex: "Confirmado DGL5KWOFKXV. Transferiste 25.00MT e a taxa foi de 2.00MT
#      para 875868157 aos 21/7/26 as 8:43 AM. ..."
PADRAO_MPESA = re.compile(
    r"Confirmado\s+(?P<id>\S+?)\.\s*"
    r"Transferiste\s+(?P<valor>[\d.,]+)\s*MT\s*e a taxa foi de\s+(?P<taxa>[\d.,]+)\s*MT\s*"
    r"para\s+(?P<numero>\d+)\s*aos\s+(?P<data>\d{1,2}/\d{1,2}/\d{2,4})\s*"
    r"as\s+(?P<hora>\d{1,2}:\d{2}\s*[AP]M)",
    re.IGNORECASE
)


def analisar_comprovativo(texto: str):
    """
    Verifica se o texto corresponde a um dos dois formatos válidos.
    Retorna um dict com os dados extraídos (id, numero, valor, ...) ou None
    se não corresponder a nenhum formato conhecido.
    """
    for padrao in (PADRAO_EMOLA, PADRAO_MPESA):
        m = padrao.search(texto)
        if m:
            dados = m.groupdict()
            dados["id"] = dados["id"].strip().rstrip(".")
            dados["numero"] = dados["numero"].strip()
            return dados
    return None


# =========================================================
#  VERIFICAÇÃO GLOBAL DE BANIMENTO (corre antes de tudo)
# =========================================================

async def checar_banido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None:
        return

    if esta_banido(user.id):
        texto = (
            "🚫 <b>Foste banido deste bot.</b>\n\n"
            "O teu ID foi guardado por teres reutilizado uma mensagem de "
            "confirmação de pagamento já usada anteriormente.\n\n"
            "Se achas que isto é um engano, contacta o suporte."
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(texto, parse_mode="HTML")
        elif update.message:
            await update.message.reply_text(texto, parse_mode="HTML")

        # Interrompe a propagação — nenhum outro handler corre para este update
        raise ApplicationHandlerStop


# =========================================================
#  HANDLERS ORIGINAIS
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = ('''\
Olá, seja bem vindo ao bot oficial do <a href='https://moztripleway-production.up.railway.app/'>M0Z Triple Way 😜 </a>!

Este é um bot criado para ajudar os usuários em tarefas simples (como comprar arquivo, etc).  
Se encontrares algum erro, <a href='https://t.me/Yannickandre'>Reporte aqui</a>.''')

    keyboard = [
        [InlineKeyboardButton('🛒 Comprar arquivos', callback_data='comprar_arquivo')],
        [InlineKeyboardButton('🆘 Ajuda', callback_data='ajuda')],
        [InlineKeyboardButton('📞 Contato', callback_data='contato')]
    ]

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            text=texto,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            text=texto,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )


async def comprar_arquivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        text='''\
Muito bem! Chegaste no setor de comprar arquivos.

Tenho arquivos VIP para:
• HTTP Custom  
• HTTP Injector  
• Dark tunnel  

Os arquivos são atualizados todos os sábados, ou seja, se tu comprares no sábado, terá validade de 7 dias, se tu comprares na quinta-feira, terá validade de 2 dias, assim sucessivamente.

Preço: 27 MZN  
Validade: depende do dia da compra.

Escolha o VPN desejado:''',
        parse_mode='HTML'
    )

    botoes = [
        [InlineKeyboardButton('HTTP custom', callback_data='http_custom')],
        [InlineKeyboardButton('HTTP injector', callback_data='http_injector')],
        [InlineKeyboardButton('Dark Tunnel', callback_data='dark_tunnel')],
    ]

    await query.message.reply_text(
        text='Escolha um VPN:',
        reply_markup=InlineKeyboardMarkup(botoes)
    )


async def escolher_vpn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    vpn = query.data
    context.user_data["vpn"] = vpn

    botao_cancelar = [[InlineKeyboardButton('❌ Cancelar compra', callback_data='cancelar_fluxo')]]

    await query.message.reply_text(
        text='''\
Envie o valor para 875868157 ou 846430884 (27 MZN).

Depois cole aqui a mensagem de confirmação EXACTAMENTE como recebeste.''',
        reply_markup=InlineKeyboardMarkup(botao_cancelar)
    )

    return ESPERANDO_COMPROVATIVO


async def receber_texto_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto_original = update.message.text

    # 1) O texto tem mesmo o formato de um comprovativo válido?
    dados = analisar_comprovativo(texto_original)
    if not dados:
        await update.message.reply_text("Mensagem inválida. Verifique e tente novamente.")
        return ESPERANDO_COMPROVATIVO

    # 2) O número de destino é um dos teus números?
    if dados["numero"] not in NUMEROS_VALIDOS:
        await update.message.reply_text(
            "O número de destino não corresponde a nenhuma das nossas contas. "
            "Verifique e tente novamente."
        )
        return ESPERANDO_COMPROVATIVO

    # 3) Esta transação já foi usada antes? (reutilização = fraude)
    dono_anterior = transacao_ja_usada(dados["id"])
    if dono_anterior is not None:
        banir_usuario(
            user_id,
            f"Reutilizou a transação {dados['id']} (usada antes pelo utilizador {dono_anterior})"
        )
        await update.message.reply_text(
            "🚫 Esta confirmação de pagamento já foi usada anteriormente por outra pessoa.\n\n"
            "Foste banido deste bot por tentares reutilizar um comprovativo. "
            "O teu ID foi guardado."
        )
        return ConversationHandler.END

    # 4) Tudo certo — regista a transação como usada e envia os arquivos
    registrar_transacao(dados["id"], user_id, texto_original)

    pasta = os.path.join(BASE_DIR, "arquivos")
    if not os.path.exists(pasta):
        await update.message.reply_text("A pasta de arquivos não foi encontrada. Contacte o ADM, para obter suporte.")
        return ConversationHandler.END

    vpn = context.user_data.get('vpn')
    formato = {
        'http_custom': '.hc',
        'http_injector': '.ehi',
        'dark_tunnel': '.dark'
    }.get(vpn, '.hc')

    arquivos_enviados = 0

    for nome in os.listdir(pasta):
        caminho = os.path.join(pasta, nome)
        if os.path.isfile(caminho) and nome.lower().endswith(formato):
            try:
                with open(caminho, 'rb') as f:
                    await update.message.reply_document(document=f, filename=nome)
                arquivos_enviados += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.exception(f"Erro ao enviar arquivo {nome}: {e}")

    if arquivos_enviados == 0:
        await update.message.reply_text("Nenhum arquivo encontrado. Por favor contacte o ADM para obter suporte.")
    else:
        await update.message.reply_text("Pronto! Todos os arquivos foram enviados, faça bom proveito.")

    return ConversationHandler.END


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = '''Bem-vindo ao setor de ajuda!
Se tu tens alguma dúvida, ou problema podes aderir aos nossos grupos e obter suporte.

Grupos de suporte:
• <a href="https://chat.whatsapp.com/LaAjlbB8umaFq251VplJ6R">WhatsApp</a>
• <a href="https://t.me/chatmoztripleway">Telegram</a>
• <a href="https://discord.gg/8YvBndtVB">Discord</a>'''

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            texto,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")]
            ])
        )
    else:
        await update.message.reply_text(texto, parse_mode='HTML')


async def contato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    texto = '''Como já foi dito antes, este é um bot programado manualmente, então pode ter alguns erros.
Se encontrares algum erro ou tiveres sugestões, contacta-me:

• <a href="https://www.facebook.com/share/1DXbZn1mi7/">Facebook</a>
• <a href="https://www.instagram.com/yanni.ckandre?igsh=NWZqNHViNXM2bzM5">Instagram</a>

Essas são as maneiras mais práticas de me contatar, pois eu certamente verei tua mensagem.'''

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            texto,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")]
            ])
        )
    else:
        await update.message.reply_text(
            texto,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")]
            ])
        )


async def cancelar_operacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Compra cancelada.")
    return ConversationHandler.END


async def voltar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END


async def interacao_botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "comprar_arquivo":
        await comprar_arquivo(update, context)
    elif query.data == "ajuda":
        await ajuda(update, context)
    elif query.data == "contato":
        await contato(update, context)


# =========================================================
#  COMANDOS DE ADMINISTRAÇÃO (só para quem está em ADMIN_IDS)
# =========================================================

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        return  # ignora silenciosamente — não revela que o comando existe

    banidos = contar_banidos()
    transacoes = contar_transacoes()
    texto = (
        "🤖 <b>Status do bot</b>\n\n"
        f"👥 Usuários banidos: <b>{banidos}</b>\n"
        f"🧾 Transações registadas: <b>{transacoes}</b>\n"
        f"🗄️ Base de dados: <code>{DB_PATH}</code>"
    )
    await update.message.reply_text(texto, parse_mode="HTML")


async def cmd_bloqueados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        return

    linhas = listar_banidos()
    if not linhas:
        await update.message.reply_text("✅ Nenhum usuário banido no momento.")
        return

    blocos = []
    for user_id, motivo, banido_em in linhas:
        blocos.append(f"• <b>ID:</b> <code>{user_id}</code>\n  <b>Motivo:</b> {motivo}\n  <b>Data:</b> {banido_em}")

    texto_completo = f"🚫 <b>Usuários banidos ({len(linhas)}):</b>\n\n" + "\n\n".join(blocos)

    # Telegram limita mensagens a 4096 caracteres — enviamos em pedaços se necessário
    LIMITE = 3800
    for i in range(0, len(texto_completo), LIMITE):
        await update.message.reply_text(texto_completo[i:i + LIMITE], parse_mode="HTML")


async def cmd_bloquear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Uso: /bloquear <id> [motivo opcional]")
        return

    try:
        alvo_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID inválido. Deve ser um número (o ID numérico do Telegram).")
        return

    motivo = " ".join(context.args[1:]) if len(context.args) > 1 else "Bloqueado manualmente pelo administrador"
    banir_usuario(alvo_id, motivo)
    await update.message.reply_text(f"🚫 Usuário {alvo_id} bloqueado.\nMotivo: {motivo}")


async def cmd_desbloquear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Uso: /desbloquear <id>")
        return

    try:
        alvo_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID inválido. Deve ser um número (o ID numérico do Telegram).")
        return

    removido = desbanir_usuario(alvo_id)
    if removido:
        await update.message.reply_text(f"✅ Usuário {alvo_id} desbloqueado.")
    else:
        await update.message.reply_text(f"O usuário {alvo_id} não estava bloqueado.")


# =========================================================
#  MAIN
# =========================================================

def main():
    print('entrou no main', flush=True)
    TOKEN = os.environ.get("MEU_TOKEN_SECRETO")
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

    if not TOKEN:
        logger.error("Token não encontrado.")
        return

    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL não definida.")
        return

    init_db()

    print('passo 2')
    application = Application.builder().token(TOKEN).build()

    print('passo 3')

    # Handler global de banimento — corre ANTES de qualquer outro handler.
    # Se o utilizador estiver banido, para tudo por ali (ApplicationHandlerStop).
    application.add_handler(MessageHandler(filters.ALL, checar_banido), group=-1)
    application.add_handler(CallbackQueryHandler(checar_banido), group=-1)

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                escolher_vpn,
                pattern='^(http_custom|http_injector|dark_tunnel)$'
            )
        ],
        states={
            ESPERANDO_COMPROVATIVO: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receber_texto_usuario
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(
                cancelar_operacao,
                pattern='^cancelar_fluxo$'
            )
        ],
        per_message=False
    )
    application.add_handler(conv_handler)

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('ajuda', ajuda))
    application.add_handler(CommandHandler('contato', contato))

    application.add_handler(
        CallbackQueryHandler(voltar_menu, pattern="^voltar_menu$")
    )

    application.add_handler(
        CallbackQueryHandler(interacao_botoes, pattern='^(comprar_arquivo|ajuda|contato)$')
    )

    # Comandos de administração (restritos a ADMIN_IDS)
    application.add_handler(CommandHandler('status', cmd_status))
    application.add_handler(CommandHandler('bloqueados', cmd_bloqueados))
    application.add_handler(CommandHandler('bloquear', cmd_bloquear))
    application.add_handler(CommandHandler('desbloquear', cmd_desbloquear))

    logger.info("Bot iniciado com sucesso.")

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        webhook_url=WEBHOOK_URL,
    )


if __name__ == "__main__":
    print("CHAMANDO MAIN", flush=True)
    main()
