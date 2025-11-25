import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import firebase_admin
from firebase_admin import credentials, firestore
import numpy as np
from datetime import datetime
import json  # Add this import

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="Faculty Evaluation Analytics Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("🎓 Faculty Evaluation Analytics Dashboard")
st.markdown("### Comprehensive Performance Insights & Visualizations")

# ---------------------------------------------------------
# FIREBASE INIT
# ---------------------------------------------------------
if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            cfg = dict(st.secrets["firebase"])
        else:
            with open("firebase_key.json") as f:
                cfg = json.load(f)
        cred = credentials.Certificate(cfg)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase init failed: {e}")
        st.stop()

db = firestore.client()

# ---------------------------------------------------------
# LOAD AND PROCESS DATA
# ---------------------------------------------------------
@st.cache_data
def load_all_evaluations():
    """Load all student evaluations from Firestore - include partially evaluated students"""
    try:
        docs = db.collection("student_responses").stream()
        
        students_data = []
        
        for doc in docs:
            data = doc.to_dict()
            roll_number = data.get('Roll', '').strip()
            section = data.get('Section', '').strip()
            
            if not roll_number or roll_number == 'Unknown':
                continue
                
            evaluation = data.get("Evaluation", {})
            
            # Include ALL documents, but mark evaluation status
            student_info = {
                'roll_number': roll_number,
                'section': section,
                'auto_mcq': evaluation.get('auto_mcq', 0),
                'auto_likert': evaluation.get('auto_likert', 0),
                'manual_total': evaluation.get('manual_total', 0),
                'final_total': evaluation.get('final_total', 0),
                'grand_total': evaluation.get('grand_total', 0),
                'doc_id': doc.id,
                'is_fully_evaluated': bool(evaluation)  # Track evaluation status
            }
            students_data.append(student_info)
        
        # Debug info
        if students_data:
            unique_students = len(set([s['roll_number'] for s in students_data]))
            evaluated_docs = len([s for s in students_data if s['is_fully_evaluated']])
            st.sidebar.info(f"📊 Loaded {len(students_data)} test records from {unique_students} students ({evaluated_docs} evaluated)")
        
        return pd.DataFrame(students_data)
        
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# Load data
df = load_all_evaluations()

# ========== ADD DEBUG SECTION ==========
st.sidebar.header("🔍 DEBUG: Data Verification")

# Check specific student data
target_student = "25BBAB152"  # Change this to your student's roll number
if target_student in df['roll_number'].values:
    st.sidebar.success(f"✅ Student {target_student} FOUND in data")
    student_records = df[df['roll_number'] == target_student]
    st.sidebar.write(f"Number of test records: {len(student_records)}")
    
    for _, record in student_records.iterrows():
        st.sidebar.write(f"**{record['section']}**:")
        st.sidebar.write(f"  - Final Total: {record['final_total']}")
        st.sidebar.write(f"  - Auto MCQ: {record['auto_mcq']}")
        st.sidebar.write(f"  - Auto Likert: {record['auto_likert']}")
        st.sidebar.write(f"  - Manual Total: {record['manual_total']}")
        st.sidebar.write(f"  - Grand Total: {record['grand_total']}")
        st.sidebar.write(f"  - Evaluated: {record['is_fully_evaluated']}")
        st.sidebar.write("  ---")
else:
    st.sidebar.error(f"❌ Student {target_student} NOT FOUND in loaded data")

# Check what's actually in Firebase for this student
st.sidebar.header("🔍 Firebase Direct Check")
try:
    student_docs = db.collection("student_responses").where("Roll", "==", target_student).stream()
    doc_count = 0
    for doc in student_docs:
        doc_count += 1
        data = doc.to_dict()
        evaluation = data.get("Evaluation", {})
        st.sidebar.write(f"📄 Firebase Document {doc_count}:")
        st.sidebar.write(f"  - Section: {data.get('Section')}")
        st.sidebar.write(f"  - Document ID: {doc.id}")
        st.sidebar.write(f"  - Final Total: {evaluation.get('final_total', 'NOT SAVED')}")
        st.sidebar.write(f"  - Auto Likert: {evaluation.get('auto_likert', 'NOT SAVED')}")
        st.sidebar.write(f"  - Grand Total: {evaluation.get('grand_total', 'NOT SAVED')}")
        st.sidebar.write("  ---")
    
    st.sidebar.write(f"Total Firebase docs for {target_student}: {doc_count}")
