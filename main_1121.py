"""
main_app.py - ChakoraHub Mobile App Entry Point
Run this file to start the application
"""

import os
import re
import json
import smtplib
import requests
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText

from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.image import Image, AsyncImage
from kivy.uix.button import Button
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.animation import Animation
from kivy.metrics import dp
from kivy.properties import (
    ObjectProperty, StringProperty, ListProperty, 
    NumericProperty, DictProperty, BooleanProperty
)

from snowflake.connector import errors, DictCursor
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

import snowflake.connector
import platform

# ==================== CONFIGURATION ====================
Window.size = (400, 700)
Window.clearcolor = (1, 1, 1, 1)

# Lambda API endpoints
LAMBDA_BASE_URL = "https://2bkklp3gbf.execute-api.eu-north-1.amazonaws.com/Prod"
API_HEADERS = { 'Content-Type': 'application/json' }
payload = {
    "action": "load_home_data",
    "user_id": "12345"
}

# ==================== DATABASE UTILS ====================
def get_db_connection():
    """Get Snowflake database connection using private key"""
    try:
        # Load private key from environment or file
        private_key_content = os.environ.get('PRIVATE_KEY_CONTENT')
        private_key_passphrase = os.environ.get('PRIVATE_KEY_PASSPHRASE')
        
        if not private_key_content:
            # Try to load from file
            try:
                with open('private_key.pem', 'r') as f:
                    private_key_content = f.read()
            except FileNotFoundError:
                print("Private key file not found")
                return None
        
        # Process private key
        p_key = serialization.load_pem_private_key(
            private_key_content.encode(),
            password=private_key_passphrase.encode() if private_key_passphrase else None,
            backend=default_backend()
        )
        
        pkb = p_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Create connection
        conn = snowflake.connector.connect(
            user=os.environ.get('SNOWFLAKE_USER', 'CHAKORA_HUB_USER'),
            account=os.environ.get('SNOWFLAKE_ACCOUNT', 'your-account'),
            private_key=pkb,
            warehouse=os.environ.get('SNOWFLAKE_WAREHOUSE', 'CHAKORA_WH'),
            database=os.environ.get('SNOWFLAKE_DATABASE', 'CHAKORA_HUB'),
            schema=os.environ.get('SNOWFLAKE_SCHEMA', 'NRM'),
            role=os.environ.get('SNOWFLAKE_ROLE', 'CHAKORA_ROLE')
        )
        
        return conn
        
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def call_lambda_api(endpoint, data=None, method='GET'):
    """Call Lambda API endpoint"""
    try:
        url = f"{LAMBDA_BASE_URL}/{endpoint}"
        
        if method.upper() == 'GET':
            response = requests.get(url, headers=API_HEADERS, params=data)
        elif method.upper() == 'POST':
            response = requests.post(url,headers=API_HEADERS,json=data,timeout=15)
            print(response.status_code, response.text)
        elif method.upper() == 'PUT':
            response = requests.put(url, headers=API_HEADERS, json=data)
        else:
            return None
            
        if response.status_code == 200:
            return response.json()
        else:
            print(f"API call failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Lambda API call error: {e}")
        return None

# ==================== CUSTOM WIDGETS ====================
class SafeImage(Image):
    """Custom AsyncImage widget that supports remote (S3) images safely."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.allow_stretch = True
        self.keep_ratio = True
        if not self.source:
            self.source = "https://chakorahub-student.s3.amazonaws.com/snaps/logo.png"

class SafeAsyncImage(AsyncImage):
    pass

class ImageButton(ButtonBehavior, Image):
    """Clickable image button"""
    scale = NumericProperty(1)

class HoverButton(Button):
    """Button with hover effect"""
    default_color = ListProperty([0.93, 0.95, 1, 1])
    hover_color = ListProperty([0.85, 0.9, 1, 1])
    scale = NumericProperty(1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = self.default_color
        Window.bind(mouse_pos=self.on_mouse_pos)

    def on_mouse_pos(self, window, pos):
        if not self.get_root_window():
            return
        inside = self.collide_point(*self.to_widget(*pos))
        if inside:
            self.background_color = self.hover_color
            Animation(scale=1.05, d=0.12).start(self)
        else:
            self.background_color = self.default_color
            Animation(scale=1, d=0.12).start(self)

    def on_size(self, *args):
        self.text_size = self.size

class DropdownHoverButton(HoverButton):
    """Dropdown menu button with hover effect"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(48)
        self.color = (0.29, 0.08, 0.55, 1)

