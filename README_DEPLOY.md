# Deploy e configuração rápida

Este branch adiciona suporte a SQLite e comandos administrativos:

Comandos disponíveis (administradores apenas):
- /status → Ver estatísticas
- /bloqueados → Ver IDs bloqueados
- /duplicados → Ver tentativas de fraude
- /bloquear <id> <motivo> → Bloquear um usuário
- /desbloquear <id> → Desbloquear um usuário
- /historic <id> → Ver histórico de um usuário
- /exportar → Gerar e enviar arquivos TXT (users.txt, blocked.txt, duplicates.txt)

Variáveis de ambiente (Railway):
- BOT_TOKEN (obrigatório)
- ADMIN_ID (ex: "123456789" ou múltiplos: "123,456")
- SQLITE_PATH (opcional, por ex. /data/bot.db para persistência se usar volumes)

Observações:
- Em muitos ambientes sem volumes persistentes, o SQLite perde dados entre deploys. Recomenda-se configurar um volume no Railway ou usar Postgres.
- Este exemplo usa polling. Para webhook, ajuste o entrypoint/start command.
