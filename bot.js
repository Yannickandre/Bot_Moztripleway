const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');

// Carregar a estrutura de menus do JSON
let menuData;
try {
  const menuJson = fs.readFileSync('menus.json', 'utf8');
  menuData = JSON.parse(menuJson);
  console.log("✅ menus.json carregado com sucesso.");
} catch (error) {
  console.error("❌ Erro FATAL ao carregar menus.json:", error.message);
  process.exit(1); // Sai se não conseguir carregar o menu
}

// **Atenção:** Mantenha o Token Seguro. Use variáveis de ambiente!
const token = process.env.MY_TELEGRAM_BOT; 
if (!token) {
    console.error("❌ Erro FATAL: O token do Telegram não está definido na variável de ambiente MY_TELEGRAM_BOT.");
    process.exit(1);
}
const bot = new TelegramBot(token, { polling: true });
console.log("🤖 Bot iniciado e ouvindo...");


// ===== Variáveis de Estado =====
const lastMessages = new Map(); // Evita mensagens duplicadas
const userFlow = new Map(); // Guarda a chave do menu que exige a próxima resposta (ex: "paymycustom")

// Regras de validação (mantidas aqui para fácil acesso pelo código, mas escondidas do usuário)
const validationRules = {
  minChars: 100,
  requiredWords: ["transferiste", "saldo", "celeste", "5"],
  forbiddenWords: ["erro", "insuficiente"]
};

// ===== Função de validação de texto =====
function validateUserMessage(text) {
  const { minChars, requiredWords, forbiddenWords } = validationRules;
  const normalized = text.toLowerCase();

  // 1. Mínimo de caracteres
  if (text.length < minChars) return false;

  // 2. Palavras obrigatórias
  for (let w of requiredWords) {
    if (!normalized.includes(w.toLowerCase())) return false;
  }
  
  // 3. Palavras proibidas
  for (let w of forbiddenWords) {
    if (normalized.includes(w.toLowerCase())) return false;
  }

  return true;
}

// ===== Função para enviar menus =====
function sendMenu(chatId, menuKey) {
  const menu = menuData[menuKey];
  if (!menu) {
    bot.sendMessage(chatId, `❌ Erro: Menu '${menuKey}' não encontrado. Volte para /start.`);
    userFlow.delete(chatId);
    return;
  }

  let buttons = [];
  if (menu.options) {
    buttons = Object.keys(menu.options).map(key => {
      const option = menu.options[key];
      // Cada botão inline deve estar em seu próprio array para ser uma linha separada
      return [{ text: option.label, callback_data: option.next }]; 
    });
    // Achata o array para a estrutura de teclado inline exigida
    buttons = buttons.flat(); 
  }

  // O estado de fluxo deve ser limpo APENAS se o menu não exige entrada.
  if (!menu.requiresTextValidation && !menu.requiresPhoto) {
    userFlow.delete(chatId);
  }

  bot.sendMessage(chatId, menu.message, { 
    parse_mode: "Markdown", 
    reply_markup: { inline_keyboard: buttons } 
  }).catch(err => console.error("Erro ao enviar menu:", err));
}

// ===== /start Handler =====
bot.onText(/\/start/, msg => {
    // Garante que o fluxo é limpo ao iniciar
    userFlow.delete(msg.chat.id);
    sendMenu(msg.chat.id, "main");
});

// ===== Callback dos botões (Interações no Menu) =====
bot.on("callback_query", q => {
  const chatId = q.message.chat.id;
  const action = q.data; // action é o 'next' do botão
  const menu = menuData[action];

  if (!menu) {
    // Responde à query sem feedback visual se for inválida/antiga
    bot.answerCallbackQuery(q.id, { text: "Opção inválida ou menu expirado." });
    return;
  }
  
  // 1. Prepara e Edita a mensagem anterior para o novo menu
  let buttons = [];
  if (menu.options) {
    buttons = Object.keys(menu.options).map(key => {
      const option = menu.options[key];
      return [{ text: option.label, callback_data: option.next }];
    });
    // Achata o array para a estrutura de teclado inline exigida
    buttons = buttons.flat(); 
  }

  bot.editMessageText(menu.message, {
      chat_id: chatId,
      message_id: q.message.message_id,
      parse_mode: "Markdown",
      reply_markup: { inline_keyboard: buttons }
  }).catch(error => {
      // É normal receber o erro 'message is not modified' se o usuário clicar no mesmo botão
      if (!(error.response && error.response.body.description.includes("message is not modified"))) {
          console.error("Erro ao editar mensagem:", error);
      }
  });


  // 2. Trata o fluxo de estado (Define o que o bot deve esperar em seguida)
  if (menu.requiresTextValidation || menu.requiresPhoto) {
    userFlow.set(chatId, action); 
  } else {
    // Se o menu não exige validação (como voltar), limpa o estado
    userFlow.delete(chatId);
  }

  // 3. Remove o "loading" do botão
  bot.answerCallbackQuery(q.id);
});

