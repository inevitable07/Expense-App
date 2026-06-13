# Architecture Decisions

## Authentication Strategy

For the initial setup of the shared expenses application, we opted for Django's built-in session-based authentication rather than alternatives like Django REST Framework (DRF) token authentication or django-allauth. 

### Why this approach was chosen:
1. **Out-of-the-Box Security:** Standard session authentication automatically manages CSRF protection, secure HTTP-only cookies, and session lifecycle validation, reducing custom security implementation overhead.
2. **Simplified Architecture:** By utilizing native Django forms, templates, and views, we avoid adding large external dependencies (like `django-allauth`) which require heavy database migrations and configurations.
3. **Template Compatibility:** Since the setup specifies rendering Bootstrap-styled HTML templates for login and signup locally, standard Django sessions fit perfectly, whereas DRF Token auth is designed for stateless REST APIs accessed by decoupled single-page applications (SPAs) or mobile apps.
