import time
import json
import requests
import feedparser
import os
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# CONFIGURATION (LOADED FROM RENDER ENVIRONMENT)
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "openai/gpt-oss-20b"

LIVE_FEEDS = [
    "https://www.fxstreet.com/rss/news",
    "https://www.forexlive.com/feed/news",
    "https://www.investing.com/rss/news_25.rss"
]

news_buffer = []

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram Delivery Error: {e}")

def synthesize_hourly_news_groq(headlines_list):
    if not GROQ_API_KEY:
        print("Groq Cloud Error: GROQ_API_KEY environment variable is not set.")
        return None

    headlines_text = "\n".join([f"- {h}" for h in headlines_list])
    prompt = f"""
    You are an elite institutional macro portfolio manager. Here are all the breaking financial news headlines collected over the past 60 minutes:
    {headlines_text}

    Synthesize these headlines collectively as a single macro environment. Predict the net directional bias for the NEXT 1 HOUR for:
    1. NASDAQ 100 (US Tech Equities)
    2. XAUUSD (Spot Gold)

    Respond ONLY in valid JSON format with no markdown formatting around it:
    {{
      "nasdaq_direction": "BULLISH" or "BEARISH" or "NEUTRAL",
      "gold_direction": "BULLISH" or "BEARISH" or "NEUTRAL",
      "summary_thesis": "2 short sentences explaining the net market driver and expected price action for the next hour."
    }}
    """
    headers = {
        "Authorization": "Bearer " + GROQ_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"model": MODEL_NAME, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}

    try:
        response = requests.post(GROQ_URL, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return json.loads(response.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"Groq Cloud Error: {e}")
    return None

def main_loop():
    global news_buffer

    print("Background Sentinel Loop Started...")
    last_synthesis_time = 0
    
    while True:
        current_time = datetime.now()
        for feed_url in LIVE_FEEDS:
            try:
                parsed = feedparser.parse(feed_url)
                for entry in parsed.entries[:5]:
                    headline = entry.title
                    link = entry.link
                    if not any(item['headline'] == headline for item in news_buffer):
                        news_buffer.append({"headline": headline, "link": link, "time": current_time})
            except Exception as e:
                print(f"Feed Polling Error: {e}")
        
        one_hour_ago = current_time - timedelta(hours=1)
        news_buffer = [item for item in news_buffer if item['time'] >= one_hour_ago]
        
        if time.time() - last_synthesis_time >= 3600 or last_synthesis_time == 0:
            if news_buffer:
                headlines_only = [item['headline'] for item in news_buffer]
                analysis = synthesize_hourly_news_groq(headlines_only)
                
                if analysis:
                    n_dir = analysis.get("nasdaq_direction", "NEUTRAL")
                    g_dir = analysis.get("gold_direction", "NEUTRAL")
                    thesis = analysis.get("summary_thesis", "Insufficient data.")
                    
                    n_icon = "📈" if n_dir == "BULLISH" else ("📉" if n_dir == "BEARISH" else "⚖️")
                    g_icon = "📈" if g_dir == "BULLISH" else ("📉" if g_dir == "BEARISH" else "⚖️")
                    
                    report = (
                        f"📊 *HOURLY MACRO SYNTHESIS REPORT*\n"
                        f"⏱ *Window:* Past 60 Mins ({len(news_buffer)} headlines)\n\n"
                        f"💻 *NASDAQ 100:* `{n_icon} {n_dir}`\n"
                        f"🥇 *XAUUSD:* `{g_icon} {g_dir}`\n\n"
                        f"🧠 *Outlook:* {thesis}"
                    )
                    send_telegram_alert(report)
            last_synthesis_time = time.time()
        
        time.sleep(300)

# Dummy web server to satisfy Render's port binding requirement
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Sentinel is active and running 24/7!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    print(f"Web server running on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    # Start the background market sentinel loop in a separate thread
    t = Thread(target=main_loop, daemon=True)
    t.start()
    
    # Run web server on main thread
    run_web_server()
