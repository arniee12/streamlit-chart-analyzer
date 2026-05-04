import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import os
import json
import base64
from dotenv import load_dotenv
import yfinance as yf
from datetime import datetime
from openai import OpenAI, AuthenticationError, RateLimitError

load_dotenv()

st.set_page_config(page_title="Chart Analyzer + Overlays", layout="wide")
st.title("📈 Advanced Trading Chart Analyzer with Visual Overlays")

st.sidebar.header("Settings")
ticker = st.sidebar.text_input("Ticker Symbol", value="AAPL").upper().strip()
api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
show_overlays = st.sidebar.checkbox("Show Visual Overlays", value=True)
model_choice = st.sidebar.selectbox("Model", ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"])

uploaded_file = st.file_uploader("Upload Chart Screenshot", type=["png", "jpg", "jpeg", "webp"])

def get_real_time_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        current = info.get('currentPrice') or info.get('regularMarketPrice')
        return {"current_price": round(current, 4) if current else None}
    except Exception as e:
        st.warning(f"Could not fetch real-time data: {e}")
        return {"current_price": None}

def encode_image_to_base64(image):
    import io
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return img_str

def get_font(size=20):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except:
        try:
            return ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", size)
        except:
            return ImageFont.load_default()

def draw_overlays(image, analysis, price_min, price_max):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    font = get_font(16)
    
    try:
        for level in analysis.get("key_levels", {}).get("support", []):
            if price_min and price_max and price_max > price_min:
                y = height * (1 - (level - price_min) / (price_max - price_min))
                if 0 <= y <= height:
                    draw.line([(0, y), (width, y)], fill=(0, 255, 0), width=3)
                    draw.text((10, y-15), f"Support ${level:.2f}", fill=(0, 255, 0), font=font)
        
        for level in analysis.get("key_levels", {}).get("resistance", []):
            if price_min and price_max and price_max > price_min:
                y = height * (1 - (level - price_min) / (price_max - price_min))
                if 0 <= y <= height:
                    draw.line([(0, y), (width, y)], fill=(255, 0, 0), width=3)
                    draw.text((10, y-15), f"Resistance ${level:.2f}", fill=(255, 0, 0), font=font)
        
        target = analysis.get("target_price")
        if target and price_min and price_max and price_max > price_min:
            y = height * (1 - (target - price_min) / (price_max - price_min))
            if 0 <= y <= height:
                draw.line([(0, y), (width, y)], fill=(0, 191, 255), width=4)
                draw.text((width-200, max(0, y-15)), f"Target ${target:.2f}", fill=(0, 191, 255), font=font)
        
        stop = analysis.get("stop_loss")
        if stop and price_min and price_max and price_max > price_min:
            y = height * (1 - (stop - price_min) / (price_max - price_min))
            if 0 <= y <= height:
                draw.line([(0, y), (width, y)], fill=(255, 140, 0), width=3)
                draw.text((10, max(0, y-15)), f"Stop ${stop:.2f}", fill=(255, 140, 0), font=font)
            
    except Exception as e:
        st.warning(f"Could not draw all overlays: {e}")
    
    return image

def analyze_chart(image, api_key, ticker, rt_data, model):
    try:
        client = OpenAI(api_key=api_key)
        img_base64 = encode_image_to_base64(image)
        
        prompt = f"""Analyze this trading chart for {ticker} and provide a detailed technical analysis in JSON format.
        
Current price: ${rt_data.get('current_price', 'Unknown')}
Chart date: {datetime.now().strftime('%Y-%m-%d')}

Please provide your analysis in this exact JSON structure (NO markdown, pure JSON):
{{
    "summary": "Brief 1-2 sentence summary of chart structure and trend",
    "direction": "Bullish|Bearish|Neutral",
    "confidence": 0-100,
    "target_price": float,
    "stop_loss": float,
    "patterns": ["pattern1", "pattern2", "pattern3"],
    "key_levels": {{
        "support": [level1, level2],
        "resistance": [level1, level2]
    }},
    "risk_reward_ratio": "1:X",
    "timeframe": "identified timeframe",
    "entry_point": "description of entry",
    "exit_strategy": "description of exit"
}}

Analyze the chart carefully for:
- Price action and trend direction
- Support and resistance levels
- Chart patterns (Cup & Handle, Head & Shoulders, Wedges, etc.)
- Volume signals if visible
- Moving averages or other indicators
- Key price levels
"""
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.7,
            max_tokens=1500
        )
        
        response_text = response.choices[0].message.content.strip()
        
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                analysis = json.loads(json_str)
            else:
                analysis = json.loads(response_text)
        except json.JSONDecodeError:
            st.error("Could not parse API response as JSON")
            return None
        
        return analysis
        
    except AuthenticationError:
        st.error("❌ Invalid OpenAI API Key - please check your key in Settings")
        return None
    except RateLimitError:
        st.error("⏱️ Rate limit reached. Please wait a moment and try again.")
        return None
    except Exception as e:
        st.error(f"❌ Analysis failed: {str(e)}")
        return None

