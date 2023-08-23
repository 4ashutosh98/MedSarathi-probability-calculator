from datetime import datetime
import math
import pandas as pd
from flask import Flask, render_template, request, Response, redirect, url_for, flash
from flask import session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from flask_mail import Mail, Message
from flask_migrate import Migrate
import csv
import io
import openai

openai.api_key = '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'

use_refine_recommendations = "no"


app = Flask(__name__)
app.secret_key = 'roses_are_red_violets_are_blue'


app.config['MAIL_SERVER']='smtp.mailtrap.io'
app.config['MAIL_PORT'] = 2525
app.config['MAIL_USERNAME'] = '7f5f8937ce4af5'
app.config['MAIL_PASSWORD'] = '2ec22f4dba124f'
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_DEFAULT_SENDER'] = 'default@usmlesarthi.com'


mail = Mail(app)

# Dictionary containing average step 1 score for each specialty for Non-U.S. IMGs
visa_step1_dict = {'anesth': 234, 'intmed': 238, 'neuro': 239, 'patho': 232, 'psych': 229, 'fammed': 219, 'pediat': 229}

# Dictionary containing average step 1 score for each specialty for U.S. IMGs
no_visa_step1_dict = {'anesth': 233, 'intmed': 225, 'neuro': 225, 'patho': 238, 'psych': 216, 'fammed': 211, 'pediat': 220}

# Dictionary containing average step 2 score for each specialty for Non-U.S. IMGs
visa_step2_dict = {'anesth': 240, 'intmed': 245, 'neuro': 245, 'patho': 219, 'psych': 236, 'fammed': 231, 'pediat': 240}

# Dictionary containing average step 2 score for each specialty for U.S. IMGs
no_visa_step2_dict = {'anesth': 243, 'intmed': 235, 'neuro': 235, 'patho': 228, 'psych': 228, 'fammed': 225, 'pediat': 233}

# Dictionary containing average research experience (in months) for each specialty for Non-U.S. IMGs
visa_research_exp_dict = {'anesth': 2.8, 'intmed': 2.6, 'neuro': 3.4, 'patho': 2.9, 'psych': 3.8, 'fammed':2.0, 'pediat': 2.8}

# Dictionary containing average research experience (in months) for each specialty for U.S. IMGs
no_visa_research_exp_dict = {'anesth': 2.0, 'intmed': 2.2, 'neuro': 3.5, 'patho': 2.9, 'psych': 2.3, 'fammed': 1.8, 'pediat': 2.0}

# Dictionary containing average research publications (in months) for each specialty for Non-U.S. IMGs
visa_research_pub_dict = {'anesth': 9.1, 'intmed': 5.8, 'neuro': 10.6, 'patho': 10.5, 'psych': 9.1, 'fammed': 3.8, 'pediat': 5.7}

# Dictionary containing average research publications (in months) for each specialty for U.S. IMGs
no_visa_research_pub_dict = {'anesth': 5.1, 'intmed': 2.8, 'neuro': 5.7, 'patho': 5.6, 'psych': 3.9, 'fammed': 2.3, 'pediat': 2.9}

# Dictionary containing average work experience (in months) for each specialty for Non-U.S. IMGs
visa_usce_dict = {'anesth': 5.8, 'intmed': 6.3, 'neuro': 6.3, 'patho': 5.7, 'psych': 6.6, 'fammed': 5.3, 'pediat': 6.1}

# Dictionary containing average work experience (in months) for each specialty for U.S. IMGs
no_visa_usce_dict = {'anesth': 4.4, 'intmed': 4.8, 'neuro': 4.7, 'patho': 6.3, 'psych': 5.0, 'fammed': 4.7, 'pediat': 5.4}

#####################################create an average gap dict##############################

# Read the CSV file containing the weights/coefficients into a pandas DataFrame
df = pd.read_csv('coefs.csv')

# Convert the DataFrame into a dictionary, where the keys are the specialties and the values are the coefficients
coefs = df.set_index('speciality').T.to_dict('list')


def send_email(to, subject, template, **kwargs):
    msg = Message(subject, sender='pawankhera@usmlesarthi.com', recipients=[to]) #sender=app.config.get("MAIL_DEFAULT_SENDER")
    msg.body = render_template(template + '.txt', **kwargs)
    msg.html = render_template(template + '.html', **kwargs)
    mail.send(msg)


