from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin
import requests
import time
import json
import re
from urllib.parse import urlencode, quote
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'linkedin_job_app_secret_key_12345'

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# In-memory user store and job applications (for demonstration only)
users = {"demo@example.com": {"password": "password", "profile": {
    "name": "Demo User",
    "title": "Software Engineer", 
    "experience": "3 years",
    "skills": "Python, JavaScript, Flask, React"
}}}

# Store job applications and search history
job_applications = []
search_history = []

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if email in users and users[email]['password'] == password:
            user = User(email)
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', 
                         applications=job_applications,
                         search_history=search_history)

@app.route('/job-search', methods=['GET', 'POST'])
@login_required
def job_search():
    if request.method == 'POST':
        keywords = request.form.get('keywords', '')
        location = request.form.get('location', '')
        experience_level = request.form.get('experience_level', '')
        
        # Search for jobs (mock implementation)
        jobs = search_linkedin_jobs(keywords, location, experience_level)
        
        # Add to search history
        search_entry = {
            'keywords': keywords,
            'location': location,
            'experience_level': experience_level,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'results_count': len(jobs)
        }
        search_history.append(search_entry)
        
        return render_template('job_results.html', jobs=jobs, search_params=search_entry)
    
    return render_template('job_search.html')

@app.route('/apply-job', methods=['POST'])
@login_required
def apply_job():
    job_id = request.form.get('job_id')
    job_title = request.form.get('job_title')
    company = request.form.get('company')
    cover_letter = request.form.get('cover_letter', '')
    
    # Mock application process
    application = {
        'id': len(job_applications) + 1,
        'job_id': job_id,
        'job_title': job_title,
        'company': company,
        'cover_letter': cover_letter,
        'status': 'Applied',
        'applied_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    job_applications.append(application)
    flash(f'Successfully applied to {job_title} at {company}!')
    
    return redirect(url_for('dashboard'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    from flask_login import current_user
    user_data = users.get(current_user.id, {})
    
    if request.method == 'POST':
        # Update user profile
        profile_data = {
            'name': request.form.get('name', ''),
            'title': request.form.get('title', ''),
            'experience': request.form.get('experience', ''),
            'skills': request.form.get('skills', '')
        }
        users[current_user.id]['profile'] = profile_data
        flash('Profile updated successfully!')
        return redirect(url_for('profile'))
    
    return render_template('profile.html', profile=user_data.get('profile', {}))

def search_linkedin_jobs(keywords, location, experience_level):
    """
    Mock LinkedIn job search function.
    In a real implementation, this would use LinkedIn's API or web scraping
    (following LinkedIn's terms of service and rate limits).
    """
    # Mock job data for demonstration
    mock_jobs = [
        {
            'id': '1',
            'title': f'{keywords} Developer',
            'company': 'Tech Corp',
            'location': location or 'Remote',
            'description': f'Looking for an experienced {keywords} developer...',
            'experience_level': experience_level or 'Mid-level',
            'posted_date': '2 days ago',
            'linkedin_url': 'https://linkedin.com/jobs/view/123456'
        },
        {
            'id': '2', 
            'title': f'Senior {keywords} Engineer',
            'company': 'Innovation Inc',
            'location': location or 'San Francisco, CA',
            'description': f'Join our team as a {keywords} engineer...',
            'experience_level': 'Senior',
            'posted_date': '1 week ago',
            'linkedin_url': 'https://linkedin.com/jobs/view/789012'
        },
        {
            'id': '3',
            'title': f'{keywords} Specialist',
            'company': 'StartUp Co',
            'location': location or 'New York, NY',
            'description': f'We are seeking a {keywords} specialist...',
            'experience_level': experience_level or 'Entry-level',
            'posted_date': '3 days ago',
            'linkedin_url': 'https://linkedin.com/jobs/view/345678'
        }
    ]
    
    # Filter by experience level if specified
    if experience_level:
        mock_jobs = [job for job in mock_jobs if experience_level.lower() in job['experience_level'].lower()]
    
    return mock_jobs

@app.route('/api/job-stats')
@login_required
def job_stats():
    """API endpoint for job application statistics"""
    stats = {
        'total_applications': len(job_applications),
        'total_searches': len(search_history),
        'applications_this_month': len([app for app in job_applications 
                                      if datetime.now().month == datetime.strptime(app['applied_date'], '%Y-%m-%d %H:%M:%S').month])
    }
    return jsonify(stats)

if __name__ == '__main__':
    app.run(debug=True, port=5001)