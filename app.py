import streamlit as st
import pandas as pd
import os
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

# 3. Load Both Datasets into Memory
@st.cache_data
def load_data():
    skater_df = pd.read_csv("northeastern_hockey_stats_mcp.csv")
    goalie_df = pd.read_csv("northeastern_goalie_stats.csv")
    return skater_df, goalie_df

try:
    df_skaters, df_goalies = load_data()
except FileNotFoundError:
    st.error("Datasets not found. Please ensure both 'northeastern_hockey_stats_mcp.csv' and 'northeastern_goalie_stats.csv' are uploaded to the repository.")
    st.stop()

# 4. Initialize the Gemini LLM and Pandas Agent
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash", 
    google_api_key=api_key, 
    temperature=0  
)

# By passing a list of dataframes, the agent can query both.
# df1 will be skaters, df2 will be goalies.
agent = create_pandas_dataframe_agent(
    llm, 
    [df_skaters, df_goalies], 
    verbose=True, 
    allow_dangerous_code=True
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
                # To help the agent, we subtly inject a hint about which dataframe is which
                contextual_prompt = (
                    f"You have access to two dataframes. df1 contains skater stats. df2 contains goalie stats. "
                    f"Answer this question: {prompt}"
                )
                response = agent.run(contextual_prompt)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                error_msg = f"Sorry, I encountered an error running that calculation: {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})