if uploaded_file:
    try:
        original_image = Image.open(uploaded_file).convert("RGB")
        st.image(original_image, caption="Original Chart", use_column_width=True)
        
        rt_data = get_real_time_data(ticker)
        if rt_data.get("current_price"):
            st.success(f"**Live {ticker} Price:** ${rt_data['current_price']}")
        else:
            st.info(f"Could not fetch live price for {ticker}")

        col1, col2 = st.columns(2)
        with col1:
            price_min = st.number_input("Chart Minimum Price", value=100.0, step=0.1)
        with col2:
            price_max = st.number_input("Chart Maximum Price", value=150.0, step=0.1)

        if st.button("🚀 Analyze + Generate Overlays", use_container_width=True):
            if not api_key:
                st.error("❌ Please provide OpenAI API Key in Settings")
            elif price_max <= price_min:
                st.error("❌ Maximum price must be greater than minimum price")
            else:
                with st.spinner("🔍 Analyzing chart and generating overlays..."):
                    analysis = analyze_chart(original_image, api_key, ticker, rt_data, model_choice)
                    
                    if analysis:
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Direction", analysis.get("direction", "N/A"))
                        with col2:
                            st.metric("Target", f"${analysis.get('target_price', 'N/A')}")
                        with col3:
                            st.metric("Confidence", f"{analysis.get('confidence', 'N/A')}%")
                        with col4:
                            st.metric("Risk:Reward", analysis.get("risk_reward_ratio", "N/A"))
                        
                        st.subheader("📊 Analysis Summary")
                        st.write(analysis.get("summary", "No summary available"))
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.subheader("📈 Entry & Exit")
                            st.write(f"**Entry:** {analysis.get('entry_point', 'N/A')}")
                            st.write(f"**Exit:** {analysis.get('exit_strategy', 'N/A')}")
                        with col2:
                            st.subheader("⏱️ Timeframe & Levels")
                            st.write(f"**Timeframe:** {analysis.get('timeframe', 'N/A')}")
                        
                        st.subheader("🎯 Detected Patterns")
                        for p in analysis.get("patterns", []):
                            st.info(f"✓ {p}")
                        
                        if show_overlays:
                            st.subheader("📊 Chart with Visual Overlays")
                            overlaid = original_image.copy()
                            overlaid = draw_overlays(overlaid, analysis, price_min, price_max)
                            st.image(overlaid, caption="Chart with Support/Resistance/Target Levels", use_column_width=True)
                        
                        with st.expander("📋 View Raw Analysis (JSON)"):
                            st.json(analysis)
    
    except Exception as e:
        st.error(f"Error processing image: {str(e)}")
else:
    st.info("👆 Please upload a chart screenshot to begin analysis")
