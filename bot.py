import os
import asyncio
import io
from telegram import Update, __version__ as tg_version
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from db import (
    init_db, add_or_update_user, count_users, get_all_user_ids, get_users_list,
    block_user, unblock_user, is_blocked, get_blocked, add_duplicate, get_duplicates,
    add_history, get_history
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Defina a variável de ambiente BOT_TOKEN")

# ADMIN_ID pode ser "123456789" ou "123,456,789" para múltiplos admins
ADMIN_IDS_ENV = os.getenv("ADMIN_ID", "")
ADMIN_IDS = set()
for part in ADMIN_IDS_ENV.split(","):
    part = part.strip()
    if part:
        try:
            ADMIN_IDS.add(int(part))
        except ValueError:
            pass  # ignora valores inválidos

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await is_blocked(user.id):
        await update.message.reply_text("Você está bloqueado e não pode usar este bot.")
        return
    await add_or_update_user(user)
    await update.message.reply_text(f"Olá, {user.first_name}! Bot pronto.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("Acesso negado. Somente administradores.")
        return
    total = await count_users()
    blocked = await get_blocked()
    duplicates = await get_duplicates()
    text = (
        f"Status do bot:\n"
        f"- Versão python-telegram-bot: {tg_version}\n"
        f"- Usuários registrados: {total}\n"
        f"- Bloqueados: {len(blocked)}\n"
        f"- Tentativas duplicadas registradas: {len(duplicates)}\n"
    )
    await update.message.reply_text(text)

async def bloqueados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("Acesso negado. Somente administradores.")
        return
    rows = await get_blocked()
    if not rows:
        await update.message.reply_text("Nenhum usuário bloqueado.")
        return
    lines = [f"{r[0]} — motivo: {r[1]} — por: {r[2]} — em: {r[3]}" for r in rows]
    text = "\n".join(lines[:2000])
    await update.message.reply_text(text)

async def duplicados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("Acesso negado. Somente administradores.")
        return
    rows = await get_duplicates()
    if not rows:
        await update.message.reply_text("Nenhuma tentativa duplicada registrada.")
        return
    lines = [f"{r[0]} — user_id: {r[1]} — info: {r[2]} — em: {r[3]}" for r in rows]
    text = "\n".join(lines[:4000])
    await update.message.reply_text(text)

async def bloquear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("Acesso negado. Somente administradores.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /bloquear <user_id> <motivo>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID inválido.")
        return
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "sem motivo fornecido"
    await block_user(target_id, reason, by_admin=uid)
    await update.message.reply_text(f"Usuário {target_id} bloqueado. Motivo: {reason}")

async def desbloquear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("Acesso negado. Somente administradores.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /desbloquear <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID inválido.")
        return
    await unblock_user(target_id, by_admin=uid)
    await update.message.reply_text(f"Usuário {target_id} desbloqueado.")

async def historic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("Acesso negado. Somente administradores.")
        return
    if not context.args:
        await update.message.reply_text("Uso: /historic <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID inválido.")
        return
    rows = await get_history(target_id)
    if not rows:
        await update.message.reply_text("Nenhum histórico para esse usuário.")
        return
    lines = [f"{r[4]} — {r[1]} — {r[2]} — por: {r[3]}" for r in rows]
    text = "\n".join(lines[:4000])
    await update.message.reply_text(text)

async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("Acesso negado. Somente administradores.")
        return
    users = await get_users_list()
    blocked = await get_blocked()
    duplicates = await get_duplicates()

    users_txt = "\n".join([f"{u[0]}\t{u[1]}\t{u[2]}" for u in users])
    blocked_txt = "\n".join([f"{b[0]}\t{b[1]}\t{b[2]}\t{b[3]}" for b in blocked])
    dup_txt = "\n".join([f"{d[0]}\t{d[1]}\t{d[2]}\t{d[3]}" for d in duplicates])

    files_to_send = [
        ("users.txt", users_txt),
        ("blocked.txt", blocked_txt),
        ("duplicates.txt", dup_txt),
    ]

    for name, content in files_to_send:
        bio = io.BytesIO()
        bio.write(content.encode("utf-8"))
        bio.seek(0)
        await context.bot.send_document(chat_id=uid, document=bio, filename=name)

async def main():
    await init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("bloqueados", bloqueados))
    app.add_handler(CommandHandler("duplicados", duplicados))
    app.add_handler(CommandHandler("bloquear", bloquear))
    app.add_handler(CommandHandler("desbloquear", desbloquear))
    app.add_handler(CommandHandler("historic", historic))
    app.add_handler(CommandHandler("exportar", exportar))

    # Polling por defeito; para webhook adapte o comando de start no Railway
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