// ===== Captura mensagens de TEXTO / ARQUIVO (A PARTE CRÍTICA) =====
bot.on("message", async msg => { 
  const chatId = msg.chat.id;
  const text = msg.text;
  
  // *** CORREÇÃO: Evita a duplicação de mensagens após callback_query ***
  // Ignora updates que não são texto, foto, documento, ou vídeo, o que filtra a maioria
  // dos updates "vazios" gerados após o clique em um botão inline.
  if (!text && !msg.photo && !msg.document && !msg.video) {
      return; 
  }
  // ********************************************************************
  
  const userCurrentFlowKey = userFlow.get(chatId);
  const currentMenu = menuData[userCurrentFlowKey];
  
  // Ignora comandos (se a mensagem tiver texto)
  if (text && text.startsWith("/")) return; 

  // --- 1. TRATAMENTO DE FOTO (Se o menu exige foto) ---
  if (currentMenu?.requiresPhoto) {
      if (msg.photo) {
          bot.sendMessage(chatId, "✅ Foto recebida com sucesso! Obrigado por enviar.");
          userFlow.delete(chatId);
          return;
      }
      // Se o menu exige foto, mas o usuário enviou texto (e não era um comando)
      if (text) { 
          bot.sendMessage(chatId, "❌ Esperava uma **foto**, não texto. Por favor, envie a foto.", { parse_mode: "Markdown" });
          return;
      }
      // Ignora outros tipos de mídia se está esperando uma foto
      return; 
  }

  // --- 2. TRATAMENTO DE VALIDAÇÃO DE TEXTO ---
  
  // Se não estamos esperando uma validação de texto ou se não há texto, ignora.
  if (!text || !userCurrentFlowKey || !currentMenu?.requiresTextValidation) {
      // Se o usuário está mandando texto aleatório ou mídia onde o bot não espera nada.
      // Você pode adicionar um 'else' aqui para enviar uma mensagem padrão (ex: "Use o menu ou /start")
      // mas por enquanto, apenas ignora para não floodar.
      return; 
  }
  
  // A. Evita mensagem repetida (Proteção contra spam/erro do usuário)
  if (lastMessages.get(chatId) === text) {
    // Apenas retorna sem enviar a mensagem de erro novamente se o lastMessages já tiver sido configurado.
    return;
  }
  lastMessages.set(chatId, text);


  // B. Tenta validar o texto
  if (validateUserMessage(text)) {
      // *** LÓGICA DE SUCESSO E ENVIO DE ARQUIVO ***
      
      await bot.sendMessage(chatId, "✅ **Mensagem validada com sucesso!** O teu arquivo está a ser processado...", { parse_mode: "Markdown" });
      
      // Verifica o campo 'fileToSend'
      if (currentMenu.fileToSend) {
        try {
            await bot.sendDocument(chatId, currentMenu.fileToSend, { caption: "🎉 Arquivo de Acesso - MOZ Triple Way" });
            await bot.sendMessage(chatId, "🎉 Arquivo enviado! Aproveite a conexão.");
        } catch (error) {
            console.error(`❌ Erro ao enviar arquivo (${currentMenu.fileToSend}):`, error.message);
            await bot.sendMessage(chatId, "❌ Erro ao enviar o arquivo. Contacte o ADM.");
        }
      } else {
        await bot.sendMessage(chatId, "⚠️ Configuração: Não há arquivo definido para este menu. Contacte o ADM.");
      }
      
      // Finaliza o fluxo após validação (limpa o estado)
      userFlow.delete(chatId);
      
    } else {
      // *** MENSAGEM DE ERRO GENÉRICA E DISCRETA ***
      await bot.sendMessage(
        chatId,
        "❌ **Mensagem Inválida.**\n\nO comprovativo não está no formato correto. Por favor, verifique se copiou todo o SMS corretamente e **tente novamente**.",
        { parse_mode: "Markdown" }
      );
    }
});