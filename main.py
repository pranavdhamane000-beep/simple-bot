import os
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# In-memory storage (clears when bot restarts)
VIDEOS = []

# REPLACE WITH YOUR TELEGRAM USER ID - ONLY THIS ID CAN UPLOAD VIDEOS
ADMIN_ID = 6234222988  # CHANGE THIS TO YOUR USER ID!

# How to get your ID: Message @userinfobot on Telegram


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    user_id = update.effective_user.id
    is_admin = (user_id == ADMIN_ID)
    
    if is_admin:
        welcome = "👑 *Welcome Admin!*\n\n"
        welcome += "You can upload videos and manage the library.\n\n"
    else:
        welcome = "👋 *Welcome User!*\n\n"
        welcome += "You can watch videos from the library.\n\n"
    
    welcome += (
        "*Commands:*\n"
        "📹 /send10 - Get first 10 videos\n"
        "📹 /send50 - Get first 50 videos\n"
        "📹 /send100 - Get first 100 videos\n"
        "📹 /sendall - Get all videos\n"
        "📊 /total - Show statistics\n"
        "🆕 /recent - Show last 5 videos\n"
        "ℹ️ /status - Bot status\n\n"
    )
    
    if is_admin:
        welcome += (
            "*Admin Commands:*\n"
            "📤 Upload any video - Add to library\n"
            "🗑️ /clear - Delete ALL videos\n"
            "💾 /backup - Export video list\n\n"
        )
    else:
        welcome += (
            "*Note:* Only admin can upload videos.\n"
            "You can only watch videos using /send commands.\n\n"
        )
    
    welcome += "⚠️ Videos disappear when bot restarts!"
    
    await update.message.reply_text(welcome, parse_mode='Markdown')


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Only admin can upload videos"""
    global VIDEOS
    
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "❌ *Access Denied!*\n\n"
            "Only the bot admin can upload videos.\n"
            "You can only *watch* videos using:\n"
            "/send10, /send50, /send100, or /sendall",
            parse_mode='Markdown'
        )
        return
    
    video_file_id = None
    video_caption = ""
    video_size = 0
    video_type = "Unknown"
    
    # Check for different video types
    if update.message.video:
        video_file_id = update.message.video.file_id
        video_caption = update.message.caption or f"Video #{len(VIDEOS) + 1}"
        video_size = update.message.video.file_size
        video_type = "Video"
        
    elif update.message.document:
        mime_type = update.message.document.mime_type or ""
        if mime_type.startswith('video/'):
            video_file_id = update.message.document.file_id
            video_caption = update.message.caption or f"Video #{len(VIDEOS) + 1}"
            video_size = update.message.document.file_size
            video_type = "Video File"
        else:
            await update.message.reply_text("❌ Please send a VIDEO file!")
            return
            
    elif update.message.animation:
        video_file_id = update.message.animation.file_id
        video_caption = update.message.caption or f"Animation #{len(VIDEOS) + 1}"
        video_size = update.message.animation.file_size
        video_type = "Animation"
        
    else:
        await update.message.reply_text(
            "❌ Please send a video file!\n\n"
            "Supported: MP4, MOV, AVI, MKV, etc."
        )
        return
    
    # Save to memory
    video_data = {
        'file_id': video_file_id,
        'caption': video_caption,
        'sender_name': update.effective_user.first_name,
        'sender_id': user_id,
        'file_size': video_size,
        'type': video_type,
        'timestamp': datetime.now().isoformat()
    }
    VIDEOS.append(video_data)
    
    await update.message.reply_text(
        f"✅ *Video #{len(VIDEOS)} added to library!*\n\n"
        f"📝 Title: {video_caption[:100]}\n"
        f"📏 Size: {video_size // 1024} KB\n"
        f"🎬 Type: {video_type}\n\n"
        f"📊 Total videos in library: {len(VIDEOS)}\n\n"
        f"Users can now watch this video using /send commands!",
        parse_mode='Markdown'
    )


async def send_videos(update: Update, context: ContextTypes.DEFAULT_TYPE, limit=None):
    """Send videos to ANY user"""
    global VIDEOS
    
    if not VIDEOS:
        await update.message.reply_text(
            "📭 *No videos in library!*\n\n"
            "The admin hasn't uploaded any videos yet.\n"
            "Please check back later.",
            parse_mode='Markdown'
        )
        return
    
    # Determine how many to send
    if limit is None:
        count = len(VIDEOS)
        title = "All Videos"
    else:
        count = min(limit, len(VIDEOS))
        title = f"First {count} Videos"
    
    # Notify user
    await update.message.reply_text(
        f"📹 *{title}*\n\n"
        f"Sending {count} of {len(VIDEOS)} total videos...\n"
        f"⏳ Please wait...",
        parse_mode='Markdown'
    )
    
    sent_count = 0
    failed_count = 0
    
    for idx, video in enumerate(VIDEOS[:count], start=1):
        try:
            # First try to send as video
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video['file_id'],
                caption=f"🎬 *Video {idx}/{count}*\n📝 {video['caption'][:150]}",
                parse_mode='Markdown',
                timeout=60
            )
            sent_count += 1
            await asyncio.sleep(0.5)  # Delay between videos
            
        except Exception as e:
            # If video fails, try as document
            try:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=video['file_id'],
                    caption=f"🎬 *Video {idx}/{count}* (as file)\n📝 {video['caption'][:150]}",
                    parse_mode='Markdown',
                    timeout=60
                )
                sent_count += 1
                await asyncio.sleep(0.5)
            except Exception as e2:
                failed_count += 1
                print(f"Failed to send video #{idx}: {e2}")
    
    # Send summary
    if sent_count > 0:
        await update.message.reply_text(
            f"✅ *Delivery Complete!*\n\n"
            f"✓ Sent: {sent_count} videos\n"
            f"✗ Failed: {failed_count} videos\n"
            f"📊 Total in library: {len(VIDEOS)}\n\n"
            f"Use /total to see statistics",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"❌ *Failed to send videos!*\n\n"
            f"No videos could be sent. The video files may be corrupted or inaccessible.\n\n"
            f"Please contact the admin.",
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
    """Show statistics for all users"""
    global VIDEOS
    
    if not VIDEOS:
        await update.message.reply_text("📊 No videos in library yet!")
        return
    
    total_size = sum(v.get('file_size', 0) for v in VIDEOS)
    size_mb = total_size // (1024 * 1024)
    size_gb = size_mb // 1024
    
    size_text = f"{size_mb} MB" if size_mb < 1024 else f"{size_gb}.{size_mb % 1024} GB"
    
    await update.message.reply_text(
        f"📊 *Library Statistics*\n\n"
        f"📹 Total videos: {len(VIDEOS)}\n"
        f"💾 Total size: {size_text}\n"
        f"🎬 Formats: {len(set(v.get('type', 'Unknown') for v in VIDEOS))} types\n\n"
        f"📝 Latest video: {VIDEOS[-1]['caption'][:50] if VIDEOS else 'None'}\n\n"
        f"Use /send10 to watch videos!",
        parse_mode='Markdown'
    )


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show last 5 videos info for all users"""
    if not VIDEOS:
        await update.message.reply_text("No videos yet!")
        return
    
    recent_count = min(5, len(VIDEOS))
    recent_videos = VIDEOS[-recent_count:]
    
    msg = f"🆕 *Last {recent_count} videos added:*\n\n"
    for idx, video in enumerate(reversed(recent_videos), start=1):
        size_mb = video.get('file_size', 0) // (1024 * 1024)
        msg += f"{idx}. 📝 {video['caption'][:50]}\n"
        msg += f"   📏 {size_mb} MB | 🎬 {video.get('type', 'Video')}\n\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')
    
    # Offer to send them
    await update.message.reply_text(
        f"💡 Type /send{recent_count} to watch these videos!",
        parse_mode='Markdown'
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: Clear all videos"""
    global VIDEOS
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ *Access Denied!*\n\nOnly the bot admin can clear videos.", parse_mode='Markdown')
        return
    
    if not VIDEOS:
        await update.message.reply_text("Library is already empty!")
        return
    
    count = len(VIDEOS)
    VIDEOS = []
    await update.message.reply_text(
        f"🗑️ *Cleared {count} videos from library!*\n\n"
        f"All videos have been deleted. Users can no longer watch them.",
        parse_mode='Markdown'
    )


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: Export video list to file"""
    global VIDEOS
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Access Denied!")
        return
    
    if not VIDEOS:
        await update.message.reply_text("No videos to backup!")
        return
    
    backup_text = f"Video Library Backup\n"
    backup_text += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    backup_text += f"Total Videos: {len(VIDEOS)}\n"
    backup_text += "=" * 50 + "\n\n"
    
    for idx, video in enumerate(VIDEOS, start=1):
        backup_text += f"Video #{idx}\n"
        backup_text += f"File ID: {video['file_id']}\n"
        backup_text += f"Caption: {video['caption']}\n"
        backup_text += f"Added by: {video['sender_name']}\n"
        backup_text += f"Size: {video['file_size']} bytes\n"
        backup_text += f"Type: {video.get('type', 'Video')}\n"
        backup_text += "-" * 30 + "\n\n"
    
    filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(backup_text)
    
    with open(filename, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=filename,
            caption=f"📦 Backup of {len(VIDEOS)} videos"
        )
    
    os.remove(filename)
    await update.message.reply_text("💾 Backup created successfully!")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot status for all users"""
    is_admin = (update.effective_user.id == ADMIN_ID)
    
    status_text = (
        f"🤖 *Bot Status*\n\n"
        f"✅ Bot is running\n"
        f"🐍 Python 3.14.3\n"
        f"📹 Videos in library: {len(VIDEOS)}\n"
        f"👑 Admin ID: {ADMIN_ID}\n"
        f"🔒 Upload permissions: Admin only\n"
        f"👀 View permissions: Everyone\n"
        f"💾 Storage: RAM (resets on restart)\n\n"
    )
    
    if is_admin:
        status_text += f"🛠️ *Admin commands available*\n"
        status_text += f"• /clear - Delete all videos\n"
        status_text += f"• /backup - Export video list"
    else:
        status_text += f"👋 You are a *regular user*\n"
        status_text += f"• You can only *watch* videos\n"
        status_text += f"• Use /send10, /send50, /send100, /sendall"
    
    await update.message.reply_text(status_text, parse_mode='Markdown')


async def main_async():
    """Async main function for Python 3.14"""
    print("=" * 50)
    print("🤖 Starting Video Library Bot...")
    print(f"🐍 Python version: 3.14.3")
    print("=" * 50)
    
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    print(f"✅ Bot token loaded")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"🔒 Upload permissions: Admin only")
    print(f"👀 View permissions: Everyone")
    
    # Create application
    app = Application.builder().token(TOKEN).build()
    
    # Command handlers (available to everyone)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send10", send10))
    app.add_handler(CommandHandler("send50", send50))
    app.add_handler(CommandHandler("send100", send100))
    app.add_handler(CommandHandler("sendall", sendall))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("recent", recent))
    app.add_handler(CommandHandler("status", status))
    
    # Admin only commands
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("backup", backup))
    
    # Video upload (admin only - checked inside function)
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.Document.VIDEO | filters.ANIMATION, 
        handle_video
    ))
    
    print(f"✅ Commands registered:")
    print(f"   📹 View commands: /send10, /send50, /send100, /sendall")
    print(f"   📊 Info commands: /total, /recent, /status")
    print(f"   🔧 Admin commands: /clear, /backup")
    print(f"✅ Upload permission: Only user ID {ADMIN_ID}")
    print("🤖 Bot is polling for updates...")
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
