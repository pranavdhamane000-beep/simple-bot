import os
import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, Optional
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from aiohttp import web

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# In-memory storage
chat_sessions: Dict[str, Dict] = {}
user_sessions: Dict[int, str] = {}
chat_links: Dict[str, int] = {}
messages: Dict[str, Dict] = {}

# Constants
CHAT_EXPIRY = 3600
MESSAGE_EXPIRY = 60

class ChatManager:
    @staticmethod
    def create_chat_session(user_id: int) -> str:
        """Create a new chat session and return the link ID"""
        link_id = f"link_{user_id}_{int(datetime.now().timestamp())}"
        
        session_data = {
            'user1': user_id,
            'user2': None,
            'created_at': datetime.now().isoformat(),
            'active': True
        }
        
        chat_sessions[link_id] = session_data
        chat_links[link_id] = user_id
        user_sessions[user_id] = link_id
        
        return link_id
    
    @staticmethod
    def join_chat(link_id: str, user_id: int) -> Optional[Dict]:
        """Join an existing chat session"""
        session = chat_sessions.get(link_id)
        
        if not session:
            return None
        
        if not session['active'] or session['user2'] is not None:
            return None
        
        if session['user1'] == user_id:
            return None
        
        session['user2'] = user_id
        user_sessions[user_id] = link_id
        
        return session
    
    @staticmethod
    def get_chat_session(link_id: str) -> Optional[Dict]:
        """Get chat session data"""
        return chat_sessions.get(link_id)
    
    @staticmethod
    def get_user_chat(user_id: int) -> Optional[str]:
        """Get active chat link for a user"""
        return user_sessions.get(user_id)
    
    @staticmethod
    def end_chat(link_id: str, user_id: int = None):
        """End a chat session"""
        session = chat_sessions.get(link_id)
        
        if session:
            session['active'] = False
            
            if session['user1'] and session['user1'] in user_sessions:
                del user_sessions[session['user1']]
            if session['user2'] and session['user2'] in user_sessions:
                del user_sessions[session['user2']]
            
            if link_id in chat_links:
                del chat_links[link_id]
            
            if link_id in chat_sessions:
                del chat_sessions[link_id]
            
            messages_to_delete = [k for k in messages.keys() if k.startswith(f"{link_id}:")]
            for key in messages_to_delete:
                del messages[key]
    
    @staticmethod
    def store_message(link_id: str, message_id: int, sender_id: int, receiver_id: int):
        """Store message metadata for auto-deletion"""
        message_key = f"{link_id}:{message_id}"
        message_data = {
            'message_id': message_id,
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'sent_at': datetime.now().isoformat(),
            'delivered': False
        }
        messages[message_key] = message_data
        return message_key

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - create a new chat link or join existing"""
    user_id = update.effective_user.id
    
    # Check if this is a deep link (joining a chat)
    if context.args and context.args[0].startswith('link_'):
        await join_chat(update, context)
        return
    
    # Create new chat session
    existing_chat = ChatManager.get_user_chat(user_id)
    if existing_chat:
        session = ChatManager.get_chat_session(existing_chat)
        if session and session['active']:
            # Already in chat, just send the link again
            return
    
    try:
        link_id = ChatManager.create_chat_session(user_id)
        bot_username = context.bot.username
        chat_link = f"https://t.me/{bot_username}?start={link_id}"
        
        keyboard = [
            [InlineKeyboardButton("📋 Copy Link", callback_data=f"copy_{link_id}")],
            [InlineKeyboardButton("🔗 Share Link", switch_inline_query=chat_link)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"`{chat_link}`\n\n"
            f"Share with ONE person to start chatting",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error creating chat session: {e}")

async def join_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle joining a chat via link"""
    user_id = update.effective_user.id
    
    if not context.args:
        return
    
    link_id = context.args[0]
    
    existing_chat = ChatManager.get_user_chat(user_id)
    if existing_chat:
        session = ChatManager.get_chat_session(existing_chat)
        if session and session['active']:
            return
    
    try:
        session = ChatManager.join_chat(link_id, user_id)
        
        if not session:
            return
        
        user1_id = session['user1']
        
        # Only notify the chat creator that someone joined
        try:
            await context.bot.send_message(
                user1_id,
                "_"
            )
        except Exception as e:
            logger.error(f"Error notifying user1: {e}")
        
        # Don't send any message to the joining user
        # They can just start chatting
        
    except Exception as e:
        logger.error(f"Error joining chat: {e}")

async def end_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /end command - end current chat"""
    user_id = update.effective_user.id
    link_id = ChatManager.get_user_chat(user_id)
    
    if not link_id:
        return
    
    session = ChatManager.get_chat_session(link_id)
    
    if session and session['active']:
        other_user_id = session['user1'] if session['user1'] != user_id else session['user2']
        ChatManager.end_chat(link_id, user_id)

async def delete_message_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = 60):
    """Delete a message after specified delay"""
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Failed to delete message {message_id}: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular messages (anonymous chatting)"""
    user_id = update.effective_user.id
    message_text = update.message.text
    message_id = update.message.message_id
    
    if not message_text:
        return
    
    link_id = ChatManager.get_user_chat(user_id)
    
    if not link_id:
        return
    
    session = ChatManager.get_chat_session(link_id)
    
    if not session or not session['active']:
        ChatManager.end_chat(link_id)
        return
    
    other_user_id = session['user1'] if session['user1'] != user_id else session['user2']
    
    if not other_user_id:
        return
    
    ChatManager.store_message(link_id, message_id, user_id, other_user_id)
    
    try:
        # Send the message to the other user
        sent_message = await context.bot.send_message(
            other_user_id,
            f"💬 {message_text}"
        )
        
        ChatManager.store_message(link_id, sent_message.message_id, user_id, other_user_id)
        
        # Schedule deletion of both messages
        asyncio.create_task(
            delete_message_after_delay(
                context, 
                update.effective_chat.id, 
                message_id, 
                MESSAGE_EXPIRY
            )
        )
        
        asyncio.create_task(
            delete_message_after_delay(
                context, 
                other_user_id, 
                sent_message.message_id, 
                MESSAGE_EXPIRY
            )
        )
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("copy_"):
        link_id = query.data.replace("copy_", "")
        chat_link = f"https://t.me/{context.bot.username}?start={link_id}"
        await query.message.reply_text(
            f"`{chat_link}`",
            parse_mode='Markdown'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    # Don't send any help message
    pass

# Health check endpoint
async def health_check(request):
    """Handles GET requests for health checks"""
    return web.Response(text="OK", status=200)

async def start_health_server():
    """Runs a simple web server for health checks"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    print("🩺 Health server running on port 8080")
    await site.start()
    await asyncio.Event().wait()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

async def async_main() -> None:
    """Async main function to start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("end", end_chat))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_error_handler(error_handler)

    await application.initialize()
    
    health_task = asyncio.create_task(start_health_server())

    print("🤖 Bot is starting...")
    print(f"Bot username: @{application.bot.username}")
    
    try:
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()
    finally:
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass
        await application.stop()
        await application.shutdown()

def main() -> None:
    """Entry point for the bot"""
    asyncio.run(async_main())

if __name__ == '__main__':
    main()
