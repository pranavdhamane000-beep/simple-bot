import os
import asyncio
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# File to store videos (survives restarts!)
VIDEO_FILE = "videos.json"

# Load videos from file
def load_videos():
    if os.path.exists(VIDEO_FILE):
        try:
            with open(VIDEO_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

# Save videos to file
def save_videos(videos):
    with open(VIDEO_FILE, 'w') as f:
        json.dump(videos, f)

# Load videos on startup
VIDEOS = load_videos()

# REPLACE WITH YOUR TELEGRAM USER ID
ADMIN_ID = 6234222988


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = (user_id == ADMIN_ID)
    
    msg = "🎬 *Video Library Bot*\n\n"
    
    if is_admin:
        msg += "👑 *You are the ADMIN*\n"
        msg += "• Send videos to add them\n"
        msg += "• All videos save permanently\n\n"
    else:
        msg += "👋 *Welcome User*\n"
        msg += "• You can only WATCH videos\n"
        msg += "• Admin adds the videos\n\n"
    
    msg += "*Commands:*\n"
    msg += "/send10 - Get first 10 videos\n"
    msg += "/send50 - Get first 50 videos\n"
    msg += "/send100 - Get first 100 videos\n"
    msg += "/sendall - Get all videos\n"
    msg += "/total - Show statistics\n"
    msg += "/recent - Last 5 videos\n\n"
    
    if is_admin:
        msg += "*Admin Commands:*\n"
        msg += "/clear - Delete all videos\n"
        msg += "/save - Force save to file\n\n"
    
    msg += f"📊 Videos in library: {len(VIDEOS)}\n"
    msg += f"💾 Storage: File-based (permanent)"
    
    await update.message.reply_text(msg, parse_mode='Markdown')


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Only admin can upload videos"""
    global VIDEOS
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can upload videos!")
        return
    
    video_file_id = None
    
    # Get file_id from video
    if update.message.video:
        video_file_id = update.message.video.file_id
        caption = update.message.caption or f"Video #{len(VIDEOS) + 1}"
    elif update.message.document and update.message.document.mime_type.startswith('video/'):
        video_file_id = update.message.document.file_id
        caption = update.message.caption or f"Video #{len(VIDEOS) + 1}"
    else:
        await update.message.reply_text("❌ Please send a video file!")
        return
    
    # Save to memory and file
    video_data = {
        'file_id': video_file_id,
        'caption': caption,
        'added_by': update.effective_user.first_name,
        'added_at': datetime.now().isoformat()
    }
    
    VIDEOS.append(video_data)
    save_videos(VIDEOS)  # Save to file immediately
    
    await update.message.reply_text(
        f"✅ *Video #{len(VIDEOS)} saved!*\n\n"
        f"📝 {caption[:100]}\n"
        f"💾 Saved to permanent storage\n\n"
        f"Users can now watch it using /send10",
        parse_mode='Markdown'
    )


async def send_videos(update: Update, context: ContextTypes.DEFAULT_TYPE, limit=None):
    """Send videos to users"""
    global VIDEOS
    
    # Refresh videos from file (in case of restart)
    VIDEOS = load_videos()
    
    if not VIDEOS:
        await update.message.reply_text("📭 No videos in library yet!")
        return
    
    count = len(VIDEOS) if limit is None else min(limit, len(VIDEOS))
    
    await update.message.reply_text(
        f"📹 Sending {count} of {len(VIDEOS)} videos...\n"
        f"⏳ Please wait...",
        parse_mode='Markdown'
    )
    
    sent = 0
    failed = 0
    
    for idx, video in enumerate(VIDEOS[:count], start=1):
        try:
            # Send the video
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video['file_id'],
                caption=f"🎬 Video {idx}/{count}\n📝 {video['caption'][:100]}",
                timeout=30
            )
            sent += 1
            await asyncio.sleep(0.3)
            
        except Exception as e:
            print(f"Error sending video {idx}: {e}")
            failed += 1
    
    await update.message.reply_text(
        f"✅ *Complete!*\n\n"
        f"✓ Sent: {sent}\n"
        f"✗ Failed: {failed}\n"
        f"📊 Total: {len(VIDEOS)}",
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
    VIDEOS = load_videos()
    await update.message.reply_text(
        f"📊 *Library Stats*\n\n"
        f"📹 Videos: {len(VIDEOS)}\n"
        f"💾 Storage: videos.json file\n"
        f"✅ Persists across restarts",
        parse_mode='Markdown'
    )


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    VIDEOS = load_videos()
    if not VIDEOS:
        await update.message.reply_text("No videos!")
        return
    
    recent_count = min(5, len(VIDEOS))
    recent_videos = VIDEOS[-recent_count:]
    
    msg = f"🆕 *Last {recent_count} videos:*\n\n"
    for idx, video in enumerate(reversed(recent_videos), start=1):
        msg += f"{idx}. {video['caption'][:50]}\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global VIDEOS
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    
    count = len(VIDEOS)
    VIDEOS = []
    save_videos(VIDEOS)
    await update.message.reply_text(f"🗑️ Cleared {count} videos!")


async def save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Force save to file"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    
    save_videos(VIDEOS)
    await update.message.reply_text(f"💾 Saved {len(VIDEOS)} videos to file!")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    VIDEOS = load_videos()
    await update.message.reply_text(
        f"🤖 *Bot Status*\n\n"
        f"✅ Running on Python 3.14.3\n"
        f"📹 Videos: {len(VIDEOS)}\n"
        f"💾 Storage: JSON file (permanent)\n"
        f"🔄 Data survives restarts!\n"
        f"👑 Admin ID: {ADMIN_ID}",
        parse_mode='Markdown'
    )


async def main_async():
    print("=" * 50)
    print("🤖 Starting Video Library Bot (File Storage)")
    print("=" * 50)
    
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ Token not set!")
        return
    
    # Load existing videos
    videos = load_videos()
    print(f"✅ Loaded {len(videos)} videos from file")
    
    app = Application.builder().token(TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send10", send10))
    app.add_handler(CommandHandler("send50", send50))
    app.add_handler(CommandHandler("send100", send100))
    app.add_handler(CommandHandler("sendall", sendall))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("recent", recent))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("save", save))
    
    # Video upload
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.Document.VIDEO, 
        handle_video
    ))
    
    print("✅ Bot is running...")
    print("=" * 50)
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")


if __name__ == "__main__":
    main()
