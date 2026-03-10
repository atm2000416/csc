"""
ui/filter_sidebar.py
Sidebar filters for camp search. Returns a dict of non-default active filters.
"""
import streamlit as st

_PROVINCES = [
    "Any", "Alberta", "British Columbia", "Manitoba", "New Brunswick",
    "Newfoundland and Labrador", "Nova Scotia", "Ontario", "Prince Edward Island",
    "Quebec", "Saskatchewan",
]

_TYPES = ["Any", "Day Camp", "Overnight", "Virtual"]

# Maps sidebar display labels to CSSL type map keys
_TYPE_TO_CSSL = {"Day Camp": "Day", "Overnight": "Overnight", "Virtual": "Virtual"}


def render_filters() -> dict:
    """
    Render sidebar filter controls and return active filter params dict.
    Only non-default values are included in the returned dict.
    """
    with st.sidebar:
        st.header("Filter Results")

        age_range = st.slider("Age", min_value=4, max_value=18, value=(4, 18))
        camp_type = st.selectbox("Type", _TYPES)
        cost_max = st.number_input("Max cost ($)", min_value=0, value=0, step=100)
        province = st.selectbox("Province", _PROVINCES)

    params = {}

    if age_range != (4, 18):
        params["age_from"] = age_range[0]
        params["age_to"] = age_range[1]

    if camp_type != "Any":
        params["type"] = _TYPE_TO_CSSL.get(camp_type, camp_type)

    if cost_max > 0:
        params["cost_max"] = int(cost_max)

    if province != "Any":
        params["province"] = province

    return params
