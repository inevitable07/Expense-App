from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

class CustomUserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier for authentication
    instead of usernames.
    
    Why: Overridden to allow users to register and authenticate using their email
    address, matching modern web standards for identification.
    """
    def create_user(self, email, password=None, **extra_fields):
        """
        Creates and saves a User with the given email and password.
        
        Why: Ensures normalized email is set as the user identification field
        and sets active status as default.
        """
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Creates and saves a superuser with the given email and password.
        
        Why: Configures staff and superuser permissions required for Django's
        administrative panels.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    """
    Custom User model extending AbstractUser to use email as the unique identifier.
    
    Why: By subclassing AbstractUser, we retain Django's robust authentication
    infrastructure (permissions, sessions, passwords) while customizing the
    primary identifier field.
    """
    # Why: Disables username field from AbstractUser as email is the unique identifier.
    username = None
    
    # Why: Email address serves as the unique login credential.
    email = models.EmailField(
        unique=True,
        verbose_name="Email Address",
        help_text="Required. Unique email address for authentication."
    )
    
    # Why: Full name of the user for display and personalization in groups/ledger.
    name = models.CharField(
        max_length=255,
        verbose_name="Name",
        help_text="The full name of the user."
    )

    objects = CustomUserManager()

    # Why: Informs Django to treat email as the login username credential.
    USERNAME_FIELD = 'email'
    
    # Why: Prompts createsuperuser command to ask for the user's name.
    REQUIRED_FIELDS = ['name']

    def __str__(self):
        """
        Why: Returns string representation of User displaying name and email.
        """
        return f"{self.name} ({self.email})"
