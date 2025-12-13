const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');
const path = require('path');

// ===== Carregar menus.json =====
let menuData;
try {
  const menuJson = fs.readFileSync('menus.json', 'utf8');
  menuData = JSON.parse(menuJson);
  console.log("✅ menus.json carregado com sucesso.");
} catch (error) {
  console.error("❌ Erro FATAL ao carregar menus.json:", error.message);
  process.exit(1);
}

// ===== Token =====
const token = process.env.MY_TELEGRAM_BOT;
if (!token) {
  console.error("❌ Erro FATAL: variável MY_TELEGRAM_BOT não definida.");
  process.exit(1);
}

const bot = new TelegramBot(token, { polling: true });
console.log("🤖 Bot iniciado e ouvindo...");

// ===== Estados =====
const lastMessages = new Map();
const userFlow = new Map();

// ===== Regras de validação =====
const validationRules = {
  minChars: 100,
  requiredWords: ["transferiste", "saldo", "celeste", "5"],
  forbiddenWords: ["erro", "insuficiente"]
};

// ===== Validação de texto =====
function validateUserMessage(text) {
  const normalized = text.toLowerCase();

  if (text.length < validationRules.minChars) return false;

  for (const w of validationRules.requiredWords) {
    if (!normalized.includes(w)) return false;
  }

  for (const w of validationRules.forbiddenWords) {
    if (normalized.includes(w)) return false;
  }

  return true;
}

// ===== Enviar menu =====
function sendMenu(chatId, menuKey) {
  const menu = menuData[menuKey];
  if (!menu) {
    bot.sendMessage(chatId, "❌ Menu não encontrado. Use /start.");
    userFlow.delete(chatId);
    return;
  }

  let buttons = [];
  if (menu.options) {
    buttons = Object.keys(menu.options).map(key => {
      const option = menu.options[key];
      return [{ text: option.label, callback_data: option.next }];
    });
  }

  bot.sendMessage(chatId, menu.message, {
    parse_mode: "Markdown",
    reply_markup: { inline_keyboard: buttons }
  }).catch(console.error);

  if (menu.requiresTextValidation || menu.requiresPhoto) {
    userFlow.set(chatId, menuKey);
  } else {
    userFlow.delete(chatId);
  }
}

// ===== /start =====
bot.onText(/\/start/, msg => {
  userFlow.delete(msg.chat.id);
  sendMenu(msg.chat.id, "main");
});

// ===== Botões =====
bot.on("callback_query", q => {
  const chatId = q.message.chat.id;
  const action = q.data;
  const menu = menuData[action];

  if (!menu) {
    bot.answerCallbackQuery(q.id, { text: "Opção inválida." });
    return;
  }

  let buttons = [];
  if (menu.options) {
    buttons = Object.keys(menu.options).map(key => {
      const option = menu.options[key];
      return [{ text: option.label, callback_data: option.next }];
    });
  }

  // Envia nova mensagem (chat contínuo)
  bot.sendMessage(chatId, menu.message, {
    parse_mode: "Markdown",
    reply_markup: { inline_keyboard: buttons }
  }).catch(console.error);

  if (menu.requiresTextValidation || menu.requiresPhoto) {
    userFlow.set(chatId, action);
  } else {
    userFlow.delete(chatId);
  }

  bot.answerCallbackQuery(q.id);
});

// ===== Mensagens =====
bot.on("message", async msg => {
  const chatId = msg.chat.id;
  const text = msg.text;

  if (!text && !msg.photo && !msg.document && !msg.video) return;
  if (text && text.startsWith("/")) return;

  const flowKey = userFlow.get(chatId);
  const currentMenu = menuData[flowKey];

  // ===== Foto =====
  if (currentMenu?.requiresPhoto) {
    if (msg.photo) {
      await bot.sendMessage(chatId, "✅ Foto recebida com sucesso.");
      userFlow.delete(chatId);
    } else {
      await bot.sendMessage(chatId, "❌ Envie uma **foto**.", { parse_mode: "Markdown" });
    }
    return;
  }

  // ===== Texto =====
  if (!text || !currentMenu?.requiresTextValidation) return;

  if (lastMessages.get(chatId) === text) return;
  lastMessages.set(chatId, text);

  if (!validateUserMessage(text)) {
    await bot.sendMessage(
      chatId,
      "❌ **Mensagem inválida.**\nVerifique o comprovativo e tente novamente.",
      { parse_mode: "Markdown" }
    );
    return;
  }

  await bot.sendMessage(chatId, "✅ **Mensagem validada!** Enviando arquivo...", {
    parse_mode: "Markdown"
  });

  if (!currentMenu.fileToSend) {
    await bot.sendMessage(chatId, "⚠️ Arquivo não configurado.");
    userFlow.delete(chatId);
    return;
  }

  const filePath = path.resolve(currentMenu.fileToSend);

  if (!fs.existsSync(filePath)) {
    await bot.sendMessage(chatId, "❌ Arquivo não encontrado no servidor.");
    userFlow.delete(chatId);
    return;
  }

  try {
    await bot.sendDocument(chatId, filePath, {
      caption: "🎉 Arquivo de Acesso - MOZ Triple Way"
    });
    await bot.sendMessage(chatId, "🎉 Arquivo enviado com sucesso!");
  } catch (err) {
    console.error(err);
    await bot.sendMessage(chatId, "❌ Erro ao enviar o arquivo.");
  }

  userFlow.delete(chatId);
});
