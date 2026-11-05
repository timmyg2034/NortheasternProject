import streamlit as st
import pandas as pd
import os
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent

# 1. Page Configuration
st.set_page_config(page_title="NU Hockey Stats Explorer", page_icon="🏒", layout="centered")
st.title("🏒 Northeastern Men's Hockey Stats Explorer")
st.write("Ask any question about historical skater or goalie statistics, game box scores, or opponent leaderboards.")

# 2. Securely Load the Gemini API Key
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

if not api_key:
    st.warning("Please configure your GEMINI_API_KEY in the application secrets to enable the AI agent.")
    st.stop()

def clean_opponent_name(name):
    name = str(name).strip()
    name = re.sub(r'^(?:#|No\.\s*)\d+(?:/(?:\d+|rv|RV))?(?:\s+\[\d+\])?\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^\[\d+\]\s+', '', name)
    name = re.sub(r'\s*\(exh\.?\)\s*$', ' (Exh)', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\(Championship Game\)\s*$', '', name, flags=re.IGNORECASE)
    name = name.replace('UMass Lowell', 'Massachusetts Lowell')
    name = name.replace('UMASS LOWELL', 'Massachusetts Lowell')
    name = name.replace('UMass-Lowell', 'Massachusetts Lowell')
    name = name.replace('UMass', 'Massachusetts')
    name = name.replace('UConn', 'Connecticut')
    name = name.replace('UNH', 'New Hampshire')
    name = name.replace('Rpi', 'Rensselaer')
    name = name.replace('RPI', 'Rensselaer')
    name = name.title()
    name = name.replace('Aic', 'AIC').replace('Rit', 'RIT')
    replacements = {
        'University Of Maine': 'Maine',
        'Univ. Of Maine': 'Maine',
        'Rv Maine': 'Maine',
        'University Of Connecticut': 'Connecticut',
        'University Of Massachusetts Lowell': 'Massachusetts Lowell',
        'Massachusetts-Amherst': 'Massachusetts',
        'University Of Massachusetts': 'Massachusetts',
        'University Of New Hampshire': 'New Hampshire',
        'U. Of New Hampshire': 'New Hampshire',
        'University Of Denver': 'Denver',
        'University Of Vermont': 'Vermont',
        'Providence College': 'Providence',
        'Merrimack College': 'Merrimack',
        'Quinnipiac University': 'Quinnipiac',
        'Quinnipiac University (Exh)': 'Quinnipiac',
        'Stonehill College': 'Stonehill',
        'Union College': 'Union',
        'Bentley University': 'Bentley',
        'Brown University': 'Brown',
        'Colgate University': 'Colgate',
        'Harvard University': 'Harvard',
        'Alabama-Huntsville': 'Alabama Huntsville',
        'Alaska-Anchorage': 'Alaska Anchorage',
        'University Of Alaska Anchorage': 'Alaska Anchorage',
        'Minnesota-Duluth': 'Minnesota Duluth',
        'Army West Point': 'Army',
        'Harvard (Exh)': 'Harvard',
        'Harvard (Championship Game)': 'Harvard',
        'Quinnipiac (Exh)': 'Quinnipiac',
        'Simon Fraser (Exh)': 'Simon Fraser',
        'Prince Edward Island (Exh)': 'Prince Edward Island',
        'Dalhousie University (Exh)': 'Dalhousie University',
        'Acadia (Exh)': 'Acadia',
    }
    return replacements.get(name, name)

# 3. Load Both Datasets into Memory
@st.cache_data
def load_data():
    skater_df = pd.read_csv("northeastern_hockey_stats_mcp.csv")
    goalie_df = pd.read_csv("northeastern_goalie_stats.csv")
    if "opponent" in skater_df.columns:
        skater_df["opponent"] = skater_df["opponent"].dropna().apply(clean_opponent_name)
    if "opponent" in goalie_df.columns:
        goalie_df["opponent"] = goalie_df["opponent"].dropna().apply(clean_opponent_name)
    return skater_df, goalie_df

try:
    df_skaters, df_goalies = load_data()
except FileNotFoundError:
    st.error("Datasets not found. Please ensure both 'northeastern_hockey_stats_mcp.csv' and 'northeastern_goalie_stats.csv' are uploaded to the repository.")
    st.stop()

# 4. Initialize the Gemini LLM and Pandas Agent
llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite", 
    google_api_key=api_key, 
    temperature=0  
)

# By passing a list of dataframes, the agent can query both.
# df1 will be skaters, df2 will be goalies.
agent = create_pandas_dataframe_agent(
    llm, 
    [df_skaters, df_goalies], 
    verbose=True, 
    allow_dangerous_code=True,
    agent_executor_kwargs={"handle_parsing_errors": True},
)

# 5. Initialize Chat History in Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 6. Capture User Input and Process the Query
if prompt := st.chat_input("e.g. How many saves did Devon Levi have against BU?"):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Querying the historical box scores..."):
            try:
                contextual_prompt = (
                    "You have access to two pandas DataFrames already loaded in memory: "
                    "`df1` (skater stats: date, opponent, nu_goals, opp_goals, player_name, goals, assists, points, shots, plus_minus) "
                    "and `df2` (goalie stats: date, opponent, nu_goals, opp_goals, goalie_name, decision, minutes, goals_against, empty_net_goals, saves, shots_against, save_pct). "
                    "Note that player_name and goalie_name may appear as 'Last, First' or 'First Last', so use `.str.contains(..., case=False, na=False)` when filtering by name. "
                    "When running Python code, ALWAYS use the exact ReAct format:\n"
                    "Thought: <your thought>\n"
                    "Action: python_repl_ast\n"
                    "Action Input: <single line of raw Python code without markdown backticks>\n"
                    "And when finished, output:\n"
                    "Thought: I now know the final answer\n"
                    "Final Answer: <your answer>\n\n"
                    f"Question: {prompt}"
                )
                result = agent.invoke({"input": contextual_prompt})
                response = result["output"] if isinstance(result, dict) and "output" in result else str(result)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                error_msg = f"Sorry, I encountered an error running that calculation: {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
