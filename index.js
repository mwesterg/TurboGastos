require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const { createClient } = require('redis');

// --- Environment Variables ---
const API_KEY = process.env.API_KEY || 'your-secret-key';
const PORT = process.env.PORT || 3000;
const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const TARGET_GROUP_NAME = 'GastosMyM';
const REDIS_STREAM_NAME = 'gastos:msgs';

// --- Express App Setup ---
const app = express();
app.use(bodyParser.json());

// --- Middleware for API Key Authentication ---
const apiKeyAuth = (req, res, next) => {
    const providedKey = req.headers['x-api-key'] || req.query.api_key;
    if (providedKey && providedKey === API_KEY) {
        return next();
    }
    res.status(401).json({ error: 'Unauthorized' });
};

// --- WhatsApp Client Setup ---
const client = new Client({
    authStrategy: new LocalAuth({ dataPath: './sessions' }),
    puppeteer: {
        headless: true,
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    }
});

client.on('qr', qr => {
    console.log('QR RECEIVED, scan it with your phone');
    qrcode.generate(qr, { small: true });
});

client.on('ready', async () => {
    console.log('WhatsApp client is ready! Waiting for full connection before sending startup message...');

    // Wait up to 30 seconds for the client to be fully connected
    try {
        let state = await client.getState();
        let waitTime = 0;
        const maxWaitTime = 30; // 30 seconds

        while (state !== 'CONNECTED' && waitTime < maxWaitTime) {
            console.log(`Current state: ${state}. Waiting for connection... (${waitTime}s)`);
            await new Promise(resolve => setTimeout(resolve, 1000)); // wait 1 second
            state = await client.getState();
            waitTime++;
        }

        if (state !== 'CONNECTED') {
            console.error(`Error: Client did not reach a fully connected state within ${maxWaitTime} seconds.`);
            return;
        }

        console.log('Client is fully connected. Sending startup message...');
        const chats = await client.getChats();
        const targetGroup = chats.find(chat => chat.isGroup && chat.name === TARGET_GROUP_NAME);

        if (targetGroup) {
            const msg = '🤖: TurboGastos conectado y listo para procesar gastos.';
            await client.sendMessage(targetGroup.id._serialized, msg);
            console.log(`Successfully sent startup message to '${TARGET_GROUP_NAME}'.`);
        } else {
            console.warn(`Warning: Could not find target group '${TARGET_GROUP_NAME}' to send startup message.`);
        }
    } catch (error) {
        console.error('Error during ready state check or message sending:', error);
    }
});

client.on('auth_failure', msg => {
    console.error('AUTHENTICATION FAILURE:', msg);
});

client.on('disconnected', (reason) => {
    console.log('Client was logged out:', reason);
});

client.on('error', (err) => {
    console.error('WhatsApp client error:', err);
});

// --- Redis Client Setup ---
const redisClient = createClient({ url: REDIS_URL });

redisClient.on('error', (err) => console.error('Redis Client Error', err));

// --- Shared Message Processing Logic ---
async function processAndPublishMessage(msg, eventType) {
    console.log(`DEBUG: [${eventType}] event fired. From: ${msg.from}, To: ${msg.to}, Body: ${msg.body}`);

    // Ignore the bot's own automated replies to prevent processing loops
    if (msg.fromMe && msg.body.startsWith('🤖:')) {
        console.log(`DEBUG: Ignoring self-sent automated message from [${eventType}] event.`);
        return;
    }

    try {
        const chat = await msg.getChat();
        console.log(`DEBUG: Chat obtained for [${eventType}]. Name: ${chat.name}, IsGroup: ${chat.isGroup}`);

        if (chat.isGroup && chat.name === TARGET_GROUP_NAME) {
            console.log(`DEBUG: Message from [${eventType}] is from target group '${TARGET_GROUP_NAME}'. Processing...`);
            const contact = await msg.getContact();
            
            // Ensure all payload values are strings for Redis
            const payload = {
                wid: String(msg.id._serialized),
                chat_id: String(chat.id._serialized),
                chat_name: String(chat.name),
                sender_id: String(msg.author || msg.from),
                sender_name: String(contact.pushname || contact.name || 'Unknown'),
                timestamp: String(msg.timestamp),
                type: String(msg.type),
                body: String(msg.body),
            };

            console.log(`DEBUG: Publishing payload from [${eventType}] to Redis:`, payload);
            await redisClient.xAdd(REDIS_STREAM_NAME, '*', payload);
            console.log(`DEBUG: Successfully published to Redis stream '${REDIS_STREAM_NAME}' from [${eventType}].`);;
        } else {
            console.log(`DEBUG: Ignoring message from [${eventType}] because it is not from the target group. Chat: '${chat.name}', Target: '${TARGET_GROUP_NAME}'`);
        }
    } catch (error) {
        console.error(`Error processing message from [${eventType}] event:`, error);
    }
}

// --- Message Event Handlers ---
// Fires for incoming messages from others
client.on('message', (msg) => processAndPublishMessage(msg, 'message'));

// Fires for messages created by this client, including from the linked device
client.on('message_create', (msg) => {
    if (msg.fromMe) {
        processAndPublishMessage(msg, 'message_create');
    }
});

client.on('change_state', s => console.log('[WWebJS] State:', s));
client.on('auth_failure', msg => console.error('[WWebJS] AUTH FAILURE:', msg));
client.on('disconnected', reason => {
  console.warn('[WWebJS] DISCONNECTED:', reason);
  // Optionally: process.exit(1) and rely on Docker restart policy
});


process.on('SIGINT', async () => {
  console.log('Shutting down…');
  try { await client.destroy(); } catch {}
  process.exit(0);
});

// --- API Endpoints ---
app.get('/health', (req, res) => {
    res.status(200).json({ status: 'ok', ready: client.info ? true : false });
});

app.get('/groups', apiKeyAuth, async (req, res) => {
    try {
        const chats = await client.getChats();
        const groups = chats
            .filter(chat => chat.isGroup)
            .map(group => ({ id: group.id._serialized, name: group.name }));
        res.status(200).json(groups);
    } catch (error) {
        console.error('Error getting groups:', error);
        res.status(500).json({ error: 'Failed to retrieve groups' });
    }
});

// --- Main Application Logic ---
async function main() {
    await redisClient.connect();
    console.log('Connected to Redis for publishing.');

    // Create a dedicated subscriber client
    const redisSubscriber = redisClient.duplicate();
    await redisSubscriber.connect();
    console.log('Connected to Redis for subscribing.');

    // Subscribe to the confirmation channel
    await redisSubscriber.subscribe('gastos:confirmations', async (message) => {
        try {
            const { chat_id, original_wid } = JSON.parse(message);
            if (chat_id && original_wid) {
                console.log(`Sending confirmation reply to ${chat_id}`);
                await client.sendMessage(chat_id, '🤖: ✅ Gasto procesado.', { quotedMessageId: original_wid });
            }
        } catch (error) {
            console.error('Error handling confirmation message:', error);
        }
    });

    await client.initialize();
    console.log('WhatsApp client initialized.');

    app.listen(PORT, () => {
        console.log(`Ingestor API listening on http://localhost:${PORT}`);
    });
}

main().catch(console.error);