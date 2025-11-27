# ---------------------------------------------------------
# COMPREHENSIVE INSIGHTS & RECOMMENDATIONS - FIXED VERSION
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
    
    # DYNAMIC MESSAGING SYSTEM
    def generate_performance_narrative(avg_mcq, avg_likert, avg_manual, overall_avg, test_analysis):
        """Generate dynamic narrative based on actual performance data"""
        
        # Analyze performance patterns
        strong_adaptability = avg_likert >= 20
        strong_analytical = avg_mcq >= 15
        strong_communication = avg_manual >= 10
        balanced_performance = all([strong_adaptability, strong_analytical, strong_communication])
        
        # Count strong areas
        strong_areas = sum([strong_adaptability, strong_analytical, strong_communication])
        
        # Generate narrative based on performance patterns
        if balanced_performance:
            return {
                "title": "🎉 Exceptional All-Round Performance",
                "narrative": f"""
                Students are demonstrating <b>excellent balanced performance</b> across all assessment domains with an overall average of {overall_avg:.1f}. 
                The strong adaptability scores ({avg_likert:.1f}) indicate great learning agility, while solid analytical ({avg_mcq:.1f}) 
                and communication skills ({avg_manual:.1f}) show well-rounded development. This foundation positions students ideally 
                for advanced challenges and leadership opportunities.
                """,
                "tone": "success"
            }
        
        elif strong_adaptability and strong_areas >= 2:
            return {
                "title": "🚀 Strong Foundation with Key Strengths",
                "narrative": f"""
                Students show <b>promising performance patterns</b> with particular strength in adaptability and learning agility ({avg_likert:.1f}). 
                The overall score of {overall_avg:.1f} reflects good foundational skills, with analytical abilities at {avg_mcq:.1f} 
                and communication at {avg_manual:.1f}. The key opportunity lies in bringing all skill areas to the same high standard 
                as the demonstrated adaptability capabilities.
                """,
                "tone": "info"
            }
        
        elif strong_adaptability:
            return {
                "title": "🔄 Adaptability Strength with Growth Opportunities",
                "narrative": f"""
                The analysis reveals <b>strong adaptability potential</b> ({avg_likert:.1f}) alongside an overall score of {overall_avg:.1f}. 
                While students show excellent learning agility and flexibility, there are significant opportunities to strengthen 
                analytical thinking ({avg_mcq:.1f}) and communication skills ({avg_manual:.1f}). Focusing on these areas will create 
                more balanced and comprehensive skill development.
                """,
                "tone": "warning"
            }
        
        else:
            return {
                "title": "📚 Foundational Development Focus Needed",
                "narrative": f"""
                With an overall score of {overall_avg:.1f}, students are building their foundational skills across adaptability ({avg_likert:.1f}), 
                analytical thinking ({avg_mcq:.1f}), and communication ({avg_manual:.1f}). This represents an important developmental 
                phase where targeted interventions in conceptual understanding and skill application can drive significant 
                improvement. The current scores provide a clear baseline for measurable growth.
                """,
                "tone": "warning"
            }
    
    # Generate dynamic narrative
    performance_insight = generate_performance_narrative(avg_mcq, avg_likert, avg_manual, overall_avg, test_analysis)
    
    # Create a visually appealing layout
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # MAIN INSIGHTS CARD
        st.subheader("🎯 Executive Summary")
        
        insights_container = st.container()
        with insights_container:
            # Performance narrative with dynamic content
            st.markdown(f"### {performance_insight['title']}")
            
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
            
            # Dynamic performance narrative
            st.markdown("---")
            
            # Color code based on performance tone
            tone_colors = {
                "success": "#4CAF50",
                "info": "#2196F3", 
                "warning": "#FF9800"
            }
            
            st.markdown(f"""
            <div style='background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 5px solid {tone_colors[performance_insight['tone']]};'>
            <h4 style='color: {tone_colors[performance_insight['tone']]}; margin-top: 0;'>📈 Performance Analysis</h4>
            <p style='font-size: 16px; line-height: 1.6; color: #333;'>
            {performance_insight['narrative']}
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
        
        # Sort by priority
        priority_order = {"High": 1, "Medium": 2, "Low": 3}
        recommendations.sort(key=lambda x: priority_order[x["priority"]])
        
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