class BatchBox(BoxLayout):
    """Batch box widget for displaying batches"""
    heading = StringProperty("")

class ServiceItem(BoxLayout):
    """Service item widget for main screen"""
    title = StringProperty("")
    desc = StringProperty("")
    icon = StringProperty("")

class LoginBox(BoxLayout):
    """Login box widget"""
    pass

class MainScreen(Screen):
    current_batches = ListProperty([])
    upcoming_batches = ListProperty([])
    feedback = ListProperty([])

    def on_enter(self):
        self.load_home_data()

    def load_home_data(self):
        try:
            response = call_lambda_api("home", method="POST", data={"action": "fetch_batches"})
            if response:
                self.current_batches = response.get("current_batches", [])
                self.upcoming_batches = response.get("upcoming_batches", [])
                self.feedback = response.get("feedback", [])
                self.update_ui()
        except Exception as e:
            print("Home API error:", e)

    def update_ui(self):
        # Fill current batch list
        self.ids.current_batches.ids.rv.data = [
            {"text": f"• {item}"} for item in self.current_batches
        ]

        # Fill upcoming batch list
        self.ids.upcoming_batches.ids.rv.data = [
            {"text": f"• {item}"} for item in self.upcoming_batches
        ]

        # Fill feedback section
        self.ids.feedback_rv.data = [
            {"msg": fb["message"], "name": fb["name"]} for fb in self.feedback
        ]

class CourseCard(BoxLayout):
    """Course card widget with submenu"""
    course_name = StringProperty("")
    image_source = StringProperty("")
    submenu_id = StringProperty("")
    img_scale = NumericProperty(1)
    offers = DictProperty({})
    discount_label = StringProperty("")
    langmenu_open = BooleanProperty(False)
    submenu_open = BooleanProperty(False)

    def on_course_name(self, instance, value):
        self.update_discount_label()

    def on_offers(self, instance, value):
        self.update_discount_label()

    def update_discount_label(self):
        offer = self.offers.get(self.course_name, {})
        discount = offer.get("discount_percentage", 0)
        self.discount_label = f"{discount}% OFF" if discount > 0 else ""

    def toggle_submenu(self, force_close=False):
        sub = self.ids.get('sub_menu')
        if not sub:
            return
        if force_close or sub.height > 0:
            Animation(height=0, d=0.18).start(sub)
            sub.opacity = 0
            sub.disabled = True
            self.submenu_open = False
        else:
            if self.parent:
                for sibling in self.parent.children:
                    if isinstance(sibling, CourseCard) and sibling.submenu_open:
                        sibling.toggle_submenu(force_close=True)
            Animation(height=dp(70), d=0.18).start(sub)
            sub.opacity = 1
            sub.disabled = False
            self.submenu_open = True

    def toggle_lang_menu(self, button=None, force_close=False):
        sub_lang = self.ids.get('sub_lang')
        if not sub_lang:
            return
        if force_close or sub_lang.height > 0:
            Animation(height=0, d=0.18).start(sub_lang)
            sub_lang.opacity = 0
            sub_lang.disabled = True
            self.langmenu_open = False
        else:
            if self.parent:
                for sibling in self.parent.children:
                    if isinstance(sibling, CourseCard) and sibling.langmenu_open:
                        sibling.toggle_lang_menu(force_close=True)
            Animation(height=dp(50), d=0.18).start(sub_lang)
            sub_lang.opacity = 1
            sub_lang.disabled = False
            self.langmenu_open = True

