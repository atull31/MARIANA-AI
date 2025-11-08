# research_agent.py

# This script is the Python equivalent of the Deep Research AI Agent web application.
# It replicates the core logic for brainstorming, researching, and synthesizing reports.

# --- Dependencies ---
# To run this, you need to install the following packages in your terminal:
# pip install google-generativeai python-dotenv
#
# --- Setup ---
# 1. You already have this file: research_agent.py
# 2. You already have a file named ".env" in the same directory.
# 3. Ensure your API key is in the .env file like this:
#    API_KEY="YOUR_API_KEY_HERE"

import google.generativeai as genai
import os
import sys
import json
import argparse
import time
import re
import traceback
import genai
from dotenv import load_dotenv

# --- Initialization ---

# Load environment variables from your .env file
load_dotenv()

# Configure the Gemini API with the key
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    print("ERROR: API_KEY not found in the .env file.", file=sys.stderr)
    sys.exit(1)

genai.configure(api_key=API_KEY)

# --- Core Logic (Equivalent to services/geminiService.ts) ---

def brainstorm_sub_topics(topic: str) -> list[str]:
    """
    Generates a list of sub-topics for a given main topic.
    Equivalent to the `brainstormSubTopics` function.
    """
    print("🧠 Brainstorming sub-topics...")
    try:
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        
        # Define the JSON schema for the expected response to ensure a list of strings
        json_schema = genai.protos.Schema(
            type=genai.protos.Type.ARRAY,
            items=genai.protos.Schema(type=genai.protos.Type.STRING)
        )
        
        prompt = (
            "You are a research assistant. Your goal is to break down a main topic into a set of 5 to 7 "
            "specific, answerable sub-topics for a deep-dive report. Generate a JSON array of strings, "
            f'where each string is a sub-topic. Do not output anything else but the JSON array. Main Topic: "{topic}"'
        )

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                response_schema=json_schema
            )
        )
        
        sub_topics_list = json.loads(response.text)
        if not isinstance(sub_topics_list, list) or not all(isinstance(s, str) for s in sub_topics_list):
             raise ValueError("Model returned data in an unexpected format.")
        
        return sub_topics_list
        
    except (Exception, json.JSONDecodeError) as e:
        print(f"Error during brainstorming: {e}", file=sys.stderr)
        raise ValueError("Failed to brainstorm sub-topics. The model may have returned an invalid response.")


def research_sub_topic(sub_topic: str) -> str:
    """
    Researches a single sub-topic using Google Search grounding and returns a summary.
    Robust to different tool names and quota (429) errors with retries/backoff.
    """
    print(f"   -> Researching: '{sub_topic}'")
    model_name = os.getenv("RESEARCH_MODEL", "gemini-2.5-flash")
    max_retries = 3
    tool_candidates = ["google_search", "google_search_retrieval", "google_search_tool"]

    prompt = (
        "You are a research assistant. Gather detailed information on the following topic and provide a concise "
        "but comprehensive summary (around 200-300 words). Focus on key facts, figures, and concepts. "
        f'Topic: "{sub_topic}"'
    )

    try:
        model = genai.GenerativeModel(model_name=model_name)
    except Exception as e:
        print("Failed to create model:", e, file=sys.stderr)
        return f"Could not research topic: {sub_topic}. Reason: {e}"

    response = None
    last_err = None

    for attempt in range(1, max_retries + 1):
        # Try each candidate tool name until one succeeds
        for tool_name in tool_candidates:
            try:
                # map e.g. "google_search" -> "GoogleSearch"
                class_name = "".join(part.capitalize() for part in tool_name.split("_"))
                if hasattr(genai.protos, class_name):
                    tool_cls = getattr(genai.protos, class_name)
                    tool_inst = tool_cls()
                    tool_proto = genai.protos.Tool(**{tool_name: tool_inst})
                    print(f"Attempt {attempt}: trying tool '{tool_name}'")
                    response = model.generate_content(prompt, tools=[tool_proto])
                    break
                else:
                    # class not present, skip
                    continue
            except Exception as e:
                last_err = e
                s = str(e).lower()
                # If it's explicitly the unsupported-tool message, try next candidate
                if "not supported" in s or "unsupported" in s or "is not supported" in s:
                    print(f"Tool '{tool_name}' not supported, trying next tool...", file=sys.stderr)
                    continue
                # Quota / 429 handling: parse retry_delay or back off
                if "quota" in s or "you exceeded" in s or "429" in s:
                    # try to find seconds in the message
                    m = re.search(r'retry in (\d+\.?\d*)s', str(e), re.IGNORECASE) or re.search(r'retry_delay.*?seconds:\s*(\d+)', str(e), re.IGNORECASE)
                    wait = float(m.group(1)) if m else min(60, 2 ** attempt * 5)
                    print(f"Quota / rate limit hit; sleeping {wait:.1f}s (attempt {attempt})", file=sys.stderr)
                    time.sleep(wait)
                    continue
                # other errors: break and try next overall attempt
                print(f"Tool '{tool_name}' error: {e}", file=sys.stderr)
                traceback.print_exc()
                continue

        if response:
            break

        # If none of the tools succeeded in this attempt, try without tools as a fallback
        try:
            print(f"Attempt {attempt}: trying without tools (fallback)", file=sys.stderr)
            response = model.generate_content(prompt)
            break
        except Exception as e:
            last_err = e
            s = str(e).lower()
            if "quota" in s or "you exceeded" in s or "429" in s:
                m = re.search(r'retry in (\d+\.?\d*)s', str(e), re.IGNORECASE) or re.search(r'retry_delay.*?seconds:\s*(\d+)', str(e), re.IGNORECASE)
                wait = float(m.group(1)) if m else min(60, 2 ** attempt * 5)
                print(f"Quota / rate limit hit on fallback; sleeping {wait:.1f}s (attempt {attempt})", file=sys.stderr)
                time.sleep(wait)
                continue
            print("Fallback call failed:", e, file=sys.stderr)
            traceback.print_exc()
            # small pause before next attempt
            time.sleep(min(5 * attempt, 30))

    if not response:
        err_msg = f"Failed to research '{sub_topic}'. Last error: {last_err}"
        print(err_msg, file=sys.stderr)
        return f"Could not research topic: {sub_topic}. Reason: {last_err}"

    # Prefer response.text but tolerate different SDK attribute names
    return getattr(response, "text", None) or getattr(response, "output_text", "") or str(response)


