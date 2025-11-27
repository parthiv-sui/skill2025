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
        
        insights_container = st.container()
        with insights_container:
            # Overall Performance Score with visual indicator
            st.markdown("### 📊 Overall Performance Overview")
            
            # Create a performance score card
            score_col1, score_col2, score_col3 = st.columns(3)
            with score_col1:
                st.metric("Overall Score", f"{overall_avg:.1f}")
            with score_col2:
                st.metric("MCQ Performance", f"{avg_mcq:.1f}")
            with score_col3:
                st.metric("Adaptability", f"{avg_likert:.1f}")
            
            # Performance narrative
            st.markdown("---")
            st.markdown("""
            <div style='background-color: #f0f8ff; padding: 20px; border-radius: 10px; border-left: 5px solid #4CAF50;'>
            <h4 style='color: #2E86AB; margin-top: 0;'>📈 Key Performance Insights</h4>
            <p style='font-size: 16px; line-height: 1.6;'>
            Students demonstrate <b>strong adaptability and learning agility</b> with excellent performance in adaptability assessments. 
            However, there's a clear need to strengthen conceptual understanding through targeted practice tests and enhance 
            communication skills with structured writing exercises. The analytical foundation shows promise but requires 
            further development to reach its full potential.
            </p>
            </div>
            """, unsafe_allow_html=True)
        
        # TEST-WISE PERFORMANCE BREAKDOWN
        st.markdown("### 🎯 Test-Wise Performance Analysis")
        
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
            if "Aptitude" in test_name:
                mcq_avg = test_data['auto_mcq']
                insight_text = "• Strong analytical thinking demonstrated" if mcq_avg >= 15 else "• Focus on logical reasoning and quantitative skills"
                st.markdown(f"<p style='margin: 10px 0; color: #666;'>{insight_text}</p>", unsafe_allow_html=True)
                
            elif "Adaptability" in test_name:
                likert_avg = test_data['auto_likert']
                insight_text = "• Excellent adaptability and learning agility" if likert_avg >= 20 else "• Develop flexibility and change management skills"
                st.markdown(f"<p style='margin: 10px 0; color: #666;'>{insight_text}</p>", unsafe_allow_html=True)
                
            elif "Communication Skills - Objective" in test_name:
                mcq_avg = test_data['auto_mcq']
                insight_text = "• Good command of language basics" if mcq_avg >= 10 else "• Improve grammar and vocabulary fundamentals"
                st.markdown(f"<p style='margin: 10px 0; color: #666;'>{insight_text}</p>", unsafe_allow_html=True)
                
            elif "Communication Skills - Descriptive" in test_name:
                manual_avg = test_data['manual_total']
                insight_text = "• Effective written communication skills" if manual_avg >= 15 else "• Practice structured writing and expression"
                st.markdown(f"<p style='margin: 10px 0; color: #666;'>{insight_text}</p>", unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        # RECOMMENDATIONS & ACTION PLAN
        st.subheader("🚀 Action Plan & Recommendations")
        
        # Priority Recommendations
        st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px;'>
        <h4 style='color: white; margin-top: 0;'>🎯 Priority Actions</h4>
        """, unsafe_allow_html=True)
        
        recommendations = []
        
        if avg_mcq < 15:
            recommendations.append({
                "title": "Strengthen Conceptual Understanding",
                "icon": "🧠",
                "details": "Through targeted practice tests and analytical exercises"
            })
        if avg_likert < 20:
            recommendations.append({
                "title": "Develop Adaptability Skills", 
                "icon": "🔄",
                "details": "Through scenario-based learning and change management training"
            })
        if avg_manual < 10:
            recommendations.append({
                "title": "Enhance Communication Skills",
                "icon": "✍️", 
                "details": "With structured writing exercises and expression practice"
            })
        if avg_mcq >= 20 and avg_likert >= 25:
            recommendations.append({
                "title": "Advanced Skill Development",
                "icon": "⭐",
                "details": "Focus on advanced topics and complex problem-solving"
            })
        if len(recommendations) == 0:
            recommendations.append({
                "title": "Maintain Balanced Performance",
                "icon": "✅",
                "details": "Continue current learning strategies across all areas"
            })
        
        # Display recommendations
        for i, rec in enumerate(recommendations[:3], 1):
            st.markdown(f"""
            <div style='background-color: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px; margin: 10px 0;'>
                <div style='font-size: 24px; margin-bottom: 10px;'>{rec['icon']}</div>
                <h5 style='color: white; margin: 5px 0;'>{rec['title']}</h5>
                <p style='color: rgba(255,255,255,0.9); margin: 0; font-size: 14px;'>{rec['details']}</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # SKILL DISTRIBUTION VISUALIZATION
        st.markdown("### 🔧 Skill Distribution")
        
        skill_data = {
            'Category': ['Analytical Skills', 'Adaptability', 'Communication'],
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
            title="Skill Mastery Levels",
            xaxis_title="Mastery Percentage (%)",
            yaxis_title="Skill Category",
            showlegend=False,
            height=300,
            margin=dict(l=50, r=50, t=50, b=50)
        )
        
        st.plotly_chart(fig_skills, use_container_width=True)
        
        # QUICK STATS
        st.markdown("### 📈 Quick Stats")
        stats_col1, stats_col2 = st.columns(2)
        
        with stats_col1:
            st.metric("Avg. Adaptability", f"{avg_likert:.1f}", 
                     delta="Strong" if avg_likert >= 20 else "Needs Work")
        
        with stats_col2:
            st.metric("Avg. Communication", f"{avg_manual:.1f}", 
                     delta="Good" if avg_manual >= 10 else "Improve")

# Performance Trends Over Time (if applicable)
st.markdown("---")
st.subheader("📈 Performance Improvement Roadmap")

# Create a timeline visualization for improvement
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div style='text-align: center; padding: 15px; background-color: #e8f4f8; border-radius: 10px;'>
    <div style='font-size: 24px;'>🎯</div>
    <h4>Short Term</h4>
    <p>Focus on communication skills and conceptual clarity</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div style='text-align: center; padding: 15px; background-color: #e8f4f8; border-radius: 10px;'>
    <div style='font-size: 24px;'>🚀</div>
    <h4>Medium Term</h4>
    <p>Develop advanced analytical and adaptability skills</p>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div style='text-align: center; padding: 15px; background-color: #e8f4f8; border-radius: 10px;'>
    <div style='font-size: 24px;'>⭐</div>
    <h4>Long Term</h4>
    <p>Achieve balanced excellence across all skill domains</p>
    </div>
    """, unsafe_allow_html=True)

# Final Summary
st.markdown("""
<div style='background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); padding: 20px; border-radius: 10px; margin-top: 20px;'>
<h4 style='color: #333;'>💡 Summary</h4>
<p style='color: #333; line-height: 1.6;'>
The analysis reveals a group with <b>strong adaptability potential</b> but varying performance across different skill domains. 
The immediate focus should be on strengthening foundational conceptual understanding while maintaining the excellent 
adaptability scores. Communication skills, particularly written expression, present the most significant opportunity 
for improvement through structured practice and targeted exercises.
</p>
</div>
""", unsafe_allow_html=True)
