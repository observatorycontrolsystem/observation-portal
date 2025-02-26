import copy
import string

from rest_framework import serializers, validators
from django.contrib.auth.models import User
from django.utils.translation import gettext as _
from django.utils.module_loading import import_string
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site

from observation_portal.accounts.models import Profile
from observation_portal.accounts.tasks import send_mail
from observation_portal.proposals.models import ProposalInvite


class ProfileSerializer(serializers.ModelSerializer):
    terms_accepted = serializers.DateTimeField(read_only=True)
    sciencecollaborationallocation = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = (
            'education_user', 'notifications_enabled', 'notifications_on_authored_only',
            'simple_interface', 'view_authored_requests_only', 'title', 'staff_view',
            'institution', 'api_quota', 'terms_accepted', 'sciencecollaborationallocation',
            'password_expiration'
        )
        extra_kwargs = {
            'password_expiration': {'read_only': True}
        }

    def get_sciencecollaborationallocation(self, obj):
        if obj.is_scicollab_admin:
            return obj.user.sciencecollaborationallocation.as_dict()
        else:
            return None

    def validate_staff_view(self, staff_view):
        user = self.context.get('request').user
        is_staff = user and user.is_authenticated and user.is_staff
        if staff_view and not is_staff:
            raise serializers.ValidationError(_('Must be staff to set staff_view'))
        return staff_view


class UserSerializer(serializers.ModelSerializer):
    is_staff = serializers.BooleanField(read_only=True)
    proposals = serializers.SerializerMethodField()
    proposal_notifications = serializers.SerializerMethodField()
    profile = import_string(settings.SERIALIZERS['accounts']['Profile'])(required=False)
    available_instrument_types = serializers.SerializerMethodField()
    tokens = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email', 'profile', 'is_staff', 'is_superuser', 'proposals',
            'available_instrument_types', 'tokens', 'proposal_notifications'
        )

    def get_proposals(self, obj):
        proposals = []
        for proposal in obj.proposal_set.all():
            proposal_details = {
                'id': proposal.id, 'title': proposal.title, 'current': proposal in obj.profile.current_proposals
            }
            if 'include_current_time_allocations' in self.context and self.context['include_current_time_allocations']:
                membership = obj.membership_set.filter(proposal=proposal).first()
                proposal_details['time_limit'] = membership.time_limit
                proposal_details['time_used'] = obj.profile.time_used_in_proposal(proposal)
                proposal_details['time_allocations'] = []
                for time_allocation in proposal.timeallocation_set.filter(semester=proposal.current_semester):
                    proposal_details['time_allocations'].append(time_allocation.as_dict(
                        exclude=['semester', 'proposal', 'id', 'instrument_type']))
            proposals.append(proposal_details)
        return proposals

    def get_proposal_notifications(self, obj):
        return [pn.proposal.id for pn in obj.proposalnotification_set.all()]

    def get_available_instrument_types(self, obj):
        instrument_types = set()
        active_proposals = [proposal for proposal in obj.proposal_set.all() if proposal.active]
        for proposal in active_proposals:
            for timeallocation in proposal.timeallocation_set.all():
                for instrument_type in timeallocation.instrument_types:
                    instrument_types.add(instrument_type)
        return list(instrument_types)

    def get_tokens(self, obj):
        return {
            'archive': obj.profile.archive_bearer_token,
            'api_token': obj.profile.api_token.key
        }

    def validate_email(self, data):
        if data and User.objects.filter(email=data).exclude(pk=self.instance.id).exists():
            raise serializers.ValidationError(_('User with this email already exists'))
        return data

    def update(self, instance, validated_data):
        user_update_fields = ['email', 'last_name', 'first_name']
        instance.email = validated_data.get('email', instance.email)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.save(update_fields=user_update_fields)

        profile_data = validated_data.pop('profile', {})
        if profile_data:
            Profile.objects.filter(pk=instance.profile.pk).update(**profile_data)

        return instance


class AccountRemovalRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


class AccountRemovalResponseSerializer(serializers.Serializer):
    message = serializers.CharField(default='Account removal request successfully submitted.')


class RevokeTokenResponseSerializer(serializers.Serializer):
    message = serializers.CharField(default='API token revoked.')


class AcceptTermsResponseSerializer(serializers.Serializer):
    message = serializers.CharField(default='Terms accepted')


class CreateUserSerializer(serializers.Serializer):
    """Flattend User/Profile model seralizer with the bare minimum needed to
    create an account.
    """

    # User model stuff
    username = serializers.CharField(
        max_length=150,
        validators=[
            validators.UniqueValidator(
                queryset=User.objects.all(),
                message="username already exists",
                lookup="exact"
            )
        ]
    )

    # allow passing in the password, but if one is not provided generate one
    # also don't return this in the response (write only)
    password = serializers.CharField(
        max_length=128, required=False, default=None, write_only=True
    )
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(
        validators=[
            validators.UniqueValidator(
                queryset=User.objects.all(),
                message="user with email already exists",
                lookup="iexact"
            )
        ]
    )

    # Profile model stuff
    institution = serializers.CharField(max_length=200)
    title = serializers.CharField(max_length=200)
    education_user = serializers.BooleanField(required=False, default=True)


class BulkCreateUsersSerializer(serializers.Serializer):
    users = serializers.ListField(
        child=import_string(settings.SERIALIZERS["accounts"]["CreateUserSerializer"])(),
        max_length=50
    )

    def validate_users(self, data):
        """Make sure usernames & emails are unique within the request payload"""
        usernames = set()
        emails = set()
        for user in data:
            username = user["username"]
            if username in usernames:
                raise serializers.ValidationError(f"username '{username}' provided multiple times")
            usernames.add(username)

            email = user["email"].lower()
            if email in emails:
                raise serializers.ValidationError(f"email '{email}' provided multiple times")
            emails.add(email)

        return data

    def create_user(self, validated_data, created_by):
        password = validated_data.pop("password", None)

        if password is None:
            password = User.objects.make_random_password(
                length=12,
                allowed_chars=string.ascii_letters + string.digits + "!@#$%^&*" * 3
            )

        user = User.objects.create_user(
            username=validated_data.pop("username"),
            password=password,
            first_name=validated_data.pop("first_name"),
            last_name=validated_data.pop("last_name"),
            email=validated_data.pop("email"),
            is_active=True,
        )
        Profile.objects.create(
            user=user,
            password_expiration=timezone.now(),
            created_by=created_by,
            **validated_data
        )

        # accept all pending proposal invites
        for invite in ProposalInvite.objects.filter(
            email__iexact=user.email,
            used__isnull=True,
        ).order_by("sent"):
            invite.accept(user)

        return password, user

    def create_users(self, validated_data, created_by):
        res = []
        for user in validated_data:
            res.append(self.create_user(user, created_by))
        return res

    def save(self):
        # DRF madness to avoid messing up the reponse :(
        validated_data = copy.deepcopy(self.validated_data)

        users = validated_data.get("users") or []

        created_by = self.context["request"].user

        with transaction.atomic():
            saved_users = self.create_users(users, created_by)

        # send out emails
        for password, user in saved_users:
            msg = render_to_string(
                "bulkapi-account-created-email.txt",
                {
                    "user": user,
                    "password": password,
                    "org": settings.ORGANIZATION_NAME,
                    "site": get_current_site(self.context["request"])
                }
            )

            send_mail.send(
                f"{settings.ORGANIZATION_NAME} Account Created!",
                msg,
                settings.ORGANIZATION_EMAIL,
                [user.email]
            )

