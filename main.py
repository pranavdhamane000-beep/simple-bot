import os
import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, Optional
import redis
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Add this near the top of your bot.py with other imports
from aiohttp import web
import asyncio
import threading

# ... (your existing imports and code)

async def health_check(request):
    """Handles GET requests for health checks"""
    return web.Response(text="I'm alive! (Bot is running)")

async def start_health_server():
    """Runs a simple web server for health checks"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080) # You can use any available port
    print("🩺 Health server running on port 8080")
    await site.start()
    # Keep the server running
    await asyncio.Event().wait()

# In your main() function, run the health server in the background
def main():
    # ... (your existing bot initialization code)

    # Start the health check server in the background using asyncio
    loop = asyncio.get_event_loop()
    asyncio.create_task(start_health_server())

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Redis for session management
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(REDIS_URL)

# Bot token
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# Constants
CHAT_SESSION_PREFIX = "chat_session:"
USER_SESSION_PREFIX = "user_session:"
CHAT_LINK_PREFIX = "chat_link:"
MESSAGE_PREFIX = "message:"
CHAT_EXPIRY = 3600  # 1 hour
MESSAGE_EXPIRY = 60  # 1 minute in seconds

class ChatManager:
    @staticmethod
    def create_chat_session(user_id: int) -> str:
        """Create a new chat session and return the link ID"""
        link_id = f"link_{user_id}_{int(datetime.now().timestamp())}"
        
        # Store chat session
        session_data = {
            'user1': user_id,
            'user2': None,
            'created_at': datetime.now().isoformat(),
            'active': True
        }
        
        redis_client.setex(
            f"{CHAT_SESSION_PREFIX}{link_id}",
            CHAT_EXPIRY,
            json.dumps(session_data)
        )
        
        # Store link to user mapping
        redis_client.setex(
            f"{CHAT_LINK_PREFIX}{link_id}",
            CHAT_EXPIRY,
            str(user_id)
        )
        
        # Store user's active chat
        redis_client.setex(
            f"{USER_SESSION_PREFIX}{user_id}",
            CHAT_EXPIRY,
            link_id
        )
        
        return link_id
    
    @staticmethod
    def join_chat(link_id: str, user_id: int) -> Optional[Dict]:
        """Join an existing chat session"""
        session_key = f"{CHAT_SESSION_PREFIX}{link_id}"
        session_data = redis_client.get(session_key)
        
        if not session_data:
            return None
        
        session = json.loads(session_data)
        
        # Check if chat is still active and not full
        if not session['active'] or session['user2'] is not None:
            return None
        
        # Check if user is trying to join their own chat
        if session['user1'] == user_id:
            return None
        
        # Add second user
        session['user2'] = user_id
        redis_client.setex(session_key, CHAT_EXPIRY, json.dumps(session))
        
        # Store user's active chat
        redis_client.setex(
            f"{USER_SESSION_PREFIX}{user_id}",
            CHAT_EXPIRY,
            link_id
        )
        
        return session
    
    @staticmethod
    def get_chat_session(link_id: str) -> Optional[Dict]:
        """Get chat session data"""
        session_data = redis_client.get(f"{CHAT_SESSION_PREFIX}{link_id}")
        if session_data:
            return json.loads(session_data)
        return None
    
    @staticmethod
    def get_user_chat(user_id: int) -> Optional[str]:
        """Get active chat link for a user"""
        link_id = redis_client.get(f"{USER_SESSION_PREFIX}{user_id}")
        if link_id:
            return link_id.decode('utf-8')
        return None
    
    @staticmethod
    def end_chat(link_id: str, user_id: int = None):
        """End a chat session"""
        session_key = f"{CHAT_SESSION_PREFIX}{link_id}"
        session_data = redis_client.get(session_key)
        
        if session_data:
            session = json.loads(session_data)
            session['active'] = False
            redis_client.setex(session_key, 300, json.dumps(session))  # Keep for 5 mins
            
            # Remove user sessions
            if session['user1']:
                redis_client.delete(f"{USER_SESSION_PREFIX}{session['user1']}")
            if session['user2']:
                redis_client.delete(f"{USER_SESSION_PREFIX}{session['user2']}")
            
            # Remove link
            redis_client.delete(f"{CHAT_LINK_PREFIX}{link_id}")
            
            # Clean up any pending messages
            pattern = f"{MESSAGE_PREFIX}{link_id}:*"
            for key in redis_client.scan_iter(match=pattern):
                redis_client.delete(key)
    
    @staticmethod
    def store_message(link_id: str, message_id: int, sender_id: int, receiver_id: int):
        """Store message metadata for auto-deletion"""
        message_key = f"{MESSAGE_PREFIX}{link_id}:{message_id}"
        message_data = {
            'message_id': message_id,
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'sent_at': datetime.now().isoformat(),
            'delivered': False
        }
        redis_client.setex(message_key, MESSAGE_EXPIRY + 10, json.dumps(message_data))
        return message_key
    
    @staticmethod
    def mark_message_delivered(link_id: str, message_id: int):
        """Mark message as delivered (seen by receiver)"""
        message_key = f"{MESSAGE_PREFIX}{link_id}:{message_id}"
        message_data = redis_client.get(message_key)
        if message_data:
            data = json.loads(message_data)
            data['delivered'] = True
            data['delivered_at'] = datetime.now().isoformat()
            redis_client.setex(message_key, MESSAGE_EXPIRY + 5, json.dumps(data))
            return True
        return False
    
    @staticmethod
    def get_message(link_id: str, message_id: int) -> Optional[Dict]:
        """Get message data"""
        message_key = f"{MESSAGE_PREFIX}{link_id}:{message_id}"
        message_data = redis_client.get(message_key)
        if message_data:
            return json.loads(message_data)
        return None

# Bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user_id = update.effective_user.id
    
    # Check if this is a deep link (joining a chat)
    if context.args and context.args[0].startswith('link_'):
        await join_chat(update, context)
        return
    
    welcome_text = """