except Exception as e:
    st.sidebar.error(f"Error checking Firebase: {e}")

if df.empty:
    st.warning("No evaluation data found. Please evaluate some students first.")
    st.stop()
# ========== END DEBUG SECTION ==========

# ---------------------------------------------------------
# SIDEBAR FILTERS
# ---------------------------------------------------------
st.sidebar.header("🔍 Filters & Controls")

# Add refresh button
if st.sidebar.button("🔄 Clear Cache & Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# Roll number filter
all_rolls = sorted(df['roll_number'].unique())
selected_rolls = st.sidebar.multiselect(
    "Select Students:",
    options=all_rolls,
    default=all_rolls[:min(5, len(all_rolls))]  # Show first 5 by default
)

# Test type filter
all_tests = sorted(df['section'].unique())
selected_tests = st.sidebar.multiselect(
    "Select Tests:",
    options=all_tests,
    default=all_tests
)

# Filter data
filtered_df = df[
    (df['roll_number'].isin(selected_rolls)) & 
    (df['section'].isin(selected_tests))
]

# ---------------------------------------------------------
# KEY METRICS DASHBOARD
# ---------------------------------------------------------
st.header("📈 Key Performance Metrics")

# Calculate overall metrics
total_students = len(filtered_df['roll_number'].unique())
total_tests = len(filtered_df)
avg_grand_total = filtered_df.groupby('roll_number')['grand_total'].max().mean()
top_performer = filtered_df.loc[filtered_df.groupby('roll_number')['grand_total'].idxmax()].nlargest(1, 'grand_total')

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Students", total_students)
with col2:
    st.metric("Total Tests Evaluated", total_tests)
with col3:
    st.metric("Average Grand Total", f"{avg_grand_total:.1f}")
with col4:
    if not top_performer.empty:
        st.metric("Top Performer", top_performer.iloc[0]['roll_number'], 
                 delta=f"Score: {top_performer.iloc[0]['grand_total']}")

# ---------------------------------------------------------
# INDIVIDUAL STUDENT ANALYSIS
# ---------------------------------------------------------
st.header("👨‍🎓 Individual Student Performance")

if selected_rolls:
    selected_student = st.selectbox("Select Student for Detailed Analysis:", selected_rolls)
    
    student_data = filtered_df[filtered_df['roll_number'] == selected_student]
    
    if not student_data.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            # Student performance across tests
            fig_tests = px.bar(
                student_data, 
                x='section', 
                y='final_total',
                title=f"📊 {selected_student} - Performance by Test",
                color='final_total',
                color_continuous_scale='viridis'
            )
            fig_tests.update_layout(showlegend=False)
            st.plotly_chart(fig_tests, use_container_width=True)
        
        with col2:
            # Score composition for student
            test_scores = student_data[['section', 'auto_mcq', 'auto_likert', 'manual_total']].set_index('section')
            fig_composition = go.Figure()
            
            for test in test_scores.index:
                scores = test_scores.loc[test]
                fig_composition.add_trace(go.Bar(
                    name=test,
                    x=['MCQ', 'Likert', 'Manual'],
                    y=[scores['auto_mcq'], scores['auto_likert'], scores['manual_total']],
                    text=[scores['auto_mcq'], scores['auto_likert'], scores['manual_total']],
                    textposition='auto',
                ))
            
            fig_composition.update_layout(
                title=f"🎯 {selected_student} - Score Composition",
                barmode='group',
                xaxis_title="Score Type",
                yaxis_title="Marks"
            )
            st.plotly_chart(fig_composition, use_container_width=True)

# ---------------------------------------------------------
# COMPARATIVE ANALYSIS
# ---------------------------------------------------------
st.header("📊 Comparative Analysis")

col1, col2 = st.columns(2)

with col1:
    # Overall performance distribution
    student_totals = filtered_df.groupby('roll_number')['grand_total'].max()
    fig_distribution = px.histogram(
        x=student_totals,
        title="📈 Overall Score Distribution",
        labels={'x': 'Grand Total Score', 'y': 'Number of Students'},
        color_discrete_sequence=['#FF6B6B']
    )
    fig_distribution.update_layout(showlegend=False)
    st.plotly_chart(fig_distribution, use_container_width=True)

with col2:
    # Test-wise average performance
    test_avgs = filtered_df.groupby('section')['final_total'].mean().reset_index()
    fig_test_avg = px.pie(
        test_avgs,
        values='final_total',
        names='section',
        title="🥧 Average Performance by Test Type",
        hole=0.4
    )
    st.plotly_chart(fig_test_avg, use_container_width=True)

# ---------------------------------------------------------
# HEATMAP - STUDENT vs TEST PERFORMANCE
# ---------------------------------------------------------
st.header("🔥 Performance Heatmap")

# Create pivot table for heatmap
pivot_data = filtered_df.pivot_table(
    index='roll_number', 
    columns='section', 
    values='final_total', 
    aggfunc='max'
).fillna(0)

if not pivot_data.empty:
    fig_heatmap = px.imshow(
        pivot_data,
        title="Student vs Test Performance Heatmap",
        color_continuous_scale='RdYlGn',
        aspect="auto"
    )
    fig_heatmap.update_layout(
        xaxis_title="Tests",
        yaxis_title="Students"
    )
    st.plotly_chart(fig_heatmap, use_container_width=True)

# ---------------------------------------------------------
# TREND ANALYSIS
# ---------------------------------------------------------
st.header("📈 Trend Analysis")

if len(selected_rolls) > 1:
    # Line chart comparing multiple students
    trend_data = filtered_df.pivot_table(
        index='section', 
        columns='roll_number', 
        values='final_total', 
        aggfunc='max'
    ).reset_index()
    
    fig_trend = go.Figure()
    for student in selected_rolls[:5]:  # Limit to 5 students for clarity
        if student in trend_data.columns:
            fig_trend.add_trace(go.Scatter(
                x=trend_data['section'],
                y=trend_data[student],
                mode='lines+markers',
                name=student
            ))
    
    fig_trend.update_layout(
        title="📈 Performance Trends Across Tests",
        xaxis_title="Tests",
        yaxis_title="Scores",
        hovermode='x unified'
    )
    st.plotly_chart(fig_trend, use_container_width=True)

# ---------------------------------------------------------
# SCORE COMPOSITION ANALYSIS
# ---------------------------------------------------------
st.header("🎯 Score Composition Analysis")

col1, col2 = st.columns(2)

with col1:
    # Overall score type distribution
    total_mcq = filtered_df['auto_mcq'].sum()
    total_likert = filtered_df['auto_likert'].sum()
    total_manual = filtered_df['manual_total'].sum()
    
    composition_data = pd.DataFrame({
        'Type': ['MCQ', 'Likert', 'Manual'],
        'Total Marks': [total_mcq, total_likert, total_manual]
    })
    
    fig_composition = px.bar(
        composition_data,
        x='Type',
        y='Total Marks',
        title="📊 Total Marks by Assessment Type",
        color='Type',
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    st.plotly_chart(fig_composition, use_container_width=True)

with col2:
    # Test-wise score type breakdown
    test_breakdown = filtered_df.groupby('section')[['auto_mcq', 'auto_likert', 'manual_total']].sum().reset_index()
    test_breakdown_melted = test_breakdown.melt(
        id_vars=['section'], 
        value_vars=['auto_mcq', 'auto_likert', 'manual_total'],
        var_name='Score Type', 
        value_name='Marks'
    )
    
    # Clean up score type names
    test_breakdown_melted['Score Type'] = test_breakdown_melted['Score Type'].replace({
        'auto_mcq': 'MCQ',
        'auto_likert': 'Likert',
        'manual_total': 'Manual'
    })
    
    fig_breakdown = px.bar(
        test_breakdown_melted,
        x='section',
        y='Marks',
        color='Score Type',
        title="🎨 Score Type Breakdown by Test",
        barmode='stack'
    )
    st.plotly_chart(fig_breakdown, use_container_width=True)

# ---------------------------------------------------------
# RANKING AND LEADERBOARD
# ---------------------------------------------------------
st.header("🏆 Student Leaderboard")

# Calculate rankings
leaderboard = filtered_df.groupby('roll_number').agg({
    'grand_total': 'max',
    'section': 'count'
}).rename(columns={'section': 'tests_completed'}).reset_index()

leaderboard = leaderboard.nlargest(10, 'grand_total')  # Top 10 students

fig_leaderboard = px.bar(
    leaderboard,
    x='roll_number',
    y='grand_total',
    title="🎖️ Top 10 Performers",
    color='grand_total',
    color_continuous_scale='thermal',
    text='grand_total'
)
fig_leaderboard.update_traces(texttemplate='%{text}', textposition='outside')
fig_leaderboard.update_layout(showlegend=False)
st.plotly_chart(fig_leaderboard, use_container_width=True)

# ---------------------------------------------------------
# PERFORMANCE QUARTILES
# ---------------------------------------------------------
st.header("📊 Performance Segmentation")

if not filtered_df.empty:
    # Calculate quartiles
    grand_totals = filtered_df.groupby('roll_number')['grand_total'].max()
    quartiles = pd.cut(grand_totals, bins=4, labels=['Q4 (Low)', 'Q3', 'Q2', 'Q1 (High)'])
    quartile_counts = quartiles.value_counts().sort_index()
    
    fig_quartiles = px.pie(
        values=quartile_counts.values,
        names=quartile_counts.index,
        title="🥧 Performance Quartile Distribution",
        color_discrete_sequence=px.colors.sequential.RdBu
    )
    st.plotly_chart(fig_quartiles, use_container_width=True)

# ---------------------------------------------------------
# EXPORT AND REPORTING
# ---------------------------------------------------------
st.header("📥 Export Analytics")

col1, col2 = st.columns(2)

with col1:
    # Summary statistics
    st.subheader("📋 Summary Statistics")
    summary_stats = filtered_df.groupby('section')['final_total'].agg(['mean', 'median', 'std', 'min', 'max']).round(2)
    st.dataframe(summary_stats)

with col2:
    # Raw data export
    st.subheader("📤 Export Data")
    if st.button("📊 Download Filtered Data as CSV"):
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="⬇️ Download CSV",
            data=csv,
            file_name=f"evaluation_analytics_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# ---------------------------------------------------------
# INSIGHTS AND RECOMMENDATIONS
# ---------------------------------------------------------
st.header("💡 Insights & Recommendations")

if not filtered_df.empty:
    # Generate automatic insights
    avg_mcq = filtered_df['auto_mcq'].mean()
    avg_likert = filtered_df['auto_likert'].mean()
    avg_manual = filtered_df['manual_total'].mean()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info(f"**MCQ Performance**: {avg_mcq:.1f} avg")
        if avg_mcq < 15:
            st.warning("Consider reinforcing conceptual understanding")
        else:
            st.success("Strong conceptual knowledge!")
    
    with col2:
        st.info(f"**Likert Scale**: {avg_likert:.1f} avg")
        if avg_likert < 20:
            st.warning("Focus on adaptability skills development")
        else:
            st.success("Excellent adaptability traits!")
    
    with col3:
        st.info(f"**Manual Evaluation**: {avg_manual:.1f} avg")
        if avg_manual < 10:
            st.warning("Practice descriptive answer writing")
        else:
            st.success("Good communication skills!")

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.markdown("---")
st.markdown(
    "📊 *Dashboard created with ❤️ using Streamlit and Plotly* • "
    f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
)