def refine_recommendations(recommendations):
    # Convert the list of recommendations to a format suitable for the prompt
    rec_text = '\n'.join([rec[0] for rec in recommendations])
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Help me refine these recommendations by combining similar ones."},
        {"role": "user", "content": f"Please identify and combine similar recommendations from the following list:\n{rec_text}"}
    ]

    # Ask GPT to identify and combine similar recommendations
    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
    refined_recs_text = response.choices[0].message['content'].strip().split('\n')

    # Create a new list of recommendations with the refined ones
    old_recs = [rec[0] for rec in recommendations]
    refined_recommendations = []
    for refined_rec in refined_recs_text:
        if refined_rec not in old_recs:
            # This is a combined recommendation. Assign the highest priority of the combined recs to it
            priorities_used = [rec[1] for rec in recommendations if refined_rec in rec[0]]
            highest_priority = min(priorities_used) if priorities_used else 999  # 999 as a default if no match
            refined_recommendations.append((refined_rec, highest_priority))
        else:
            # This recommendation remains unchanged
            refined_recommendations.append((refined_rec, recommendations[old_recs.index(refined_rec)][1]))

    # Sort the recommendations based on priority and return
    refined_recommendations = sorted(refined_recommendations, key=lambda x: x[1])
    return refined_recommendations


