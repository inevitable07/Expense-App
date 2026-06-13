from datetime import date
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework import status

from .models import Group, GroupMembership
from .services import is_member_active_on_date

User = get_user_model()

class GroupMembershipModelTests(TestCase):
    """
    Unit tests for GroupMembership model validators and date constraints.
    
    Why: Validates that joined_at/left_at boundaries and non-overlapping
    membership intervals are strictly enforced on database/model level.
    """

    def setUp(self):
        """
        Why: Sets up baseline user and group objects for test cases.
        """
        self.creator = User.objects.create_user(
            email="creator@example.com", name="Creator", password="password123"
        )
        self.user = User.objects.create_user(
            email="user@example.com", name="User", password="password123"
        )
        # Creating group. Note: we use base create() to bypass perform_create logic
        # which is part of the API ViewSet.
        self.group = Group.objects.create(name="Study Group", created_by=self.creator)

    def test_join_date_validation_success(self):
        """
        Why: Assures that saving a membership with joined_at <= left_at works correctly.
        """
        membership = GroupMembership(
            group=self.group,
            user=self.user,
            joined_at=date(2026, 1, 1),
            left_at=date(2026, 1, 15)
        )
        try:
            membership.save()
        except ValidationError:
            self.fail("ValidationError raised unexpectedly for joined_at <= left_at.")

    def test_leave_date_validation_failure(self):
        """
        Why: Assures that setting joined_at > left_at raises a validation error.
        """
        membership = GroupMembership(
            group=self.group,
            user=self.user,
            joined_at=date(2026, 1, 15),
            left_at=date(2026, 1, 1)
        )
        with self.assertRaises(ValidationError) as ctx:
            membership.save()
        self.assertIn('left_at', ctx.exception.message_dict)

    def test_multiple_active_memberships_failure(self):
        """
        Why: Prevents a user from having more than one active membership (left_at is Null) in a group at the same time.
        """
        # First active membership
        GroupMembership.objects.create(
            group=self.group,
            user=self.user,
            joined_at=date(2026, 1, 1),
            left_at=None
        )
        # Try second active membership
        duplicate = GroupMembership(
            group=self.group,
            user=self.user,
            joined_at=date(2026, 2, 1),
            left_at=None
        )
        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_overlap_prevention_historical_and_new_active(self):
        """
        Why: Assures that an active membership cannot start during a user's previous historical membership period.
        """
        GroupMembership.objects.create(
            group=self.group,
            user=self.user,
            joined_at=date(2026, 1, 1),
            left_at=date(2026, 1, 15)
        )
        # Tries to join while already having been a member (starts on 2026-01-10, which overlaps)
        overlapping = GroupMembership(
            group=self.group,
            user=self.user,
            joined_at=date(2026, 1, 10),
            left_at=None
        )
        with self.assertRaises(ValidationError):
            overlapping.save()

    def test_overlap_prevention_bounded_periods(self):
        """
        Why: Assures that two bounded historical membership periods cannot overlap.
        """
        GroupMembership.objects.create(
            group=self.group,
            user=self.user,
            joined_at=date(2026, 1, 10),
            left_at=date(2026, 1, 20)
        )
        
        overlapping = GroupMembership(
            group=self.group,
            user=self.user,
            joined_at=date(2026, 1, 5),
            left_at=date(2026, 1, 12)  # Overlaps 10 to 12
        )
        with self.assertRaises(ValidationError):
            overlapping.save()

    def test_active_member_lookup_helper(self):
        """
        Why: Tests that is_member_active_on_date helper correctly queries user status on date boundaries.
        """
        GroupMembership.objects.create(
            group=self.group,
            user=self.user,
            joined_at=date(2026, 1, 10),
            left_at=date(2026, 1, 20)
        )

        # Before join date
        self.assertFalse(is_member_active_on_date(self.user, self.group, date(2026, 1, 9)))
        # Exactly on join date
        self.assertTrue(is_member_active_on_date(self.user, self.group, date(2026, 1, 10)))
        # Between join and leave dates
        self.assertTrue(is_member_active_on_date(self.user, self.group, date(2026, 1, 15)))
        # Exactly on leave date
        self.assertTrue(is_member_active_on_date(self.user, self.group, date(2026, 1, 20)))
        # After leave date
        self.assertFalse(is_member_active_on_date(self.user, self.group, date(2026, 1, 21)))

        # Add an active membership in the future
        future_membership = GroupMembership.objects.create(
            group=self.group,
            user=self.user,
            joined_at=date(2026, 2, 1),
            left_at=None
        )
        # Verify active membership lookup
        self.assertFalse(is_member_active_on_date(self.user, self.group, date(2026, 1, 25)))
        self.assertTrue(is_member_active_on_date(self.user, self.group, date(2026, 2, 1)))
        self.assertTrue(is_member_active_on_date(self.user, self.group, date(2026, 12, 31)))


