from rest_framework import viewsets, filters, mixins
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.translation import ugettext as _
from django.utils.module_loading import import_string
from django.conf import settings
from rest_framework import status

from observation_portal.accounts.permissions import IsPrincipleInvestigator
from observation_portal.common.mixins import ListAsDictMixin, DetailAsDictMixin
from observation_portal.common.utils import get_queryset_field_values
from observation_portal.proposals.filters import SemesterFilter, ProposalFilter, MembershipFilter, ProposalInviteFilter
from observation_portal.proposals.models import Proposal, Semester, ProposalNotification, Membership, ProposalInvite
from observation_portal.common.schema import ObservationPortalSchema
from observation_portal.common.doc_examples import EXAMPLE_RESPONSES


class ProposalViewSet(DetailAsDictMixin, ListAsDictMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated,)
    schema = ObservationPortalSchema(tags=['Proposals'])
    serializer_class = import_string(settings.SERIALIZERS['proposals']['Proposal'])
    filter_class = ProposalFilter
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    ordering = ('-id',)

    def get_queryset(self):
        if self.request.user.is_staff and self.request.user.profile.staff_view:
            return Proposal.objects.all().prefetch_related(
                'sca', 'membership_set', 'membership_set__user', 'timeallocation_set'
            )
        else:
            return self.request.user.proposal_set.all().prefetch_related(
                'sca', 'membership_set', 'membership_set__user', 'timeallocation_set'
            )

    @action(detail=True, methods=['post'])
    def notification(self, request, pk=None):
        proposal = self.get_object()
        request_serializer = self.get_request_serializer(data=request.data)
        if request_serializer.is_valid():
            if request_serializer.validated_data['enabled']:
                ProposalNotification.objects.get_or_create(user=request.user, proposal=proposal)
            else:
                ProposalNotification.objects.filter(user=request.user, proposal=proposal).delete()

            response_serializer = self.get_response_serializer({'message': 'Preferences saved'})
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        else:
            return Response({'errors': request_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=(IsPrincipleInvestigator,))
    def invite(self, request, pk=None):
        proposal = self.get_object()
        request_serializer = self.get_request_serializer(
            data=request.data,
            context={'user': self.request.user, 'proposal': proposal}
        )
        if request_serializer.is_valid():
            proposal.add_users(request_serializer.validated_data['emails'], Membership.CI)

            response_serializer = self.get_response_serializer({'message': _('Co Investigator(s) invited')})
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=(IsPrincipleInvestigator,))
    def globallimit(self, request, pk=None):
        proposal = self.get_object()
        request_serializer = self.get_request_serializer(data=request.data)
        if request_serializer.is_valid():
            time_limit_hours = request_serializer.validated_data['time_limit_hours']
            proposal.membership_set.filter(role=Membership.CI).update(time_limit=time_limit_hours * 3600)

            response_serializer = self.get_response_serializer({'message': f'All CI time limits set to {time_limit_hours} hours'})
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        else:
            return Response({'errors': request_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def tags(self, request, pk=None):
        proposal_tags = get_queryset_field_values(self.get_queryset(), 'tags')
        return Response(list(proposal_tags))

    def get_request_serializer(self, *args, **kwargs):
        serializers = {'notification': import_string(settings.SERIALIZERS['proposals']['ProposalNotification']),
                       'invite': import_string(settings.SERIALIZERS['proposals']['ProposalInvite']),
                       'globallimit': import_string(settings.SERIALIZERS['proposals']['TimeLimit'])}
        return serializers.get(self.action, self.serializer_class)(*args, **kwargs)

    def get_response_serializer(self, *args, **kwargs):
        serializers = {'notification': import_string(settings.SERIALIZERS['proposals']['ProposalNotificationResponse']),
                       'invite': import_string(settings.SERIALIZERS['proposals']['ProposalInviteResponse']),
                       'globallimit': import_string(settings.SERIALIZERS['proposals']['TimeLimitResponse'])}

        return serializers.get(self.action, self.serializer_class)(*args, **kwargs)

    def get_example_response(self):
        example_data = {'tags': Response(data=EXAMPLE_RESPONSES['proposals']['tags'], status=status.HTTP_200_OK)}

        return example_data.get(self.action)

    def get_endpoint_name(self):
        endpoint_names = {'notification': 'createProposalNotification',
                          'invite': 'createProposalInvite',
                          'globallimit': 'setTimeLimit',
                          'tags': 'getProposalTags'}

        return endpoint_names.get(self.action)


class SemesterViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    schema = ObservationPortalSchema(tags=['Proposals'])
    serializer_class = import_string(settings.SERIALIZERS['proposals']['Semester'])
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = SemesterFilter
    ordering = ('-start',)
    queryset = Semester.objects.all()
    undocumented_actions = ['proposals', 'timeallocations']

    @action(detail=True, methods=['get'])
    def proposals(self, request, pk=None):
        semester = self.get_object()
        proposals = semester.proposals.filter(
            active=True, non_science=False
        ).prefetch_related(
            'sca', 'membership_set', 'membership_set__user', 'membership_set__user__profile',
            'semester_set', 'timeallocation_set'
        ).distinct().order_by('sca__name')
        results = []
        for proposal in proposals:
            results.append({
                'id': proposal.id,
                'title': proposal.title,
                'abstract': proposal.abstract,
                'allocation': proposal.allocation(semester=semester),
                'pis': [
                    {
                        'first_name': mem.user.first_name,
                        'last_name': mem.user.last_name,
                        'institution': mem.user.profile.institution
                    } for mem in proposal.membership_set.all() if mem.role == Membership.PI
                ],
                'sca_id': proposal.sca.id,
                'sca_name': proposal.sca.name,
                'semesters': proposal.semester_set.distinct().values_list('id', flat=True)
            })
        return Response(results)

    @action(detail=True, methods=['get'], permission_classes=(IsAdminUser,))
    def timeallocations(self, request, pk=None):
        timeallocations = self.get_object().timeallocation_set.prefetch_related(
            'proposal', 'proposal__membership_set', 'proposal__membership_set__user'
        ).distinct()
        results = []
        for timeallocation in timeallocations:
            memberships = timeallocation.proposal.membership_set
            timeallocation_dict = timeallocation.as_dict(exclude=['proposal', 'semester'])
            timeallocation_dict['proposal'] = {
                'notes': timeallocation.proposal.notes,
                'id': timeallocation.proposal.id,
                'tac_priority': timeallocation.proposal.tac_priority,
                'num_users': memberships.count(),
                'pis': [
                    {
                        'first_name': mem.user.first_name,
                        'last_name': mem.user.last_name
                    } for mem in memberships.all() if mem.role == Membership.PI
                ]
            }
            results.append(timeallocation_dict)
        return Response(results)


class MembershipViewSet(ListAsDictMixin, DetailAsDictMixin, mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    http_method_names = ('get', 'head', 'options', 'post', 'delete')
    schema = ObservationPortalSchema(tags=['Proposals'])
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = MembershipFilter
    serializer_class = import_string(settings.SERIALIZERS['proposals']['Membership'])

    def get_queryset(self):
        if self.request.user.is_staff and self.request.user.profile.staff_view:
            return Membership.objects.all()
        else:
            users_memberships = self.request.user.membership_set.all()
            pi_memberships_of_users_proposals = Membership.objects.filter(
                proposal__in=self.request.user.proposal_set.all(), role=Membership.PI
            )
            memberships_where_user_is_pi = Membership.objects.filter(
                proposal__in=self.request.user.proposal_set.filter(membership__role=Membership.PI)
            )
            all_memberships = users_memberships | memberships_where_user_is_pi | pi_memberships_of_users_proposals
            return all_memberships.distinct()

    def get_permissions(self):
        pi_only_actions = ('destroy', 'limit')
        if self.action in pi_only_actions:
            permission_classes = [IsPrincipleInvestigator]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    @action(detail=True, methods=['post'])
    def limit(self, request, pk=None):
        membership = self.get_object()
        request_serializer = self.get_request_serializer(data=request.data, context={'membership': membership})
        if request_serializer.is_valid():
            time_limit_hours = request_serializer.validated_data['time_limit_hours']
            membership.time_limit = time_limit_hours * 3600
            membership.save()
            message = (
                f'Time limit for {membership.user.first_name} {membership.user.last_name} set '
                f'to {time_limit_hours} hours'
            )

            response_serializer = self.get_response_serializer({'message': message})
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        else:
            return Response({'errors': request_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def perform_destroy(self, instance):
        if instance.role == Membership.CI:
            instance.delete()

    def get_request_serializer(self, *args, **kwargs):
        serializers = {'limit': import_string(settings.SERIALIZERS['proposals']['TimeLimit'])}

        return serializers.get(self.action, self.serializer_class)(*args, **kwargs)

    def get_response_serializer(self, *args, **kwargs):
        serializers = {'limit': import_string(settings.SERIALIZERS['proposals']['TimeLimitResponse'])}

        return serializers.get(self.action, self.serializer_class)(*args, **kwargs)


class ProposalInviteViewSet(mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    http_method_names = ('get', 'head', 'options', 'delete')
    schema = ObservationPortalSchema(tags=['Proposals'])
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = ProposalInviteFilter
    serializer_class = import_string(settings.SERIALIZERS['proposals']['ProposalInvite'])

    def get_queryset(self):
        if self.request.user.is_staff and self.request.user.profile.staff_view:
            return ProposalInvite.objects.all()
        else:
            proposals = self.request.user.proposal_set.filter(membership__role=Membership.PI)
            return ProposalInvite.objects.filter(proposal__in=proposals)

    def get_permissions(self):
        pi_only_actions = ('destroy', )
        if self.action in pi_only_actions:
            permission_classes = [IsPrincipleInvestigator]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def perform_destroy(self, instance):
        if instance.used is None:
            instance.delete()
