from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Group, GroupMembership

User = get_user_model()

class UserShortSerializer(serializers.ModelSerializer):
    """
    Serializer to represent a simple User summary in API responses.
    
    Why: Keeps API payloads concise by including only basic identification
    attributes (id, name, email) of users.
    """
    class Meta:
        model = User
        fields = ('id', 'name', 'email')

class GroupSerializer(serializers.ModelSerializer):
    """
    Serializer for Group records.
    
    Why: Handles serialization of Group details and ensures that the creator
    (created_by) is exposed as read-only.
    """
    created_by = UserShortSerializer(read_only=True)

    class Meta:
        model = Group
        fields = ('id', 'name', 'created_at', 'created_by')

class GroupMembershipSerializer(serializers.ModelSerializer):
    """
    Serializer for GroupMembership records.
    
    Why: Serializes membership information showing the user metadata alongside
    the active/historical dates (joined_at, left_at).
    """
    user = UserShortSerializer(read_only=True)

    class Meta:
        model = GroupMembership
        fields = ('id', 'user', 'joined_at', 'left_at')

class AddMemberSerializer(serializers.Serializer):
    """
    Serializer input payload validation for adding a member to a group.
    
    Why: Validates that the target user email exists in the system and captures
    the join date for membership history.
    """
    email = serializers.EmailField(
        help_text="Unique email address of the user to invite."
    )
    joined_at = serializers.DateField(
        help_text="Date when the user joined the group."
    )

    def validate_email(self, value):
        """
        Why: Ensures we reject the signup if the email does not correspond to a registered account.
        """
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email address.")
        return value

class RemoveMemberSerializer(serializers.Serializer):
    """
    Serializer input payload validation for removing a member from a group.
    
    Why: Validates that the user email exists in the system and captures the
    leaving date to mark the end of their active membership period.
    """
    email = serializers.EmailField(
        help_text="Email address of the user leaving the group."
    )
    left_at = serializers.DateField(
        help_text="Date when the user left the group."
    )

    def validate_email(self, value):
        """
        Why: Ensures we reject the removal request if the email does not correspond to a registered account.
        """
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email address.")
        return value
