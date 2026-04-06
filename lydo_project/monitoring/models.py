from django.conf import settings
from django.db import models

class Barangay(models.Model):
    name = models.CharField(max_length=100)
    
    def __str__(self):
        return self.name


class UserBarangayAssignment(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='barangay_assignment')
    barangay = models.ForeignKey(Barangay, on_delete=models.CASCADE, related_name='assigned_users')

    def __str__(self):
        return f"{self.user.username} - {self.barangay.name}"


class UserAccessLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='access_logs')
    barangay = models.ForeignKey(Barangay, null=True, blank=True, on_delete=models.SET_NULL, related_name='access_logs')
    session_key = models.CharField(max_length=80, blank=True, db_index=True)
    login_time = models.DateTimeField(auto_now_add=True)
    logout_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-login_time']

    def __str__(self):
        return f"{self.user.username} @ {self.login_time:%Y-%m-%d %H:%M:%S}"


class Youth(models.Model):
    # --- DEMOGRAPHICS ---
    name = models.CharField(max_length=200, help_text="Full Name")
    birthdate = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female')])
    civil_status = models.CharField(max_length=20, choices=[
        ('Single', 'Single'), ('Married', 'Married'), ('Widowed', 'Widowed'), 
        ('Separated', 'Separated'), ('Live-in', 'Live-in')
    ])
    religion = models.CharField(max_length=100, blank=True)
    
    # --- ADDRESS ---
    purok = models.CharField(max_length=100, blank=True)
    barangay = models.ForeignKey(Barangay, on_delete=models.CASCADE)
    municipality = models.CharField(max_length=100, default="Manolo Fortich")
    province = models.CharField(max_length=100, default="Bukidnon")
    region = models.CharField(max_length=50, default="X")
    
    # --- CONTACT ---
    email = models.EmailField(blank=True)
    contact_number = models.CharField(max_length=20, blank=True)
    
    # --- YOUTH CLASSIFICATION ---
    is_in_school = models.BooleanField(default=False, verbose_name="In School")
    is_osy = models.BooleanField(default=False, verbose_name="Out of School Youth")
    is_working_youth = models.BooleanField(default=False, verbose_name="Working Youth")
    is_unemployed = models.BooleanField(default=False, verbose_name="Unemployed Youth")
    is_pwd = models.BooleanField(default=False, verbose_name="Person with Disability")
    
    # OSY Specifics
    osy_willing_to_enroll = models.BooleanField(default=False, verbose_name="Willing to enroll?")
    osy_program_type = models.CharField(max_length=50, blank=True, choices=[
        ('Educational', 'Educational'), ('Vocational', 'Vocational')
    ])
    osy_reason_no_enroll = models.CharField(max_length=200, blank=True)
    
    # PWD Specifics
    disability_type = models.CharField(max_length=100, blank=True)
    
    # Specific Needs
    has_specific_needs = models.BooleanField(default=False)
    specific_needs_condition = models.CharField(max_length=100, blank=True, choices=[
        ('SLD', 'Specific Learning Disability'), ('OHI', 'Other Hearing Impairment'),
        ('ASD', 'Autism Spectrum Disorder'), ('ED', 'Emotional Disturbance'),
        ('SLI', 'Speech Language Impairment'), ('VI', 'Visual Impairment'),
        ('Deafness', 'Deafness'), ('HI', 'Hearing Impairment'),
        ('DB', 'Deaf-Blind'), ('OI', 'Orthopedic Impairment'),
        ('ID', 'Intellectual Disability'), ('TBI', 'Traumatic Brain Injury'),
        ('MI', 'Multiple Intelligence')
    ])
    
    # --- CULTURAL GROUP ---
    is_ip = models.BooleanField(default=False, verbose_name="Indigenous People (7 Tribes)")
    tribe_name = models.CharField(max_length=50, blank=True, choices=[
        ('Higaonon', 'Higaonon'), ('Tala-andig', 'Tala-andig'), ('Bukidnon', 'Bukidnon'),
        ('Umayamnon', 'Umayamnon'), ('Manobo', 'Manobo'), ('Matigsalug', 'Matigsalug'),
        ('Tigwahanon', 'Tigwahanon')
    ])
    
    is_muslim = models.BooleanField(default=False)
    muslim_group = models.CharField(max_length=50, blank=True, choices=[
        ('Tausug', 'Tausug'), ('Maranao', 'Maranao'), ('Maguindanao', 'Maguindanao'),
        ('Yakan', 'Yakan'), ('Sama-bajau', 'Sama-bajau')
    ])
    
    # --- EDUCATION ---
    education_level = models.CharField(max_length=50, choices=[
        ('Elementary', 'Elementary'), ('High School', 'High School'), 
        ('Senior High', 'Senior High'), ('Open High', 'Open High'), 
        ('ALS', 'Alternative Learning System'), ('College', 'College'),
        ('Masters', 'Masters'), ('Doctorate', 'Doctorate')
    ])
    course = models.CharField(max_length=150, blank=True, help_text="Course/Degree")
    school_name = models.CharField(max_length=150, blank=True, help_text="School/University")
    
    is_scholar = models.BooleanField(default=False)
    scholarship_program = models.CharField(max_length=100, blank=True)
    
    # --- WORK & CIVIC ---
    work_status = models.CharField(max_length=50, blank=True)
    
    registered_voter_sk = models.BooleanField(default=False, verbose_name="Registered SK Voter")
    registered_voter_national = models.BooleanField(default=False, verbose_name="Registered National Voter")
    voted_last_sk = models.BooleanField(default=False, verbose_name="Voted Last SK Election")
    
    attended_kk_assembly = models.BooleanField(default=False)
    kk_assembly_times = models.IntegerField(default=0, help_text="How many times?")
    kk_assembly_no_reason = models.CharField(max_length=100, blank=True, choices=[
        ('No KK assembly', 'No KK assembly'), ('No interest', 'No interest')
    ])
    
    # --- OTHER ---
    is_4ps = models.BooleanField(default=False, verbose_name="4Ps Beneficiary")
    number_of_children = models.IntegerField(default=0)

    def __str__(self):
        return self.name

    @property
    def age(self):
        import datetime
        if self.birthdate:
            today = datetime.date.today()
            return today.year - self.birthdate.year - ((today.month, today.day) < (self.birthdate.month, self.birthdate.day))
        return 0
