import os
from fastapi import FastAPI, Request
from telegram import Update
from bot import create_application

app = FastAPI()

application = create_application()

@app.on_event("startup")
async def startup():
    print("Bot iniciado com FastAPI")

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()

        update = Update.de_json(data, application.bot)
        await application.process_update(update)

        return {"ok": True}

    except Exception as e:
        print("Erro no webhook:", e)
        return {"ok": False}