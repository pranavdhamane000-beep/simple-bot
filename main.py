import os
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# In-memory storage (clears when bot restarts)
VIDEOS: list = []

# ADMIN USER ID - REPLACE WITH YOUR TELEGRAM USER ID
# How to get it: Message @userinfobot on Telegram
ADMIN_ID: int = 6234222988  # ⚠️ CHANGE THIS!


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message"""
    await update.message.reply_text(
        "🎬 *Video Library Bot*\n\n"
        "Send me any video and I'll store it in memory!\n\n"
        "*Commands:*\n"
        "📹 /send10 - Show first 10 videos\n"
        "📹 /send50 - Show first 50 videos\n"
        "📹 /send100 - Show first 100 videos\n"
        "📹 /sendall - Show all videos\n"
        "📊 /total - Show total videos in library\n"
        "🆕 /recent - Show last 5 videos added\n"
        "ℹ️ /status - Show bot status\n\n"
        "*Admin commands:*\n"
        "🗑️ /clear - Delete all videos\n"
        "💾 /backup - Export video list to file\n\n"
        "⚠️ *Note:* Videos disappear when the bot restarts!",
        parse_mode='Markdown'
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save video to memory"""
    global VIDEOS
    
    if not update.message.video:
        await update.message.reply_text("❌ Please send a video file.")
        return
    
    # Get video information
    video = update.message.video
    file_id = video.file_id
    caption = update.message.caption or "No caption"
    user_name = update.effective_user.first_name
    user_id = update.effective_user.id
    
    # Store in memory
    VIDEOS.append({
        'file_id': file_id,
        'caption': caption,
        'sender_name': user_name,
        'sender_id': user_id,
        'file_size': video.file_size,
        'width': video.width,
        'height': video.height,
        'timestamp': datetime.now().isoformat()
    })
    
    await update.message.reply_text(
        f"✅ *Video saved!*\n\n"
        f"📹 Total videos: {len(VIDEOS)}\n"
        f"📝 Caption: {caption[:100]}\n"
        f"👤 By: {user_name}\n"
        f"📏 Size: {video.file_size // 1024} KB",
        parse_mode='Markdown'
    )


async def send_videos(update: Update, context: ContextTypes.DEFAULT_TYPE, limit: int = None) -> None:
    """Send requested number of videos"""
    global VIDEOS
    
    if not VIDEOS:
        await update.message.reply_text("📭 *No videos in library!*\n\nSend me some videos first!", parse_mode='Markdown')
        return
    
    # Determine count to send
    if limit is None:
        count = len(VIDEOS)
        title = "All Videos"
    else:
        count = min(limit, len(VIDEOS))
        title = f"First {count} Videos"
    
    status_msg = await update.message.reply_text(f"📹 *{title}*\n\nSending {count} of {len(VIDEOS)} total videos...", parse_mode='Markdown')
    
    sent_count = 0
    failed_count = 0
    
    for idx, video in enumerate(VIDEOS[:count], start=1):
        try:
            await update.message.reply_video(
                video['file_id'],
                caption=f"🎬 *Video #{idx}*\n📝 {video['caption'][:200]}\n👤 By: {video['sender_name']}",
                parse_mode='Markdown',
                timeout=30
            )
            sent_count += 1
            # Small delay to avoid flooding
            await asyncio.sleep(0.5)
        except Exception as e:
            failed_count += 1
            print(f"Failed to send video #{idx}: {e}")
    
    await status_msg.delete()
    
    await update.message.reply_text(
        f"✅ *Finished!*\n\n"
        f"✓ Sent: {sent_count} videos\n"
        f"✗ Failed: {failed_count} videos\n"
        f"📊 Total in library: {len(VIDEOS)}",
        parse_mode='Markdown'
    )