def recommendations_func(data, probability, primary_speciality, usce_updated, visa_updated, gap):
    recommendations = []
    avg_score_step3 = 230
    priority = 0

    if primary_speciality == 'anesth':
        specialty_name = "Anesthesiology"
    elif primary_speciality == 'intmed':
        specialty_name = "Internal Medicine"
    elif primary_speciality == 'neuro':
        specialty_name = "Neurology"
    elif primary_speciality == 'patho':
        specialty_name = "Pathology"
    elif primary_speciality == 'psych':
        specialty_name = "Psychiatry"
    elif primary_speciality == 'fammed':
        specialty_name = "Family Medicine"
    elif primary_speciality == 'pedia':
        specialty_name = "Pediatrics"
    else:
        specialty_name = "Unknown"

    # Determine average scores and experiences based on visa requirement
    if data["visa_residency"].lower() == "yes":
        avg_score_step1 = visa_step1_dict[primary_speciality]
        avg_score_step2 = visa_step2_dict[primary_speciality]
        avg_research_exp = visa_research_exp_dict[primary_speciality]
        avg_research_pub = visa_research_pub_dict[primary_speciality]
        avg_usce = visa_usce_dict[primary_speciality]
    else:
        avg_score_step1 = no_visa_step1_dict[primary_speciality]
        avg_score_step2 = no_visa_step2_dict[primary_speciality]
        avg_research_exp = no_visa_research_exp_dict[primary_speciality]
        avg_research_pub = no_visa_research_pub_dict[primary_speciality]
        avg_usce = no_visa_usce_dict[primary_speciality]

    # Step 1: Calculate the difference for each parameter
    # For exams that are taken, we consider the difference. For exams not taken, the difference is set to zero to avoid recommendation.
    if data["step1_exam"].lower() == "yes":
        difference_step1 = (coefs[primary_speciality.lower()][1] * avg_score_step1) - (coefs[primary_speciality.lower()][1] * int(data["step1_num_score"]))
    else:
        difference_step1 = 0

    if data["step2_exam"].lower() == "yes":
        difference_step2 = (coefs[primary_speciality.lower()][2] * avg_score_step2) - (coefs[primary_speciality.lower()][2] * int(data["step2_score"]))
    else:
        difference_step2 = 0

    if data["step3_exam"].lower() == "yes":
        difference_step3 = (coefs[primary_speciality.lower()][3] * avg_score_step3) - (coefs[primary_speciality.lower()][3] * int(data["step3_score"]))
    else:
        difference_step3 = 0


    difference_visa = (coefs[primary_speciality.lower()][4] * 1) - (coefs[primary_speciality.lower()][4] * visa_updated)
    difference_gap = (coefs[primary_speciality.lower()][5] * 0) - (coefs[primary_speciality.lower()][5] * gap)
    difference_usce = (coefs[primary_speciality.lower()][6] * avg_usce) - (coefs[primary_speciality.lower()][6] * usce_updated)
    difference_research_pub = (coefs[primary_speciality.lower()][7] * avg_research_pub) - (coefs[primary_speciality.lower()][7] * int(data["research_publications"]))
    difference_research_exp = (coefs[primary_speciality.lower()][7] * avg_research_exp) - (coefs[primary_speciality.lower()][7] * (int(data["research_experience_months"]) / 6))

    if probability < 40:
        recommendations.append((f"Your chances for {specialty_name} are currently low with a probability of {probability} %. Consider re-evaluating your target specialties or working on strengthening your application.", priority))
        priority += 1
    elif 40 <= probability < 70:
        recommendations.append((f"Your chances for {specialty_name} are moderate with a probability of {probability} %. Keep refining your application and gaining relevant experiences.", priority))
        priority += 1
    else:
        recommendations.append((f"You have strong chances for {specialty_name} with a probability of {probability} %. Stay focused and continue networking.", priority))
        priority += 1

    # Recommendations based on whether USMLE exams are taken or not
    if data["step1_exam"].lower() == "no":
        recommendations.append((f"Secure a Pass grade in the USMLE Step 1 exam.",  priority))
        priority += 1
    elif difference_step1 > 0:
        recommendations.append(("Consider gaining more USCE experience or publishing more research publications to compensate for your Step 1 score.",  priority))
        priority += 1

    if data["step2_exam"].lower() == "no":
        recommendations.append((f"Pass the USMLE Step 2 exam. Aim for a score more than {avg_score_step2 + 10}.",  priority))
        priority += 1
    elif difference_step2 > 0:
        recommendations.append(("Consider gaining more USCE experience or publishing more research publications to compensate for your Step 2 score.",  priority))
        priority += 1

    if data["step3_exam"].lower() == "no":
        recommendations.append((f"Pass  the USMLE Step 3 exam. Aim for a score more than {avg_score_step3 + 10}.",  priority))
        priority += 1
    elif difference_step3 > 0:
        recommendations.append(("Consider gaining more USCE experience or publishing more research publications to compensate for your Step 3 score.",  priority))
        priority += 1

    # Step 2: Filter out the negative differences
    differences = {
        "visa": difference_visa,
        "gap": difference_gap,
        "usce": difference_usce,
        "research_pub": difference_research_pub,
        "research_exp": difference_research_exp
    }

    positive_differences = {k: v for k, v in differences.items() if v > 0}

    # Step 3: Rank the positive differences
    ranked_differences = sorted(positive_differences.items(), key=lambda x: x[1], reverse=True)

    # Prioritize and add the recommendations based on the ranked differences
    priority = 7  # Starting from 7 as the previous recommendations have priorities from 1-6

    for diff in ranked_differences:
        if diff[0] == "visa":
            recommendations.append(("Consider gaining more USCE experience or publishing more research publications to compensate for your visa requirement.", priority))
            priority += 1
        elif diff[0] == "gap":
            recommendations.append(("Consider gaining more USCE experience or publishing more research publications to compensate for the gap in your clinical experiences.", priority))
            priority += 1
        elif diff[0] == "usce":
            recommendations.append((f"Gain more clinical experience, especially in {specialty_name} rotations.", priority))
            priority += 1
        elif diff[0] == "research_pub":
            recommendations.append((f"Consider increasing your research publications related to {specialty_name}.", priority))
            priority += 1
        elif diff[0] == "research_exp":
            recommendations.append((f"Consider increasing your research experience related to {specialty_name}.", priority))
            priority += 1

    # Sort the recommendations based on priority
    recommendations = sorted(recommendations, key=lambda x: x[1])

    # Check if the user wants to refine the recommendations
    if use_refine_recommendations.lower() == 'yes':
        try:
            recommendations = refine_recommendations(recommendations)
        except Exception as e:
            # You might want to log the error or handle it in some other way
            print(f"Error refining recommendations: {e}")

    return recommendations


ENV = 'prod'

if ENV == "dev":
    app.debug = True
    app.config["SQLALCHEMY_DATABASE_URI"] = 'postgresql://postgres:ashutosh49@localhost:5432/msresponsesdata'