👋 Welcome to Anonymous Chat Bot!

🔒 Your identity is completely hidden
👤 No one can see your name or username
💬 Chat anonymously with others
🗑️ Messages auto-delete 1 minute after being seen

Commands:
/chat - Start a new anonymous chat
/end - End current chat
/help - Show this help message

To start chatting, use /chat and share the generated link with someone!
    """
    await update.message.reply_text(welcome_text)

async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /chat command - create a new chat link"""
    user_id = update.effective_user.id
    
    # Check if user is already in a chat
    existing_chat = ChatManager.get_user_chat(user_id)
    if existing_chat:
        session = ChatManager.get_chat_session(existing_chat)
        if session and session['active']:
            await update.message.reply_text(
                "⚠️ You're already in a chat! Use /end to end the current chat first."
            )
            return
        else:
            # Clean up stale session
            ChatManager.end_chat(existing_chat)
    
    # Create new chat session
    link_id = ChatManager.create_chat_session(user_id)
    
    # Generate bot link
    bot_username = context.bot.username
    chat_link = f"https://t.me/{bot_username}?start={link_id}"
    
    # Create inline keyboard
    keyboard = [
        [InlineKeyboardButton("📋 Copy Link", callback_data=f"copy_{link_id}")],
        [InlineKeyboardButton("🔗 Share Link", switch_inline_query=chat_link)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔐 Your anonymous chat link is ready!\n\n"
        f"Share this link with ONE person to start chatting:\n"
        f"`{chat_link}`\n\n"
        f"⚠️ Link expires in 1 hour\n"
        f"⚠️ Only the first person who clicks will join\n"
        f"⚠️ You can't join your own chat\n"
        f"🗑️ Messages auto-delete 1 minute after being seen",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def join_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle joining a chat via link"""
    user_id = update.effective_user.id
    
    # Get link ID from the start parameter
    if not context.args:
        await update.message.reply_text("❌ Invalid chat link!")
        return
    
    link_id = context.args[0]
    
    # Check if user is already in a chat
    existing_chat = ChatManager.get_user_chat(user_id)
    if existing_chat:
        session = ChatManager.get_chat_session(existing_chat)
        if session and session['active']:
            await update.message.reply_text(
                "⚠️ You're already in a chat! Use /end to end the current chat first."
            )
            return
    
    # Join the chat
    session = ChatManager.join_chat(link_id, user_id)
    
    if not session:
        await update.message.reply_text(
            "❌ This chat link is invalid or already in use!\n\n"
            "Possible reasons:\n"
            "• Link has expired (1 hour limit)\n"
            "• Someone already joined this chat\n"
            "• You're trying to join your own chat"
        )
        return
    
    # Notify both users
    user1_id = session['user1']
    user2_id = session['user2']
    
    try:
        await context.bot.send_message(
            user1_id,
            "✅ Someone has joined your chat! Start messaging anonymously.\n\n"
            "💬 Send messages to chat anonymously\n"
            "🗑️ Messages auto-delete 1 minute after being seen\n"
            "🚫 Use /end to end the chat"
        )
    except Exception as e:
        logger.error(f"Error notifying user1: {e}")
    
    await update.message.reply_text(
        "✅ You've joined the anonymous chat!\n\n"
        "💬 Send messages to chat anonymously\n"
        "📤 Your identity is completely hidden\n"
        "🗑️ Messages auto-delete 1 minute after being seen\n"
        "🚫 Use /end to end the chat"
    )

async def end_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /end command - end current chat"""
    user_id = update.effective_user.id
    
    # Find user's chat
    link_id = ChatManager.get_user_chat(user_id)
    
    if not link_id:
        await update.message.reply_text("❌ You're not in any active chat!")
        return
    
    # Get chat session
    session = ChatManager.get_chat_session(link_id)
    
    if session and session['active']:
        # Get other user ID
        other_user_id = session['user1'] if session['user1'] != user_id else session['user2']
        
        # End the chat
        ChatManager.end_chat(link_id, user_id)
        
        # Notify other user
        if other_user_id:
            try:
                await context.bot.send_message(
                    other_user_id,
                    "🔚 The other user has ended the chat."
                )
            except Exception as e:
                logger.error(f"Error notifying other user: {e}")
        
        await update.message.reply_text("🔚 Chat ended successfully!")
    else:
        await update.message.reply_text("❌ Chat not found or already ended!")

async def delete_message_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = 60):
    """Delete a message after specified delay"""
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Deleted message {message_id} in chat {chat_id} after {delay} seconds")
    except Exception as e:
        logger.error(f"Failed to delete message {message_id}: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular messages (anonymous chatting)"""
    user_id = update.effective_user.id
    message_text = update.message.text
    message_id = update.message.message_id
    
    if not message_text:
        return
    
    # Find user's active chat
    link_id = ChatManager.get_user_chat(user_id)
    
    if not link_id:
        await update.message.reply_text(
            "❌ You're not in an active chat!\n"
            "Use /chat to start a new anonymous chat."
        )
        return
    
    # Get chat session
    session = ChatManager.get_chat_session(link_id)
    
    if not session or not session['active']:
        await update.message.reply_text("❌ This chat is no longer active!")
        # Clean up
        ChatManager.end_chat(link_id)
        return
    
    # Determine other user
    other_user_id = session['user1'] if session['user1'] != user_id else session['user2']
    
    if not other_user_id:
        await update.message.reply_text("❌ No other user in the chat!")
        return
    
    # Store message in Redis for tracking
    ChatManager.store_message(link_id, message_id, user_id, other_user_id)
    
    # Send message to other user
    try:
        # Send the message to the other user
        sent_message = await context.bot.send_message(
            other_user_id,
            f"💬 {message_text}"
        )
        
        # Store the forwarded message ID for deletion
        ChatManager.store_message(link_id, sent_message.message_id, user_id, other_user_id)
        
        # Schedule deletion of the sender's original message
        asyncio.create_task(
            delete_message_after_delay(
                context, 
                update.effective_chat.id, 
                message_id, 
                MESSAGE_EXPIRY
            )
        )
        
        # Schedule deletion of the sent message (to other user)
        asyncio.create_task(
            delete_message_after_delay(
                context, 
                other_user_id, 
                sent_message.message_id, 
                MESSAGE_EXPIRY
            )
        )
        
        # Send confirmation to sender (this will also be deleted)
        confirm_msg = await update.message.reply_text(
            f"✅ Message sent anonymously (will auto-delete in {MESSAGE_EXPIRY}s)"
        )
        
        # Delete confirmation message after 5 seconds (not 1 minute)
        asyncio.create_task(
            delete_message_after_delay(
                context, 
                update.effective_chat.id, 
                confirm_msg.message_id, 
                5
            )
        )
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        error_msg = await update.message.reply_text("❌ Failed to send message. The other user might have left.")
        # Delete error message after 5 seconds
        asyncio.create_task(
            delete_message_after_delay(
                context, 
                update.effective_chat.id, 
                error_msg.message_id, 
                5
            )
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("copy_"):
        link_id = query.data.replace("copy_", "")
        chat_link = f"https://t.me/{context.bot.username}?start={link_id}"
        await query.message.reply_text(
            f"📋 Share this link with someone:\n\n"
            f"`{chat_link}`\n\n"
            f"⚠️ Only the first person who clicks will join\n"
            f"🗑️ Messages auto-delete 1 minute after being seen",
            parse_mode='Markdown'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    help_text = """
🤖 Anonymous Chat Bot Help

Commands:
/chat - Create a new anonymous chat link
/end - End your current chat
/help - Show this help message

How it works:
1. Use /chat to generate a unique link
2. Share the link with someone (only ONE person)
3. When they join, you can chat anonymously
4. Your name and username are never shown
5. Messages auto-delete 1 minute after being seen

Privacy Features:
🔒 Complete anonymity
👤 No personal information shared
🗑️ No chat history stored
⏰ Messages auto-delete after 60 seconds
🔐 End-to-end private chatting

Auto-Delete Details:
• Messages are deleted 60 seconds after being sent
• Both sender and receiver see messages disappear
• Confirmation messages delete after 5 seconds
• No message history is stored

⚠️ Important Notes:
• Link expires in 1 hour
• Only the first person who clicks can join
• You can't join your own chat
• Both users must stay in the chat
    """
    await update.message.reply_text(help_text)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main() -> None:
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("chat", chat_command))
    application.add_handler(CommandHandler("end", end_chat))
    application.add_handler(CommandHandler("help", help_command))
    
    # Add callback handler for buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add message handler for chat messages
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    
    # Add error handler
    application.add_error_handler(error_handler)

    # Start the Bot
    print("🤖 Bot is starting...")
    print(f"Bot username: @{application.bot.username}")
    print(f"🗑️ Messages will auto-delete after {MESSAGE_EXPIRY} seconds")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
