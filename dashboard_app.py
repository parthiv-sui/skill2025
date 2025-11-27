import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import firebase_admin
from firebase_admin import credentials, firestore
import numpy as np
from datetime import datetime
import json

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

if df.empty:
    st.warning("No evaluation data found. Please evaluate some students first.")
    st.stop()

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
# TREND ANALYSIS
# ---------------------------------------------------------
st.header("📈 Performance Trends")

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
# RANKING AND LEADERBOARD (SIMPLIFIED)
# ---------------------------------------------------------
st.header("🏆 Student Rankings")

# Calculate rankings
leaderboard = filtered_df.groupby('roll_number').agg({
    'grand_total': 'max',
    'section': 'count'
}).rename(columns={'section': 'tests_completed'}).reset_index()

leaderboard = leaderboard.nlargest(10, 'grand_total')  # Top 10 students

# Display as a clean table instead of chart
st.subheader("Top 10 Performers")
leaderboard_display = leaderboard[['roll_number', 'grand_total', 'tests_completed']].rename(
    columns={'roll_number': 'Student', 'grand_total': 'Total Score', 'tests_completed': 'Tests Completed'}
)
st.dataframe(leaderboard_display, use_container_width=True)

# ---------------------------------------------------------
# INSIGHTS AND RECOMMENDATIONS
# ---------------------------------------------------------
st.header("💡 Insights & Recommendations")

if not filtered_df.empty:
    # Test-specific analysis
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Test-Wise Performance Analysis")
        
        # Calculate averages for each test type
        test_analysis = filtered_df.groupby('section').agg({
            'final_total': 'mean',
            'auto_mcq': 'mean',
            'auto_likert': 'mean', 
            'manual_total': 'mean'
        }).round(1)
        
        # Display test-wise performance
        for test_name in test_analysis.index:
            test_data = test_analysis.loc[test_name]
            avg_score = test_data['final_total']
            
            # Determine performance level
            if avg_score >= 80:
                performance_icon = "🎯"
                performance_level = "Excellent"
                color = "green"
            elif avg_score >= 60:
                performance_icon = "✅"
                performance_level = "Good" 
                color = "blue"
            elif avg_score >= 40:
                performance_icon = "⚠️"
                performance_level = "Average"
                color = "orange"
            else:
                performance_icon = "🚨"
                performance_level = "Needs Improvement"
                color = "red"
            
            st.markdown(f"**{performance_icon} {test_name}**")
            st.markdown(f"Average Score: **{avg_score}** ({performance_level})")
            
            # Test-specific insights
            if "Aptitude" in test_name:
                mcq_avg = test_data['auto_mcq']
                if mcq_avg < 15:
                    st.warning("• Focus on logical reasoning and quantitative skills")
                else:
                    st.success("• Strong analytical thinking demonstrated")
                    
            elif "Adaptability" in test_name:
                likert_avg = test_data['auto_likert']
                if likert_avg < 20:
                    st.warning("• Develop flexibility and change management skills")
                else:
                    st.success("• Excellent adaptability and learning agility")
                    
            elif "Communication Skills - Objective" in test_name:
                mcq_avg = test_data['auto_mcq']
                if mcq_avg < 10:
                    st.warning("• Improve grammar and vocabulary fundamentals")
                else:
                    st.success("• Good command of language basics")
                    
            elif "Communication Skills - Descriptive" in test_name:
                manual_avg = test_data['manual_total']
                if manual_avg < 15:
                    st.warning("• Practice structured writing and expression")
                else:
                    st.success("• Effective written communication skills")
            
            st.write("---")
    
    with col2:
        st.subheader("🎯 Overall Performance Insights")
        
        # Overall metrics
        avg_mcq = filtered_df['auto_mcq'].mean()
        avg_likert = filtered_df['auto_likert'].mean()
        avg_manual = filtered_df['manual_total'].mean()
        overall_avg = filtered_df['final_total'].mean()
        
        # Simple metrics display instead of gauge
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Average MCQ Score", f"{avg_mcq:.1f}")
        with col2:
            st.metric("Average Likert Score", f"{avg_likert:.1f}")
        with col3:
            st.metric("Average Manual Score", f"{avg_manual:.1f}")
        
        st.metric("Overall Average Score", f"{overall_avg:.1f}")
        
        # Skill category analysis
        st.subheader("🔧 Skill Category Breakdown")
        
        skill_data = {
            'Category': ['Analytical Skills', 'Adaptability', 'Communication'],
            'Average Score': [avg_mcq, avg_likert, avg_manual],
            'Max Possible': [30, 40, 30]  # Adjust based on your max scores
        }
        skill_df = pd.DataFrame(skill_data)
        skill_df['Percentage'] = (skill_df['Average Score'] / skill_df['Max Possible'] * 100).round(1)
        
        # Display as table instead of chart
        st.dataframe(skill_df[['Category', 'Average Score', 'Percentage']], use_container_width=True)
        
        # Top recommendations
        st.subheader("🎯 Top 3 Recommendations")
        
        recommendations = []
        
        if avg_mcq < 15:
            recommendations.append("• **Strengthen conceptual understanding** through practice tests")
        if avg_likert < 20:
            recommendations.append("• **Develop adaptability** through scenario-based learning")
        if avg_manual < 10:
            recommendations.append("• **Enhance communication skills** with writing exercises")
        if avg_mcq >= 20 and avg_likert >= 25:
            recommendations.append("• **Excellent overall performance** - focus on advanced topics")
        if len(recommendations) == 0:
            recommendations.append("• **Good balanced performance** across all areas")
        
        for i, rec in enumerate(recommendations[:3], 1):
            st.info(f"{rec}")

# Additional detailed analysis
st.header("📈 Detailed Performance Analytics")

col1, col2 = st.columns(2)

with col1:
    # Score distribution by test type
    st.subheader("📋 Score Distribution by Test")
    fig_box = px.box(
        filtered_df,
        x='section',
        y='final_total',
        title="Score Distribution Across Tests",
        color='section'
    )
    st.plotly_chart(fig_box, use_container_width=True)

with col2:
    # Performance consistency
    st.subheader("📈 Performance Consistency")
    
    # Calculate coefficient of variation (consistency metric)
    consistency_data = filtered_df.groupby('roll_number')['final_total'].std() / filtered_df.groupby('roll_number')['final_total'].mean()
    avg_consistency = consistency_data.mean()
    
    if avg_consistency < 0.2:
        consistency_msg = "**High Consistency** - Stable performance across tests"
        consistency_icon = "✅"
    elif avg_consistency < 0.4:
        consistency_msg = "**Moderate Consistency** - Some variation in performance"
        consistency_icon = "⚠️"
    else:
        consistency_msg = "**Variable Performance** - Significant differences between tests"
        consistency_icon = "🔄"
    
    st.metric("Performance Consistency", f"{avg_consistency:.2f}", 
              delta=consistency_msg, delta_color="off")
    
    st.info(f"{consistency_icon} {consistency_msg}")

# Test completion analysis (simplified)
st.subheader("🎯 Test Completion Status")
completion_stats = df.groupby('section')['is_fully_evaluated'].mean().round(3) * 100
completion_df = pd.DataFrame({
    'Test': completion_stats.index,
    'Evaluation Completion %': completion_stats.values
})

# Display as table instead of chart
st.dataframe(completion_df, use_container_width=True)

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