class GroupAPIEndpointsTests(APITestCase):
    """
    Integration tests for Group and GroupMembership REST API endpoints.
    
    Why: Assures views properly create records, enforce model constraints, and serialize output.
    """

    def setUp(self):
        """
        Why: Creates standard users and authenticates client.
        """
        self.creator = User.objects.create_user(
            email="creator@example.com", name="Creator", password="password123"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", name="Other", password="password123"
        )
        self.client.force_authenticate(user=self.creator)
        self.list_create_url = reverse('group-list')

    def test_create_group_auto_adds_creator(self):
        """
        Why: Verifies group creation endpoint auto-adds the creator as a member.
        """
        data = {'name': 'New Trip Group'}
        response = self.client.post(self.list_create_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        group_id = response.data['id']
        # Assert active membership exists for the creator
        membership = GroupMembership.objects.filter(group_id=group_id, user=self.creator, left_at__isnull=True)
        self.assertTrue(membership.exists())

    def test_add_member_api(self):
        """
        Why: Verifies endpoint registers a member and creates a GroupMembership record.
        """
        group = Group.objects.create(name="Test Group", created_by=self.creator)
        add_url = reverse('group-add-member', args=[group.id])
        data = {
            'email': self.other_user.email,
            'joined_at': '2026-03-01'
        }
        
        response = self.client.post(add_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            GroupMembership.objects.filter(
                group=group, user=self.other_user, joined_at=date(2026, 3, 1)
            ).exists()
        )

    def test_remove_member_api(self):
        """
        Why: Verifies endpoint offboards an active member by assigning a left_at date.
        """
        group = Group.objects.create(name="Test Group", created_by=self.creator)
        # Create active membership
        membership = GroupMembership.objects.create(
            group=group,
            user=self.other_user,
            joined_at=date(2026, 1, 1),
            left_at=None
        )
        
        remove_url = reverse('group-remove-member', args=[group.id])
        data = {
            'email': self.other_user.email,
            'left_at': '2026-01-10'
        }
        
        response = self.client.post(remove_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Reload membership from database
        membership.refresh_from_db()
        self.assertEqual(membership.left_at, date(2026, 1, 10))

    def test_list_members_api(self):
        """
        Why: Verifies list-members API successfully retrieves historical and active memberships.
        """
        group = Group.objects.create(name="Test Group", created_by=self.creator)
        GroupMembership.objects.create(
            group=group,
            user=self.other_user,
            joined_at=date(2026, 1, 1),
            left_at=date(2026, 1, 5)
        )
        GroupMembership.objects.create(
            group=group,
            user=self.creator,
            joined_at=date(2026, 1, 1),
            left_at=None
        )
        
        members_url = reverse('group-list-members', args=[group.id])
        response = self.client.get(members_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)


class GroupTemplateViewsTests(TestCase):
    """
    Unit tests for Group HTML template views.
    
    Why: Validates page rendering, redirects for unauthorized users,
    and HTML form processing (creation, adding/removing members).
    """

    def setUp(self):
        """
        Why: Configures URL paths, mock users, and default memberships.
        """
        self.creator = User.objects.create_user(
            email="creator@example.com", name="Creator", password="password123"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", name="Other User", password="password123"
        )
        self.group = Group.objects.create(name="Template Group", created_by=self.creator)
        # Add creator to membership
        GroupMembership.objects.create(
            group=self.group,
            user=self.creator,
            joined_at=date(2026, 1, 1)
        )
        
        self.list_url = reverse('group_list')
        self.create_url = reverse('group_create')
        self.detail_url = reverse('group_detail', args=[self.group.id])
        self.add_member_url = reverse('group_add_member', args=[self.group.id])
        self.remove_member_url = reverse('group_remove_member', args=[self.group.id])

    def test_list_view_redirects_anonymous(self):
        """
        Why: Ensures anonymous requests are redirected to login.
        """
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)

    def test_list_view_success_authenticated(self):
        """
        Why: Assures the group listing page renders correctly for authenticated users.
        """
        self.client.login(username=self.creator.email, password="password123")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Template Group")

    def test_create_view_form_valid(self):
        """
        Why: Assures submitting a valid group form creates the group and registers creator.
        """
        self.client.login(username=self.creator.email, password="password123")
        post_data = {'name': 'New Group Via HTML'}
        response = self.client.post(self.create_url, post_data)
        self.assertRedirects(response, self.list_url)
        
        new_group = Group.objects.get(name='New Group Via HTML')
        self.assertEqual(new_group.created_by, self.creator)
        self.assertTrue(
            GroupMembership.objects.filter(group=new_group, user=self.creator, left_at__isnull=True).exists()
        )

    def test_detail_view_renders_memberships(self):
        """
        Why: Assures detail view shows memberships history table.
        """
        self.client.login(username=self.creator.email, password="password123")
        # Add past member
        GroupMembership.objects.create(
            group=self.group,
            user=self.other_user,
            joined_at=date(2026, 1, 5),
            left_at=date(2026, 1, 10)
        )
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Creator")
        self.assertContains(response, "Other User")

    def test_add_member_view_success(self):
        """
        Why: Assures adding a member via POST request successfully registers them.
        """
        self.client.login(username=self.creator.email, password="password123")
        post_data = {
            'email': self.other_user.email,
            'joined_at': '2026-02-01'
        }
        response = self.client.post(self.add_member_url, post_data)
        self.assertRedirects(response, self.detail_url)
        self.assertTrue(
            GroupMembership.objects.filter(
                group=self.group, user=self.other_user, joined_at=date(2026, 2, 1)
            ).exists()
        )

    def test_remove_member_view_success(self):
        """
        Why: Assures setting left_at via POST request marks active member as left.
        """
        self.client.login(username=self.creator.email, password="password123")
        # Add active member
        membership = GroupMembership.objects.create(
            group=self.group,
            user=self.other_user,
            joined_at=date(2026, 1, 1),
            left_at=None
        )
        post_data = {
            'email': self.other_user.email,
            'left_at': '2026-01-10'
        }
        response = self.client.post(self.remove_member_url, post_data)
        self.assertRedirects(response, self.detail_url)
        membership.refresh_from_db()
        self.assertEqual(membership.left_at, date(2026, 1, 10))
