"""
ui/filter_sidebar.py
Inline collapsible filter bar for camp search.
Returns a dict of non-default active filters.
"""
import streamlit as st

_PROVINCES = [
    "Any", "Alberta", "British Columbia", "Manitoba", "New Brunswick",
    "Newfoundland and Labrador", "Nova Scotia", "Ontario", "Prince Edward Island",
    "Quebec", "Saskatchewan",
]

_TYPES = ["Any", "Day Camp", "Overnight", "Virtual"]

_TYPE_TO_CSSL = {"Day Camp": "Day", "Overnight": "Overnight", "Virtual": "Virtual"}


def render_filters() -> dict:
    """
    Render inline collapsible filter controls and return active filter params dict.
    Only non-default values are included in the returned dict.
    """
    with st.expander("🔍 Filters", expanded=False):
        col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
        with col1:
            age_range = st.slider("Age", min_value=4, max_value=18, value=(4, 18),
                                  key="filter_age")
        with col2:
            camp_type = st.selectbox("Type", _TYPES, key="filter_type")
        with col3:
            cost_max = st.number_input("Max cost ($)", min_value=0, value=0, step=100,
                                       key="filter_cost")
        with col4:
            province = st.selectbox("Province", _PROVINCES, key="filter_province")
        with col5:
            st.markdown("<br>", unsafe_allow_html=True)
            debug = st.checkbox("Debug", value=False, key="filter_debug")

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
