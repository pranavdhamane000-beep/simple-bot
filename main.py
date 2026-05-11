import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# In-memory storage (clears when bot restarts)
VIDEOS = []  # List of video file_ids

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Video Library Bot*\n\n"
        "Send me any video and I'll store it!\n\n"
        "*Commands:*\n"
        "/send10 - Show first 10 videos\n"
        "/send50 - Show first 50 videos\n"
        "/send100 - Show first 100 videos\n"
        "/sendall - Show all videos\n"
        "/total - Show total videos\n"
        "/recent - Show last 5 videos added\n"
        "/clear - Clear all videos (admin only)",
        parse_mode='Markdown'
    )

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save video to memory"""
    global VIDEOS
    
    if update.message.video:
        file_id = update.message.video.file_id
        caption = update.message.caption or "No caption"
        
        VIDEOS.append({
            'file_id': file_id,
            'caption': caption,
            'sender': update.effective_user.first_name
        })
        
        await update.message.reply_text(
            f"✅ Video saved!\n"
            f"📹 Total videos: {len(VIDEOS)}\n"
            f"📝 Caption: {caption[:50]}"
        )
    else:
        await update.message.reply_text("❌ Please send a video file (not a URL or text).")

async def send_videos(update: Update, context: ContextTypes.DEFAULT_TYPE, limit=None):
    """Send requested number of videos"""
    global VIDEOS
    
    if not VIDEOS:
        await update.message.reply_text("📭 No videos in library yet. Send me some videos first!")
        return
    
    if limit is None:
        count = len(VIDEOS)
    else:
        count = min(limit, len(VIDEOS))
    
    await update.message.reply_text(f"📹 Sending first {count} of {len(VIDEOS)} videos...")
    
    sent_count = 0
    for idx, video in enumerate(VIDEOS[:count], start=1):
        try:
            await update.message.reply_video(
                video['file_id'],
                caption=f"🎬 Video #{idx}\n📝 {video['caption']}\n👤 Sent by: {video['sender']}",
                timeout=30
            )
            sent_count += 1
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to send video #{idx}: {str(e)}")
    
    await update.message.reply_text(f"✅ Successfully sent {sent_count} videos!")

async def send10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=10)

async def send50(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=50)

async def send100(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=100)

async def sendall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=None)

async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global VIDEOS
    await update.message.reply_text(f"📊 Total videos in library: {len(VIDEOS)}")

async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global VIDEOS
    if not VIDEOS:
        await update.message.reply_text("No videos yet!")
        return
    
    recent_count = min(5, len(VIDEOS))
    recent_videos = VIDEOS[-recent_count:]  # Last 5 videos
    
    msg = f"📹 *Last {recent_count} videos added:*\n\n"
    for idx, video in enumerate(recent_videos, start=1):
        msg += f"{idx}. {video['caption'][:40]}\n   👤 {video['sender']}\n\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: Clear all videos"""
    global VIDEOS
    
    # Replace with your Telegram user ID for admin access
    ADMIN_IDS = [123456789]  # CHANGE THIS TO YOUR USER ID
    
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You're not authorized to use this command!")
        return
    
    count = len(VIDEOS)
    VIDEOS = []
    await update.message.reply_text(f"🗑️ Cleared all {count} videos from library!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

def main():
    print("🤖 Bot starting...")
    
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    # Create application
    app = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("send10", send10))
    app.add_handler(CommandHandler("send50", send50))
    app.add_handler(CommandHandler("send100", send100))
    app.add_handler(CommandHandler("sendall", sendall))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("recent", recent))
    app.add_handler(CommandHandler("clear", clear))
    
    # Handle video messages
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    
    print("✅ Bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()