else:
    app.debug = False
    app.config["SQLALCHEMY_DATABASE_URI"] = 'postgresql://kilsjeyhlbejib:5de43237c25510dc62597c35e4b942cdac524ca0140366f40ba1d279dcbb8f8e@ec2-52-6-117-96.compute-1.amazonaws.com:5432/d1madvfr5nb67o'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Admin credentials for simplicity (consider using a more secure method in a production environment)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "submax"

class User(UserMixin):
    pass

@login_manager.user_loader
def user_loader(username):
    if username != ADMIN_USERNAME:
        return
    user = User()
    user.id = username
    return user

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    username = request.form['username']
    password = request.form['password']

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        user = User()
        user.id = username
        login_user(user)
        return redirect(url_for('download_page'))

    flash('Invalid username or password')
    return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return render_template('logout.html')

@app.route('/download-page', methods=['GET'])
@login_required
def download_page():
    return render_template('download.html')

@app.route('/download-database')
@login_required
def download_database():
    data = Responses.query.all()
    response_output = io.StringIO()
    writer = csv.writer(response_output)

    # Write header
    header = [column.name for column in Responses.__table__.columns]
    writer.writerow(header)

    # Write data rows
    for row in data:
        writer.writerow([getattr(row, column.name) for column in Responses.__table__.columns])

    output = Response(
        response=response_output.getvalue(),
        mimetype="text/csv",
        content_type="application/octet-stream",
    )
    output.headers["Content-Disposition"] = "attachment;filename=responses_data.csv"
    return output


class Responses(db.Model):
    __tablename__ = 'responses'
    id = db.Column(db.Integer, primary_key=True)
    firstname = db.Column(db.String(200))
    lastname = db.Column(db.String(200))
    email = db.Column(db.String(200))
    year_of_application = db.Column(db.Integer)
    step1_exam = db.Column(db.String(50))
    step1_type = db.Column(db.String(50))
    step1_letter_grade = db.Column(db.String(50))
    step1_num_score = db.Column(db.Integer)
    step1_failures = db.Column(db.Integer)
    step2_exam = db.Column(db.String(50))
    step2_score = db.Column(db.Integer)
    step2_failures = db.Column(db.Integer)
    step3_exam = db.Column(db.String(50))
    step3_score = db.Column(db.Integer)
    step3_failures = db.Column(db.Integer)
    visa_residency = db.Column(db.String(50))
    graduation_year = db.Column(db.Integer)
    primary_speciality = db.Column(db.String(200))
    clinical_experience_months = db.Column(db.Integer)
    research_publications = db.Column(db.Integer)
    research_experience_months = db.Column(db.Integer)
    prior_residency = db.Column(db.String(50))
    prior_residency_match = db.Column(db.String(50))
    probability = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, firstname, lastname, email, year_of_application, step1_exam, step1_type, step1_letter_grade, step1_num_score, step1_failures, step2_exam, step2_score, step2_failures, step3_exam, step3_score, step3_failures, visa_residency, graduation_year, primary_speciality, clinical_experience_months, research_publications, research_experience_months, prior_residency, prior_residency_match, probability):
        self.firstname = firstname
        self.lastname = lastname
        self.email = email
        self.year_of_application = year_of_application
        self.step1_exam = step1_exam
        self.step1_type = step1_type
        self.step1_letter_grade = step1_letter_grade
        self.step1_num_score = step1_num_score
        self.step1_failures = step1_failures
        self.step2_exam = step2_exam
        self.step2_score = step2_score
        self.step2_failures = step2_failures
        self.step3_exam = step3_exam
        self.step3_score = step3_score
        self.step3_failures = step3_failures
        self.visa_residency = visa_residency
        self.graduation_year = graduation_year
        self.primary_speciality = primary_speciality
        self.clinical_experience_months = clinical_experience_months
        self.research_publications = research_publications
        self.research_experience_months = research_experience_months
        self.prior_residency = prior_residency
        self.prior_residency_match = prior_residency_match
        self.probability = probability


@app.route('/', methods=['GET'])
def index():
    return render_template('form.html')


