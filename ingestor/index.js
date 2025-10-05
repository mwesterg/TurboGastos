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
const TARGET_GROUP_NAME = process.env.WHATSAPP_GROUP_NAME || 'GastosMyM';
const REDIS_STREAM_NAME = 'gastos:msgs';

// --- Globals ---
let targetGroupId = null;

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
    console.log('WhatsApp client is ready! Searching for target group...');

    try {
        const chats = await client.getChats();
        const targetGroup = chats.find(chat => chat.isGroup && chat.name === TARGET_GROUP_NAME);

        if (targetGroup) {
            targetGroupId = targetGroup.id._serialized;
            console.log(`Target group '${TARGET_GROUP_NAME}' found with ID: ${targetGroupId}`);
            const msg = '🤖: TurboGastos conectado y listo para procesar gastos.';
            await client.sendMessage(targetGroupId, msg);
            console.log(`Successfully sent startup message to '${TARGET_GROUP_NAME}'.`);
        } else {
            console.warn(`Warning: Could not find target group '${TARGET_GROUP_NAME}'. No messages will be processed or sent.`);
        }
    } catch (error) {
        console.error('Error during ready event:', error);
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
    // Ignore the bot's own automated replies to prevent processing loops
    if (msg.fromMe && msg.body.startsWith('🤖:')) {
        console.log(`DEBUG: Ignoring self-sent automated message from [${eventType}].`);
        return;
    }

    // Only process if the target group has been found
    if (!targetGroupId) return;

    try {
        const chat = await msg.getChat();
        if (chat.id._serialized === targetGroupId) {
            console.log(`DEBUG: Message from '${TARGET_GROUP_NAME}' is being processed...`);
            const contact = await msg.getContact();
            
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

            await redisClient.xAdd(REDIS_STREAM_NAME, '*', payload);
            console.log(`DEBUG: Successfully published to Redis stream '${REDIS_STREAM_NAME}'.`);
        }
    } catch (error) {
        console.error(`Error processing message from [${eventType}] event:`, error);
    }
}

// --- Message Event Handlers ---
client.on('message', (msg) => processAndPublishMessage(msg, 'message'));

client.on('message_create', (msg) => {
    if (msg.fromMe) {
        processAndPublishMessage(msg, 'message_create');
    }
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

    const redisSubscriber = redisClient.duplicate();
    await redisSubscriber.connect();
    console.log('Connected to Redis for subscribing to confirmations.');

    await redisSubscriber.subscribe('gastos:confirmations', async (message) => {
        if (!targetGroupId) {
            console.error('Cannot send confirmation: Target group not found.');
            return;
        }

        try {
            const { original_wid, reply_message } = JSON.parse(message);
            if (reply_message) {
                console.log(`Sending reply to ${TARGET_GROUP_NAME}: "${reply_message}"`);
                const final_message = `🤖: ${reply_message}`;
                
                // Only quote the original message if it was a real WhatsApp message (not from Gmail)
                const options = original_wid ? { quotedMessageId: original_wid } : {};
                
                await client.sendMessage(targetGroupId, final_message, options);
            }
        } catch (error) {
            console.error('Error handling confirmation message:', error);
        }
    });

    await client.initialize().catch(console.error);
    console.log('WhatsApp client initialized.');

    app.listen(PORT, () => {
        console.log(`Ingestor API listening on http://localhost:${PORT}`);
    });
}

main().catch(console.error);