async def send10(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send first 10 videos"""
    await send_videos(update, context, limit=10)


async def send50(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send first 50 videos"""
    await send_videos(update, context, limit=50)


async def send100(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send first 100 videos"""
    await send_videos(update, context, limit=100)


async def sendall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send all videos"""
    await send_videos(update, context, limit=None)


async def total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show total video count and statistics"""
    global VIDEOS
    
    if not VIDEOS:
        await update.message.reply_text("📊 No videos in library.")
        return
    
    total_size = sum(v['file_size'] for v in VIDEOS)
    unique_senders = len(set(v['sender_id'] for v in VIDEOS))
    
    await update.message.reply_text(
        f"📊 *Library Statistics*\n\n"
        f"📹 Total videos: {len(VIDEOS)}\n"
        f"💾 Total size: {total_size // (1024*1024)} MB\n"
        f"👥 Unique senders: {unique_senders}\n"
        f"🐍 Python version: 3.14.3\n\n"
        f"⚠️ *Note:* Data resets on restart!",
        parse_mode='Markdown'
    )


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show last 5 videos added"""
    global VIDEOS
    
    if not VIDEOS:
        await update.message.reply_text("No videos yet!")
        return
    
    recent_count = min(5, len(VIDEOS))
    recent_videos = VIDEOS[-recent_count:]
    
    message = f"🆕 *Last {recent_count} Videos Added*\n\n"
    for idx, video in enumerate(reversed(recent_videos), start=1):
        message += f"{idx}. 📝 {video['caption'][:50]}\n"
        message += f"   👤 {video['sender_name']} | 📏 {video['file_size'] // 1024}KB\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin only: Clear all videos"""
    global VIDEOS
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ *Access Denied!*\n\nThis command is only for the bot admin.", parse_mode='Markdown')
        return
    
    if not VIDEOS:
        await update.message.reply_text("Library is already empty!")
        return
    
    count = len(VIDEOS)
    VIDEOS = []
    await update.message.reply_text(f"🗑️ *Cleared {count} videos from library!*", parse_mode='Markdown')


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin only: Export video list to file"""
    global VIDEOS
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Access Denied!")
        return
    
    if not VIDEOS:
        await update.message.reply_text("No videos to backup!")
        return
    
    # Create backup content
    backup_text = f"Video Library Backup\n"
    backup_text += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    backup_text += f"Total Videos: {len(VIDEOS)}\n"
    backup_text += "="*50 + "\n\n"
    
    for idx, video in enumerate(VIDEOS, start=1):
        backup_text += f"Video #{idx}\n"
        backup_text += f"File ID: {video['file_id']}\n"
        backup_text += f"Caption: {video['caption']}\n"
        backup_text += f"Sender: {video['sender_name']} (ID: {video['sender_id']})\n"
        backup_text += f"Size: {video['file_size']} bytes\n"
        backup_text += "-"*30 + "\n"
    
    # Save to file
    filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(backup_text)
    
    # Send file
    with open(filename, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=filename,
            caption=f"📦 Backup of {len(VIDEOS)} videos"
        )
    
    # Clean up
    os.remove(filename)
    await update.message.reply_text(f"💾 Backup created successfully!")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot status"""
    uptime_status = "Data in memory (resets on restart)"
    await update.message.reply_text(
        f"🤖 *Bot Status*\n\n"
        f"✅ Bot is running\n"
        f"📹 Videos in memory: {len(VIDEOS)}\n"
        f"🐍 Python version: 3.14.3\n"
        f"📦 Library: python-telegram-bot\n"
        f"👤 Admin ID: {ADMIN_ID}\n"
        f"🔄 Storage: {uptime_status}\n"
        f"🌐 Host: Render.com",
        parse_mode='Markdown'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message"""
    await start(update, context)


def main() -> None:
    """Start the bot"""
    print("🤖 Starting Video Library Bot...")
    print(f"🐍 Python version: 3.14.3 compatible")
    print("=" * 50)
    
    # Get bot token from environment variable
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN environment variable not set!")
        print("Please set it using: export TELEGRAM_BOT_TOKEN='your_token_here'")
        return
    
    print(f"✅ Bot token found")
    print(f"👤 Admin ID set to: {ADMIN_ID}")
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("send10", send10))
    application.add_handler(CommandHandler("send50", send50))
    application.add_handler(CommandHandler("send100", send100))
    application.add_handler(CommandHandler("sendall", sendall))
    application.add_handler(CommandHandler("total", total))
    application.add_handler(CommandHandler("recent", recent))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("backup", backup))
    application.add_handler(CommandHandler("status", status))
    
    # Handle video messages
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    
    print(f"✅ Commands registered: /send10, /send50, /send100, /sendall, /total, /recent, /clear, /backup, /status")
    print("🤖 Bot is polling for updates...")
    print("=" * 50)
    
    # Start the bot
    application.run_polling()


if __name__ == "__main__":
    main()
