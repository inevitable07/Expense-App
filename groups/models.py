from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

class Group(models.Model):
    """
    Represents an expense sharing group.
    
    Why: Organizes multiple users together so that expenses can be shared,
    calculated, and settled within a specific group boundary.
    """
    # Why: The display name of the expense sharing group.
    name = models.CharField(
        max_length=255,
        verbose_name="Group Name",
        help_text="Name of the expense sharing group."
    )
    
    # Why: Automatically tracks when the group was created.
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At",
        help_text="Timestamp when the group was created."
    )
    
    # Why: Keeps track of the user who initiated the group for admin/audit purposes.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_groups",
        verbose_name="Created By",
        help_text="The user who created this group."
    )

    def __str__(self):
        """
        Why: Returns string representation of Group showing its name.
        """
        return self.name

class GroupMembership(models.Model):
    """
    Represents a historical or active membership of a user in a group.
    
    This date range (joined_at to left_at) is the mechanism that scopes
    expenses to members. An expense incurred on a specific date will only
    be split among users who were active members of the group on that date.
    
    Why: Tracks when users joined and left groups, enforcing validation rules
    such as non-overlapping periods and singular active memberships.
    """
    
    # Why: Links the membership to a specific expense sharing group.
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="Group",
        help_text="The group associated with this membership."
    )
    
    # Why: Links the membership to a specific registered user.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="User",
        help_text="The user associated with this membership."
    )
    
    # Why: Marks the start date from which the user is active in the group.
    joined_at = models.DateField(
        verbose_name="Joined At",
        help_text="The date when the user joined the group."
    )
    
    # Why: Marks the date when the user left the group. Null indicates currently active.
    left_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="Left At",
        help_text="The date when the user left the group. Null if membership is active."
    )

    def clean(self):
        """
        Why: Validates membership dates and checks for active/overlap constraints
        to ensure data integrity.
        """
        super().clean()
        
        # Rule 1: joined_at <= left_at if left_at is set
        if self.left_at and self.joined_at > self.left_at:
            raise ValidationError({
                'left_at': "The leave date (left_at) must be after or equal to the join date (joined_at)."
            })

        # Fetch other memberships of the same user in the same group (excluding self if updating)
        other_memberships = GroupMembership.objects.filter(group=self.group, user=self.user)
        if self.pk:
            other_memberships = other_memberships.exclude(pk=self.pk)

        # Rule 2: Multiple active memberships prevention
        if self.left_at is None:
            active_exists = other_memberships.filter(left_at__isnull=True).exists()
            if active_exists:
                raise ValidationError("A user cannot have multiple active memberships in the same group simultaneously.")

        # Rule 3: Overlapping membership periods prevention
        # A new membership period [joined_at, left_at] overlaps with an existing period [Ej, El] if:
        # (new_start <= existing_end or existing_end is None) AND (new_end >= existing_start or new_end is None)
        for existing in other_memberships:
            existing_start = existing.joined_at
            existing_end = existing.left_at
            new_start = self.joined_at
            new_end = self.left_at

            # Condition for overlap:
            # Overlaps if:
            # (new_end is None OR new_end >= existing_start) AND (existing_end is None OR new_start <= existing_end)
            is_overlap = (new_end is None or new_end >= existing_start) and (existing_end is None or new_start <= existing_end)
            
            if is_overlap:
                existing_end_str = existing_end if existing_end else "Present"
                new_end_str = new_end if new_end else "Present"
                raise ValidationError(
                    f"Membership period [{new_start} to {new_end_str}] overlaps with an existing membership "
                    f"[{existing_start} to {existing_end_str}] for this user."
                )

    def save(self, *args, **kwargs):
        """
        Why: Ensures clean() validation rules are automatically executed
        before committing the membership record to the database.
        """
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        """
        Why: Returns string representation of GroupMembership showing user, group, and dates.
        """
        return f"{self.user.email} in {self.group.name} ({self.joined_at} to {self.left_at or 'Present'})"