def synthesize_report(main_topic: str, research_data: str) -> str:
    """
    Synthesizes a final report from the research data of all sub-topics.
    Equivalent to the `synthesizeReport` function.
    """
    print("✍️  Synthesizing the final report...")
    try:
        # Use a more powerful model for high-quality synthesis
        model = genai.GenerativeModel(model_name="gemini-2.5-pro")
        
        prompt = (
            "You are a research analyst. You have been provided with research on several sub-topics related to a main topic. "
            "Your task is to synthesize all this information into a single, comprehensive, and well-structured report in Markdown format. "
            "The report should have a clear introduction, body, and conclusion. "
            "Use headings, subheadings, lists, and bold text to organize the content effectively. "
            f'Main Topic: "{main_topic}".\n\n'
            f"--- Research Data ---\n{research_data}"
        )
        
        response = model.generate_content(prompt)
        return response.text
        
    except Exception as e:
        print(f"Error synthesizing report: {e}", file=sys.stderr)
        raise ValueError("Failed to synthesize the final report.")


# --- Main Application Runner (Equivalent to App.tsx) ---

def run_research_agent():
    """
    The main function that orchestrates the research process from start to finish.
    """
    # Setup command-line argument parsing to get the topic from the user
    parser = argparse.ArgumentParser(
        description="Deep Research AI Agent - A command-line tool to generate comprehensive reports on any topic."
    )
    parser.add_argument("topic", type=str, help="The main topic you want to research.")
    args = parser.parse_args()
    
    main_topic = args.topic
    
    print("-" * 50)
    print(f"🚀 Starting research for: \"{main_topic}\"")
    print("-" * 50)

    try:
        # STEP 1: BRAINSTORMING (Corresponds to ResearchStatus.BRAINSTORMING)
        sub_topics = brainstorm_sub_topics(main_topic)
        print(f"✅ Brainstorming complete. Found {len(sub_topics)} sub-topics.")
        print("-" * 50)

        # STEP 2: RESEARCHING (Corresponds to ResearchStatus.RESEARCHING)
        # This part is like the SubTopicList component updating statuses in the UI.
        print("🔎 Gathering information for each sub-topic...")
        research_results = []
        for sub_topic in sub_topics:
            summary = research_sub_topic(sub_topic)
            research_results.append({
                "topic": sub_topic,
                "summary": summary
            })
        print("✅ Research phase complete.")
        print("-" * 50)
        
        # STEP 3: SYNTHESIZING (Corresponds to ResearchStatus.SYNTHESIZING)
        # Prepare the data for the final synthesis step.
        research_data_str = "\n---\n".join(
            f'Sub-Topic: {r["topic"]}\nResearch Summary:\n{r["summary"]}'
            for r in research_results
        )
        
        final_report = synthesize_report(main_topic, research_data_str)
        
        # STEP 4: DISPLAY REPORT (Corresponds to ResearchStatus.DONE and ReportDisplay.tsx)
        # This is the equivalent of rendering the final report in the UI.
        print("\n\n" + "=" * 50)
        print("🎉 Research Complete! Final Report 🎉")
        print("=" * 50 + "\n")
        print(f"# Report on: {main_topic}\n")
        print(final_report)

    except (ValueError, Exception) as e:
        # Corresponds to ResearchStatus.ERROR
        print(f"\n❌ A critical error occurred: {e}", file=sys.stderr)
        sys.exit(1)

# --- Entry Point ---
# This makes the script runnable from the command line.
if __name__ == "__main__":
    run_research_agent()