@app.route('/submit', methods=['POST'])
def submit():
    probability = None

    if request.method == 'POST':

        # Reset the variables to null strings
        firstname = ''
        lastname = ''
        email = ''
        step1_exam = ''
        step1_type = ''
        step1_letter_grade = ''
        step2_exam = ''
        step3_exam = ''
        visa_residency = ''
        primary_speciality = ''
        prior_residency = ''
        prior_residency_match = ''

        # Reset the variables to null integers
        year_of_application = None
        step1_num_score = None
        step1_failures = None
        step2_score = None
        step2_failures = None
        step3_score = None
        step3_failures = None
        graduation_year = None
        clinical_experience_months = None
        research_publications = None
        research_experience_months = None

        # Obtaining the user's data from the HTML file
        firstname = request.form.get('fname')
        lastname = request.form.get('lname')
        email = request.form.get('email')
        year_of_application = int(request.form.get('year_of_application'))
        step1_exam = request.form.get('step1_exam')
        step1_type = request.form.get('step1_type')
        step1_letter_grade = request.form.get('step1_letter_grade')
        step1_num_score = int(request.form.get('step1_num_score'))
        step1_failures = int(request.form.get('step1_failures'))
        step2_exam = request.form.get('step2_exam')
        step2_score = int(request.form.get('step2_score'))
        step2_failures = int(request.form.get('step2_failures'))
        step3_exam = request.form.get('step3_exam')
        step3_score = int(request.form.get('step3_score'))
        step3_failures = int(request.form.get('step3_failures'))
        visa_residency = request.form.get('visa_residency')
        graduation_year = int(request.form.get('graduation_year'))
        primary_speciality = request.form.get('primary_speciality')
        clinical_experience_months = int(
            request.form.get('clinical_experience_months'))
        research_publications = int(
            request.form.get('research_publications', 0))
        research_experience_months = int(
            request.form.get('research_experience_months'))
        prior_residency = request.form.get('prior_residency')
        prior_residency_match = request.form.get('prior_residency_match')

        # Get all the form fields
        form_fields = [
            'fname', 'lname', 'email', 'primary_speciality',
            'year_of_application', 'graduation_year', 'step1_exam', 'step1_type',
            'step1_letter_grade', 'step1_num_score', 'step1_failures', 'step2_exam',
            'step2_score', 'step2_failures', 'step3_exam', 'step3_score',
            'step3_failures', 'visa_residency', 'clinical_experience_months',
            'research_publications', 'research_experience_months', 'prior_residency',
            'prior_residency_match'
        ]

        # Check that none of the fields are empty or just whitespace
        for field in form_fields:
            value = request.form.get(field, '').strip()
            if value == '':
                return render_template('form.html', message='Please enter all the fields and then click submit')

        # Initialize variables
        step1_score_updated = 0
        step2_score_updated = 0
        step3_score_updated = 0
        visa_updated = 0
        usce_updated = 0
        gap = 0
        research = 0

        # Calculate score updates

        # for step 1
        # Step 1 score is not available
        if step1_exam.lower() == "no":
            # Visa is required
            if visa_residency.lower() == "yes":
                # assigning average score for step 1 if the IMG hasn't appeared for step 1
                step1_num_score = visa_step1_dict.get(
                    primary_speciality.lower(), 0)
            # Visa is not required
            else:
                # assigning average score for step 1 if the IMG hasn't appeared for step 1
                step1_num_score = no_visa_step1_dict.get(
                    primary_speciality.lower(), 0)
        else:
            # if the IMG has a letter grade, Pass or Fail
            if step1_type.lower() == "letter":
                # Visa is required
                if visa_residency.lower() == "yes":
                    # assigning average score for step 1 if the IMG hasn't appeared for step 1
                    step1_num_score = visa_step1_dict.get(
                        primary_speciality.lower(), 0)
                # Visa is not required
                else:
                    # assigning average score for step 1 if the IMG hasn't appeared for step 1
                    step1_num_score = no_visa_step1_dict.get(
                        primary_speciality.lower(), 0)

        # subtracting 15 for each failure in step 1
        step1_score_updated = max(0, step1_num_score - (step1_failures * 15))

        # for step 2
        # Step 2 score is not available
        if step2_exam.lower() == "no":
            # Visa is required
            if visa_residency.lower() == "yes":
                # assigning average score for step 2 if the IMG hasn't appeared for step 2
                step2_score = visa_step2_dict.get(
                    primary_speciality.lower(), 0)
            # Visa is not required
            else:
                # assigning average score for step 2 if the IMG hasn't appeared for step 2
                step2_score = no_visa_step2_dict.get(
                    primary_speciality.lower(), 0)

        # subtracting 15 for each failure in step 2
        step2_score_updated = max(0, step2_score - (step2_failures * 15))

        # for step 3
        # subtracting 15 for each failure in step 3
        step3_score_updated = max(0, step3_score - (step3_failures * 10))

        # for visa requirement
        # if visa is required for the IMG, then this is set to 1.
        visa_updated = 1 if visa_residency.lower() == "yes" else 0

        # number of gap years
        gap = year_of_application - graduation_year

        # for Clinical experience
        # adding 18 to the score if IMG has prior residency
        usce_updated = clinical_experience_months + \
            18 if prior_residency.lower() == "yes" else clinical_experience_months
        # subtracting 12 if the prior residency doesn't match the primary specialty
        usce_updated = usce_updated - \
            12 if prior_residency_match.lower() == "no" else usce_updated

        # research papers/research experience
        # Here it is assumed that 6 months of research experience is equivalent to 1 reasearch paper.
        research = research_publications + round(research_experience_months / 6)

        # Calculating logodds
        log_odds = coefs[primary_speciality.lower()][0] + (coefs[primary_speciality.lower()][1]*step1_score_updated) + (coefs[primary_speciality.lower()][2]*step2_score_updated) + (coefs[primary_speciality.lower()][3]*step3_score_updated) + \
            (coefs[primary_speciality.lower()][4]*visa_updated) + (coefs[primary_speciality.lower()][5]*gap) + \
            (coefs[primary_speciality.lower()][6]*usce_updated) + \
            (coefs[primary_speciality.lower()][7]*research)

        probability = round((math.exp(log_odds) / (1 + math.exp(log_odds))) * 100, 2)


        session['form_data'] = request.form
        session['probability'] = probability

        # Creating the Responses object
        response = Responses(
            firstname, lastname, email, year_of_application,
            step1_exam, step1_type, step1_letter_grade, step1_num_score,
            step1_failures, step2_exam, step2_score, step2_failures,
            step3_exam, step3_score, step3_failures, visa_residency,
            graduation_year, primary_speciality, clinical_experience_months,
            research_publications, research_experience_months, prior_residency,
            prior_residency_match, probability
        )

        # Adding to database
        try:
            db.session.add(response)
            db.session.commit()
            send_email(email, 'Submission Confirmation', 'email', firstname=firstname, lastname=lastname, email=email, primary_speciality=primary_speciality, probability=probability)
            message = "Data stored successfully on the data base!"
        except Exception as e:
            db.session.rollback()
            print("Error encountered:", str(e))  # This will print the error to your console
            message = "Data was not stored successfully on the data base!"


    return render_template('submit.html', firstname=firstname, lastname=lastname, email=email, primary_speciality=primary_speciality, year_of_application=year_of_application, graduation_year=graduation_year, step1_exam=step1_exam, step1_type=step1_type, step1_letter_grade=step1_letter_grade, step1_num_score=step1_num_score, step1_failures=step1_failures, step2_exam=step2_exam, step2_score=step2_score, step2_failures=step2_failures, step3_exam=step3_exam, step3_score=step3_score, step3_failures=step3_failures, visa_residency=visa_residency, clinical_experience_months=clinical_experience_months, research_publications=research_publications, research_experience_months=research_experience_months, prior_residency=prior_residency, prior_residency_match=prior_residency_match, probability=probability, message=message)

@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    data = session.get('form_data')
    probability = session.get('probability')

    # for Clinical experience
    # adding 18 to the score if IMG has prior residency
    usce_updated = int(data["clinical_experience_months"]) + \
        18 if data["prior_residency"].lower() == "yes" else int(data["clinical_experience_months"])
    # subtracting 12 if the prior residency doesn't match the primary specialty
    usce_updated = usce_updated - \
        12 if data["prior_residency_match"].lower() == "no" else usce_updated

    # for visa requirement
    # if visa is required for the IMG, then this is set to 1.
    visa_updated = 1 if data["visa_residency"].lower() == "yes" else 0

    # number of gap years
    gap = int(data["year_of_application"]) - int(data["graduation_year"])

    # Calling the recommendation function
    recommendations = recommendations_func(data, probability, data['primary_speciality'].lower(), usce_updated, visa_updated, gap)

    return render_template('recommendations.html', recommendations=recommendations)

if __name__ == '__main__':
    app.run(debug=True)
