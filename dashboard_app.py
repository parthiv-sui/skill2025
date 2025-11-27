import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
# ---------------------------------------------------------
# COMPREHENSIVE INSIGHTS & RECOMMENDATIONS - SINGULAR VERSION
# ---------------------------------------------------------
st.header("💡 Individual Student Performance Insights")

if not filtered_df.empty and selected_rolls:
    # For individual student analysis, use data only for the selected student
    if len(selected_rolls) == 1:
        # SINGLE STUDENT ANALYSIS
        student_df = filtered_df[filtered_df['roll_number'] == selected_rolls[0]]
        
        # Calculate metrics for this specific student
        avg_mcq = student_df['auto_mcq'].mean()
        avg_likert = student_df['auto_likert'].mean()
        avg_manual = student_df['manual_total'].mean()
        overall_avg = student_df['final_total'].mean()
        
        # Test-specific averages for this student
        test_analysis = student_df.groupby('section').agg({
            'final_total': 'mean',
            'auto_mcq': 'mean',
            'auto_likert': 'mean', 
            'manual_total': 'mean'
        }).round(1)
        
        student_name = selected_rolls[0]
        
    else:
        # MULTIPLE STUDENTS ANALYSIS (keep plural)
        avg_mcq = filtered_df['auto_mcq'].mean()
        avg_likert = filtered_df['auto_likert'].mean()
        avg_manual = filtered_df['manual_total'].mean()
        overall_avg = filtered_df['final_total'].mean()
        test_analysis = filtered_df.groupby('section').agg({
            'final_total': 'mean',
            'auto_mcq': 'mean',
            'auto_likert': 'mean', 
            'manual_total': 'mean'
        }).round(1)
        student_name = "Selected Students"

    # Create a visually appealing layout
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # MAIN INSIGHTS CARD
        st.subheader(f"🎯 {student_name} - Executive Summary")
        
        # Performance narrative
        st.markdown("### 📊 Performance Overview")
        
        # Create a performance score card
        score_col1, score_col2, score_col3, score_col4 = st.columns(4)
        with score_col1:
            st.metric("Overall Score", f"{overall_avg:.1f}")
        with score_col2:
            st.metric("Analytical", f"{avg_mcq:.1f}")
        with score_col3:
            st.metric("Adaptability", f"{avg_likert:.1f}")
        with score_col4:
            st.metric("Communication", f"{avg_manual:.1f}")
        
        # DYNAMIC PERFORMANCE NARRATIVE - SINGULAR VERSION
        if len(selected_rolls) == 1:
            # SINGULAR LANGUAGE FOR INDIVIDUAL STUDENT
            if avg_likert >= 20 and avg_mcq >= 15 and avg_manual >= 10:
                narrative = f"""
                <b>{student_name}</b> is demonstrating <b>excellent balanced performance</b> across all assessment domains with an overall average of {overall_avg:.1f}. 
                The strong adaptability score ({avg_likert:.1f}) indicates great learning agility, while solid analytical ({avg_mcq:.1f}) 
                and communication skills ({avg_manual:.1f}) show well-rounded development.
                """
                tone_color = "#4CAF50"
                title = "🎉 Exceptional All-Round Performance"
            elif avg_likert >= 20:
                narrative = f"""
                <b>{student_name}</b> shows <b>strong adaptability and learning agility</b> ({avg_likert:.1f}) with an overall score of {overall_avg:.1f}. 
                While adaptability is a key strength, there are opportunities to enhance analytical thinking ({avg_mcq:.1f}) 
                and communication skills ({avg_manual:.1f}) to achieve more balanced performance.
                """
                tone_color = "#2196F3"
                title = "🚀 Adaptability Strength with Growth Opportunities"
            else:
                narrative = f"""
                With an overall score of {overall_avg:.1f}, <b>{student_name}</b> is building foundational skills across adaptability ({avg_likert:.1f}), 
                analytical thinking ({avg_mcq:.1f}), and communication ({avg_manual:.1f}). Targeted focus on conceptual understanding 
                and skill application can drive significant improvement.
                """
                tone_color = "#FF9800"
                title = "📚 Foundational Development Focus Needed"
        else:
            # PLURAL LANGUAGE FOR MULTIPLE STUDENTS
            if avg_likert >= 20 and avg_mcq >= 15 and avg_manual >= 10:
                narrative = f"""
                Students are demonstrating <b>excellent balanced performance</b> across all assessment domains with an overall average of {overall_avg:.1f}. 
                The strong adaptability scores ({avg_likert:.1f}) indicate great learning agility, while solid analytical ({avg_mcq:.1f}) 
                and communication skills ({avg_manual:.1f}) show well-rounded development.
                """
                tone_color = "#4CAF50"
                title = "🎉 Exceptional All-Round Performance"
            elif avg_likert >= 20:
                narrative = f"""
                Students show <b>strong adaptability and learning agility</b> ({avg_likert:.1f}) with an overall score of {overall_avg:.1f}. 
                While adaptability is a key strength, there are opportunities to enhance analytical thinking ({avg_mcq:.1f}) 
                and communication skills ({avg_manual:.1f}) to achieve more balanced performance.
                """
                tone_color = "#2196F3"
                title = "🚀 Adaptability Strength with Growth Opportunities"
            else:
                narrative = f"""
                With an overall score of {overall_avg:.1f}, students are building foundational skills across adaptability ({avg_likert:.1f}), 
                analytical thinking ({avg_mcq:.1f}), and communication ({avg_manual:.1f}). Targeted focus on conceptual understanding 
                and skill application can drive significant improvement.
                """
                tone_color = "#FF9800"
                title = "📚 Foundational Development Focus Needed"
        
        st.markdown("---")
        st.markdown(f"""
        <div style='background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 5px solid {tone_color};'>
        <h4 style='color: {tone_color}; margin-top: 0;'>{title}</h4>
        <p style='font-size: 16px; line-height: 1.6; color: #333;'>
        {narrative}
        </p>
        </div>
        """, unsafe_allow_html=True)
        
        # TEST-WISE PERFORMANCE BREAKDOWN
        st.markdown("### 🎯 Test Performance Analysis")
        
        # Create performance cards for each test
        for test_name in test_analysis.index:
            test_data = test_analysis.loc[test_name]
            avg_score = test_data['final_total']
            
            # Determine performance level and styling
            if avg_score >= 80:
                performance_level = "Excellent"
                color = "#4CAF50"
                icon = "🎯"
                bg_color = "#f0fff0"
            elif avg_score >= 60:
                performance_level = "Good"
                color = "#2196F3"
                icon = "✅"
                bg_color = "#f0f8ff"
            elif avg_score >= 40:
                performance_level = "Average"
                color = "#FF9800"
                icon = "⚠️"
                bg_color = "#fff8f0"
            else:
                performance_level = "Needs Improvement"
                color = "#F44336"
                icon = "🚨"
                bg_color = "#fff0f0"
            
            # Create test performance card
            st.markdown(f"""
            <div style='background-color: {bg_color}; padding: 15px; border-radius: 10px; border-left: 5px solid {color}; margin: 10px 0;'>
            <div style='display: flex; justify-content: space-between; align-items: center;'>
                <div>
                    <h4 style='color: {color}; margin: 0;'>{icon} {test_name}</h4>
                    <p style='margin: 5px 0; font-size: 18px; font-weight: bold;'>Score: <span style='color: {color};'>{avg_score}</span> ({performance_level})</p>
                </div>
                <div style='text-align: right;'>
                    <div style='font-size: 24px; color: {color};'>{icon}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Add test-specific insights - SINGULAR VERSION
            insight_text = ""
            if "Aptitude" in test_name:
                mcq_avg = test_data['auto_mcq']
                if len(selected_rolls) == 1:
                    insight_text = "• Demonstrates strong analytical thinking and problem-solving skills" if mcq_avg >= 15 else "• Could benefit from strengthening logical reasoning and quantitative analysis"
                else:
                    insight_text = "• Strong analytical thinking and problem-solving skills demonstrated" if mcq_avg >= 15 else "• Opportunity to strengthen logical reasoning and quantitative analysis"
                
            elif "Adaptability" in test_name:
                likert_avg = test_data['auto_likert']
                if len(selected_rolls) == 1:
                    insight_text = "• Shows excellent learning agility and flexibility in new situations" if likert_avg >= 20 else "• Should develop resilience and adaptability to changing circumstances"
                else:
                    insight_text = "• Excellent learning agility and flexibility in new situations" if likert_avg >= 20 else "• Develop resilience and adaptability to changing circumstances"
                
            elif "Communication Skills - Objective" in test_name:
                mcq_avg = test_data['auto_mcq']
                if len(selected_rolls) == 1:
                    insight_text = "• Has a solid foundation in language fundamentals and comprehension" if mcq_avg >= 10 else "• Should build vocabulary and grammar fundamentals for better expression"
                else:
                    insight_text = "• Solid foundation in language fundamentals and comprehension" if mcq_avg >= 10 else "• Build vocabulary and grammar fundamentals for better expression"
                
            elif "Communication Skills - Descriptive" in test_name:
                manual_avg = test_data['manual_total']
                if len(selected_rolls) == 1:
                    insight_text = "• Demonstrates effective written expression and structured communication" if manual_avg >= 15 else "• Should practice organizing thoughts and expressing ideas clearly in writing"
                else:
                    insight_text = "• Effective written expression and structured communication" if manual_avg >= 15 else "• Practice organizing thoughts and expressing ideas clearly in writing"
            
            st.markdown(f"<p style='margin: 10px 0; color: #666;'>{insight_text}</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        # RECOMMENDATIONS & ACTION PLAN
        if len(selected_rolls) == 1:
            st.subheader(f"🚀 Action Plan for {student_name}")
        else:
            st.subheader("🚀 Group Action Plan")
        
        # Generate recommendations first
        recommendations = []
        
        # Dynamic recommendations based on actual performance
        if avg_mcq < 15:
            if len(selected_rolls) == 1:
                recommendations.append({
                    "title": "Strengthen Analytical Thinking",
                    "icon": "🧠",
                    "priority": "High",
                    "details": "Practice logical reasoning and problem-solving exercises"
                })
            else:
                recommendations.append({
                    "title": "Strengthen Analytical Thinking",
                    "icon": "🧠",
                    "priority": "High",
                    "details": "Students should practice logical reasoning exercises"
                })
        
        if avg_likert < 20:
            if len(selected_rolls) == 1:
                recommendations.append({
                    "title": "Develop Adaptability", 
                    "icon": "🔄",
                    "priority": "Medium" if avg_likert >= 15 else "High",
                    "details": "Scenario-based learning and flexibility training"
                })
            else:
                recommendations.append({
                    "title": "Develop Adaptability", 
                    "icon": "🔄",
                    "priority": "Medium" if avg_likert >= 15 else "High",
                    "details": "Students need scenario-based learning practice"
                })
        
        if avg_manual < 10:
            if len(selected_rolls) == 1:
                recommendations.append({
                    "title": "Enhance Communication",
                    "icon": "✍️",
                    "priority": "High", 
                    "details": "Structured writing practice and expression exercises"
                })
            else:
                recommendations.append({
                    "title": "Enhance Communication",
                    "icon": "✍️",
                    "priority": "High", 
                    "details": "Students need structured writing practice"
                })
        
        # Add positive reinforcement for strengths
        if avg_likert >= 20:
            if len(selected_rolls) == 1:
                recommendations.append({
                    "title": "Leverage Adaptability Strength",
                    "icon": "⭐",
                    "priority": "Low",
                    "details": "Apply learning agility to other skill areas"
                })
            else:
                recommendations.append({
                    "title": "Leverage Adaptability Strength",
                    "icon": "⭐",
                    "priority": "Low",
                    "details": "Students can apply learning agility to other areas"
                })
        
        if avg_mcq >= 15:
            if len(selected_rolls) == 1:
                recommendations.append({
                    "title": "Build on Analytical Skills", 
                    "icon": "📊",
                    "priority": "Low",
                    "details": "Tackle more complex problem-solving challenges"
                })
            else:
                recommendations.append({
                    "title": "Build on Analytical Skills", 
                    "icon": "📊",
                    "priority": "Low",
                    "details": "Students can tackle complex problem-solving"
                })
        
        # If no specific recommendations, add general one
        if not recommendations:
            if len(selected_rolls) == 1:
                recommendations.append({
                    "title": "Maintain Current Progress",
                    "icon": "✅",
                    "priority": "Low", 
                    "details": "Continue with current learning strategies"
                })
            else:
                recommendations.append({
                    "title": "Maintain Current Progress",
                    "icon": "✅",
                    "priority": "Low", 
                    "details": "Students should continue current strategies"
                })
        
        # Priority Recommendations
        st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px;'>
        <h4 style='color: white; margin-top: 0;'>🎯 Priority Actions</h4>
        """, unsafe_allow_html=True)
        
        # Display recommendations
        for i, rec in enumerate(recommendations[:4]):
            priority_color = {"High": "#FF6B6B", "Medium": "#FFA726", "Low": "#66BB6A"}
            
            st.markdown(f"""
            <div style='background-color: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px; margin: 10px 0;'>
                <div style='display: flex; justify-content: space-between; align-items: start;'>
                    <div style='font-size: 24px; margin-right: 10px;'>{rec['icon']}</div>
                    <div style='flex-grow: 1;'>
                        <h5 style='color: white; margin: 0 0 5px 0;'>{rec['title']}</h5>
                        <p style='color: rgba(255,255,255,0.9); margin: 0; font-size: 14px;'>{rec['details']}</p>
                    </div>
                    <div style='background-color: {priority_color[rec['priority']]}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px;'>
                        {rec['priority']}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # SKILL DISTRIBUTION VISUALIZATION
        st.markdown("### 🔧 Skill Mastery Levels")
        
        skill_data = {
            'Category': ['Analytical', 'Adaptability', 'Communication'],
            'Score': [avg_mcq, avg_likert, avg_manual],
            'Max_Possible': [30, 40, 30],
            'Color': ['#FF6B6B', '#4ECDC4', '#45B7D1']
        }
        skill_df = pd.DataFrame(skill_data)
        skill_df['Percentage'] = (skill_df['Score'] / skill_df['Max_Possible'] * 100).round(1)
        
        # Create a horizontal bar chart for skill distribution
        fig_skills = go.Figure()
        
        for i, row in skill_df.iterrows():
            fig_skills.add_trace(go.Bar(
                y=[row['Category']],
                x=[row['Percentage']],
                orientation='h',
                name=row['Category'],
                marker_color=row['Color'],
                text=[f"{row['Percentage']}%"],
                textposition='auto',
                hovertemplate=f"<b>{row['Category']}</b><br>Score: {row['Score']}<br>Percentage: {row['Percentage']}%<extra></extra>"
            ))
        
        fig_skills.update_layout(
            title="Skill Mastery Percentage",
            xaxis=dict(range=[0, 100], title="Mastery %"),
            yaxis_title="Skill Area",
            showlegend=False,
            height=250,
            margin=dict(l=50, r=50, t=50, b=50)
        )
        
        st.plotly_chart(fig_skills, use_container_width=True)

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
# COMPREHENSIVE INSIGHTS & RECOMMENDATIONS
# ---------------------------------------------------------
st.header("💡 Comprehensive Performance Insights & Recommendations")

if not filtered_df.empty:
    # Calculate overall metrics
    avg_mcq = filtered_df['auto_mcq'].mean()
    avg_likert = filtered_df['auto_likert'].mean()
    avg_manual = filtered_df['manual_total'].mean()
    overall_avg = filtered_df['final_total'].mean()
    
    # Test-specific averages
    test_analysis = filtered_df.groupby('section').agg({
        'final_total': 'mean',
        'auto_mcq': 'mean',
        'auto_likert': 'mean', 
        'manual_total': 'mean'
    }).round(1)
    
    # Create a visually appealing layout
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # MAIN INSIGHTS CARD
        st.subheader("🎯 Executive Summary")
        
        # Performance narrative
        st.markdown("### 📊 Overall Performance Overview")
        
        # Create a performance score card
        score_col1, score_col2, score_col3, score_col4 = st.columns(4)
        with score_col1:
            st.metric("Overall Score", f"{overall_avg:.1f}")
        with score_col2:
            st.metric("Analytical", f"{avg_mcq:.1f}")
        with score_col3:
            st.metric("Adaptability", f"{avg_likert:.1f}")
        with score_col4:
            st.metric("Communication", f"{avg_manual:.1f}")
        
        # Dynamic performance narrative based on scores
        if avg_likert >= 20 and avg_mcq >= 15 and avg_manual >= 10:
            narrative = f"""
            Students are demonstrating <b>excellent balanced performance</b> across all assessment domains with an overall average of {overall_avg:.1f}. 
            The strong adaptability scores ({avg_likert:.1f}) indicate great learning agility, while solid analytical ({avg_mcq:.1f}) 
            and communication skills ({avg_manual:.1f}) show well-rounded development.
            """
            tone_color = "#4CAF50"
            title = "🎉 Exceptional All-Round Performance"
        elif avg_likert >= 20:
            narrative = f"""
            Students show <b>strong adaptability and learning agility</b> ({avg_likert:.1f}) with an overall score of {overall_avg:.1f}. 
            While adaptability is a key strength, there are opportunities to enhance analytical thinking ({avg_mcq:.1f}) 
            and communication skills ({avg_manual:.1f}) to achieve more balanced performance.
            """
            tone_color = "#2196F3"
            title = "🚀 Adaptability Strength with Growth Opportunities"
        else:
            narrative = f"""
            With an overall score of {overall_avg:.1f}, students are building foundational skills across adaptability ({avg_likert:.1f}), 
            analytical thinking ({avg_mcq:.1f}), and communication ({avg_manual:.1f}). Targeted focus on conceptual understanding 
            and skill application can drive significant improvement.
            """
            tone_color = "#FF9800"
            title = "📚 Foundational Development Focus Needed"
        
        st.markdown("---")
        st.markdown(f"""
        <div style='background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 5px solid {tone_color};'>
        <h4 style='color: {tone_color}; margin-top: 0;'>{title}</h4>
        <p style='font-size: 16px; line-height: 1.6; color: #333;'>
        {narrative}
        </p>
        </div>
        """, unsafe_allow_html=True)
        
        # TEST-WISE PERFORMANCE BREAKDOWN
        st.markdown("### 🎯 Detailed Test Analysis")
        
        # Create performance cards for each test
        for test_name in test_analysis.index:
            test_data = test_analysis.loc[test_name]
            avg_score = test_data['final_total']
            
            # Determine performance level and styling
            if avg_score >= 80:
                performance_level = "Excellent"
                color = "#4CAF50"
                icon = "🎯"
                bg_color = "#f0fff0"
            elif avg_score >= 60:
                performance_level = "Good"
                color = "#2196F3"
                icon = "✅"
                bg_color = "#f0f8ff"
            elif avg_score >= 40:
                performance_level = "Average"
                color = "#FF9800"
                icon = "⚠️"
                bg_color = "#fff8f0"
            else:
                performance_level = "Needs Improvement"
                color = "#F44336"
                icon = "🚨"
                bg_color = "#fff0f0"
            
            # Create test performance card
            st.markdown(f"""
            <div style='background-color: {bg_color}; padding: 15px; border-radius: 10px; border-left: 5px solid {color}; margin: 10px 0;'>
            <div style='display: flex; justify-content: space-between; align-items: center;'>
                <div>
                    <h4 style='color: {color}; margin: 0;'>{icon} {test_name}</h4>
                    <p style='margin: 5px 0; font-size: 18px; font-weight: bold;'>Average Score: <span style='color: {color};'>{avg_score}</span> ({performance_level})</p>
                </div>
                <div style='text-align: right;'>
                    <div style='font-size: 24px; color: {color};'>{icon}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Add test-specific insights
            insight_text = ""
            if "Aptitude" in test_name:
                mcq_avg = test_data['auto_mcq']
                insight_text = "• Strong analytical thinking and problem-solving skills demonstrated" if mcq_avg >= 15 else "• Opportunity to strengthen logical reasoning and quantitative analysis"
                
            elif "Adaptability" in test_name:
                likert_avg = test_data['auto_likert']
                insight_text = "• Excellent learning agility and flexibility in new situations" if likert_avg >= 20 else "• Develop resilience and adaptability to changing circumstances"
                
            elif "Communication Skills - Objective" in test_name:
                mcq_avg = test_data['auto_mcq']
                insight_text = "• Solid foundation in language fundamentals and comprehension" if mcq_avg >= 10 else "• Build vocabulary and grammar fundamentals for better expression"
                
            elif "Communication Skills - Descriptive" in test_name:
                manual_avg = test_data['manual_total']
                insight_text = "• Effective written expression and structured communication" if manual_avg >= 15 else "• Practice organizing thoughts and expressing ideas clearly in writing"
            
            st.markdown(f"<p style='margin: 10px 0; color: #666;'>{insight_text}</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        # RECOMMENDATIONS & ACTION PLAN
        st.subheader("🚀 Personalized Action Plan")
        
        # Priority Recommendations
        st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px;'>
        <h4 style='color: white; margin-top: 0;'>🎯 Priority Actions</h4>
        """, unsafe_allow_html=True)
        
        recommendations = []
        
        # Dynamic recommendations based on actual performance
        if avg_mcq < 15:
            recommendations.append({
                "title": "Strengthen Analytical Thinking",
                "icon": "🧠",
                "priority": "High",
                "details": "Practice logical reasoning and problem-solving exercises"
            })
        
        if avg_likert < 20:
            recommendations.append({
                "title": "Develop Adaptability", 
                "icon": "🔄",
                "priority": "Medium" if avg_likert >= 15 else "High",
                "details": "Scenario-based learning and flexibility training"
            })
        
        if avg_manual < 10:
            recommendations.append({
                "title": "Enhance Communication",
                "icon": "✍️",
                "priority": "High", 
                "details": "Structured writing practice and expression exercises"
            })
        
        # Add positive reinforcement for strengths
        if avg_likert >= 20:
            recommendations.append({
                "title": "Leverage Adaptability Strength",
                "icon": "⭐",
                "priority": "Low",
                "details": "Apply learning agility to other skill areas"
            })
        
        if avg_mcq >= 15:
            recommendations.append({
                "title": "Build on Analytical Skills", 
                "icon": "📊",
                "priority": "Low",
                "details": "Tackle more complex problem-solving challenges"
            })
        
        # If no specific recommendations, add general one
        if not recommendations:
            recommendations.append({
                "title": "Maintain Current Progress",
                "icon": "✅",
                "priority": "Low", 
                "details": "Continue with current learning strategies"
            })
        
        # Display recommendations
        for i, rec in enumerate(recommendations[:4]):  # Show top 4
            priority_color = {"High": "#FF6B6B", "Medium": "#FFA726", "Low": "#66BB6A"}
            
            st.markdown(f"""
            <div style='background-color: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px; margin: 10px 0;'>
                <div style='display: flex; justify-content: space-between; align-items: start;'>
                    <div style='font-size: 24px; margin-right: 10px;'>{rec['icon']}</div>
                    <div style='flex-grow: 1;'>
                        <h5 style='color: white; margin: 0 0 5px 0;'>{rec['title']}</h5>
                        <p style='color: rgba(255,255,255,0.9); margin: 0; font-size: 14px;'>{rec['details']}</p>
                    </div>
                    <div style='background-color: {priority_color[rec['priority']]}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px;'>
                        {rec['priority']}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # SKILL DISTRIBUTION VISUALIZATION
        st.markdown("### 🔧 Skill Mastery Levels")
        
        skill_data = {
            'Category': ['Analytical', 'Adaptability', 'Communication'],
            'Score': [avg_mcq, avg_likert, avg_manual],
            'Max_Possible': [30, 40, 30],
            'Color': ['#FF6B6B', '#4ECDC4', '#45B7D1']
        }
        skill_df = pd.DataFrame(skill_data)
        skill_df['Percentage'] = (skill_df['Score'] / skill_df['Max_Possible'] * 100).round(1)
        
        # Create a horizontal bar chart for skill distribution
        fig_skills = go.Figure()
        
        for i, row in skill_df.iterrows():
            fig_skills.add_trace(go.Bar(
                y=[row['Category']],
                x=[row['Percentage']],
                orientation='h',
                name=row['Category'],
                marker_color=row['Color'],
                text=[f"{row['Percentage']}%"],
                textposition='auto',
                hovertemplate=f"<b>{row['Category']}</b><br>Score: {row['Score']}<br>Percentage: {row['Percentage']}%<extra></extra>"
            ))
        
        fig_skills.update_layout(
            title="Skill Mastery Percentage",
            xaxis=dict(range=[0, 100], title="Mastery %"),
            yaxis_title="Skill Area",
            showlegend=False,
            height=250,
            margin=dict(l=50, r=50, t=50, b=50)
        )
        
        st.plotly_chart(fig_skills, use_container_width=True)
        
        # QUICK STATS
        st.markdown("### 📈 Performance Snapshot")
        
        # Calculate performance indicators
        strong_areas = sum([avg_mcq >= 15, avg_likert >= 20, avg_manual >= 10])
        
        stats_col1, stats_col2 = st.columns(2)
        with stats_col1:
            st.metric("Strong Areas", strong_areas)
        
        with stats_col2:
            improvement_needed = 3 - strong_areas
            st.metric("Focus Areas", improvement_needed)

# Performance Growth Pathway
st.markdown("---")
st.subheader("📈 Growth Pathway")

# Create dynamic growth recommendations based on performance
growth_col1, growth_col2, growth_col3 = st.columns(3)

with growth_col1:
    focus_area = "Communication" if avg_manual < 10 else ("Analytical" if avg_mcq < 15 else "Advanced Skills")
    st.markdown(f"""
    <div style='text-align: center; padding: 15px; background-color: #e8f4f8; border-radius: 10px;'>
    <div style='font-size: 24px;'>🎯</div>
    <h4>Immediate Focus</h4>
    <p><b>{focus_area}</b><br>Build foundational strength</p>
    </div>
    """, unsafe_allow_html=True)

with growth_col2:
    development_area = "Applied Learning" if avg_likert >= 20 else "Adaptability"
    st.markdown(f"""
    <div style='text-align: center; padding: 15px; background-color: #e8f4f8; border-radius: 10px;'>
    <div style='font-size: 24px;'>🚀</div>
    <h4>Next Phase</h4>
    <p><b>{development_area}</b><br>Develop advanced capabilities</p>
    </div>
    """, unsafe_allow_html=True)

with growth_col3:
    mastery_goal = "Balanced Excellence" if strong_areas >= 2 else "Skill Integration"
    st.markdown(f"""
    <div style='text-align: center; padding: 15px; background-color: #e8f4f8; border-radius: 10px;'>
    <div style='font-size: 24px;'>⭐</div>
    <h4>Long-term Goal</h4>
    <p><b>{mastery_goal}</b><br>Achieve comprehensive mastery</p>
    </div>
    """, unsafe_allow_html=True)

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
