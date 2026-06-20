import os
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler, MessageHandler
import asyncio

print('Bot iniciado', flush=True)
# Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ESPERANDO_COMPROVATIVO = 1

# /start
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

    # Tratar tanto mensagens quanto callback queries
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


# Comprar arquivo
async def comprar_arquivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        text='''\
Muito bem! Chegaste no setor de comprar arquivos.

Tenho arquivos VIP para:
• HTTP Custom  
• HTTP Injector  
• OpenTunnel  

Os arquivos são atualizados todos os sábados, ou seja, se tu comprares no sábado, terá validade de 7 dias, se tu comprares na quinta-feira, terá validade de 2 dias, assim sucessivamente.

Preço: 27 MZN  
Validade: depende do dia da compra.

Escolha o VPN desejado:''',
        parse_mode='HTML'
    )

    botoes = [
        [InlineKeyboardButton('HTTP custom', callback_data='http_custom')],
        [InlineKeyboardButton('HTTP injector', callback_data='http_injector')],
        [InlineKeyboardButton('OpenTunnel', callback_data='open_tunnel')],
    ]

    await query.message.reply_text(
        text='Escolha um VPN:',
        reply_markup=InlineKeyboardMarkup(botoes)
    )

# Escolher VPN
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

# Receber comprovativo
async def receber_texto_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_de_confirmacao = update.message.text.lower()
    requerimentos = ['27', 'celeste', 'onelta', 'saldo']

    if all(p in texto_de_confirmacao for p in requerimentos) and ("875868157" in requerimentos or "846430884" in requerimentos):

        # Extrair ID da transação
        padrao_codigo = re.search(r'\b[a-z0-9]{10}\b', texto_de_confirmacao)
        id_transacao = padrao_codigo.group(0) if padrao_codigo else "".join(texto_de_confirmacao.split())

        FICHEIRO_COMPROVATIVOS = "comprovativos.db"

        # Verificar duplicados
        if os.path.exists(FICHEIRO_COMPROVATIVOS):
            with open(FICHEIRO_COMPROVATIVOS, "r") as f:
                usados = f.read().splitlines()
                if id_transacao in usados:
                    await update.message.reply_text("⚠️ Este comprovativo já foi utilizado!")
                    return ConversationHandler.END

        # Salvar novo comprovativo
        with open(FICHEIRO_COMPROVATIVOS, "a") as f:
            f.write(id_transacao + "\n")

        # Enviar arquivos
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))

        pasta = os.path.join(BASE_DIR, "arquivos")
        if not os.path.exists(pasta):
            await update.message.reply_text("A pasta de arquivos não foi encontrada. Contacte o ADM, para obter suporte.")
            return ConversationHandler.END

        vpn = context.user_data.get('vpn')
        formato = {
            'http_custom': '.hc',
            'http_injector': '.ehi',
            'open_tunnel': '.tnl'
        }.get(vpn, '.hc')

        arquivos_enviados = 0

        for nome in os.listdir(pasta):
            caminho = os.path.join(pasta, nome)
            if os.path.isfile(caminho) and nome.lower().endswith(formato):
                try:
                    with open(caminho, 'rb') as f:
                        await update.message.reply_document(document=f, 
                        filename=nome)
                    arquivos_enviados += 1
                    await asyncio.sleep(0.5)  # Reduzir delay entre arquivos
                except Exception as e:
                    logger.exception(f"Erro ao enviar arquivo {nome}: {e}")

        if arquivos_enviados == 0:
            await update.message.reply_text("Nenhum arquivo encontrado. Por favor contacte o ADM para obter suporte.")
        else:
            await update.message.reply_text("Pronto! Todos os arquivos foram enviados, faça bom proveito.")

        return ConversationHandler.END

    else:
        await update.message.reply_text("Mensagem inválida. Verifique e tente novamente.")
        return ESPERANDO_COMPROVATIVO

# Ajuda
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
        await update.message.reply_text(
            texto,
            parse_mode='HTML'
        )

# Contato
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

# Cancelar
async def cancelar_operacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Compra cancelada.")
    return ConversationHandler.END

# Voltar ao menu principal
async def voltar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END

# Botões
async def interacao_botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    
    if query.data == "comprar_arquivo":
        await comprar_arquivo(update, context)
    elif query.data == "ajuda":
        await ajuda(update, context)
    elif query.data == "contato":
        await contato(update, context)

# MAIN
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

    print('passo 2')
    application = Application.builder().token(TOKEN).build()
    
    print('passo 3')
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                escolher_vpn,
                pattern='^(http_custom|http_injector|open_tunnel)$'
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

    logger.info("Bot iniciado com sucesso.")
   
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        webhook_url=WEBHOOK_URL,
    )

if __name__ == "__main__":
    print("CHAMANDO MAIN", flush=True)
    main()