class FileChooserPopup(Popup):
    """File selection popup"""
    file_type = StringProperty()
    
    def __init__(self, file_type, callback, **kwargs):
        super().__init__(**kwargs)
        self.file_type = file_type
        self.callback = callback
        self.title = f"Select {file_type.upper()} File"
        self.size_hint = (0.9, 0.9)
        
        layout = BoxLayout(orientation='vertical')
        
        home_path = str(Path.home())
        documents_path = os.path.join(home_path, 'Documents')
        start_path = documents_path if os.path.exists(documents_path) else home_path
        
        self.filechooser = FileChooserListView(
            path=start_path,
            filters=[
                '*.pdf', '*.ppt', '*.pptx', '*.doc', '*.docx', 
                '*.txt', '*.py', '*.java', '*.html', '*.css', 
                '*.js', '*.zip', '*.rar'
            ]
        )
        layout.add_widget(self.filechooser)
        
        btn_layout = BoxLayout(size_hint_y=None, height=50)
        select_btn = Button(text='Select')
        cancel_btn = Button(text='Cancel')
        
        select_btn.bind(on_release=self.select_file)
        cancel_btn.bind(on_release=self.dismiss)
        
        btn_layout.add_widget(select_btn)
        btn_layout.add_widget(cancel_btn)
        layout.add_widget(btn_layout)
        
        self.content = layout
    
    def select_file(self, instance):
        if self.filechooser.selection:
            selected_file = self.filechooser.selection[0]
            self.callback(selected_file)
            self.dismiss()

# ==================== SCREEN CLASSES ====================
class AboutUsScreen(Screen):
    about_text = StringProperty("Loading...")

    def go_home(self):
        self.manager.current = "main"

class AdminRegisterForm(Screen):
    message = StringProperty("")

class ContactUsScreen(Screen):
    def go_home(self):
        self.manager.current = "main"

    def open_email(self):
        import webbrowser
        webbrowser.open("mailto:support@chakorahub.com")

class EnquiryScreen(Screen):
    profile_pic = StringProperty("images/default_profile.png")

class RegisterScreen(Screen):
    pass

class BloggerRoot(Screen):
    pass

class CalendarScreen(Screen):
    profile_pic = StringProperty("images/default_profile.png")

class DemoVideosScreen(Screen):
    profile_pic = StringProperty("images/default_profile.png")

class FeedbackScreen(Screen):
    profile_pic = StringProperty("images/default_profile.png")

class OffersScreen(Screen):
    rv_data = ListProperty([])

class ProfileScreen(Screen):
    address = StringProperty("")

class ResourcesScreen(Screen):
    def image_path(self, filename):
        return f"images/{filename}"

class SettingsScreen(Screen):
    username = StringProperty("")

class StudentReportScreen(Screen):
    profile_pic = StringProperty("images/default_profile.png")

class AdminPortalScreen(Screen):
    uploaded_files = ListProperty([]) 
    categories = DictProperty({       
        "practice_test": [],
        "assignments": [],
        "documents": []
    })

class HomeScreen(Screen):
    pass

class BillingScreen(Screen):
    course_fee = StringProperty("0")   # or "₹0" if you prefer

# ==================== UTILITY FUNCTIONS ====================
def fetch_as_dicts(cursor):
    """Convert cursor results to list of dicts"""
    cols = [col[0].lower() for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]

def is_password_valid(password):
    """Validate password: 8+ chars, 1 special, 1 upper, 1 number"""
    if len(password) < 8:
        return False
    special_chars = re.findall(r'[\W_]', password)
    has_upper = re.search(r'[A-Z]', password)
    has_number = re.search(r'\d', password)
    return len(special_chars) == 1 and has_upper and has_number

