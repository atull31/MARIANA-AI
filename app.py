import os
import sys
import json
import time
import re
import traceback
from dotenv import load_dotenv
import google.generativeai as genai
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key-for-research-agent!'
socketio = SocketIO(app, async_mode='eventlet', ping_timeout=120, ping_interval=25)

# --- Gemini API Configuration ---
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    print("ERROR: API_KEY not found in the .env file.", file=sys.stderr)
    sys.exit(1)
genai.configure(api_key=API_KEY)

# --- DYNAMIC MODEL FINDER ---
def find_best_model():
    """Automatically finds a working model name for this account."""
    print("🔍 Detecting available models for your API key...")
    try:
        available_models = list(genai.list_models())
        # Priority 1: newer flash models (fast/cheap)
        for m in available_models:
            if 'generateContent' in m.supported_generation_methods and 'flash' in m.name.lower() and '1.5' in m.name:
                 print(f"✅ Auto-selected model: {m.name}")
                 return m.name
        # Priority 2: any pro model
        for m in available_models:
             if 'generateContent' in m.supported_generation_methods and 'pro' in m.name.lower():
                 print(f"✅ Auto-selected model: {m.name}")
                 return m.name
        # Priority 3: ANY working model
        for m in available_models:
             if 'generateContent' in m.supported_generation_methods:
                 print(f"✅ Auto-selected model: {m.name}")
                 return m.name
    except Exception as e:
        print(f"⚠️ Could not list models ({e}). Defaulting to 'gemini-1.5-flash'")
    return "gemini-1.5-flash"

# Set the model once at startup
ACTIVE_MODEL_NAME = find_best_model()

# --- Core Research Logic ---

def brainstorm_sub_topics(topic: str) -> list[str]:
    model = genai.GenerativeModel(model_name=ACTIVE_MODEL_NAME)
    prompt = (
        "You are a research assistant. Break down this main topic into exactly 3 specific, "
        "answerable sub-topics for a report. Return ONLY a raw JSON array of strings, like this: "
        '["Topic 1", "Topic 2", "Topic 3"]\n'
        f'Main Topic: "{topic}"'
    )
    try:
        # Try standard generation and manual JSON parsing for maximum compatibility
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Find the first '[' and last ']'
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end != -1:
            json_str = text[start:end]
            return json.loads(json_str)[:3] # Ensure max 3
        else:
             raise ValueError("No JSON array found in response")
    except Exception as e:
        print(f"Brainstorm fallback used due to: {e}")
        return [f"{topic} - Key Concepts", f"{topic} - Historical Context", f"{topic} - Future Outlook"]

def research_sub_topic_with_retry(sub_topic: str, update_callback=None) -> str:
    model = genai.GenerativeModel(model_name=ACTIVE_MODEL_NAME)
    max_retries = 3
    
    # Try to find a valid tool definition
    search_tool = None
    try:
        # Modern approach
        search_tool = {'google_search': {}}
        # Test if library accepts this by quickly creating a dummy (not sending)
        genai.protos.Tool(google_search=genai.protos.GoogleSearch())
    except:
        # Fallback for older libraries
        try: 
             search_tool = genai.protos.Tool(google_search_retrieval=genai.protos.GoogleSearchRetrieval())
        except:
             print("⚠️ No Google Search tool available in this environment.")
             search_tool = None

    prompt = (
        "Gather detailed information on this topic. Provide a comprehensive summary (approx 200 words). "
        "Focus on facts and figures. Cite sources if available."
        f'\nTopic: "{sub_topic}"'
    )

    for attempt in range(1, max_retries + 1):
        try:
            if search_tool:
                # Some older libs need it wrapped in a list, some don't. generic try/except handles it.
                try:
                     response = model.generate_content(prompt, tools=[search_tool])
                except:
                     # Retry with older tool format if modern dict failed unexpectedly
                     fallback_tool = genai.protos.Tool(google_search=genai.protos.GoogleSearch())
                     response = model.generate_content(prompt, tools=[fallback_tool])
            else:
                response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_str = str(e).lower()
            
            if "quota" in error_str or "429" in error_str:
                m = re.search(r'retry in (\d+)s', error_str)
                wait_time = int(m.group(1)) + 5 if m else 65
                msg = f"⚠️ API Rate limit hit. Waiting {wait_time}s..."
                print(msg)
                if update_callback: update_callback(msg)
                time.sleep(wait_time)
                continue

            if "not supported" in error_str or "unknown field" in error_str:
                print("Tool not supported. Retrying without tools.")
                search_tool = None; continue

            print(f"Attempt {attempt} failed for {sub_topic}: {e}")
            time.sleep(5)

    return "Failed to gather information."

def synthesize_report(main_topic: str, research_data: str) -> str:
    model = genai.GenerativeModel(model_name=ACTIVE_MODEL_NAME)
    prompt = (
        "Synthesize these notes into a Markdown report. Use # for Main Title, ## for sections. "
        f'Topic: "{main_topic}".\n\n--- Notes ---\n{research_data}'
    )
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"# Report Error\nCould not synthesize: {e}\n\n## Notes\n{research_data}"

# --- Main Process ---
def run_research(topic: str):
    try:
        socketio.emit('status_update', {'message': f'🧠 Brainstorming using {ACTIVE_MODEL_NAME}...'})
        sub_topics = brainstorm_sub_topics(topic)
        socketio.emit('sub_topics_generated', {'sub_topics': [{'topic': t, 'status': 'pending'} for t in sub_topics]})

        results = []
        for i, sub_topic in enumerate(sub_topics):
            socketio.emit('status_update', {'message': f'🔎 Researching: {sub_topic} ...'})
            socketio.emit('sub_topic_update', {'index': i, 'status': 'in-progress'})
            
            if i > 0:
                socketio.emit('status_update', {'message': '⏳ Resting API for 10s...'})
                time.sleep(10)
                socketio.emit('status_update', {'message': f'🔎 Researching: {sub_topic} ...'})

            summary = research_sub_topic_with_retry(sub_topic, lambda msg: socketio.emit('status_update', {'message': msg}))
            
            if "Failed" in summary and len(summary) < 100:
                 socketio.emit('sub_topic_update', {'index': i, 'status': 'error'})
                 results.append(f"## {sub_topic}\n(Research failed)")
            else:
                 results.append(f"## {sub_topic}\n{summary}")
                 socketio.emit('sub_topic_update', {'index': i, 'status': 'complete'})

        socketio.emit('status_update', {'message': '✍️ Synthesizing...'})
        final_report = synthesize_report(topic, "\n\n".join(results))
        socketio.emit('final_report', {'report': final_report})
        socketio.emit('status_update', {'message': '🎉 Done!'})

    except Exception as e:
        traceback.print_exc()
        socketio.emit('research_error', {'error': str(e)})

@app.route('/')
def index(): return render_template('index.html')

@socketio.on('start_research')
def on_start(data):
    topic = data.get('topic')
    if topic:
        print(f"Starting research on: {topic}")
        socketio.start_background_task(run_research, topic)

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)