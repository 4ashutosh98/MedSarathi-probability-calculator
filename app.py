import math
import csv
import pandas as pd
from flask import Flask, render_template, request
from sqlalchemy import create_engine

app = Flask(__name__)

# Set up the database connection
DATABASE_URL = 'postgresql-convex-24895'  # Replace this with actual URL
engine = create_engine(DATABASE_URL)

# Create the table if it does not exist
conn = engine.connect()
query = '''
CREATE TABLE IF NOT EXISTS responses_data (
    firstname VARCHAR(100),
    lastname VARCHAR(100),
    email VARCHAR(100),
    year_of_application INTEGER,
    step1_exam VARCHAR(10),
    step1_type VARCHAR(10),
    step1_letter_grade VARCHAR(10),
    step1_num_score INTEGER,
    step1_failures INTEGER,
    step2_exam VARCHAR(10),
    step2_score INTEGER,
    step2_failures INTEGER,
    step3_exam VARCHAR(10),
    step3_score INTEGER,
    step3_failures INTEGER,
    visa_residency VARCHAR(10),
    graduation_year INTEGER,
    primary_speciality VARCHAR(50),
    clinical_experience_months INTEGER,
    research_publications INTEGER,
    research_experience_months INTEGER,
    prior_residency VARCHAR(10),
    prior_residency_match VARCHAR(10),
    probability FLOAT
);
'''
conn.execute(query)
conn.close()


@app.route('/', methods=['GET', 'POST'])
def index():
    probability = None

    if request.method == 'POST':
        """coefs = {
            # 'some other speciality': [-XX.XX, X.XX, X.XX, -X.XX, -X.XX, X.XX, X.XX, X.XX]  # substitute with actual coefficients
            # 'speci': [constant, step 1, step 2, step 3,  visa,   gap, usce, research]  # these are the columns and below are the weights/coefficients for each specialty.
            'anesth': [-45.10,     0.27,   0.13,   0.00, -0.41, -0.19, 0.25,     0.08],
            'intmed': [-57.91,     0.24,   0.20,   0.14, -0.48, -0.09, 0.41,     0.13],
            'neuro': [-48.43,     0.24,   0.20,   0.14, -0.47, -0.09, 0.39,     0.14],
            'patho': [-35.36,     0.17,   0.19,   0.12, -0.48, -0.08, 0.44,     0.13],
            'psych': [-35.36,     0.17,   0.19,   0.12, -0.48, -0.08, 0.44,     0.13],
            'fammed': [-47.82,     0.22,   0.17,   0.13, -0.44, -0.11, 0.45,     0.12],
            'pediat': [-48.34,     0.23,   0.17,   0.13, -0.45, -0.10, 0.43,     0.13]
        }"""

        # Read the CSV file containing the weights/coefficients into a pandas DataFrame
        df = pd.read_csv('coefs.csv')

        # Convert the DataFrame into a dictionary, where the keys are the specialties and the values are the coefficients
        coefs = df.set_index('speciality').T.to_dict('list')

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

        # Initialize variables
        step1_score_updated = 0
        step2_score_updated = 0
        step3_score_updated = 0
        visa_updated = 0
        usce_updated = 0
        gap = 0
        research_publications = 0
        papers = 0

        # Calculate score updates

        # Dictionary containing average average step 1 score for each specialty for Non-U.S. IMGs
        visa_step1_dict = {'anesth': 234, 'intmed': 238, 'neuro': 239,
                           'patho': 232, 'psych': 229, 'fammed': 219, 'pediat': 229}

        # Dictionary containing average average step 1 score for each specialty for Non-U.S. IMGs
        no_visa_step1_dict = {'anesth': 233, 'intmed': 225, 'neuro': 225,
                              'patho': 238, 'psych': 216, 'fammed': 211, 'pediat': 220}

        # Dictionary containing average average step 2 score for each specialty for U.S. IMGs
        visa_step2_dict = {'anesth': 240, 'intmed': 245, 'neuro': 245,
                           'patho': 219, 'psych': 236, 'fammed': 231, 'pediat': 240}

        # Dictionary containing average average step 3 score for each specialty for U.S. IMGs
        no_visa_step2_dict = {'anesth': 243, 'intmed': 235, 'neuro': 235,
                              'patho': 228, 'psych': 228, 'fammed': 225, 'pediat': 233}

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
        papers = research_publications + round(research_experience_months / 6)

        # Calculating logodds
        log_odds = coefs[primary_speciality.lower()][0] + (coefs[primary_speciality.lower()][1]*step1_score_updated) + (coefs[primary_speciality.lower()][2]*step2_score_updated) + (coefs[primary_speciality.lower()][3]*step3_score_updated) + \
            (coefs[primary_speciality.lower()][4]*visa_updated) + (coefs[primary_speciality.lower()][5]*gap) + \
            (coefs[primary_speciality.lower()][6]*usce_updated) + \
            (coefs[primary_speciality.lower()][7]*papers)

        probability = math.exp(log_odds) / (1 + math.exp(log_odds))
        # probability = 1 / (1 + math.exp(-log_odds))

        # Gather the user input data to save in the csv file
        data_to_save = [firstname, lastname, email, year_of_application, step1_exam, step1_type,
                        step1_letter_grade, step1_num_score, step1_failures, step2_exam, step2_score,
                        step2_failures, step3_exam, step3_score, step3_failures, visa_residency,
                        graduation_year, primary_speciality, clinical_experience_months,
                        research_publications, research_experience_months, prior_residency,
                        prior_residency_match, float('{:.2f}'.format(probability))]

        """# Save the data in the CSV file
        with open('responses_data.csv', 'a', newline='\n') as file:
            writer = csv.writer(file)
            writer.writerow(data_to_save)"""

        # Create a connection to the database
        conn = engine.connect()

        # Create a SQL query to insert the data
        query = '''
        INSERT INTO responses_data (firstname, lastname, email, year_of_application, step1_exam,
                                    step1_type, step1_letter_grade, step1_num_score, step1_failures,
                                    step2_exam, step2_score, step2_failures, step3_exam, step3_score,
                                    step3_failures, visa_residency, graduation_year, primary_speciality,
                                    clinical_experience_months, research_publications, research_experience_months,
                                    prior_residency, prior_residency_match, probability)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        '''
        conn.execute(query, data_to_save)
        conn.close()

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

    return render_template('form.html', probability=probability)


if __name__ == '__main__':
    app.run(debug=True)
