"""
ui/clarification_widget.py
Renders clarification prompts as chat messages with suggestion chips.
Dimension answers pre-fill the next search turn via session state.
"""
import streamlit as st

_ACTIVITY_SUGGESTIONS = [
    "Hockey", "Soccer", "Swimming", "Basketball", "Tennis",
    "Coding", "Art", "Music", "Theatre", "Science",
]

_DIMENSION_CONFIG = {
    "activity": {
        "question": "What kind of activity are you looking for?",
        "widget": "chips",
        "options": _ACTIVITY_SUGGESTIONS,
    },
    "location": {
        "question": "Which city or region?",
        "widget": "text",
    },
    "age": {
        "question": "How old is your child?",
        "widget": "slider",
    },
}


def render_clarification(dimensions: list[str]):
    """
    Render clarification UI for the given dimensions.
    Stores answer in st.session_state['_clarification_answer'].
    """
    if not dimensions:
        return

    dimension = dimensions[0]
    config = _DIMENSION_CONFIG.get(dimension)
    if config is None:
        return

    with st.chat_message("assistant"):
        st.markdown(config["question"])

        if config["widget"] == "chips":
            cols = st.columns(min(len(config["options"]), 5))
            for i, option in enumerate(config["options"]):
                col = cols[i % len(cols)]
                if col.button(option, key=f"clarify_chip_{option}"):
                    st.session_state["_clarification_answer"] = option

        elif config["widget"] == "text":
            answer = st.text_input("Enter location", key="clarify_location_input")
            if answer:
                st.session_state["_clarification_answer"] = answer

        elif config["widget"] == "slider":
            age = st.slider("Child's age", min_value=4, max_value=18, value=10,
                            key="clarify_age_slider")
            if st.button("Use this age", key="clarify_age_submit"):
                st.session_state["_clarification_answer"] = str(age)
