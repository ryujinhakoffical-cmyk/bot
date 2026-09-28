import gradio as gr
import json
import threading
import time
from binance_bot import start_bot_sync

def get_stats():
    try:
        with open("dashboard_data.json", "r") as f:
            data = json.load(f)
            return data.get("total_pnl", 0.0), data.get("streak", 0), data.get("risk", 25.0)
    except Exception:
        return 0.0, 0, 25.0

def generate_dashboard():
    pnl, streak, risk = get_stats()
    
    html = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; background-color: #1a1a24; padding: 40px; border-radius: 15px; border: 2px solid #2e2e42; color: #a6accd;">
        <h1 style="color: #89ddff; font-size: 3em; margin-bottom: 5px;">Binance Kinetic Velocity Bot</h1>
        <p style="color: #636a88; font-size: 1.2em; margin-top: 0;">Asymmetric Compounding (Kamatos Kamat)</p>
        
        <div style="display: flex; justify-content: space-around; margin-top: 40px;">
            <div style="background-color: #232333; padding: 20px; border-radius: 10px; width: 30%;">
                <h3 style="color: #f07178; margin: 0;">Total PnL (Estimated)</h3>
                <h2 style="color: #c3e88d; font-size: 2.5em; margin: 10px 0;">${pnl:.2f}</h2>
            </div>
            
            <div style="background-color: #232333; padding: 20px; border-radius: 10px; width: 30%;">
                <h3 style="color: #f07178; margin: 0;">Current Win Streak</h3>
                <h2 style="color: #ffcb6b; font-size: 2.5em; margin: 10px 0;">{streak} 🔥</h2>
            </div>
            
            <div style="background-color: #232333; padding: 20px; border-radius: 10px; width: 30%;">
                <h3 style="color: #f07178; margin: 0;">Next Trade Risk</h3>
                <h2 style="color: #82aaff; font-size: 2.5em; margin: 10px 0;">${risk:.2f}</h2>
            </div>
        </div>
        <p style="margin-top: 30px; color: #636a88;">Dashboard auto-updates every 2 seconds. Powered by DeepMind Experience Replay.</p>
    </div>
    """
    return html

with gr.Blocks(theme=gr.themes.Monochrome()) as demo:
    dashboard_html = gr.HTML(value=generate_dashboard)
    
    def refresh():
        return generate_dashboard()
        
    # Auto refresh every 2 seconds using gr.Timer in gradio 4.0+
    # Or just use the native every=2 in HTML component (which is cleaner if supported)
    # Since we can't guarantee Gradio version, a simple Refresh button as fallback
    refresh_btn = gr.Button("🔄 Refresh Dashboard Manually")
    refresh_btn.click(fn=refresh, outputs=dashboard_html)

if __name__ == "__main__":
    # Start the Binance bot in a daemon thread so it runs infinitely in the background of the Space
    print("Starting Binance HFT Bot thread...")
    bot_thread = threading.Thread(target=start_bot_sync, daemon=True)
    bot_thread.start()
    
    # Launch Gradio
    print("Starting Web Dashboard...")
    demo.launch(server_name="0.0.0.0", server_port=7860)
