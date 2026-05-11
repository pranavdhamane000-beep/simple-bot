import os
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# In-memory storage (clears when bot restarts)
VIDEOS = []

# REPLACE WITH YOUR TELEGRAM USER ID
ADMIN_ID = 6234222988  # Your ID

# Store user states (not needed for basic functionality)
user_states = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Video Library Bot*\n\n"
        "Send me ANY video and I'll store it!\n\n"
        "*How to add videos:*\n"
        "• Upload video directly (📎 → Video)\n"
        "• Send video as file (📎 → File)\n"
        "• Forward any video to me\n\n"
        "*Commands:*\n"
        "/send10 - Get first 10 videos\n"
        "/send50 - Get first 50 videos\n"
        "/send100 - Get first 100 videos\n"
        "/sendall - Get all videos\n"
        "/total - Show statistics\n"
        "/recent - Last 5 videos\n\n"
        "*Admin:* /clear - Delete all videos\n\n"
        "⚠️ Videos disappear when bot restarts!",
        parse_mode='Markdown'
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save ANY video to memory"""
    global VIDEOS
    
    video_file_id = None
    video_caption = ""
    video_size = 0
    video_type = "Unknown"
    
    # Check for different video types
    if update.message.video:
        video_file_id = update.message.video.file_id
        video_caption = update.message.caption or "No caption"
        video_size = update.message.video.file_size
        video_type = "Video"
        
    elif update.message.document:
        # Check if document is a video
        mime_type = update.message.document.mime_type or ""
        if mime_type.startswith('video/'):
            video_file_id = update.message.document.file_id
            video_caption = update.message.caption or "No caption"
            video_size = update.message.document.file_size
            video_type = "Video (Document)"
        else:
            await update.message.reply_text("❌ Please send a VIDEO file!")
            return
            
    elif update.message.animation:
        video_file_id = update.message.animation.file_id
        video_caption = update.message.caption or "Animation/GIF"
        video_size = update.message.animation.file_size
        video_type = "Animation"
        
    else:
        await update.message.reply_text("❌ Please send a video file!")
        return
    
    # Save to memory
    VIDEOS.append({
        'file_id': video_file_id,
        'caption': video_caption,
        'sender_name': update.effective_user.first_name,
        'sender_id': update.effective_user.id,
        'file_size': video_size,
        'type': video_type,
        'timestamp': datetime.now().isoformat()
    })
    
    await update.message.reply_text(
        f"✅ *Video #{len(VIDEOS)} saved!*\n\n"
        f"📹 Total videos: {len(VIDEOS)}\n"
        f"📝 Caption: {video_caption[:50]}\n"
        f"👤 By: {update.effective_user.first_name}\n"
        f"📏 Size: {video_size // 1024} KB\n\n"
        f"Try /send10 to see all videos!",
        parse_mode='Markdown'
    )


async def send_videos(update: Update, context: ContextTypes.DEFAULT_TYPE, limit=None):
    """Send requested number of videos"""
    global VIDEOS
    
    if not VIDEOS:
        await update.message.reply_text("📭 *No videos in library!*\n\nPlease send me some videos first!", parse_mode='Markdown')
        return
    
    # Determine how many to send
    if limit is None:
        count = len(VIDEOS)
        title = "All Videos"
    else:
        count = min(limit, len(VIDEOS))
        title = f"First {count} Videos"
    
    # Send initial message
    await update.message.reply_text(f"📹 *{title}*\n\nSending {count} of {len(VIDEOS)} total videos...", parse_mode='Markdown')
    
    sent_count = 0
    failed_count = 0
    
    for idx, video in enumerate(VIDEOS[:count], start=1):
        try:
            # Try to send as video
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video['file_id'],
                caption=f"🎬 Video #{idx}\n📝 {video['caption'][:100]}",
                timeout=30
            )
            sent_count += 1
            await asyncio.sleep(0.3)  # Small delay between videos
            
        except Exception as e:
            # If video fails, try sending as document
            try:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=video['file_id'],
                    caption=f"🎬 Video #{idx} (as file)\n📝 {video['caption'][:100]}",
                    timeout=30
                )
                sent_count += 1
            except:
                failed_count += 1
                print(f"Failed to send video #{idx}: {e}")
    
    # Send summary
    await update.message.reply_text(
        f"✅ *Delivery Complete!*\n\n"
        f"✓ Sent: {sent_count} videos\n"
        f"✗ Failed: {failed_count} videos\n"
        f"📊 Videos in library: {len(VIDEOS)}",
        parse_mode='Markdown'
    )


async def send10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=10)


async def send50(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=50)


async def send100(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=100)


async def sendall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=None)


async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show statistics"""
    global VIDEOS
    
    if not VIDEOS:
        await update.message.reply_text("📊 No videos in library yet!")
        return
    
    total_size = sum(v.get('file_size', 0) for v in VIDEOS)
    unique_senders = len(set(v.get('sender_id', 0) for v in VIDEOS))
    
    await update.message.reply_text(
        f"📊 *Library Statistics*\n\n"
        f"📹 Total videos: {len(VIDEOS)}\n"
        f"💾 Total size: {total_size // (1024*1024)} MB\n"
        f"👥 Total senders: {unique_senders}\n"
        f"📝 Latest: {VIDEOS[-1]['caption'][:50] if VIDEOS else 'None'}\n\n"
        f"Use /send10 to watch videos!",
        parse_mode='Markdown'
    )


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show last 5 videos info"""
    if not VIDEOS:
        await update.message.reply_text("No videos yet!")
        return
    
    recent_count = min(5, len(VIDEOS))
    recent_videos = VIDEOS[-recent_count:]
    
    msg = f"🆕 *Last {recent_count} videos added:*\n\n"
    for idx, video in enumerate(reversed(recent_videos), start=1):
        size_mb = video.get('file_size', 0) // (1024*1024)
        msg += f"{idx}. 📝 {video['caption'][:40]}\n"
        msg += f"   👤 {video['sender_name']} | 📏 {size_mb} MB\n\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')
    
    # Offer to send them
    await update.message.reply_text(
        f"Type /send{recent_count} to watch these videos!",
        parse_mode='Markdown'
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot status"""
    await update.message.reply_text(
        f"🤖 *Bot Status*\n\n"
        f"✅ Bot is running\n"
        f"🐍 Python 3.14.3\n"
        f"📹 Videos in library: {len(VIDEOS)}\n"
        f"🎬 Supports: All video formats\n"
        f"💾 Storage: RAM (resets on restart)\n\n"
        f"Commands ready: /send10, /send50, /send100, /sendall",
        parse_mode='Markdown'
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages that aren't commands"""
    text = update.message.text.lower()
    
    # If user just types a number, send that many videos
    if text.isdigit():
        num = int(text)
        if 1 <= num <= 100:
            await send_videos(update, context, limit=num)
        else:
            await update.message.reply_text("Please enter a number between 1 and 100")
    else:
        # Ignore other text
        pass


async def main_async():
    """Async main function for Python 3.14"""
    print("🤖 Starting Video Library Bot...")
    print(f"🐍 Python version: 3.14.3")
    print("=" * 50)
    
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    print(f"✅ Bot token loaded")
    print(f"👤 Admin ID: {ADMIN_ID}")
    
    # Create application
    app = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send10", send10))
    app.add_handler(CommandHandler("send50", send50))
    app.add_handler(CommandHandler("send100", send100))
    app.add_handler(CommandHandler("sendall", sendall))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("recent", recent))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("status", status))
    
    # Handle videos (any format)
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.Document.VIDEO | filters.ANIMATION, 
        handle_video
    ))
    
    # Handle text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print(f"✅ Commands registered:")
    print(f"   • /send10, /send50, /send100, /sendall")
    print(f"   • /total, /recent, /status")
    print(f"   • /clear (admin only)")
    print(f"✅ Video detection: ON (all formats)")
    print("🤖 Bot is polling...")
    print("=" * 50)
    
    # Initialize and start
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main():
    """Entry point"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")


if __name__ == "__main__":
    main()