def get_festival_today():
    """Get today's festival from database"""
    today = datetime.today().strftime('%Y-%m-%d')
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(DictCursor)
        cursor.execute("SELECT FESTIVAL_NAME FROM NRM_FESTIVALS WHERE FESTIVAL_DATE = %s", (today,))
        row = cursor.fetchone()
        return row['FESTIVAL_NAME'] if row else None
    except Exception as e:
        print(f"Error fetching festival: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_user_info(email):
    """Fetch user information from database"""
    conn = get_db_connection()
    if not conn:
        return {}
    try:
        cursor = conn.cursor(DictCursor)
        cursor.execute("""
            SELECT u.id AS user_id, u.usertype, u.username, u.profile_pic,
                   l.created_at, s.id AS student_id, s.first_name, s.last_name,
                   s.location AS location_name, r.registration_id
            FROM nrm_users u
            JOIN nrm_logins l ON u.id = l.user_id
            LEFT JOIN nrm_students s ON s.email = u.email
            LEFT JOIN nrm_registrations r ON r.student_id = s.id
            WHERE u.email = %s
            ORDER BY r.created_dt DESC LIMIT 1
        """, (email,))
        return cursor.fetchone() or {}
    except Exception as e:
        print(f"Error fetching user info: {e}")
        return {}
    finally:
        cursor.close()
        conn.close()

def get_offers():
    """Fetch active offers from database"""
    today = datetime.today().strftime('%Y-%m-%d')
    conn = get_db_connection()
    if not conn:
        return {}
    try:
        cursor = conn.cursor(DictCursor)
        cursor.execute("""
            SELECT c.course_name, c.course_fee, o.discount_percentage,
                   o.valid_from, o.valid_to
            FROM nrm_offers o
            JOIN nrm_courses c ON c.id = o.course_id
            WHERE o.is_active = TRUE
              AND (%s BETWEEN o.valid_from AND o.valid_to OR 
                   o.valid_from IS NULL OR o.valid_to IS NULL)
        """, (today,))
        
        offers = {}
        for row in cursor.fetchall():
            original_fee = row.get('COURSE_FEE', 0)
            discount = row.get('DISCOUNT_PERCENTAGE', 0)
            discounted_fee = original_fee - (original_fee * discount / 100)
            offers[row['COURSE_NAME']] = {
                "original_fee": int(original_fee),
                "discounted_fee": int(discounted_fee),
                "discount_percentage": int(discount)
            }
        return offers
    except Exception as e:
        print(f"Error fetching offers: {e}")
        return {}
    finally:
        cursor.close()
        conn.close()

def send_enquiry_email(name, email, phone, enquiry_text):
    """Send enquiry notification email"""
    sender_email = "vsrsubhash@gmail.com"
    sender_password = "Vaishnava@108"
    receiver_email = "vsrsubhash@gmail.com"

    subject = f"New Enquiry from {name}"
    body = f"""
New enquiry received:

Name: {name}
Email: {email}
Phone: {phone}

Message:
{enquiry_text}
    """

    msg = MIMEText(body, "plain")
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("Enquiry email sent")
    except Exception as e:
        print(f"Email failed: {e}")

# ==================== MAIN APP ====================
class ChakoraHubApp(App):
    logged_in_user = ObjectProperty(None, allownone=True)
    logged_in_email = StringProperty("")
    user_email = StringProperty("testuser@chakorahub.com")
    selected_file_path = StringProperty("No file selected")
    current_file_type = StringProperty("")
    
    def build(self):
        from kivy.lang import Builder
        self.root = Builder.load_file("home.kv")
        return self.root

        # print("Starting ChakoraHub App...")
        
        # # Register a safe, cross-platform font
        # try:
        #     if platform.system() == "Windows":
        #         LabelBase.register(name="EmojiFont", fn_regular="C:/Windows/Fonts/seguiemj.ttf")
        #     elif platform.system() == "Darwin":
        #         LabelBase.register(name="EmojiFont", fn_regular="/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
        #     else:
        #         LabelBase.register(name="EmojiFont", fn_regular="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        # except Exception as e:
        #     print(f"Emoji font not loaded: {e}")
        
        # # Load all KV files
        # kv_files = [
        #     "aboutus.kv", "adminregister.kv","billing.kv", "contactus.kv", "enquiry.kv",
        #     "register.kv", "blogger.kv", "calender.kv", "demovideos.kv", "home.kv",
        #     "feedback.kv", "offers.kv", "profile.kv", "resources.kv","profile.kv","resources.kv",
        #     "settings.kv", "student_report.kv", "upload.kv","practice_test.kv"
        # ]
        
        # for kv_file in kv_files:
        #     try:
        #         Builder.load_file(kv_file)
        #         print(f"Loaded {kv_file}")
        #     except Exception as e:
        #         print(f"Failed to load {kv_file}: {e}")
        
        # # Create ScreenManager from home.kv
        # try:
        #     #self.root = Builder.load_file("home.kv")
        #     print("Successfully loaded home.kv")
        # except Exception as e:
        #     print(f"Error loading home.kv: {e}")
        #     self.root = ScreenManager()
        #     main_screen = MainScreen(name="main")
        #     self.root.add_widget(main_screen)
        #     print("Created fallback screen manager")
        
        # # Add all screens
        # print("Adding screens...")
        # screens_to_add = [
        #     (AboutUsScreen, "aboutus_screen"),
        #     (AdminRegisterForm, "adminregister"),
        #     (ContactUsScreen, "contactus_screen"),
        #     (EnquiryScreen, "enquiry_screen"),
        #     (RegisterScreen, "register"),
        #     (BloggerRoot, "blogger_screen"),
        #     (CalendarScreen, "calendar_screen"),
        #     (DemoVideosScreen, "demo_videos_screen"),
        #     (FeedbackScreen, "feedback_screen"),
        #     (OffersScreen, "offers_screen"),
        #     (ProfileScreen, "profile_screen"),
        #     (ResourcesScreen, "resources_screen"),
        #     (SettingsScreen, "settings_screen"),
        #     (StudentReportScreen, "student_report_screen"),
        #     (AdminPortalScreen, "admin_portal"),
        #     (BillingScreen, "billing_screen")
        # ]
        
        # for screen_class, screen_name in screens_to_add:
        #     try:
        #         if screen_name not in self.root.screen_names:
        #             self.root.add_widget(screen_class(name=screen_name))
        #             print(f"Added {screen_name}")
        #         else:
        #             print(f"{screen_name} already exists")
        #     except Exception as e:
        #         print(f"Failed to add {screen_name}: {e}")
        
        # print(f"Total screens: {len(self.root.screen_names)}")
        
        # # Load initial data
        # try:
        #     main_screen = self.root.get_screen("main")
        #     Clock.schedule_once(lambda dt: self.load_data(main_screen), 0.1)
        # except Exception as e:
        #     print(f"Error loading initial data: {e}")
        
        # print("App built successfully!")
        # return self.root
    
    def get_s3_image(self, image_name):
        """Return full S3 URL for given image name"""
        base_url = "https://chakorahub-student.s3.amazonaws.com/snaps/"
        image_map = {
            'logo': base_url + 'logo.png',
            'theme': base_url + 'theme.gif'
        }
    # Fallback image (can use a default hosted image)
        return image_map.get(image_name, base_url + 'logo.png')
    
    def choose_file(self, file_type):
        """Open file chooser"""
        self.current_file_type = file_type
        popup = FileChooserPopup(file_type=file_type, callback=self.on_file_selected)
        popup.open()
    
    def on_file_selected(self, file_path):
        """File selected callback"""
        self.selected_file_path = file_path
        print(f"Selected file: {file_path}")
        
        try:
            admin_screen = self.root.get_screen("admin_portal")
            filename = os.path.basename(file_path)
            admin_screen.ids.flash_msg.text = f"[color=0000ff]Selected: {filename}[/color]"
        except Exception as e:
            print(f"Error updating admin screen: {e}")
    
    def login_user(self, username, password, message_label):
        """User login using Lambda API"""
        if not username or not password:
            message_label.text = "[color=ff0000]Please fill both fields[/color]"
            return

        # Call Lambda API for login
        
        result = call_lambda_api("home", method="POST", data={"action": "login","data": {"username": username, "password": password}})
        
        if result and result.get('success'):
            user_data = result.get('user', {})
            self.logged_in_user = user_data
            self.logged_in_email = username
            self.user_email = username
            
            message_label.text = f"[color=008000]Welcome {user_data.get('USERNAME', username)}![/color]"

            # Navigate to resources
            if "resources_screen" in self.root.screen_names:
                self.root.current = 'resources_screen'
            
            # Clear login fields
            try:
                main_screen = self.root.get_screen('main')
                main_screen.ids.login_box.ids.username_input.text = ""
                main_screen.ids.login_box.ids.password_input.text = ""
                main_screen.ids.login_box.ids.message_label.text = ""
            except Exception as e:
                print(f"Error clearing login fields: {e}")
        else:
            error_msg = result.get('message', 'Login failed') if result else 'Connection error'
            message_label.text = f"[color=ff0000]{error_msg}[/color]"

    def logout_user(self):
        """Logout user"""
        print("Logging out user")
        self.logged_in_user = None
        self.logged_in_email = ""
        self.user_email = ""
        self.root.current = 'main'
        print("Logout successful")

    def go_to(self, screen_name):
        """Navigate to screen"""
        self.root.current = f"{screen_name}_screen"

    def load_data(self, screen):
        """Load initial data for main screen using Lambda API"""
        try:
            # Try Lambda API first
            response = call_lambda_api("home", method="POST", data={"action": "fetch_batches"})
            
            if result and result.get('success'):
                data = result.get('data', {})
                current_batches = data.get('current_batches', [])
                upcoming_batches = data.get('upcoming_batches', [])
                feedbacks = data.get('feedbacks', [])
                self.populate_ui(screen, current_batches, upcoming_batches, feedbacks)
            else:
                # Fallback to direct database
                self.load_data_from_db(screen)
                
        except Exception as e:
            print(f"Error loading data: {e}")
            self.load_fallback_data(screen)

    def load_data_from_db(self, screen):
        """Load data directly from database"""
        try:
            conn = get_db_connection()
            if not conn:
                self.load_fallback_data(screen)
                return
            
            cursor = conn.cursor()
            
            # Current batches
            cursor.execute("""
                SELECT c.course_name, l.language AS language_name
                FROM nrm_registrations r
                JOIN nrm_statuses s ON r.status_id = s.id
                JOIN nrm_courses c ON r.course_id = c.id
                JOIN nrm_languages l ON r.language_id = l.id
                WHERE LOWER(s.status) = 'active'
            """)
            current_batches = fetch_as_dicts(cursor)
            
            # Upcoming batches
            cursor.execute("""
                SELECT c.course_name, l.language AS language_name
                FROM nrm_registrations r
                JOIN nrm_statuses s ON r.status_id = s.id
                JOIN nrm_courses c ON r.course_id = c.id
                JOIN nrm_languages l ON r.language_id = l.id
                WHERE LOWER(s.status) = 'pending'
            """)
            upcoming_batches = fetch_as_dicts(cursor)
            
            # Feedbacks
            cursor.execute("""
                SELECT u.username, f.feedback_message
                FROM nrm_feedback f
                JOIN nrm_users u ON f.student_id = u.id
                ORDER BY f.submitted_at DESC LIMIT 20
            """)
            feedbacks = fetch_as_dicts(cursor)
            
            conn.close()
            self.populate_ui(screen, current_batches, upcoming_batches, feedbacks)
            
        except Exception as e:
            print(f"Error loading data from DB: {e}")
            self.load_fallback_data(screen)

    def populate_ui(self, screen, current_batches, upcoming_batches, feedbacks):
        """Populate UI with data"""
        try:
            black_text = (0, 0, 0, 1)
            
            # Set headings for batch boxes
            if hasattr(screen.ids, 'current_batches'):
                screen.ids.current_batches.heading = "Current Batches"
            if hasattr(screen.ids, 'upcoming_batches'):
                screen.ids.upcoming_batches.heading = "Upcoming Batches"
            
            if hasattr(screen.ids, 'current_batches') and hasattr(screen.ids.current_batches.ids, 'rv'):
                screen.ids.current_batches.ids.rv.data = [
                    {"text": f"{c['course_name']} - {c['language_name']}", "color": black_text}
                    for c in current_batches
                ] or [{"text": "No Current Batches", "color": black_text}]

            if hasattr(screen.ids, 'upcoming_batches') and hasattr(screen.ids.upcoming_batches.ids, 'rv'):
                screen.ids.upcoming_batches.ids.rv.data = [
                    {"text": f"{c['course_name']} - {c['language_name']}", "color": black_text}
                    for c in upcoming_batches
                ] or [{"text": "No Upcoming Batches", "color": black_text}]

            if hasattr(screen.ids, 'feedback_rv'):
                screen.ids.feedback_rv.data = [
                    {"msg": f['feedback_message'], "name": f['username']}
                    for f in feedbacks
                ] or [{"msg": "No feedback available", "name": ""}]
            
        except Exception as e:
            print(f"UI population failed: {e}")

    def load_fallback_data(self, screen):
        """Load fallback data if DB fails"""
        print("Loading fallback data...")
        self.populate_ui(
            screen,
            current_batches=[{"course_name": "Python Full Stack", "language_name": "English"}],
            upcoming_batches=[],
            feedbacks=[
                {"username": "Alice", "feedback_message": "Great course!"},
                {"username": "Raj", "feedback_message": "Very good teaching!"}
            ]
        )

# ==================== RUN APP ====================
if __name__ == "__main__":
    ChakoraHubApp().run()