from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomUserModelTests(TestCase):
    """
    Unit tests for the custom User model and CustomUserManager behavior.
    
    Why: Validates that the custom User creation, normalization, and superuser
    privilege setting functions correctly.
    """

    def test_create_user_success(self):
        """
        Why: Ensures we can create a normal user with email and name,
        and that password hashing works correctly.
        """
        user = User.objects.create_user(email="test@example.com", name="Test User", password="password123")
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.name, "Test User")
        self.assertTrue(user.check_password("password123"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_without_email_raises_error(self):
        """
        Why: Ensures that creating a user without providing an email address raises a ValueError.
        """
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", name="No Email User", password="password123")

    def test_create_superuser_success(self):
        """
        Why: Ensures we can create a superuser with admin staff and superuser flags set.
        """
        admin = User.objects.create_superuser(email="admin@example.com", name="Admin User", password="adminpassword")
        self.assertEqual(admin.email, "admin@example.com")
        self.assertEqual(admin.name, "Admin User")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

class AuthenticationViewsTests(TestCase):
    """
    Integration tests for user authentication views (signup, login, logout).
    
    Why: Asserts that form validation, view routing, sessions, and redirects
    operate seamlessly across the login lifecycle.
    """

    def setUp(self):
        """
        Why: Sets up baseline URL paths and user accounts to test authentication scenarios.
        """
        self.signup_url = reverse('signup')
        self.login_url = reverse('login')
        self.logout_url = reverse('logout')
        self.home_url = reverse('home')
        
        self.user_email = "existing@example.com"
        self.user_password = "secure_password_123"
        self.user_name = "Existing User"
        self.user = User.objects.create_user(
            email=self.user_email,
            name=self.user_name,
            password=self.user_password
        )

    def test_signup_success(self):
        """
        Why: Verifies that valid signup form details successfully register
        a user, establish a session, and redirect to the home landing page.
        """
        signup_data = {
            'email': 'newuser@example.com',
            'name': 'New User',
            'password1': 'new_password_123',
            'password2': 'new_password_123'
        }
        
        # Act
        response = self.client.post(self.signup_url, signup_data)
        
        # Assert
        self.assertRedirects(response, self.home_url)
        # Verify user was saved in DB
        user_exists = User.objects.filter(email='newuser@example.com').exists()
        self.assertTrue(user_exists)
        # Verify user is authenticated in the current session
        self.assertIn('_auth_user_id', self.client.session)

    def test_duplicate_email_rejection(self):
        """
        Why: Assures that registering with a pre-existing email is rejected
        with form validation errors, preventing multiple accounts per email.
        """
        signup_data = {
            'email': self.user_email,
            'name': 'Duplicate User',
            'password1': 'diff_password_123',
            'password2': 'diff_password_123'
        }
        
        # Act
        response = self.client.post(self.signup_url, signup_data)
        
        # Assert
        # Should stay on page (200 OK) with validation errors
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'email', 'User with this Email Address already exists.')
        # Ensure database count for the email remains exactly 1
        self.assertEqual(User.objects.filter(email=self.user_email).count(), 1)

    def test_login_success(self):
        """
        Why: Verifies that standard credentials authenticate the user,
        initiating a secure session and redirecting to home.
        """
        login_data = {
            'username': self.user_email,
            'password': self.user_password
        }
        
        # Act
        response = self.client.post(self.login_url, login_data)
        
        # Assert
        self.assertRedirects(response, self.home_url)
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_failure(self):
        """
        Why: Assures that invalid credentials (wrong password) reject authentication
        and do not establish a session.
        """
        login_data = {
            'username': self.user_email,
            'password': 'incorrect_password'
        }
        
        # Act
        response = self.client.post(self.login_url, login_data)
        
        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_success(self):
        """
        Why: Verifies that requesting the logout endpoint clears session tokens
        and redirects the user back to the login page.
        """
        # First login
        self.client.login(username=self.user_email, password=self.user_password)
        self.assertIn('_auth_user_id', self.client.session)
        
        # Act - Log out
        response = self.client.get(self.logout_url)
        
        # Assert
        self.assertRedirects(response, self.login_url)
        self.assertNotIn('_auth_user_id', self.client.session)
